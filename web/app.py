"""
Flask web control server - the browser-driven "steering wheel" for the
robot, composing everything built so far:
    src/hardware/motor.py          (manual-mode direct motor control)
    src/vision/camera.py           (manual-mode MJPEG preview stream)
    src/robot/ai_drive.py          (AI mode - AIDriveController)

    python3 web/app.py
    # then browse to http://<pi-ip>:5000/

================================================================================
SAFETY: before driving for real (manual OR AI mode), lift the robot chassis
off the ground / wheels free-spinning - same rule as every other module in
this project (see SAFETY.md). Nothing is physically wired yet, so running
this server right now is safe regardless.
================================================================================

--------------------------------------------------------------------------
THE CENTRAL DESIGN PROBLEM: mode exclusivity
--------------------------------------------------------------------------
AIDriveController.__init__() opens its OWN motor/camera/RGB-LED/ultrasonic
handles (see ai_drive.py). picamera2 WILL raise a real "device busy" error
if this server also tries to hold its own camera handle at the same time -
but QA found that gpiozero's default pin factory on this Pi (RPiGPIOFactory)
does NOT enforce the same protection for GPIO pins: two separate handle
sets on the same motor/LED pins can both succeed silently, with no error
from either side (see SAFETY.md's "GPIO exclusivity" section and
tests/TEST_REPORT.md's "Web control server" section for the full
investigation). So the in-process exclusivity this class enforces is a real
requirement precisely because the underlying library will NOT catch a
same-process mistake automatically for GPIO the way it would for the
camera - and it does nothing to protect against a SEPARATE process (e.g. a
notebook kernel) also touching the same pins, which is why SAFETY.md tells
the user never to run two GPIO-touching programs at once. So exactly one of
"manual hardware handles" or "an AIDriveController instance" may exist at
any moment within THIS process - never both.

This is solved by the HardwareManager class below, which:
    - owns manual mode's own get_motors()/get_camera() handles (motors for
      direct control, camera for /video_feed - see "Camera streaming"
      below for why manual mode needs its own camera handle but does NOT
      need rgb_led/ultrasonic handles at all)
    - owns the (possibly None) AIDriveController + its background thread
    - guards every mode transition with a single threading.RLock
      (self.lock), so:
        * a mode switch always fully releases the old mode's resources
          before acquiring the new mode's, in the order the task spec
          requires (manual->ai: release manual, THEN construct
          AIDriveController; ai->manual: request_stop()+join()+cleanup()
          the controller, THEN re-acquire manual handles)
        * every request handler that touches motors/camera/mode takes the
          SAME lock, so a command can never execute against a half-torn-
          down set of handles, and two overlapping /api/mode calls (e.g.
          a user double-clicking the mode toggle) simply serialize instead
          of racing - the second call sees the mode already changed and
          either no-ops or performs a clean transition from the new state,
          never a half-switched one.
    - RLock (not a plain Lock) specifically because emergency_stop() needs
      to call the same locked internal methods switch_to_manual() would use,
      from within a call that may itself already hold the lock.

Manual mode's hardware bundle is deliberately just {motors, camera} - NOT
rgb_led/ultrasonic. Manual driving does not need the LED or ultrasonic
sensor, and giving manual mode its own handles to those pins would only
recreate the exact same "two handle sets on one GPIO pin" conflict this
whole design exists to avoid, for no benefit.

--------------------------------------------------------------------------
Manual-mode command handling: "single current intent", watchdog, no queue
--------------------------------------------------------------------------
Per the task spec's anti-over-engineering guidance: there is no command
queue. Each POST /api/command simply executes immediately and overwrites
`hw.current_intent`. If a forward and a backward request land back-to-back
(e.g. from a flaky client), whichever one acquires hw.lock second simply
wins - the motors end up doing whatever the most recent command said,
which is both simple and safe (never "average" or combine two directions).

Watchdog: config.COMMAND_WATCHDOG_TIMEOUT_S (1.5s) is how long the server
waits after the last movement command before assuming the browser
disconnected/stopped responding, and force-stopping the motors. A
background thread (_watchdog_loop) checks this every WATCHDOG_POLL_INTERVAL_S
(0.25s - fine-grained relative to the 1.5s timeout). The frontend
(static/app.js) resends the currently-held command every
FRONTEND_REPEAT_INTERVAL_MS (400ms) while a movement button/key is held,
which both re-executes the command (harmless - motor functions are
idempotent) AND refreshes hw.last_command_time, so normal held-button
driving never trips the watchdog. The watchdog only runs in manual mode -
AI mode is autonomous and re-evaluates stop/go every loop iteration on its
own (obstacle/red/car checks), independent of whether a browser is even
connected, so it needs no separate watchdog here.

--------------------------------------------------------------------------
Emergency stop: same button/endpoint in EITHER mode, deliberately
conservative in AI mode
--------------------------------------------------------------------------
POST /api/estop always stops the motors immediately, in whichever mode is
currently active (calls AIDriveController.stop() if in AI mode, plain
motor stop() if in manual mode). ADDITIONALLY, if AI mode is active, estop
also fully exits AI mode back to manual (same request_stop()+join()+
cleanup() + re-acquire-manual-handles sequence as a normal mode switch).
This is the more conservative of the two reasonable choices: a plain
`.stop()` only halts the motors for the current instant, but the AI loop
is still running and free to decide "drive forward" again on its very next
~100ms iteration (e.g. the moment a red-stop condition clears, or a fresh
GREEN frame arrives). A human hitting a panic button almost certainly wants
"give me back full manual control right now", not "pause for a fraction of
a second". Exiting AI mode entirely is what actually guarantees that.

--------------------------------------------------------------------------
Camera streaming: independent of motor control, and mode-aware
--------------------------------------------------------------------------
/video_feed is a standard Flask MJPEG generator (multipart/x-mixed-replace
JPEG frames). Every single per-frame operation is wrapped in its own
try/except INSIDE the generator (_generate_mjpeg) - a capture or encode
failure is logged and produces a placeholder/last-good frame, and NEVER
raises out of the generator in a way that could affect anything else (see
SAFETY.md's "Camera / motor independence" rule). The mode-lock is held only
long enough to snapshot `mode`/`camera` (a plain attribute read), then
released BEFORE the (potentially slower) actual camera capture happens -
so a slow or stuck camera frame can never block a motor command or a mode
switch, and vice versa.

While AI mode is active, this endpoint does NOT open a second Picamera2
instance - ai_drive.py was explicitly out of scope to modify, so there is
no accessor for its last captured frame, and opening a second competing
camera handle would recreate the exact resource-conflict problem this
whole module works around. Instead /video_feed shows a simple "AI mode
active" placeholder JPEG while AI mode runs, and resumes live frames the
moment manual mode is re-entered (which is also exactly when this server
re-acquires its own camera handle). This is the simpler of the two options
the task spec offered, and is judged sufficient - the status panel already
shows what the AI loop is doing (action/stop_reason/detected_color/etc via
GET /api/status), which is the actually-requested "check status" feature;
a live camera frame during AI mode is a nice-to-have, not what was asked
for.

--------------------------------------------------------------------------
Manual movement is server-side blocked during AI mode, not just hidden
--------------------------------------------------------------------------
POST /api/command checks `hw.mode` under the lock and returns 409 with no
motor action taken if mode != "manual" - a stale browser tab or a direct
curl/API call cannot fight the AI loop for the motors, even though the
frontend also disables the buttons as the primary (nicer) UX layer.

--------------------------------------------------------------------------
Crash/shutdown safety
--------------------------------------------------------------------------
    - A Flask-wide `@app.errorhandler(Exception)` calls
      hw.stop_motors_only() (stop the motors in whichever mode, WITHOUT
      forcing a full AI-mode exit - see its docstring for why this is
      deliberately lighter than emergency_stop()) before returning a 500,
      so an unrelated bug in a request handler can never leave a stack
      trace and moving motors.
    - main() registers hw.shutdown() with atexit and on SIGTERM/SIGINT, so
      killing the server (Ctrl+C, systemd stop, etc.) always stops motors
      and releases every GPIO/camera handle it holds, including a running
      AI controller.
    - The Flask dev server is run with use_reloader=False. This is NOT
      optional: the reloader forks a second child process that would
      re-run this whole module top-to-bottom, including constructing a
      SECOND HardwareManager -> a second get_motors()/get_camera() (or a
      second AIDriveController) trying to grab the exact same GPIO pins as
      the first process. threaded=True IS required, for an unrelated
      reason: /video_feed holds its HTTP connection open indefinitely
      (streaming), and Flask's dev server is single-request-at-a-time
      unless threaded=True - without it, one open camera stream tab would
      completely block every movement command from any client.
"""

