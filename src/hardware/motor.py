"""
L298N motor driver control for the left/right DC motors (see src/config.py):
    left motor:  MOTOR_LEFT_ENABLE_PIN (ENA, PWM speed), MOTOR_LEFT_IN1_PIN,
                 MOTOR_LEFT_IN2_PIN (direction)
    right motor: MOTOR_RIGHT_ENABLE_PIN (ENB, PWM speed), MOTOR_RIGHT_IN3_PIN,
                 MOTOR_RIGHT_IN4_PIN (direction)

================================================================================
SAFETY: Before running any movement function on real hardware, the robot
must be lifted off the ground / wheels free-spinning, to prevent unexpected
movement. Nothing is physically wired yet (see HARDWARE.md), so there is no
physical risk right now - but this code will be run as-is once it IS wired,
so treat every function below as if it could move a real robot immediately.
================================================================================

Wiring assumption: L298N + motors are NOT yet wired to the Pi. Toggling
these pins is safe (nothing attached), but do not expect any real-world
movement until the hardware phase confirms wiring.

Why gpiozero.Motor is used, but NOT for speed control:
    gpiozero.Motor(forward=IN_a, backward=IN_b, enable=EN) looks at first
    like the obvious fit for an L298N channel. But checking gpiozero 1.6.2's
    actual source (Motor.__init__) shows that its `enable` pin is only ever
    constructed as a plain DigitalOutputDevice(initial_value=True) - held
    statically HIGH forever. gpiozero does NOT pulse the enable pin for
    speed; instead, when `pwm=True` (the default), it PWMs the forward/
    backward pins themselves and leaves enable permanently on. That would
    still spin a motor, but it means GPIO12/13 (ENA/ENB - the pins actually
    wired to the Pi's hardware PWM0/PWM1 channels per PINOUT.md) would never
    be PWM'd at all, contradicting how this project's pins are documented
    and wired, and how QA will verify it (duty-cycle changes on ENA/ENB).

    So this module splits the two responsibilities the way the L298N
    hardware itself expects:
        - gpiozero.Motor(forward=IN1, backward=IN2, pwm=False) for each
          motor: IN1-4 become plain DigitalOutputDevice pins, HIGH/LOW only
          - direction control, nothing else. Still uses gpiozero's built-in
            H-bridge class (forward()/backward()/stop()) instead of hand-
            rolling RPi.GPIO calls.
        - a separate gpiozero.PWMOutputDevice for each of ENA/ENB, driven
          directly by this module's speed functions - real PWM, on the
          pins actually meant to carry it.

Speed convention: functions here take speed_percent as an int 0-100 (0 =
stopped, 100 = full speed), matching rgb_led.py's beginner-friendly
0-255-style convention. 0-100 is converted to gpiozero's 0.0-1.0 PWM value
internally by _percent_to_ratio().

Turn convention: left(...) and right(...) are ROBOT-level pivot turns (spin
in place), built from the per-motor primitives:
    left(...)  = left motor backward + right motor forward (pivot left)
    right(...) = left motor forward + right motor backward (pivot right)
This assumes the two motors are wired with consistent, "normal" polarity
(both motors' OUT1/OUT2 leads connected the same way round). If, once
wired, forward() or a turn comes out backwards or mirrored, the fix is to
physically swap that motor's two wire leads at the L298N terminal - not to
edit this code.

Safety properties (see SAFETY.md):
    - Every movement function has a matching stop(): left_stop(), right_
      stop(), and the combined stop(). All three zero BOTH the direction
      pins AND the PWM speed value (ENA/ENB), not just direction - so a
      motor is never left "armed" at a nonzero speed after being stopped.
    - No function here blocks or loops. Every call sets pin state and
      returns immediately; duration is entirely controlled by the caller
      (e.g. move, then time.sleep(...), then stop() - see the smoke test
      below), so nothing here can run "forever" with no way to interrupt it.

Small, single-purpose functions, taught in this order (matching the
notebook's planned progression):

    motors = get_motors()
    left_forward(motors)     left_backward(motors)     left_stop(motors)
    right_forward(motors)    right_backward(motors)    right_stop(motors)
    forward(motors)          backward(motors)          stop(motors)
    left(motors)             right(motors)
    set_speed(motors, left_speed_percent, right_speed_percent)
    cleanup(motors)

Run this file directly on the Pi for a standalone, SHORT and TIME-BOUNDED
smoke test (pin-level only - nothing is wired yet):
    python3 src/hardware/motor.py
"""

