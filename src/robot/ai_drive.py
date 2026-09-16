"""
Autonomous color/object-detection driving - the main integration script,
composing every already-tested piece built so far:
    src/hardware/motor.py, rgb_led.py, ultrasonic.py
    src/vision/camera.py, color_detection.py, object_detection.py
    src/robot/obstacle_avoidance.py (for its obstacle-distance constant)

Nothing here reimplements any of that - this module is PURELY the
composition/decision layer, same principle as obstacle_avoidance.py
composing motor.py + ultrasonic.py.

    controller = AIDriveController()
    controller.run()          # blocks, ~10Hz loop, until stopped
    ...                       # (from another thread) controller.request_stop()
    controller.cleanup()

================================================================================
SAFETY - THIS IS THE MOST SAFETY-CRITICAL MODULE IN THE PROJECT SO FAR: it
directly and continuously drives real motors from live camera input, in a
loop with no human in it by default. Everything in motor.py's and
obstacle_avoidance.py's SAFETY notes applies here, doubly. Nothing is
physically wired yet (see HARDWARE.md), so there is no real movement risk
right now - but this code runs exactly as-is once it is wired, so:
    - Before ever running AIDriveController.run() on real hardware, the
      robot must be lifted off the ground / wheels free-spinning.
    - The motors are ALWAYS stopped in a `finally` block in run() (and in
      cleanup()), so a KeyboardInterrupt, a SIGTERM, or any unexpected
      exception mid-loop still leaves the robot stopped - same non-
      negotiable discipline as obstacle_avoidance.py's auto_drive().
    - The ultrasonic obstacle check is evaluated FIRST, every single loop
      iteration, before anything the camera says - see "Decision priority"
      below.
================================================================================

--------------------------------------------------------------------------
Decision priority (highest to lowest) - evaluated fresh every loop
iteration at ~AI_DRIVE_LOOP_HZ:
--------------------------------------------------------------------------
    1. Ultrasonic obstacle too close (< obstacle_threshold_m)      -> STOP
    2. Car detected, confidence > CAR_DETECTION_CONFIDENCE_THRESHOLD -> STOP
    3. RED detected                                                -> STOP
       STICKY: once triggered, stays stopped on ALL later iterations -
       including through a momentarily ambiguous/colorless frame or any
       other non-GREEN color - and only resumes once the detected color is
       EXPLICITLY GREEN. Deliberately stricter than "any non-red frame
       clears it": a single misdetection/occlusion/camera glitch must not
       be able to silently clear a safety stop. Implemented as an explicit
       `_stopped_for_red` flag (not just re-evaluating each frame in
       isolation), because the user specifically asked for "stay stopped
       until X", i.e. persistent behavior across iterations.
    4. BLUE detected   -> turn left for TURN_LEFT_SECONDS, then STOP
    5. YELLOW detected -> turn right for TURN_RIGHT_SECONDS, then STOP
    6. GREEN detected, nothing above blocking                      -> forward
    7. Nothing recognized / no color detected                      -> STOP
       (safe default - the robot never does something undefined)

If multiple colors are visible in the same frame, they are resolved by
this SAME priority order: RED > BLUE > YELLOW > GREEN. This is a
reasonable default (most dangerous/attention-grabbing color wins), not the
only valid choice - documented here so it is easy to find and change.

After a BLUE/YELLOW turn, the controller does NOT assume "now go forward".
It stops and lets the NEXT loop iteration re-decide from a fresh frame -
forward is only ever triggered by GREEN specifically. This also means a
BLUE/YELLOW turn is a deliberate SAFETY ENHANCEMENT over a literal blocking
`time.sleep(duration)`: the turn is implemented as its own short sub-loop
that keeps re-checking the ultrasonic sensor at the same ~10Hz cadence
WHILE turning, and aborts the turn immediately (stopping the motors) if an
obstacle appears too close mid-turn. A plain blocking sleep would leave the
robot "blind" to obstacles for the full 2 seconds of a turn, which does not
sit well with obstacle-avoidance being described as a TOP-PRIORITY safety
check evaluated "regardless of what the camera sees" - that phrase is read
here as including "regardless of what the robot is doing", not just
"regardless of color".

--------------------------------------------------------------------------
BLUE detection: color_detection.py's HSV_RANGES only defines RED/GREEN/
YELLOW. Since color_detection.py was explicitly out of scope to modify for
this task, BLUE's HSV range lives in config.py (BLUE_HSV_RANGE) instead,
and this module builds that one extra mask itself using color_detection's
own reusable bgr_to_hsv()/largest_blob() primitives - see
_detect_dominant_color() below. See config.py's BLUE_HSV_RANGE comment for
the full reasoning and a migration note.

--------------------------------------------------------------------------
Car object detection: uses src/vision/object_detection.py's
get_car_detector()/detect_cars(). The real model file (models/
car_detection.onnx) does not exist yet - get_car_detector() returns None in
that case (after logging one clear warning), and detect_cars() then returns
"no detection" immediately, cheaply, every call - so this controller runs
and drives correctly on color alone today, and picks up real car detection
automatically the moment a real model file is added, with zero code changes
here. See object_detection.py for what is verified vs. best-effort
placeholder about the model's actual input/output format.

--------------------------------------------------------------------------
Loop rate: this loop targets AI_DRIVE_LOOP_HZ (config.py, default 10) as
its FULL detect -> decide -> act cycle rate, not just the camera capture
rate - see config.py's AI_DRIVE_LOOP_HZ comment. Each iteration measures
its own actual elapsed time and only sleeps the remainder of the target
interval (never sleeps a negative amount), so a slow iteration (e.g. a
real car-detection inference) does not compound into a growing backlog -
it just means that iteration ran slower than 10Hz, which is logged.

--------------------------------------------------------------------------
Stopping this controller from outside: run() checks `self._stop_requested`
every loop iteration - call `controller.request_stop()` from any thread to
stop it (it is a plain bool flag; setting it is atomic under CPython's GIL,
no lock needed). run() also tries to install a SIGTERM handler that calls
request_stop(), but Python can only register signal handlers on the main
thread - if a future caller (e.g. a Flask web server) runs
AIDriveController on a background thread, SIGTERM cannot be caught there
and request_stop() must be called directly instead; this is logged clearly
if signal registration is skipped for that reason.

VERIFIED FINDING, relevant to whoever launches this process (e.g. a future
web control server): SIGINT (Ctrl+C) only reliably stops this when python
is running as the actual foreground process of an interactive terminal.
Confirmed live on this Pi: launching this script as a `&` background job of
a non-interactive shell (e.g. `python3 ai_drive.py &` inside another
script/over a plain non-pty ssh command) means bash has already set SIGINT
to be IGNORED for that job before exec'ing python (standard POSIX shell
behavior for asynchronous lists, so Ctrl+C in a script doesn't kill its
background jobs) - Python inherits that ignored disposition and SIGINT
does nothing at all, silently, no matter how long you wait. SIGTERM is NOT
affected by this and worked correctly in the same test. So: a supervisor
that launches this as a background/daemonized process (systemd, a web
server's subprocess, `nohup ... &`, etc.) MUST use SIGTERM (or, for
in-process/threaded use, request_stop()) to stop it - do not rely on
SIGINT/Ctrl+C in that context.

--------------------------------------------------------------------------
`status`: a plain dict (self.status / self.get_status()) describing what
the controller is doing right now, updated once per loop iteration -
designed for a future web status page to poll. See get_status()'s
docstring for the exact shape and the (intentionally lock-free) read
pattern.

Run this file directly on the Pi to drive standalone:
    python3 src/robot/ai_drive.py
"""

