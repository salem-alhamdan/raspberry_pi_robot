"""
Car object detection via an ONNX model (SSD-family), using onnxruntime.

    detector = get_car_detector()                    # None if model missing/broken
    result = detect_cars(detector, frame)             # never raises, even if detector is None
    result["car_detected"], result["confidence"]

--------------------------------------------------------------------------
STATUS: the real model file (models/car_detection.onnx) does not exist yet.
This module is written to be genuinely safe in that state: get_car_detector()
returns None (logging one clear warning) instead of crashing, and
detect_cars() treats detector=None as "no detection", cheaply, on every
call - this matters because ai_drive.py calls detect_cars() ~10x/second and
that path must never throw and never do real work when there is no model.

onnxruntime itself IS installed and verified working on this Pi (aarch64,
Debian 11 bullseye, Python 3.9.2): `pip3 install --user onnxruntime`
installed a prebuilt wheel (1.19.2 at verification time, no compilation
needed) and it imports cleanly with CPUExecutionProvider available. See
scripts/install_pi_dependencies.sh and requirements.txt for where that is
installed. So the gap right now is purely "no model file", not "onnxruntime
doesn't work here".
--------------------------------------------------------------------------

--------------------------------------------------------------------------
WHAT IS VERIFIED VS. BEST-EFFORT PLACEHOLDER - READ BEFORE TRUSTING THIS
--------------------------------------------------------------------------
Everything in the "ADJUST THIS ONCE THE REAL MODEL EXISTS" section below
(_preprocess() and _parse_ssd_output()) is a REASONABLE DEFAULT based on the
most common SSD-MobileNet-family ONNX export/serving convention (the same
convention OpenCV's own DNN SSD tutorials and the classic Caffe/TF
"DetectionOutput" layer use), NOT something verified against the real
car_detection.onnx model, because that file does not exist yet. Concretely,
assumed here:
    - Input: single tensor, NCHW, float32, resized to 300x300, RGB order,
      pixel values scaled to [0, 1] (divide by 255).
    - Output: single tensor shaped like [1, 1, N, 7], where each of the N
      rows is [image_id, class_id, confidence, x1, y1, x2, y2] with box
      coordinates normalized to [0, 1] of the input image.
    - class_id for "car": CAR_CLASS_ID in config.py, defaulted to 3 (COCO's
      conventional "car" category id in the label maps most SSD-MobileNet
      ONNX exports/tutorials use) - again a reasonable default, not
      confirmed against this specific model.

Once the real model is provided, verify (do not assume) the above by
inspecting `session.get_inputs()` / `session.get_outputs()` (name, shape,
dtype) and running one real inference on a known test image, then update
_preprocess()/_parse_ssd_output()/CAR_CLASS_ID to match. If the real model
turns out to be a different SSD export flavor (e.g. separate boxes/scores/
classes output tensors instead of one combined [1,1,N,7] tensor), only
_parse_ssd_output() needs to change - detect_cars()'s public return shape
stays the same for ai_drive.py.
--------------------------------------------------------------------------

Run this file directly for a standalone smoke test (works even with no
model file present - that is the point):
    python3 src/vision/object_detection.py
"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from config import (  # noqa: E402
    CAR_DETECTION_MODEL_PATH,
    CAR_DETECTION_CONFIDENCE_THRESHOLD,
    CAR_CLASS_ID,
)

logger = logging.getLogger(__name__)

try:
    import onnxruntime as ort
    _ONNXRUNTIME_AVAILABLE = True
except ImportError:
    _ONNXRUNTIME_AVAILABLE = False

import cv2  # noqa: E402

# =============================================================================
# ADJUST THIS ONCE THE REAL MODEL EXISTS - see the module docstring's
# "what is verified vs. best-effort placeholder" section above.
# =============================================================================
_MODEL_INPUT_SIZE = (300, 300)  # (width, height)


def _preprocess(frame):
    """BGR frame -> NCHW float32 [1,3,300,300] tensor scaled to [0, 1].

    PLACEHOLDER convention for a typical SSD-MobileNet ONNX export - see the
    module docstring. Verify against the real model's session.get_inputs()
    once it exists (shape, dtype, and whether it expects [0,1], [-1,1], or
    mean-subtracted input) and update this function if it differs.
    """
    resized = cv2.resize(frame, _MODEL_INPUT_SIZE)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)  # frame is BGR - see camera.py
    normalized = rgb.astype(np.float32) / 255.0
    chw = normalized.transpose(2, 0, 1)  # HWC -> CHW
    return np.expand_dims(chw, axis=0)  # add batch dim -> NCHW


def _parse_ssd_output(raw_outputs):
    """Parse onnxruntime's raw output list into a plain list of detections.

    PLACEHOLDER convention (classic SSD "DetectionOutput" shape) - see the
    module docstring. Each returned dict: {"class_id": int, "confidence":
    float, "bbox": (x1, y1, x2, y2) normalized 0-1}. Update this function
    once the real model's actual output tensor(s) are known.
    """
    if not raw_outputs:
        return []

    output = np.asarray(raw_outputs[0])
    if output.size == 0:
        return []

    # Expected [1, 1, N, 7] (or already [N, 7]) - reshape defensively rather
    # than assuming the exact rank, since export tooling sometimes differs
    # on how many leading singleton dims it keeps.
    try:
        rows = output.reshape(-1, output.shape[-1])
    except ValueError:
        logger.warning(
            "object_detection: unexpected model output shape %s - cannot "
            "parse detections with the assumed SSD [*, 7] convention. "
            "Update _parse_ssd_output() for the real model's actual format.",
            output.shape,
        )
        return []

    detections = []
    for row in rows:
        if row.shape[0] < 7:
            continue
        _image_id, class_id, confidence, x1, y1, x2, y2 = row[:7]
        detections.append(
            {
                "class_id": int(class_id),
                "confidence": float(confidence),
                "bbox": (float(x1), float(y1), float(x2), float(y2)),
            }
        )
    return detections


# =============================================================================
# Public API - this shape is what ai_drive.py depends on, and should NOT
# need to change even if the placeholder parsing above does.
# =============================================================================

def get_car_detector(model_path=CAR_DETECTION_MODEL_PATH):
    """Load the car-detection ONNX model. Returns None (never raises) if
    onnxruntime isn't installed, or the model file doesn't exist yet, or
    fails to load - logging one clear warning explaining why in each case.
    """
    if not _ONNXRUNTIME_AVAILABLE:
        logger.warning(
            "object_detection: onnxruntime is not installed - car object "
            "detection will be skipped. Install it with "
            "'pip3 install --user onnxruntime' (see scripts/"
            "install_pi_dependencies.sh) to enable it."
        )
        return None

    model_path = Path(model_path)
    if not model_path.exists():
        logger.warning(
            "object_detection: no model file at %s - car object detection "
            "will be skipped until it is added. This is expected until the "
            "trained model is provided; nothing is broken.",
            model_path,
        )
        return None

    try:
        session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    except Exception:
        logger.warning(
            "object_detection: failed to load model at %s - car object "
            "detection will be skipped. See the exception below.",
            model_path,
            exc_info=True,
        )
        return None

    logger.info("object_detection: loaded car detection model from %s", model_path)
    return session


def detect_cars(detector, frame, confidence_threshold=CAR_DETECTION_CONFIDENCE_THRESHOLD):
    """Run car detection on one frame. Never raises.

    If detector is None (model missing/onnxruntime unavailable), returns an
    empty/no-detection result immediately without doing any real work - this
    path is called ~10x/second by ai_drive.py's main loop and must stay
    cheap.

    Returns a dict:
        {
            "car_detected": bool,          # True if any car >= confidence_threshold
            "confidence": float or None,   # highest matching car confidence, if any
            "detections": [...],           # all raw parsed detections (any class)
        }
    """
    if detector is None:
        return {"car_detected": False, "confidence": None, "detections": []}

    try:
        input_tensor = _preprocess(frame)
        input_name = detector.get_inputs()[0].name
        raw_outputs = detector.run(None, {input_name: input_tensor})
        detections = _parse_ssd_output(raw_outputs)
    except Exception:
        # Inference on a real model with placeholder pre/post-processing can
        # very plausibly fail (wrong input shape, wrong output format) until
        # this is verified against the real model - see the module
        # docstring. Never let that crash the ~10Hz caller; just report "no
        # detection this frame" and log once per failure so it's visible.
        logger.warning(
            "object_detection: inference failed this frame - treating as "
            "no detection. If this happens every frame, _preprocess()/"
            "_parse_ssd_output() likely need updating for the real model's "
            "actual input/output format (see module docstring).",
            exc_info=True,
        )
        return {"car_detected": False, "confidence": None, "detections": []}

    car_detections = [
        d for d in detections
        if d["class_id"] == CAR_CLASS_ID and d["confidence"] > confidence_threshold
    ]
    if not car_detections:
        return {"car_detected": False, "confidence": None, "detections": detections}

    best = max(car_detections, key=lambda d: d["confidence"])
    return {"car_detected": True, "confidence": best["confidence"], "detections": detections}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")

    print(f"Object detection smoke test: model expected at {CAR_DETECTION_MODEL_PATH}")
    print(f"onnxruntime available: {_ONNXRUNTIME_AVAILABLE}")

    detector = get_car_detector()
    print(f"get_car_detector() -> {detector!r} (None is expected until the model file exists)")

    # A dummy frame is enough to prove detect_cars() never crashes with no
    # model loaded - this is the important, guaranteed-to-run-today case.
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = detect_cars(detector, dummy_frame)
    print(f"detect_cars(detector, dummy_frame) -> {result}")
    print("Smoke test complete - no crash, as expected with no model file present.")
