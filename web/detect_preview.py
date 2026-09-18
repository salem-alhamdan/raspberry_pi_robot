"""
Standalone car-detection preview: opens ONLY the camera (no motors/LED/
ultrasonic), runs the ONNX car detector on each frame, draws the detection
boxes + confidence on the frame, and serves it as an MJPEG stream to view
live in a browser.

    python3 web/detect_preview.py
    # then browse to http://<pi-ip>:5001/

Ctrl+C stops it and releases the camera.

--------------------------------------------------------------------------
WHY A BROWSER STREAM, NOT cv2.imshow()
--------------------------------------------------------------------------
This Pi has opencv-python-headless installed (see scripts/
install_pi_dependencies.sh and notebooks/05_opencv_introduction.ipynb
section 1) - the GUI backend cv2.imshow() needs is deliberately not
compiled in, so imshow() would fail outright here, and wouldn't show
anything useful over a plain SSH session anyway (no local window to open
into). Every viewer in this project instead uses either inline Jupyter
display or a browser MJPEG stream - same pattern web/app.py's manual-mode
/video_feed already uses. This script is that same pattern, scoped down to
just "camera + car detector", so it can run standalone without needing the
full HardwareManager/motor/mode machinery in web/app.py.
--------------------------------------------------------------------------

--------------------------------------------------------------------------
DO NOT run this at the same time as web/app.py
--------------------------------------------------------------------------
Both would try to open their own Picamera2 handle - picamera2 WILL raise a
real "device busy" error if a second instance tries to grab the camera
while one is already open (see web/app.py's module docstring and
SAFETY.md). Stop one before starting the other.
--------------------------------------------------------------------------
"""

import atexit
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cv2  # noqa: E402
from flask import Flask, Response  # noqa: E402

from config import CAR_CLASS_ID, CAR_DETECTION_CONFIDENCE_THRESHOLD  # noqa: E402
from vision.camera import get_camera, capture_frame, cleanup as cleanup_camera  # noqa: E402
from vision.object_detection import get_car_detector, detect_cars  # noqa: E402

# Lower than CAR_DETECTION_CONFIDENCE_THRESHOLD on purpose - this is a
# visual debugging aid, not a driving decision, so it's useful to also see
# near-miss detections (drawn in orange, vs. green for "above threshold").
_VISUALIZE_MIN_CONFIDENCE = 0.30

_BOUNDARY = b"frame"
_GREEN = (0, 255, 0)
_ORANGE = (0, 140, 255)
_WHITE = (255, 255, 255)

app = Flask(__name__)
camera = None
detector = None
# picamera2 capture is not guaranteed thread-safe against concurrent
# callers - Flask's dev server is threaded (multiple browser tabs/reloads
# could overlap), so captures are serialized through this lock, same
# reasoning as web/app.py's camera_lock.
camera_lock = threading.Lock()


def _draw_detections(frame, result):
    car_detected = result["car_detected"]
    top_confidence = result["confidence"]

    for d in result["detections"]:
        if d["class_id"] != CAR_CLASS_ID or d["confidence"] < _VISUALIZE_MIN_CONFIDENCE:
            continue
        x1, y1, x2, y2 = (int(round(v)) for v in d["bbox"])
        above_threshold = d["confidence"] > CAR_DETECTION_CONFIDENCE_THRESHOLD
        color = _GREEN if above_threshold else _ORANGE
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            frame, f"car {d['confidence']:.2f}", (x1, max(y1 - 8, 12)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2, cv2.LINE_AA,
        )

    status = (
        f"CAR DETECTED ({top_confidence:.2f})" if car_detected
        else "no car above threshold"
    )
    status_color = _GREEN if car_detected else _WHITE
    cv2.putText(
        frame, status, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2, cv2.LINE_AA,
    )
    return frame


def _generate_mjpeg():
    while True:
        with camera_lock:
            frame = capture_frame(camera)
            result = detect_cars(detector, frame)
        annotated = _draw_detections(frame, result)
        ok, jpeg = cv2.imencode(".jpg", annotated)
        if not ok:
            continue
        yield (
            b"--" + _BOUNDARY + b"\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n"
        )


@app.route("/")
def index():
    return (
        "<html><body style='margin:0;background:#000'>"
        "<img src='/stream' style='width:100%;height:auto;display:block;'/>"
        "</body></html>"
    )


@app.route("/stream")
def stream():
    return Response(
        _generate_mjpeg(),
        mimetype=f"multipart/x-mixed-replace; boundary={_BOUNDARY.decode()}",
    )


def _shutdown():
    if camera is not None:
        cleanup_camera(camera)
        print("Camera released.")


def main():
    global camera, detector

    print("Car-detection preview: opening camera only (no motors/LED/ultrasonic).")
    camera = get_camera()
    detector = get_car_detector()
    if detector is None:
        print("WARNING: no car detector available (see warning above) - "
              "stream will show frames with no detection boxes.")

    atexit.register(_shutdown)
    signal.signal(signal.SIGTERM, lambda *_: (_shutdown(), sys.exit(0)))

    print("Browse to http://<pi-ip>:5001/ to view. Press Ctrl+C to stop.")
    try:
        app.run(host="0.0.0.0", port=5001, threaded=True, debug=False, use_reloader=False)
    finally:
        _shutdown()


if __name__ == "__main__":
    main()
