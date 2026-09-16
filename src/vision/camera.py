"""
Pi Camera Module v2 (imx219, CSI) capture, wrapped around picamera2.

    camera = get_camera()          # default 640x480 - see "Why 640x480" below
    frame = capture_frame(camera)  # OpenCV-native BGR numpy array, see below
    cleanup(camera)

Run this file directly on the Pi for a standalone smoke test that captures
one real frame and saves it to /tmp/camera_smoke_test.jpg:
    python3 src/vision/camera.py

--------------------------------------------------------------------------
BGR vs RGB - VERIFIED ON REAL HARDWARE, DO NOT ASSUME THIS
--------------------------------------------------------------------------
OpenCV's native in-memory channel order is BGR (blue first), not RGB. Every
other OpenCV function in this project (cv2.cvtColor, cv2.imwrite, the HSV
thresholds in color_detection.py, ...) assumes frames are BGR. Getting this
wrong silently swaps red and blue - detection code would "work" but detect
the wrong color, which is a classic, hard-to-notice camera bug. So this was
verified directly on this Pi rather than assumed:

  1. picamera2's default capture config for this sensor is format
     "XBGR8888" (confirmed via `picam2.create_preview_configuration()` and
     the libcamera log line "configuring streams: (0) 640x480-XBGR8888").
     `capture_array()` for that format returns a (h, w, 4) uint8 array -
     4 channels, not 3.

  2. Reading picamera2's own source (picamera2/request.py, Helpers.make_array)
     shows capture_array() does a raw reshape of the underlying buffer with
     NO channel reordering - so the array's channel order is whatever the
     "XBGR8888" pixel format actually lays out in memory, not necessarily
     what the format's name suggests at a glance.

  3. Empirically, on this Pi, channel index 3 is uniformly 255 in every
     capture (confirmed across multiple frames) - that is the unused "X"
     padding byte. libcamera/DRM format names are conventionally read as
     hex digits of the packed value from MOST-significant to LEAST
     (X, B, G, R for "XBGR8888"), and since storage is little-endian, the
     LEAST-significant component ends up at the LOWEST memory address /
     array index. That means the real per-index layout is the REVERSE of
     the name's left-to-right reading: index 0 = R, index 1 = G,
     index 2 = B, index 3 = X. In other words: despite being called
     "XBGR8888", `capture_array()[:, :, :3]` is actually **RGB order, not
     BGR** - a well-known picamera2 gotcha.

  4. This was cross-checked empirically by requesting several explicit
     picamera2 format strings ("RGB888", "BGR888", "XBGR8888", "XRGB8888")
     and comparing each one's per-channel means against a same-scene JPEG
     captured with picam2.capture_file() (whose decoded channel order via
     cv2.imread() is unambiguously BGR). All four formats' results are
     internally consistent with the reversed-name convention in point 3
     above (e.g. requesting format="RGB888" empirically produces an array
     that is actually in BGR memory order, and format="BGR888" empirically
     produces RGB order - the naming is consistently inverted from what it
     says). This confirms point 3 was not a one-off fluke.

  Conclusion / what this module actually does: `capture_frame()` takes the
  default XBGR8888 capture, drops the unused 4th (X) channel, and explicitly
  converts RGB -> BGR with `cv2.cvtColor(..., cv2.COLOR_RGB2BGR)` before
  returning. This is written as an explicit, visible conversion (rather
  than e.g. silently requesting format="RGB888" and relying on the inverted
  naming to "accidentally" already be BGR) specifically so it is obvious to
  a reader/notebook author *that* a conversion happens and *why* - this
  exact BGR-vs-RGB gotcha is a named teaching topic in the vision notebook.

  CAVEAT FOR QA: the room this was verified in was very dark (measured
  Lux ~= 1, even at max gain/exposure), so this was verified by exact pixel
  value/channel-mean comparisons, not by eye. Re-run the __main__ smoke
  test below with a well-lit, distinctly colored real object in frame and
  visually confirm the saved JPEG's colors look correct as a final check.

--------------------------------------------------------------------------
Why 640x480: a sensible default for OpenCV work (color detection, basic
CV) on a 4GB Pi 4 - big enough to see detail, small enough that per-frame
cv2 processing stays fast and memory use stays low. Exposed as a parameter
so a caller can ask for a different resolution if a later phase needs it.
--------------------------------------------------------------------------
"""

import sys
import time
from pathlib import Path

# Make `from config import ...` work whether this file is run directly
# (`python3 src/vision/camera.py`) or imported as `vision.camera` after a
# notebook has added the `src/` folder to sys.path. Same trick used by every
# module in src/hardware/ - see e.g. src/hardware/led.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
from picamera2 import Picamera2  # noqa: E402

DEFAULT_RESOLUTION = (640, 480)

# How long to let auto-exposure/auto-white-balance settle after start()
# before the first real capture. Without this, the first frame or two can
# be too dark/wrongly color-balanced while the ISP is still converging -
# observed directly on this Pi.
_WARMUP_SECONDS = 1.0


def get_camera(resolution=DEFAULT_RESOLUTION):
    """Configure and start a Picamera2 instance at the given resolution.

    Uses picamera2's default capture format (XBGR8888) - see the module
    docstring for exactly what capture_frame() does with that and why.
    """
    camera = Picamera2()
    config = camera.create_preview_configuration(main={"size": resolution})
    camera.configure(config)
    camera.start()
    time.sleep(_WARMUP_SECONDS)  # let AE/AWB converge - see _WARMUP_SECONDS
    return camera


def capture_frame(camera):
    """Capture one frame and return it as an OpenCV-native BGR numpy array.

    See the module docstring's "BGR vs RGB" section for how this was
    verified on real hardware and exactly why this conversion is needed.
    """
    frame_rgbx = camera.capture_array()  # (h, w, 4): verified R, G, B, X order
    frame_rgb = frame_rgbx[:, :, :3]  # drop the unused X/padding channel
    frame_bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    return frame_bgr


def cleanup(camera):
    """Stop capture and release the camera. Call this when you are done."""
    camera.stop()
    camera.close()


if __name__ == "__main__":
    OUTPUT_PATH = "/tmp/camera_smoke_test.jpg"

    print(f"Camera smoke test: capturing one frame at {DEFAULT_RESOLUTION}")
    camera = get_camera()

    try:
        frame = capture_frame(camera)
        print(f"Captured frame: shape={frame.shape}, dtype={frame.dtype}")

        # cv2.imwrite expects BGR input, which is exactly what capture_frame()
        # returns - if colors look wrong in the saved file, that is a real
        # signal something above is broken, not a display/viewer artifact.
        cv2.imwrite(OUTPUT_PATH, frame)
        print(f"Saved to {OUTPUT_PATH} - open it and visually sanity-check the colors.")
    finally:
        cleanup(camera)
        print("Camera released.")
