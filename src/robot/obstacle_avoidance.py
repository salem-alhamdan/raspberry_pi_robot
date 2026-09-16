"""
Reactive obstacle-avoidance behavior, composing src/hardware/motor.py and
src/hardware/ultrasonic.py. This is the first "robot behavior" layer in the
project - the hardware modules underneath stay independent and reusable on
their own; this module just combines them.

================================================================================
SAFETY: this module can drive the real motors. Everything in motor.py's
SAFETY warning applies here too - before running avoid_obstacle() or
auto_drive() on real hardware, the robot must be lifted off the ground /
wheels free-spinning, to prevent unexpected movement. The ultrasonic
sensor's ECHO pin also still requires its voltage divider before ECHO can
be safely wired to GPIO21 - see hardware/ultrasonic.py's SAFETY note.
================================================================================

Wiring assumption: neither the L298N/motors nor the ultrasonic sensor are
physically wired yet. Every function below is real, callable code (it
really does read the sensor and really does drive the gpiozero Motor
objects), but with nothing wired there is nothing to avoid and nothing to
move - see hardware/motor.py and hardware/ultrasonic.py for exactly what
"nothing wired" looks like at the software level for each.

Taught in this order (matching the notebook's planned progression):

    stop_if_obstacle(motors, sensor)   # simplest possible building block
    avoid_obstacle(motors, sensor)     # one full reactive step
    auto_drive(motors, sensor, ...)    # loops avoid_obstacle(), bounded + interruptible

auto_drive() safety: it is NOT a bare `while True`. It always stops on its
own after max_duration_s (required, always enforced - there is no way to
disable this bound), and can additionally be told to stop early via an
optional stop_condition() callable checked every loop iteration (e.g. wire
this to a button press, a keyboard flag, an iteration counter - whatever
the caller wants to interrupt the loop with from outside). The motors are
stopped in a `finally` block, so a KeyboardInterrupt or any exception while
auto_drive() is running still leaves the robot stopped, not driving with
nothing watching it.
"""

import sys
import time
from pathlib import Path

# Make `from hardware...` work whether this file is run directly
# (`python3 src/robot/obstacle_avoidance.py`) or imported as
# `robot.obstacle_avoidance` after a notebook has added the `src/` folder
# to sys.path. Either way, this puts the `src/` directory (this file's
# parent's parent) on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hardware.motor import (  # noqa: E402
    forward as motor_forward,
    backward as motor_backward,
    right as motor_turn_right,
    stop as motor_stop,
)
from hardware.ultrasonic import read_distance  # noqa: E402

# Obstacle distance threshold: anything closer than this counts as "an
# obstacle". 0.25m (25cm) is the middle of the project's suggested 20-30cm
# range - close enough to give the sensor's narrow beam a fair chance of
# actually seeing what's ahead, far enough to leave room to stop/back up
# before contact once this is running at real driving speed.
DEFAULT_OBSTACLE_THRESHOLD_M = 0.25

# "Brief" durations for the back-up/turn steps of one avoidance maneuver.
DEFAULT_BACKUP_SECONDS = 0.5
DEFAULT_TURN_SECONDS = 0.5

# auto_drive() ALWAYS stops itself after this long, no matter what - see
# the module docstring. Kept short by default since nothing is wired yet
# and this will be run/demoed long before any real multi-minute drive.
DEFAULT_AUTO_DRIVE_MAX_SECONDS = 30
DEFAULT_LOOP_INTERVAL_S = 0.1


def stop_if_obstacle(motors, sensor, threshold_m=DEFAULT_OBSTACLE_THRESHOLD_M):
    """Simplest building block: if the sensor sees something closer than
    threshold_m, stop the motors and return True. Otherwise do nothing and
    return False. Read distance() > threshold -> keep going; distance() <
    threshold -> stop. No backing up or turning here - that's avoid_obstacle().
    """
    distance_m = read_distance(sensor)
    if distance_m < threshold_m:
        motor_stop(motors)
        return True
    return False


def avoid_obstacle(motors, sensor, threshold_m=DEFAULT_OBSTACLE_THRESHOLD_M,
                    speed_percent=None, backup_seconds=DEFAULT_BACKUP_SECONDS,
                    turn_seconds=DEFAULT_TURN_SECONDS):
    """One full reactive step: forward -> (if obstacle) stop, back up
    briefly, turn briefly -> forward again.

    Always ends with the robot driving forward - either because the path
    was already clear, or because it just finished backing away from and
    turning away from an obstacle - so auto_drive() can simply call this
    repeatedly without any extra logic of its own.

    speed_percent (0-100) is optional and passed through to motor.py's
    movement functions unchanged; leave it as None to use motor.py's own
    default speed.

    Returns True if an obstacle was detected and avoided this call, False
    if the path was already clear (and the robot just moved forward).
    """
    speed_kwargs = {} if speed_percent is None else {"speed_percent": speed_percent}

    obstacle_avoided = stop_if_obstacle(motors, sensor, threshold_m)
    if obstacle_avoided:
        motor_backward(motors, **speed_kwargs)
        time.sleep(backup_seconds)
        motor_stop(motors)

        # Turn direction is an arbitrary but fixed choice (always turn
        # right) - simple and predictable for teaching. Alternating or
        # randomizing the turn direction is a natural next exercise.
        motor_turn_right(motors, **speed_kwargs)
        time.sleep(turn_seconds)
        motor_stop(motors)

    motor_forward(motors, **speed_kwargs)
    return obstacle_avoided


def auto_drive(motors, sensor, threshold_m=DEFAULT_OBSTACLE_THRESHOLD_M,
                speed_percent=None, max_duration_s=DEFAULT_AUTO_DRIVE_MAX_SECONDS,
                stop_condition=None, loop_interval_s=DEFAULT_LOOP_INTERVAL_S):
    """Repeatedly call avoid_obstacle() to drive around avoiding obstacles.

    Stops when EITHER:
        - max_duration_s has elapsed. This is required and always enforced
          - there is no way to call this with an unbounded run time, even
            by accident.
        - stop_condition (optional) is a callable that returns True. Check
          it every loop iteration to let the caller interrupt the loop from
          outside - e.g. a button's is_pressed, a threading.Event, a
          manually-incremented counter, anything callable with no arguments.

    The motors are ALWAYS stopped in a finally block, so a KeyboardInterrupt
    or any exception while this loop is running still leaves the robot
    stopped, not driving with nothing watching it.
    """
    if max_duration_s is None or max_duration_s <= 0:
        raise ValueError(
            "max_duration_s must be a positive number - auto_drive() must "
            "always have a time bound, it cannot be told to run forever"
        )

    stop_reason = f"max_duration_s={max_duration_s}s reached"
    start = time.monotonic()

    try:
        while time.monotonic() - start < max_duration_s:
            if stop_condition is not None and stop_condition():
                stop_reason = "stop_condition satisfied"
                break
            avoid_obstacle(motors, sensor, threshold_m, speed_percent=speed_percent)
            time.sleep(loop_interval_s)
        print(f"auto_drive: stopping ({stop_reason}).")
    finally:
        motor_stop(motors)