import sys
import time
from dataclasses import dataclass
from pathlib import Path

# Make `from config import ...` work whether this file is run directly
# (`python3 src/hardware/motor.py`) or imported as `hardware.motor` after a
# notebook has added the `src/` folder to sys.path. Either way, this puts
# the `src/` directory (this file's parent's parent) on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    MOTOR_LEFT_ENABLE_PIN,
    MOTOR_LEFT_IN1_PIN,
    MOTOR_LEFT_IN2_PIN,
    MOTOR_RIGHT_ENABLE_PIN,
    MOTOR_RIGHT_IN3_PIN,
    MOTOR_RIGHT_IN4_PIN,
)
from gpiozero import Motor, PWMOutputDevice  # noqa: E402

# Default speed (0-100) used by the movement functions below when the
# caller doesn't specify one, so left_forward()/forward()/etc. "just work"
# for teaching before set_speed() is introduced. Moderate rather than 100
# so a first real-hardware demo is calmer/more controllable.
DEFAULT_SPEED_PERCENT = 50


@dataclass
class Motors:
    """Bundles the 4 GPIO devices that make up the L298N-driven left/right motors."""

    left_motor: Motor              # direction only (IN1/IN2), pwm=False
    left_enable: PWMOutputDevice   # PWM speed control (ENA)
    right_motor: Motor             # direction only (IN3/IN4), pwm=False
    right_enable: PWMOutputDevice  # PWM speed control (ENB)


def _percent_to_ratio(speed_percent):
    """Convert a 0-100 speed value to gpiozero's 0.0-1.0 PWM value."""
    if not 0 <= speed_percent <= 100:
        raise ValueError("speed_percent must be between 0 and 100")
    return speed_percent / 100


def get_motors():
    """Create and return a Motors bundle wired to the config.py motor pins.

    Both enable/PWM pins start at 0 (motors fully disabled) so nothing can
    move as a side effect of just constructing this object.
    """
    return Motors(
        left_motor=Motor(forward=MOTOR_LEFT_IN1_PIN, backward=MOTOR_LEFT_IN2_PIN, pwm=False),
        left_enable=PWMOutputDevice(MOTOR_LEFT_ENABLE_PIN, initial_value=0.0),
        right_motor=Motor(forward=MOTOR_RIGHT_IN3_PIN, backward=MOTOR_RIGHT_IN4_PIN, pwm=False),
        right_enable=PWMOutputDevice(MOTOR_RIGHT_ENABLE_PIN, initial_value=0.0),
    )


# ---------------------------------------------------------------------------
# Per-motor primitives (taught first, independently of each other)
# ---------------------------------------------------------------------------

def left_forward(motors, speed_percent=DEFAULT_SPEED_PERCENT):
    """Drive the left motor forward at speed_percent (0-100)."""
    motors.left_enable.value = _percent_to_ratio(speed_percent)
    motors.left_motor.forward()


def left_backward(motors, speed_percent=DEFAULT_SPEED_PERCENT):
    """Drive the left motor backward at speed_percent (0-100)."""
    motors.left_enable.value = _percent_to_ratio(speed_percent)
    motors.left_motor.backward()


def left_stop(motors):
    """Stop the left motor: cut its direction signal AND zero its speed (ENA=0%)."""
    motors.left_motor.stop()
    motors.left_enable.value = 0.0


def right_forward(motors, speed_percent=DEFAULT_SPEED_PERCENT):
    """Drive the right motor forward at speed_percent (0-100)."""
    motors.right_enable.value = _percent_to_ratio(speed_percent)
    motors.right_motor.forward()


def right_backward(motors, speed_percent=DEFAULT_SPEED_PERCENT):
    """Drive the right motor backward at speed_percent (0-100)."""
    motors.right_enable.value = _percent_to_ratio(speed_percent)
    motors.right_motor.backward()


def right_stop(motors):
    """Stop the right motor: cut its direction signal AND zero its speed (ENB=0%)."""
    motors.right_motor.stop()
    motors.right_enable.value = 0.0


