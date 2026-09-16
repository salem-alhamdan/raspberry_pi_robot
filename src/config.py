"""
Central configuration for the AI Car workshop robot.

All GPIO pin numbers use BCM numbering (the "GPIOxx" numbers silkscreened
on most pinout diagrams, NOT physical board pin numbers).

Import pin numbers and hardware constants from this module everywhere else
in the project instead of hard-coding them again. If a pin ever needs to
change, it should only need to change here.

Hardware status (updated as wiring progresses):
    - Camera (CSI, Pi Camera Module v2): CONNECTED and working.
    - LED, RGB LED, push button, L298N + motors, HC-SR04 ultrasonic:
      pins are assigned below but NOTHING is physically wired yet.
      Toggling these pins is safe (nothing attached), but do not expect
      any real-world effect until the hardware phase confirms wiring.

See PINOUT.md for the human-readable pin table and HARDWARE.md for the
full bill of materials and hardware status.

Below the GPIO pin map is a separate, clearly-marked section of non-GPIO
constants for the autonomous color/object-detection driving behavior
(src/robot/ai_drive.py) - kept in this same central file for the same
reason as the pins: one place to tune, instead of magic numbers scattered
across modules.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Plain LED (Notebook 1)
# ---------------------------------------------------------------------------
LED_PIN = 17

# ---------------------------------------------------------------------------
# RGB LED (common cathode - drive R/G/B pins HIGH via PWM to light them,
# no inversion needed since it is not common anode)
# ---------------------------------------------------------------------------
RGB_RED_PIN = 22
RGB_GREEN_PIN = 23
RGB_BLUE_PIN = 24
RGB_COMMON_CATHODE = True

# ---------------------------------------------------------------------------
# Push button (simple digital input, needs internal pull-up)
# ---------------------------------------------------------------------------
BUTTON_PIN = 27

# ---------------------------------------------------------------------------
# L298N motor driver
#   ENA / ENB are the PWM speed-control pins for the left/right motors and
#   are wired to the Pi's two hardware PWM channels (PWM0 / PWM1).
#   IN1-IN4 are the direction-control pins (2 per motor).
# ---------------------------------------------------------------------------
MOTOR_LEFT_ENABLE_PIN = 12   # ENA, hardware PWM0
MOTOR_LEFT_IN1_PIN = 5
MOTOR_LEFT_IN2_PIN = 6

MOTOR_RIGHT_ENABLE_PIN = 13  # ENB, hardware PWM1
MOTOR_RIGHT_IN3_PIN = 19
MOTOR_RIGHT_IN4_PIN = 26

# ---------------------------------------------------------------------------
# Ultrasonic distance sensor (HC-SR04)
#   TRIG is 3.3V-safe and can be driven directly from the Pi.
#   ECHO outputs 5V and MUST be stepped down with a voltage divider before
#   connecting to the Pi's 3.3V-only GPIO input - not wired yet.
# ---------------------------------------------------------------------------
ULTRASONIC_TRIG_PIN = 20
ULTRASONIC_ECHO_PIN = 21  # via voltage divider (required, not yet wired)
ULTRASONIC_MODEL = "HC-SR04"

# =============================================================================
# Autonomous AI drive (src/robot/ai_drive.py) - NOT GPIO PINS, see the module
# docstring above. Obstacle-distance threshold is intentionally NOT
# duplicated here: ai_drive.py imports DEFAULT_OBSTACLE_THRESHOLD_M directly
# from src/robot/obstacle_avoidance.py (the already-tested module that owns
# that value) rather than having two constants that could drift apart.
# =============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# How long a BLUE/YELLOW turn lasts before ai_drive.py stops and reassesses
# from a fresh frame (see the module docstring there for why it doesn't just
# assume "turn then go forward"). Independently calibratable per direction,
# since the two motors/wheels are very unlikely to be perfectly symmetric.
# 2.0s each is a starting point from the user - recalibrate against the real
# robot once driving.
TURN_LEFT_SECONDS = 2.0
TURN_RIGHT_SECONDS = 2.0

# Car object-detection (src/vision/object_detection.py). 0.80 is the user's
# requested confidence threshold - a detection below this is treated as "no
# car", not acted on.
CAR_DETECTION_CONFIDENCE_THRESHOLD = 0.80

# Resolved relative to the project root rather than hardcoded, so this still
# works regardless of the caller's current working directory. The file will
# very likely NOT exist yet - see object_detection.py for how that is
# handled (no crash, a clear warning, car detection just skipped).
CAR_DETECTION_MODEL_PATH = PROJECT_ROOT / "models" / "car_detection.onnx"

# COCO-trained SSD/MobileNet-family object detectors conventionally use
# class id 3 for "car" (COCO's own category id for car is 3 in the common
# 0-indexed "background-included" label maps used by most SSD ONNX
# exports/tutorials - e.g. TensorFlow's mscoco_label_map.pbtxt and most
# SSD-MobileNet ONNX model zoo exports). This is a REASONABLE DEFAULT, NOT
# verified against the real car_detection.onnx model, which does not exist
# yet - confirm the actual class mapping once that file is provided, and
# update this constant if it differs. See object_detection.py for the full
# "what's verified vs. best-effort placeholder" breakdown.
CAR_CLASS_ID = 3

# Target rate (Hz) for ai_drive.py's full detect -> decide -> act loop - the
# "~10 FPS" the user asked for. This is the loop rate, not just the camera's
# capture rate: one loop iteration also runs color detection, optionally car
# detection, and a motor/LED decision, all of which add to the per-iteration
# cost beyond just grabbing a frame. ai_drive.py measures actual achieved
# loop time and does not pretend to hit this exactly - see its docstring.
AI_DRIVE_LOOP_HZ = 10

# =============================================================================
# Web control server (web/app.py) - NOT GPIO PINS. Kept in this same central
# file for the same one-place-to-tune reason as the AI drive section above.
# =============================================================================

# How long (seconds) the manual-mode command watchdog in web/app.py waits
# after the last movement command before assuming the browser has
# disconnected/stopped sending commands, and calling stop() automatically.
# Chosen in the 1-2s range the spec asked for: short enough that a dropped
# connection can't leave the robot rolling for long, long enough that normal
# button-repeat/keyboard-repeat traffic (app.py's frontend resends the held
# command every 400ms - well under this) never trips it during normal use.
# Only applies in MANUAL mode - AI mode is autonomous and makes its own
# stop/go decisions every loop iteration independent of the browser (see
# ai_drive.py's decision priority), so it does not need this watchdog; see
# web/app.py's module docstring for the full reasoning.
COMMAND_WATCHDOG_TIMEOUT_S = 1.5

# Target frames/sec for the MJPEG preview stream at web/app.py's
# /video_feed. Kept modest on purpose: this Pi's CPU is also running motor
# control (and, in AI mode, the full ~AI_DRIVE_LOOP_HZ detect-decide-act
# loop above), so the browser preview does not need to be high-FPS to be
# useful for a human driving the robot.
WEB_STREAM_TARGET_FPS = 8

# BLUE HSV threshold range, in the same (lower, upper) format as
# src/vision/color_detection.py's HSV_RANGES dict (H 0-179, S/V 0-255).
# ai_drive.py needs RED/GREEN/YELLOW (already in color_detection.py's
# HSV_RANGES) plus BLUE, which color_detection.py does NOT define - BLUE is
# added here, in config.py, instead of editing color_detection.py, because
# this task was explicitly scoped to NOT modify that already-tested module.
# If BLUE detection is ever needed elsewhere too, the cleaner long-term fix
# is migrating this into color_detection.py's HSV_RANGES dict.
#
# Like the RED/GREEN/YELLOW ranges, this is a standard/reference OpenCV
# blue-detection value (pure blue sits around hue ~120 on OpenCV's 0-179
# scale), NOT validated against a real blue object on this Pi's desk -
# QA/the user should confirm against a real object, same as the other
# colors (see color_detection.py's module docstring for the full caveat).
BLUE_HSV_RANGE = ((94, 80, 2), (126, 255, 255))