import atexit
import logging
import signal
import sys
import threading
import time
from pathlib import Path

# Make `from config import ...` / `from hardware.motor import ...` etc. work
# the same way every src/ module does it (see e.g. hardware/motor.py's
# comment) - this file lives in web/, so its parent's parent is the project
# root, and we need <root>/src on sys.path, not <root> itself.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from flask import Flask, Response, jsonify, render_template, request  # noqa: E402

from config import COMMAND_WATCHDOG_TIMEOUT_S, WEB_STREAM_TARGET_FPS  # noqa: E402
from hardware.motor import (  # noqa: E402
    DEFAULT_SPEED_PERCENT,
    backward as motor_backward,
    cleanup as motor_cleanup,
    forward as motor_forward,
    get_motors,
    left as motor_left,
    right as motor_right,
    stop as motor_stop,
)
from robot.ai_drive import AIDriveController  # noqa: E402
from vision.camera import capture_frame, cleanup as camera_cleanup, get_camera  # noqa: E402

logger = logging.getLogger(__name__)

# How often the watchdog thread checks for a stale manual command - fine
# relative to COMMAND_WATCHDOG_TIMEOUT_S (1.5s default), see module docstring.
WATCHDOG_POLL_INTERVAL_S = 0.25

# How long to wait for the AI drive thread to notice request_stop() and
# exit before we give up on the join() and clean up anyway. AIDriveController
# loops at ~AI_DRIVE_LOOP_HZ (config.py, default 10, i.e. ~0.1s/iteration)
# plus up to a full BLUE/YELLOW turn duration if mid-turn (config.py:
# TURN_LEFT_SECONDS/TURN_RIGHT_SECONDS, 2.0s default each) before it next
# checks _stop_requested, so this needs real headroom above that worst case.
AI_STOP_JOIN_TIMEOUT_S = 5.0