# ---------------------------------------------------------------------------
# Combined robot-level functions (built from the primitives above)
# ---------------------------------------------------------------------------

def forward(motors, speed_percent=DEFAULT_SPEED_PERCENT):
    """Drive the robot straight forward at speed_percent (0-100)."""
    left_forward(motors, speed_percent)
    right_forward(motors, speed_percent)


def backward(motors, speed_percent=DEFAULT_SPEED_PERCENT):
    """Drive the robot straight backward at speed_percent (0-100)."""
    left_backward(motors, speed_percent)
    right_backward(motors, speed_percent)


def left(motors, speed_percent=DEFAULT_SPEED_PERCENT):
    """Pivot-turn the robot left in place (left motor backward, right motor forward).

    This is a ROBOT-level turn (both motors), not to be confused with
    left_forward()/left_backward() which drive only the left motor.
    """
    left_backward(motors, speed_percent)
    right_forward(motors, speed_percent)


def right(motors, speed_percent=DEFAULT_SPEED_PERCENT):
    """Pivot-turn the robot right in place (left motor forward, right motor backward).

    This is a ROBOT-level turn (both motors), not to be confused with
    right_forward()/right_backward() which drive only the right motor.
    """
    left_forward(motors, speed_percent)
    right_backward(motors, speed_percent)


def stop(motors):
    """Stop both motors immediately. Always safe to call, in any state."""
    left_stop(motors)
    right_stop(motors)


def set_speed(motors, left_speed_percent, right_speed_percent):
    """Change speed only (0-100 each) via PWM on ENA/ENB, without changing direction.

    Has no visible effect on a motor that is currently stopped (no
    direction signal set) until a movement function is called again -
    speed and direction are independent, matching the real L298N hardware.
    """
    motors.left_enable.value = _percent_to_ratio(left_speed_percent)
    motors.right_enable.value = _percent_to_ratio(right_speed_percent)


def cleanup(motors):
    """Stop both motors and release all 4 GPIO pins. Call this when done."""
    stop(motors)
    motors.left_motor.close()
    motors.left_enable.close()
    motors.right_motor.close()
    motors.right_enable.close()


if __name__ == "__main__":
    print(
        "Motor smoke test: left motor ENA=GPIO{}, IN1=GPIO{}, IN2=GPIO{}; "
        "right motor ENB=GPIO{}, IN3=GPIO{}, IN4=GPIO{}".format(
            MOTOR_LEFT_ENABLE_PIN,
            MOTOR_LEFT_IN1_PIN,
            MOTOR_LEFT_IN2_PIN,
            MOTOR_RIGHT_ENABLE_PIN,
            MOTOR_RIGHT_IN3_PIN,
            MOTOR_RIGHT_IN4_PIN,
        )
    )
    print(
        "SAFETY: the L298N + motors are not physically wired yet, so this is "
        "a pin-level-only test (no real movement is possible right now). "
        "Once wired, ALWAYS lift the robot off the ground / wheels free-"
        "spinning before running this or any movement code."
    )

    motors = get_motors()
    STEP_SECONDS = 1.0

    demo_steps = [
        ("left_forward(motors)", lambda: left_forward(motors)),
        ("left_stop(motors)", lambda: left_stop(motors)),
        ("right_forward(motors)", lambda: right_forward(motors)),
        ("right_stop(motors)", lambda: right_stop(motors)),
        ("forward(motors)", lambda: forward(motors)),
        ("stop(motors)", lambda: stop(motors)),
        ("backward(motors)", lambda: backward(motors)),
        ("stop(motors)", lambda: stop(motors)),
        ("left(motors)  [pivot turn]", lambda: left(motors)),
        ("stop(motors)", lambda: stop(motors)),
        ("right(motors)  [pivot turn]", lambda: right(motors)),
        ("stop(motors)", lambda: stop(motors)),
        ("set_speed(motors, 25, 75)", lambda: set_speed(motors, 25, 75)),
        ("stop(motors)", lambda: stop(motors)),
    ]

    try:
        for label, action in demo_steps:
            print(f"Step: {label}")
            action()
            time.sleep(STEP_SECONDS)
        print("Smoke test complete.")
    finally:
        cleanup(motors)
        print("Motors stopped and all GPIO released.")