import logging
import signal
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from config import (  # noqa: E402
    TURN_LEFT_SECONDS,
    TURN_RIGHT_SECONDS,
    CAR_DETECTION_CONFIDENCE_THRESHOLD,
    AI_DRIVE_LOOP_HZ,
    BLUE_HSV_RANGE,
)
from hardware.motor import (  # noqa: E402
    get_motors,
    forward as motor_forward,
    left as motor_turn_left,
    right as motor_turn_right,
    stop as motor_stop,
    cleanup as cleanup_motors,
)
from hardware.rgb_led import (  # noqa: E402
    get_rgb_led,
    set_red as led_red,
    set_green as led_green,
    set_blue as led_blue,
    set_yellow as led_yellow,
    set_off as led_off,
    cleanup as cleanup_rgb_led,
)
from hardware.ultrasonic import (  # noqa: E402
    get_ultrasonic_sensor,
    read_distance,
    cleanup as cleanup_ultrasonic,
)
from robot.obstacle_avoidance import DEFAULT_OBSTACLE_THRESHOLD_M  # noqa: E402
from vision.camera import get_camera, capture_frame, cleanup as cleanup_camera  # noqa: E402
from vision.color_detection import bgr_to_hsv, detect_color, largest_blob  # noqa: E402
from vision.object_detection import get_car_detector, detect_cars  # noqa: E402

