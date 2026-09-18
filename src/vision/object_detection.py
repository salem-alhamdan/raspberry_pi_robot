"""
Car object detection via an ONNX model (SSDLite320-MobileNetV3, COCO head
fine-tuned on "car" only), using onnxruntime.

    detector = get_car_detector()                    # None if model missing/broken
    result = detect_cars(detector, frame)             # never raises, even if detector is None
    result["car_detected"], result["confidence"]

--------------------------------------------------------------------------
STATUS: models/car_detection.onnx exists and loads. get_car_detector() still
returns None (logging one clear warning) if onnxruntime isn't installed or
the file is missing/broken, and detect_cars() treats detector=None as "no
detection", cheaply, on every call - this matters because ai_drive.py calls
detect_cars() ~10x/second and that path must never throw and never do real
work when there is no model.
--------------------------------------------------------------------------

--------------------------------------------------------------------------
INPUT/OUTPUT CONTRACT - VERIFIED against the real model file, not assumed
(via session.get_inputs()/get_outputs() and one real onnxruntime inference
call - see notebooks/06_ssd_training.ipynb section 17-18 for where this was
first verified at export time, and the session used to re-verify here):

    - Input: single tensor "input", rank 3 **[3, height, width]** - NO
      batch dimension. This is a torchvision detection-model export
      (`torch.onnx.export(model, ([dummy_chw_tensor],), ...)`), which
      traces on a *list* of unbatched CHW images, not a batched NCHW
      tensor - unlike most SSD-MobileNet tutorials/exports. height/width
      are dynamic axes, and training itself never forced a fixed square
      resize (see notebook 06 section 10's transform pipeline - only
      ToImage+ToDtype, no Resize), so this module does not force one
      either: frames are preprocessed at their native captured resolution.
      RGB order, pixel values scaled to [0, 1] (divide by 255) - the
      model's own internal GeneralizedRCNNTransform does ImageNet
      mean/std normalization, so no manual mean/std subtraction here.

    - Output: three separate tensors - "boxes" [N,4] float32 (absolute
      **pixel** xyxy coordinates in the *input tensor's* H/W, NOT
      normalized 0-1), "labels" ..., "scores" ... .

    - THE NAME/CONTENT SWAP (found by actually running inference and
      inspecting raw values, not just trusting the declared names):
      the tensor NAMED "labels" is float32 and holds the **confidence
      scores** (0-1); the tensor NAMED "scores" is int64 and holds the
      **class ids**. This is backwards from torchvision's own convention
      (labels=int64 class ids, scores=float32 confidences) and from
      notebooks/06_ssd_training.ipynb's `output_names=["boxes","labels",
      "scores"]` export call - the traced model's actual output tuple
      order didn't match that list positionally, so onnx.export bound the
      names to the wrong tensors. The underlying values are NOT corrupted
      (nothing gets truncated/cast-lossy), just mislabeled - see
      _resolve_output_roles() below, which maps roles by each output's
      actual dtype/shape instead of trusting its name, so this keeps
      working even if a future re-export fixes the naming.

    - class_id for "car": CAR_CLASS_ID in config.py = 3. VERIFIED against
      notebook 06's `car_label_idx` (read from the pretrained COCO weights'
      own `weights.meta["categories"]` list at training time, since the
      classification head was fine-tuned in place rather than replaced -
      the model still speaks full COCO class ids). A real inference on
      random noise input reproduced class id 3 as the top prediction,
      consistent with this.

If the model is ever re-exported differently (e.g. a real batch dimension
added, or box coordinates normalized), only _preprocess()/
_resolve_output_roles()/_parse_ssd_output() need to change - detect_cars()'s
public return shape stays the same for ai_drive.py.
--------------------------------------------------------------------------

Run this file directly for a standalone smoke test (works even with no
model file present - that is the point):
    python3 src/vision/object_detection.py
"""

import logging
import sys
from dataclasses import dataclass
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


@dataclass
class _CarDetector:
    """Wraps an onnxruntime session plus its output-role mapping, resolved
    once at load time by _resolve_output_roles() - see the module
    docstring's "THE NAME/CONTENT SWAP" section for why this can't just be
    looked up by name each call.
    """
    session: "ort.InferenceSession"
    input_name: str
    output_names: list  # session.get_outputs() order - matches session.run(None, ...)'s return order
    boxes_name: str
    class_id_name: str
    confidence_name: str


