"""
Reusable HSV-based color detection for RED, GREEN, YELLOW.

    hsv = bgr_to_hsv(frame)              # frame must be BGR - see camera.py
    mask = detect_color(frame, "RED")    # binary mask, same (h, w)
    blob = largest_blob(mask)            # None, or {"centroid", "bbox", "area"}

This module is vision-only: it looks at a frame and reports where a color
is. It does NOT touch any actuator (no rgb_led.py import, no GPIO). Wiring
"camera sees RED -> light the RGB LED red" is notebook-level teaching logic
that composes this module with src/hardware/rgb_led.py - keeping vision and
actuation separate, same principle used throughout src/hardware/ and
src/robot/ (e.g. obstacle_avoidance.py composes motor.py + ultrasonic.py
rather than either module reaching into the other).

--------------------------------------------------------------------------
Why HSV instead of BGR/RGB for color thresholding
--------------------------------------------------------------------------
In BGR/RGB, a color's three channels all shift together when lighting
brightness changes, so a simple per-channel threshold breaks under normal
lighting variation. HSV separates Hue (the actual color, 0-179 in OpenCV),
Saturation (how vivid vs. washed-out) and Value (brightness) - thresholding
mostly on Hue makes detection far more robust to lighting changes, which
matters a lot on a robot that will not always be under the same light.

--------------------------------------------------------------------------
THE RED HUE-WRAPAROUND GOTCHA - read this before changing RED's range
--------------------------------------------------------------------------
OpenCV's Hue axis is a circle, but the values are stored linearly from 0
to 179. Red sits at the SEAM of that circle - "pure" red is hue 0, but
just past the other end of the scale, hue 179 is ALSO red (it wraps back
around to 0). A single (lower, upper) range like (170, 10) does NOT work
the way you might expect - `cv2.inRange` treats lower/upper as a normal
numeric interval, and there is no value that is simultaneously "above 170"
AND "below 10". The fix is to define TWO separate ranges - one for the low
end (0-10ish) and one for the high end (170-179ish) - build a mask for
each, and OR them together (`cv2.bitwise_or`). GREEN and YELLOW sit in the
middle of the hue axis and do not have this problem, which is exactly why
RED is treated differently below - this is not an inconsistency, it is the
gotcha.

--------------------------------------------------------------------------
Where these HSV ranges come from, and a flag for QA
--------------------------------------------------------------------------
The ranges below are standard/reference OpenCV color-detection values
(the same ballpark commonly used in OpenCV color-tracking tutorials), NOT
values measured against a real physical red/green/yellow object on this
Pi's desk - no such object was available while writing this module. They
are a reasonable, documented starting point, but real cameras/lighting/
printed-vs-plastic colors vary. QA/the user should point the camera at
real red, green, and yellow objects (construction paper, LEGO bricks,
whatever is on hand) and confirm each one is actually detected - if not,
narrow/widen the S and V bounds first (lighting/washout issues) before
touching the H bounds (the actual hue).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

# HSV ranges as (lower, upper) numpy-friendly tuples: H in [0, 179],
# S and V in [0, 255] (OpenCV's convention, not the 0-360/0-100/0-100 you
# may have seen elsewhere).
#
# RED needs two ranges OR'd together - see the module docstring's gotcha
# section above. GREEN and YELLOW are each a single contiguous range.
HSV_RANGES = {
    "RED": [
        ((0, 120, 70), (10, 255, 255)),      # low end of the hue wraparound
        ((170, 120, 70), (180, 255, 255)),   # high end of the hue wraparound
    ],
    "GREEN": [
        ((36, 60, 60), (89, 255, 255)),
    ],
    "YELLOW": [
        ((20, 100, 100), (34, 255, 255)),
    ],
}

# Minimum contour area (in pixels) for a detected blob to be considered
# "real" rather than sensor noise/a stray few pixels. Tune against real
# objects/distances - see the module docstring's QA note.
MIN_BLOB_AREA_PX = 200


def bgr_to_hsv(frame):
    """Convert a BGR frame (e.g. from camera.capture_frame()) to HSV."""
    return cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)


def detect_color(frame, color_name):
    """Return a binary mask (uint8, same h/w as frame) of pixels matching color_name.

    color_name must be one of HSV_RANGES' keys ("RED", "GREEN", "YELLOW").
    Mask pixels are 255 where the color was detected, 0 elsewhere.
    """
    if color_name not in HSV_RANGES:
        raise ValueError(
            f"Unknown color {color_name!r}. Expected one of {list(HSV_RANGES)}."
        )

    hsv = bgr_to_hsv(frame)

    mask = None
    for lower, upper in HSV_RANGES[color_name]:
        range_mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
        mask = range_mask if mask is None else cv2.bitwise_or(mask, range_mask)

    return mask


def largest_blob(mask, min_area=MIN_BLOB_AREA_PX):
    """Find the largest contour in a binary mask and describe it simply.

    Returns None if no contour reaches min_area (nothing detected).
    Otherwise returns a dict:
        {
            "centroid": (cx, cy),        # ints, pixel coordinates
            "bbox": (x, y, w, h),        # ints, top-left corner + size
            "area": float,               # contour area in pixels
        }
    """
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)
    if area < min_area:
        return None

    x, y, w, h = cv2.boundingRect(largest)

    moments = cv2.moments(largest)
    if moments["m00"] == 0:  # degenerate contour, fall back to bbox center
        cx, cy = x + w // 2, y + h // 2
    else:
        cx = int(moments["m10"] / moments["m00"])
        cy = int(moments["m01"] / moments["m00"])

    return {"centroid": (cx, cy), "bbox": (x, y, w, h), "area": area}


if __name__ == "__main__":
    # Standalone smoke test: capture one real frame from the Pi camera and
    # report what (if anything) is detected for each color. This exercises
    # the full pipeline but is NOT a substitute for pointing the camera at
    # a real colored object - see the module docstring's QA note.
    from vision.camera import get_camera, capture_frame, cleanup

    print("Color detection smoke test: capturing one frame...")
    camera = get_camera()
    try:
        frame = capture_frame(camera)
        print(f"Captured frame: shape={frame.shape}, dtype={frame.dtype}")

        for color_name in HSV_RANGES:
            mask = detect_color(frame, color_name)
            blob = largest_blob(mask)
            if blob is None:
                print(f"{color_name}: no blob >= {MIN_BLOB_AREA_PX}px detected")
            else:
                print(f"{color_name}: detected - {blob}")
    finally:
        cleanup(camera)
        print("Camera released.")