VALID_MANUAL_ACTIONS = ("forward", "backward", "left", "right", "stop")

_MOVE_FUNCS = {
    "forward": motor_forward,
    "backward": motor_backward,
    "left": motor_left,
    "right": motor_right,
}

STREAM_FRAME_INTERVAL_S = 1.0 / WEB_STREAM_TARGET_FPS
_MJPEG_BOUNDARY = b"frame"


def _make_placeholder_jpeg(text, size=(640, 480)):
    """Build a static JPEG (as bytes) showing `text` on a plain background,
    used by /video_feed when a live frame isn't available - see the module
    docstring's "Camera streaming" section for when/why.
    """
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    cv2.putText(
        img, text, (24, size[1] // 2), cv2.FONT_HERSHEY_SIMPLEX,
        0.7, (255, 255, 255), 2, cv2.LINE_AA,
    )
    ok, jpeg = cv2.imencode(".jpg", img)
    return jpeg.tobytes() if ok else b""


_AI_MODE_PLACEHOLDER_JPEG = _make_placeholder_jpeg("AI mode active - camera busy")
_CAMERA_UNAVAILABLE_PLACEHOLDER_JPEG = _make_placeholder_jpeg("Camera unavailable")


class HardwareManager:
    """Owns manual-mode motor+camera handles XOR a running AIDriveController,
    and enforces that exclusivity. See the module docstring's "THE CENTRAL
    DESIGN PROBLEM" section for the full reasoning - this class is the
    entire implementation of that design.

    Every public method acquires self.lock itself; every *_locked() helper
    assumes the caller already holds it. self.lock is an RLock so a method
    that already holds it (e.g. emergency_stop()) can call another locked
    public method (switch handling) from the same thread without deadlocking.
    """

    def __init__(self):
        self.lock = threading.RLock()
        # Separate, narrower lock just for serializing actual camera
        # captures (used by /video_feed) - deliberately NOT the same lock
        # as self.lock, so a slow camera capture can never block a motor
        # command or a mode switch. See module docstring.
        self.camera_lock = threading.Lock()

        self.mode = "manual"
        self.motors = None
        self.camera = None
        self.ai_controller = None
        self.ai_thread = None

        self.current_intent = "stop"
        self.current_speed = DEFAULT_SPEED_PERCENT
        self.last_command_time = time.monotonic()

        with self.lock:
            self._acquire_manual_locked()

    # ------------------------------------------------------------------
    # Locked internals - caller must hold self.lock
    # ------------------------------------------------------------------

    def _acquire_manual_locked(self):
        logger.info("HardwareManager: acquiring manual-mode handles (motors + camera).")
        self.motors = get_motors()
        try:
            self.camera = get_camera()
        except Exception:
            logger.exception(
                "HardwareManager: camera unavailable for manual streaming - "
                "motor control is unaffected, /video_feed will show a placeholder."
            )
            self.camera = None
        self.current_intent = "stop"
        self.last_command_time = time.monotonic()

    def _release_manual_locked(self):
        if self.motors is not None:
            try:
                motor_stop(self.motors)
                motor_cleanup(self.motors)
            except Exception:
                logger.exception("HardwareManager: error releasing manual motor handles.")
            self.motors = None
        if self.camera is not None:
            try:
                camera_cleanup(self.camera)
            except Exception:
                logger.exception("HardwareManager: error releasing manual camera handle.")
            self.camera = None

    def _start_ai_locked(self):
        logger.info("HardwareManager: starting AI drive controller.")
        self.ai_controller = AIDriveController()
        self.ai_thread = threading.Thread(
            target=self.ai_controller.run, daemon=True, name="ai-drive-loop",
        )
        self.ai_thread.start()

    def _stop_ai_locked(self):
        if self.ai_controller is None:
            return
        logger.info("HardwareManager: stopping AI drive controller.")
        self.ai_controller.request_stop()
        if self.ai_thread is not None:
            self.ai_thread.join(timeout=AI_STOP_JOIN_TIMEOUT_S)
            if self.ai_thread.is_alive():
                logger.warning(
                    "HardwareManager: AI drive thread did not stop within "
                    "%.1fs - cleaning up its hardware handles anyway.",
                    AI_STOP_JOIN_TIMEOUT_S,
                )
        try:
            self.ai_controller.cleanup()
        except Exception:
            logger.exception("HardwareManager: error cleaning up AI controller.")
        self.ai_controller = None
        self.ai_thread = None

    # ------------------------------------------------------------------
    # Public API - each acquires self.lock itself
    # ------------------------------------------------------------------

    def switch_to_ai(self):
        """Release manual handles, then start AIDriveController. No-op if
        already in AI mode. See module docstring for the ordering guarantee.
        """
        with self.lock:
            if self.mode == "ai":
                return
            self._release_manual_locked()
            try:
                self._start_ai_locked()
            except Exception:
                logger.exception(
                    "HardwareManager: failed to start AI mode - falling back to manual."
                )
                self._acquire_manual_locked()
                raise
            self.mode = "ai"

    def switch_to_manual(self):
        """Stop+cleanup AIDriveController, then re-acquire manual handles.
        No-op if already in manual mode.
        """
        with self.lock:
            if self.mode == "manual":
                return
            self._stop_ai_locked()
            self._acquire_manual_locked()
            self.mode = "manual"

    def stop_motors_only(self):
        """Stop the motors right now, in whichever mode is currently
        active, WITHOUT forcing an AI-mode exit. Used by the generic
        unhandled-exception handler (see module docstring) - a web-layer
        bug unrelated to driving shouldn't necessarily kill a otherwise-
        healthy AI drive loop, it just must never leave motors moving.
        """
        with self.lock:
            if self.mode == "ai" and self.ai_controller is not None:
                try:
                    self.ai_controller.stop()
                except Exception:
                    logger.exception("stop_motors_only: ai_controller.stop() failed")
            if self.motors is not None:
                try:
                    motor_stop(self.motors)
                except Exception:
                    logger.exception("stop_motors_only: motor_stop() failed")
            self.current_intent = "stop"

    def emergency_stop(self):
        """Stop the motors immediately, AND (if in AI mode) fully exit back
        to manual mode. See the module docstring's "Emergency stop" section
        for why this is deliberately more conservative than stop_motors_only().
        """
        with self.lock:
            self.stop_motors_only()
            if self.mode == "ai":
                self._stop_ai_locked()
                self._acquire_manual_locked()
                self.mode = "manual"

    def shutdown(self):
        """Release every resource this manager holds. Call once, on server
        shutdown - see main()'s atexit/signal registration.
        """
        with self.lock:
            if self.mode == "ai":
                self._stop_ai_locked()
            self._release_manual_locked()

    def status_payload(self):
        """Build the GET /api/status response dict. See module docstring/
        the task spec for the required fields per mode.
        """
        with self.lock:
            if self.mode == "ai":
                payload = {"mode": "ai"}
                if self.ai_controller is not None:
                    payload.update(self.ai_controller.get_status())
                return payload
            return {
                "mode": "manual",
                "action": self.current_intent,
                "speed_percent": self.current_speed,
                "camera_available": self.camera is not None,
            }


# ---------------------------------------------------------------------------
# Watchdog (manual mode only - see module docstring)
# ---------------------------------------------------------------------------

def _watchdog_loop(hw, stop_event):
    while not stop_event.wait(WATCHDOG_POLL_INTERVAL_S):
        with hw.lock:
            if (
                hw.mode == "manual"
                and hw.motors is not None
                and hw.current_intent != "stop"
                and time.monotonic() - hw.last_command_time > COMMAND_WATCHDOG_TIMEOUT_S
            ):
                logger.warning(
                    "Watchdog: no manual command for over %.1fs, stopping motors.",
                    COMMAND_WATCHDOG_TIMEOUT_S,
                )
                try:
                    motor_stop(hw.motors)
                except Exception:
                    logger.exception("Watchdog: motor_stop() failed")
                hw.current_intent = "stop"


# ---------------------------------------------------------------------------
# Camera streaming (independent of motor control - see module docstring)
# ---------------------------------------------------------------------------

def _generate_mjpeg(hw):
    """Generator yielding multipart/x-mixed-replace JPEG frame chunks.

    Every per-iteration failure is caught HERE and turned into a
    placeholder/last-good frame - see the module docstring's "Camera
    streaming" section. GeneratorExit (raised when the client disconnects)
    is intentionally NOT caught, so the generator - and this thread - exits
    cleanly when a browser tab closes.
    """
    last_good_frame = None
    while True:
        try:
            with hw.lock:
                mode = hw.mode
                camera = hw.camera
            if mode != "manual":
                frame_bytes = _AI_MODE_PLACEHOLDER_JPEG
            elif camera is None:
                frame_bytes = _CAMERA_UNAVAILABLE_PLACEHOLDER_JPEG
            else:
                with hw.camera_lock:
                    frame_bgr = capture_frame(camera)
                ok, jpeg = cv2.imencode(".jpg", frame_bgr)
                if not ok:
                    raise RuntimeError("cv2.imencode failed")
                frame_bytes = jpeg.tobytes()
                last_good_frame = frame_bytes
        except Exception:
            # Deliberately broad: ANY camera-path failure must degrade to a
            # placeholder/last-good frame, never propagate - see SAFETY.md's
            # "Camera / motor independence" rule and the module docstring.
            logger.exception("video_feed: frame capture/encode failed.")
            frame_bytes = last_good_frame or _CAMERA_UNAVAILABLE_PLACEHOLDER_JPEG

        yield (
            b"--" + _MJPEG_BOUNDARY + b"\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )
        time.sleep(STREAM_FRAME_INTERVAL_S)


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
hw = None  # HardwareManager instance - constructed in main(), see its docstring


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    return jsonify(hw.status_payload())


@app.route("/api/command", methods=["POST"])
def api_command():
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in VALID_MANUAL_ACTIONS:
        return jsonify(ok=False, error=f"invalid action: {action!r}"), 400

    try:
        speed = int(data.get("speed", DEFAULT_SPEED_PERCENT))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="invalid speed"), 400
    speed = max(0, min(100, speed))

    with hw.lock:
        if hw.mode != "manual":
            # Server-side enforcement - see module docstring's "Manual
            # movement is server-side blocked during AI mode" section.
            return jsonify(ok=False, error="AI mode active - manual commands disabled", mode=hw.mode), 409
        if hw.motors is None:
            return jsonify(ok=False, error="motor hardware unavailable"), 503

        if action == "stop":
            motor_stop(hw.motors)
        else:
            _MOVE_FUNCS[action](hw.motors, speed)

        hw.current_intent = action
        hw.current_speed = speed
        hw.last_command_time = time.monotonic()

    return jsonify(ok=True, mode="manual", action=action, speed=speed)


@app.route("/api/mode", methods=["POST"])
def api_mode():
    data = request.get_json(silent=True) or {}
    target = data.get("mode")
    if target not in ("manual", "ai"):
        return jsonify(ok=False, error="mode must be 'manual' or 'ai'"), 400

    try:
        if target == "ai":
            hw.switch_to_ai()
        else:
            hw.switch_to_manual()
    except Exception:
        logger.exception("api_mode: mode switch to %r failed", target)
        hw.stop_motors_only()  # belt-and-braces: never leave motors running after a failed switch
        return jsonify(ok=False, error="mode switch failed, see server logs; motors stopped", mode=hw.mode), 500

    return jsonify(ok=True, mode=hw.mode)


@app.route("/api/estop", methods=["POST"])
def api_estop():
    hw.emergency_stop()
    return jsonify(ok=True, mode=hw.mode)


@app.route("/video_feed")
def video_feed():
    return Response(
        _generate_mjpeg(hw),
        mimetype=f"multipart/x-mixed-replace; boundary={_MJPEG_BOUNDARY.decode()}",
    )


@app.errorhandler(Exception)
def handle_unhandled_exception(error):
    """Catch-all safety net: an unhandled exception anywhere in a request
    handler must never leave motors running. See module docstring's
    "Crash/shutdown safety" section for why this uses stop_motors_only()
    rather than the stronger emergency_stop().
    """
    logger.exception("Unhandled exception in request handler - stopping motors for safety.")
    try:
        hw.stop_motors_only()
    except Exception:
        logger.exception("handle_unhandled_exception: stop_motors_only() itself failed")
    return jsonify(ok=False, error="internal server error, motors stopped for safety"), 500


def main():
    global hw

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s: %(message)s")

    print("Web control server starting.")
    print(
        "SAFETY: lift the robot chassis off the ground / wheels free-spinning "
        "before driving for real, in either manual or AI mode."
    )

    hw = HardwareManager()

    watchdog_stop_event = threading.Event()
    watchdog_thread = threading.Thread(
        target=_watchdog_loop, args=(hw, watchdog_stop_event), daemon=True, name="watchdog",
    )
    watchdog_thread.start()

    def _shutdown():
        logger.info("Shutting down: stopping watchdog and releasing all hardware.")
        watchdog_stop_event.set()
        hw.shutdown()

    atexit.register(_shutdown)

    def _handle_signal(signum, _frame):
        logger.info("Received signal %s, shutting down.", signum)
        _shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        # threaded=True: required, see module docstring ("Crash/shutdown
        # safety") - /video_feed holds a connection open indefinitely.
        # use_reloader=False: required, NOT optional - see the same section
        # for why the reloader's forked child would double-acquire GPIO.
        app.run(host="0.0.0.0", port=5000, threaded=True, debug=False, use_reloader=False)
    finally:
        _shutdown()


if __name__ == "__main__":
    main()