def _resolve_output_roles(session):
    """Figure out which of the model's 3 output tensors is boxes/class-ids/
    confidences by actual dtype/shape, not by trusting its name - see the
    module docstring's "THE NAME/CONTENT SWAP" section. Raises ValueError
    if the model's output shape doesn't look like this SSD's 3-tensor
    convention at all (caught by get_car_detector()'s broad except).
    """
    outputs = session.get_outputs()
    if len(outputs) != 3:
        raise ValueError(f"expected 3 output tensors (boxes/labels/scores), got {len(outputs)}")

    boxes = [o for o in outputs if o.shape and o.shape[-1] == 4]
    if len(boxes) != 1:
        raise ValueError(f"expected exactly one output shaped [*, 4] for boxes, found {len(boxes)}")
    boxes_name = boxes[0].name

    remaining = [o for o in outputs if o.name != boxes_name]
    int_ones = [o for o in remaining if "int" in o.type]
    float_ones = [o for o in remaining if o not in int_ones]
    if len(int_ones) != 1 or len(float_ones) != 1:
        raise ValueError(
            f"expected one int-typed (class ids) and one float-typed (confidences) "
            f"output among the non-box outputs, got types {[o.type for o in remaining]}"
        )
    class_id_name = int_ones[0].name
    confidence_name = float_ones[0].name

    if confidence_name != "labels" or class_id_name != "scores":
        # Not necessarily wrong - just means a re-export changed the naming
        # convention this was verified against. Logged, not fatal.
        logger.info(
            "object_detection: output name/role mapping differs from the "
            "swap this module was verified against (boxes=%r, class_ids=%r, "
            "confidences=%r) - if this is a freshly re-exported model, that's fine.",
            boxes_name, class_id_name, confidence_name,
        )

    return boxes_name, class_id_name, confidence_name


def _preprocess(frame):
    """BGR frame -> rank-3 CHW float32 [3,H,W] tensor scaled to [0, 1], at
    the frame's native resolution - see the module docstring's INPUT/OUTPUT
    CONTRACT section for why there's no batch dim and no forced resize.
    """
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # frame is BGR - see camera.py
    normalized = rgb.astype(np.float32) / 255.0
    return normalized.transpose(2, 0, 1)  # HWC -> CHW, no batch dim


def _parse_ssd_output(raw_outputs, detector):
    """Parse onnxruntime's raw output list (boxes/class-ids/confidences,
    per detector's resolved role mapping) into a plain list of detections:
    {"class_id": int, "confidence": float, "bbox": (x1, y1, x2, y2) in
    absolute pixel coordinates of the frame passed to _preprocess()}.
    """
    by_name = dict(zip(detector.output_names, raw_outputs))
    boxes = np.asarray(by_name[detector.boxes_name])
    class_ids = np.asarray(by_name[detector.class_id_name])
    confidences = np.asarray(by_name[detector.confidence_name])

    n = boxes.shape[0]
    detections = []
    for i in range(n):
        x1, y1, x2, y2 = boxes[i]
        detections.append(
            {
                "class_id": int(round(float(class_ids[i]))),
                "confidence": float(confidences[i]),
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
        boxes_name, class_id_name, confidence_name = _resolve_output_roles(session)
    except Exception:
        logger.warning(
            "object_detection: failed to load model at %s - car object "
            "detection will be skipped. See the exception below.",
            model_path,
            exc_info=True,
        )
        return None

    detector = _CarDetector(
        session=session,
        input_name=session.get_inputs()[0].name,
        output_names=[o.name for o in session.get_outputs()],
        boxes_name=boxes_name,
        class_id_name=class_id_name,
        confidence_name=confidence_name,
    )
    logger.info(
        "object_detection: loaded car detection model from %s (boxes=%r, class_ids=%r, confidences=%r)",
        model_path, boxes_name, class_id_name, confidence_name,
    )
    return detector


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
        raw_outputs = detector.session.run(None, {detector.input_name: input_tensor})
        detections = _parse_ssd_output(raw_outputs, detector)
    except Exception:
        # Should not normally happen now that pre/post-processing is
        # verified against the real model (see module docstring), but a
        # frame-specific oddity (e.g. an unexpected camera resolution)
        # should still degrade gracefully rather than crash the ~10Hz
        # caller. Logged so it's visible if it ever fires.
        logger.warning(
            "object_detection: inference failed this frame - treating as no detection.",
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