logger = logging.getLogger(__name__)

# RED > BLUE > YELLOW > GREEN - see the module docstring's "Decision
# priority" section for why this order is used both to resolve multiple
# simultaneously-visible colors AND (separately, in _decide_and_act) as the
# actual driving decision priority.
COLOR_PRIORITY_ORDER = ("RED", "BLUE", "YELLOW", "GREEN")

_LED_SETTERS = {
    "RED": led_red,
    "GREEN": led_green,
    "BLUE": led_blue,
    "YELLOW": led_yellow,
    None: led_off,
}


class AIDriveController:
    """Owns the camera/motor/LED/ultrasonic/car-detector hardware handles
    and runs the ~10Hz color+object-detection driving loop described in
    the module docstring.

    Designed with a clean public API for a future second phase (a web
    control page) to start/stop this and read its live status:
        controller = AIDriveController()
        thread = threading.Thread(target=controller.run, daemon=True)
        thread.start()
        ...
        status = controller.get_status()
        ...
        controller.request_stop()
        thread.join()
        controller.cleanup()
    """

    def __init__(self, obstacle_threshold_m=DEFAULT_OBSTACLE_THRESHOLD_M,
                 loop_hz=AI_DRIVE_LOOP_HZ, turn_left_seconds=TURN_LEFT_SECONDS,
                 turn_right_seconds=TURN_RIGHT_SECONDS,
                 car_confidence_threshold=CAR_DETECTION_CONFIDENCE_THRESHOLD):
        self.obstacle_threshold_m = obstacle_threshold_m
        self.loop_interval_s = 1.0 / loop_hz
        self.turn_left_seconds = turn_left_seconds
        self.turn_right_seconds = turn_right_seconds
        self.car_confidence_threshold = car_confidence_threshold

        self.camera = get_camera()
        self.motors = get_motors()
        self.rgb = get_rgb_led()
        self.ultrasonic = get_ultrasonic_sensor()
        self.car_detector = get_car_detector()  # None if model missing - see object_detection.py

        self._stop_requested = False
        self._stopped_for_red = False

        # Single-writer (run(), plus __init__/stop() before/outside a run()
        # call), many-reader dict. Every individual assignment below is a
        # plain `self.status[...] = ...` / whole-dict replace, which is
        # atomic under CPython's GIL, and get_status() returns a shallow
        # copy (also atomic) rather than the live dict - good enough for a
        # status display without needing a real threading.Lock. If this
        # controller is ever read/written from many threads doing more than
        # simple polling, revisit this and add a lock.
        self.status = {
            "running": False,
            "timestamp": time.time(),
            "distance_m": None,
            "detected_color": None,
            "car_detected": False,
            "car_confidence": None,
            "action": "stop",
            "stop_reason": "not started yet",
        }

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self):
        """Return a snapshot dict of the controller's current state:
            running: bool - True while run()'s loop is executing
            timestamp: float - time.time() of the last update
            distance_m: float or None - last ultrasonic reading
            detected_color: "RED"/"GREEN"/"BLUE"/"YELLOW"/None - this frame's
                dominant detected color (None = no color detected)
            car_detected: bool - car seen above the confidence threshold
            car_confidence: float or None - that car's confidence, if any
            action: "forward" / "stop" / "turning_left" / "turning_right"
            stop_reason: human-readable string when action == "stop"
                (e.g. "red detected", "car detected (0.87 confidence)",
                "obstacle at 0.18m"), else None
        Safe to call from any thread - see the __init__ comment above for
        the (deliberately lock-free) read/write pattern.
        """
        return dict(self.status)

    def _update_status(self, **fields):
        fields["timestamp"] = time.time()
        self.status.update(fields)

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def request_stop(self):
        """Ask run()'s loop to stop after its current iteration. Safe to
        call from any thread (see __init__'s status comment - same
        GIL-atomic-assignment reasoning applies to this plain bool flag).
        """
        self._stop_requested = True

    def stop(self):
        """Stop the motors immediately. Safe to call at any time, from
        outside the loop too (e.g. a future web 'emergency stop' button).
        Does not affect the sticky-RED state or request_stop() - it only
        stops the motors right now.
        """
        motor_stop(self.motors)
        self._update_status(action="stop")

    # ------------------------------------------------------------------
    # Perception helpers
    # ------------------------------------------------------------------

    def _detect_dominant_color(self, frame):
        """Return the single winning color name (RED/GREEN/BLUE/YELLOW) for
        this frame, or None if nothing is detected. If more than one color
        is present, COLOR_PRIORITY_ORDER decides the winner - see the
        module docstring.
        """
        for color_name in COLOR_PRIORITY_ORDER:
            if color_name == "BLUE":
                # Not in color_detection.py's HSV_RANGES - built locally
                # from config.BLUE_HSV_RANGE using color_detection's own
                # reusable primitives. See the module docstring.
                hsv = bgr_to_hsv(frame)
                lower, upper = BLUE_HSV_RANGE
                mask = cv2.inRange(hsv, np.array(lower), np.array(upper))
            else:
                mask = detect_color(frame, color_name)

            if largest_blob(mask) is not None:
                return color_name
        return None

    # ------------------------------------------------------------------
    # Decision + action
    # ------------------------------------------------------------------

    def _timed_turn(self, motor_turn_fn, duration_s, action_label):
        """Turn for up to duration_s, re-checking the ultrasonic sensor at
        the controller's normal loop cadence the whole time and aborting
        (stopping) immediately if an obstacle appears too close mid-turn.
        See the module docstring's safety note for why this is a sub-loop
        rather than a single blocking time.sleep(duration_s).

        Always leaves the motors stopped when it returns, and always
        updates self.status to action="stop" with an appropriate
        stop_reason - the caller does not need to do either afterward.
        """
        self._update_status(action=action_label, stop_reason=None)
        motor_turn_fn(self.motors)

        start = time.monotonic()
        aborted_distance_m = None
        while time.monotonic() - start < duration_s:
            distance_m = read_distance(self.ultrasonic)
            self._update_status(distance_m=distance_m)
            if distance_m < self.obstacle_threshold_m:
                aborted_distance_m = distance_m
                break
            time.sleep(self.loop_interval_s)

        motor_stop(self.motors)
        if aborted_distance_m is not None:
            self._update_status(
                action="stop",
                stop_reason=f"obstacle at {aborted_distance_m:.2f}m (turn aborted)",
            )
        else:
            # Normal end of turn - next loop iteration reassesses from a
            # fresh frame. Forward is only ever triggered by GREEN.
            self._update_status(action="stop", stop_reason=None)

    def _decide_and_act(self, distance_m, color, car_result):
        """Apply the priority logic in the module docstring for one loop
        iteration. Always leaves self.status reflecting what was done.
        """
        # 1. Obstacle - top priority, regardless of anything else.
        if distance_m < self.obstacle_threshold_m:
            motor_stop(self.motors)
            self._update_status(action="stop", stop_reason=f"obstacle at {distance_m:.2f}m")
            return

        # 2. Car detected above threshold.
        if car_result["car_detected"]:
            motor_stop(self.motors)
            self._update_status(
                action="stop",
                stop_reason=f"car detected ({car_result['confidence']:.2f} confidence)",
            )
            return

        # 3. Sticky RED - see the module docstring for why this is a
        # persistent flag rather than a stateless per-frame check.
        if self._stopped_for_red:
            if color == "GREEN":
                # GREEN explicitly seen - clear the sticky flag and fall
                # through to re-evaluate normally below, using this same
                # fresh frame (no wasted extra iteration).
                self._stopped_for_red = False
            else:
                # Anything other than an explicit GREEN (including a
                # momentarily ambiguous/colorless frame, or any other
                # color) keeps the stop in effect - a single misdetection
                # must not be able to silently clear a safety stop.
                motor_stop(self.motors)
                self._update_status(
                    action="stop",
                    stop_reason="red detected (stopped - waiting for green)",
                )
                return

        # 4. RED (first time, or re-triggered after having cleared).
        if color == "RED":
            self._stopped_for_red = True
            motor_stop(self.motors)
            self._update_status(action="stop", stop_reason="red detected")
            return

        # 5. BLUE -> turn left, then stop and reassess next iteration.
        if color == "BLUE":
            self._timed_turn(motor_turn_left, self.turn_left_seconds, "turning_left")
            return

        # 6. YELLOW -> turn right, then stop and reassess next iteration.
        if color == "YELLOW":
            self._timed_turn(motor_turn_right, self.turn_right_seconds, "turning_right")
            return

        # 7. GREEN, nothing above blocking -> forward.
        if color == "GREEN":
            motor_forward(self.motors)
            self._update_status(action="forward", stop_reason=None)
            return

        # 8. Nothing recognized - safe default.
        motor_stop(self.motors)
        self._update_status(action="stop", stop_reason="no color detected")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _install_sigterm_handler(self):
        """Best-effort: make SIGTERM call request_stop(). Only possible on
        the main thread - see the module docstring's "Stopping this
        controller from outside" section for what to do otherwise.
        """
        if threading.current_thread() is not threading.main_thread():
            logger.info(
                "ai_drive: running on a non-main thread, cannot install a "
                "SIGTERM handler here - call request_stop() directly to "
                "stop this controller instead."
            )
            return
        try:
            signal.signal(signal.SIGTERM, lambda signum, frame: self.request_stop())
        except (ValueError, RuntimeError, OSError):
            logger.info("ai_drive: could not install a SIGTERM handler - use request_stop().")

    def run(self, max_duration_s=None):
        """Run the ~AI_DRIVE_LOOP_HZ detect -> decide -> act loop until
        stopped.

        Unlike obstacle_avoidance.py's auto_drive() (which REQUIRES a
        max_duration_s bound, being a short bounded demo function), this is
        designed to be a long-running production loop started/stopped
        externally (e.g. by a future web control server calling
        request_stop(), or a SIGTERM) - so max_duration_s is OPTIONAL here
        and defaults to None (run until stopped). Pass a value if you want
        a bounded run anyway (e.g. for testing).

        Stops when ANY of: request_stop() was called, SIGTERM was received
        (main thread only), max_duration_s elapsed (if given), or
        KeyboardInterrupt/any exception occurred. The motors are ALWAYS
        stopped in a `finally` block - see the module SAFETY note.
        """
        self._install_sigterm_handler()
        self._stop_requested = False
        self._update_status(running=True, action="stop", stop_reason="starting up")

        start = time.monotonic()
        try:
            while not self._stop_requested:
                if max_duration_s is not None and time.monotonic() - start >= max_duration_s:
                    logger.info("ai_drive: max_duration_s=%s reached, stopping.", max_duration_s)
                    break

                iteration_start = time.monotonic()

                distance_m = read_distance(self.ultrasonic)
                frame = capture_frame(self.camera)
                color = self._detect_dominant_color(frame)
                car_result = detect_cars(self.car_detector, frame, self.car_confidence_threshold)

                _LED_SETTERS.get(color, led_off)(self.rgb)

                self._update_status(
                    distance_m=distance_m,
                    detected_color=color,
                    car_detected=car_result["car_detected"],
                    car_confidence=car_result["confidence"],
                )
                self._decide_and_act(distance_m, color, car_result)

                elapsed = time.monotonic() - iteration_start
                remaining = self.loop_interval_s - elapsed
                if remaining > 0:
                    time.sleep(remaining)
                else:
                    logger.debug(
                        "ai_drive: loop iteration took %.3fs, slower than the %.3fs target.",
                        elapsed, self.loop_interval_s,
                    )
        except KeyboardInterrupt:
            logger.info("ai_drive: KeyboardInterrupt received, stopping.")
        except Exception:
            logger.exception("ai_drive: unexpected error in main loop, stopping.")
            raise
        finally:
            motor_stop(self.motors)
            led_off(self.rgb)
            self._update_status(running=False, action="stop", stop_reason="stopped")

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        """Stop the motors and release every GPIO/camera resource. Call
        this when completely done with the controller (not between run()
        calls - request_stop() is for that).
        """
        motor_stop(self.motors)  # belt-and-braces, run()'s finally already does this
        cleanup_motors(self.motors)
        cleanup_rgb_led(self.rgb)
        cleanup_ultrasonic(self.ultrasonic)
        cleanup_camera(self.camera)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")

    print("AI drive smoke test: starting AIDriveController.")
    print(
        "SAFETY: motors/ultrasonic are not physically wired yet, so this is "
        "safe to run as-is. Once wired, ALWAYS lift the robot off the "
        "ground / wheels free-spinning before running this."
    )
    print("Press Ctrl+C to stop.")

    controller = AIDriveController()
    try:
        # Bounded here only for an unattended smoke test; interactive use
        # would normally call controller.run() with no max_duration_s and
        # rely on Ctrl+C / request_stop() / SIGTERM instead.
        controller.run(max_duration_s=30)
    finally:
        controller.cleanup()
        print("AI drive controller cleaned up, all GPIO/camera released.")
