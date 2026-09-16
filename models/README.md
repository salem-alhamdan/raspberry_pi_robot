# models/

## Expected file

`car_detection.onnx` - an SSD-family ONNX car-detection model, loaded by
`src/vision/object_detection.py` (path comes from `CAR_DETECTION_MODEL_PATH`
in `src/config.py`, resolved relative to the project root as
`models/car_detection.onnx`).

This file does not exist yet. Until it is added, `src/vision/object_detection.py`
degrades gracefully: `get_car_detector()` returns `None` (logging one clear
warning) and car detection is simply skipped - `src/robot/ai_drive.py` still
runs and drives on color detection alone. Nothing crashes.

## What to verify once you add the real model

`src/vision/object_detection.py`'s pre/post-processing was written as a
best-effort placeholder for the most common SSD-MobileNet ONNX export
convention, since no real model existed while it was written. It is
**not verified against your actual model.** Once you add
`models/car_detection.onnx`, check:

1. **Input shape/dtype** - the code assumes NCHW `float32`, resized to
   `300x300`, RGB order, pixel values scaled to `[0, 1]`. Verify with:
   ```python
   import onnxruntime as ort
   session = ort.InferenceSession("models/car_detection.onnx")
   print(session.get_inputs())
   ```
   If your model expects a different size, channel order, or normalization
   (e.g. `[-1, 1]` or mean-subtracted), update `_preprocess()` in
   `src/vision/object_detection.py`.

2. **Output format** - the code assumes a single output tensor shaped like
   `[1, 1, N, 7]`, each row `[image_id, class_id, confidence, x1, y1, x2, y2]`
   with box coordinates normalized to `[0, 1]` (the classic SSD
   "DetectionOutput" convention). Verify with `session.get_outputs()` and a
   real inference call on a test image. If your model instead returns
   separate boxes/scores/classes tensors, update `_parse_ssd_output()` -
   `detect_cars()`'s return shape (the part `ai_drive.py` depends on) does
   not need to change either way.

3. **`CAR_CLASS_ID`** (`src/config.py`, currently `3`) - the class index
   that means "car" in your model's label map. `3` is COCO's conventional
   "car" category id, used by many common SSD-MobileNet exports/tutorials,
   but this is a reasonable default, not confirmed against your specific
   model. Update it if your model's label map differs.

4. Run `python3 src/vision/object_detection.py` after adding the model - it
   will report whether the model loads successfully, and
   `python3 src/robot/ai_drive.py` (or `AIDriveController` in a notebook)
   to confirm real car detections actually trigger a stop.
