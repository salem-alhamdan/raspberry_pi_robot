"""
HC-SR04 ultrasonic distance sensor on TRIG=ULTRASONIC_TRIG_PIN / ECHO=
ULTRASONIC_ECHO_PIN (see src/config.py). Model: ULTRASONIC_MODEL ("HC-SR04").

================================================================================
SAFETY - READ BEFORE WIRING: the HC-SR04's ECHO pin outputs 5V logic. The
Raspberry Pi's GPIO inputs are 3.3V MAX - connecting ECHO directly to GPIO21
WILL DAMAGE THE PI. A voltage divider (or level shifter) between ECHO and
GPIO21 is MANDATORY and is NOT yet wired (see SAFETY.md / HARDWARE.md /
PINOUT.md). Do not connect ECHO to the Pi without it. TRIG is 3.3V-safe and
can be wired directly from the Pi.
================================================================================

Wiring assumption: the sensor is NOT yet wired. Reading these pins from
software is safe (nothing attached), but the result is NOT simply "0" or
an exception - see the "IMPORTANT finding" note below for what it actually
does, verified directly on this Pi.

Why gpiozero.DistanceSensor: it already handles the TRIG pulse and the
ECHO pulse-width timing (and the speed-of-sound math) internally, so there
is no need to hand-roll a time.time() pulse-measurement loop.

IMPORTANT finding from checking gpiozero 1.6.2's actual source before
assuming defaults (same "verify, don't assume" discipline applied to
motor.py's Motor class):

    - `max_distance` (constructor param, meters) HARD-CLAMPS what
      `.distance` can ever report: internally, `_read()` computes
      `value = min(1.0, raw_distance / max_distance)`, and `.distance` is
      just `value * max_distance`. Anything at or beyond max_distance reads
      back as EXACTLY max_distance - not a rough cap, a real loss of
      information (a wall 2m away and a wall 10m away would both read back
      identically). gpiozero's own default is only 1 meter, too short for
      room-scale obstacle avoidance, so this module uses
      DEFAULT_MAX_DISTANCE_M = 3.0 instead of gpiozero's default - chosen
      as a reasonable room-scale bound for this project's small robot,
      documented here rather than left as an unexplained constant.

    - `partial` (constructor param, bool) matters far more than it looks.
      With gpiozero's default `partial=False`, reading `.distance` BLOCKS
      until its internal 9-sample averaging queue has filled with real echo
      data. Verified directly on this Pi: with nothing wired (no echo ever
      received), `.distance` hangs indefinitely - it does not raise, return
      None, or time out on its own. That would be a serious hidden safety
      hazard for this project: a blocked read inside a driving loop (see
      src/robot/obstacle_avoidance.py) would freeze the whole control loop
      with the motors potentially still running, and nothing left able to
      call stop(). So this module always constructs the sensor with
      `partial=True`, which returns immediately (falling back to a default
      of 0.0m - "assume something is very close" - until real samples
      arrive). Verified on this Pi: with partial=True and nothing wired,
      `.distance` returns 0.0 immediately, every time, with a background
      "no echo received" warning logged instead of a hang. 0.0 ("too close,
      stop") is also the fail-safe direction if the sensor ever glitches or
      disconnects mid-drive - far better than silently reporting "clear"
      and continuing to drive forward blind.

Small, single-purpose functions:

    sensor = get_ultrasonic_sensor()
    distance_m = read_distance(sensor)   # float, meters (gpiozero's native unit)
    cleanup(sensor)

Run this file directly on the Pi for a standalone, bounded smoke test:
    python3 src/hardware/ultrasonic.py
"""

import sys
import time
from pathlib import Path

# Make `from config import ...` work whether this file is run directly
# (`python3 src/hardware/ultrasonic.py`) or imported as `hardware.ultrasonic`
# after a notebook has added the `src/` folder to sys.path. Either way, this
# puts the `src/` directory (this file's parent's parent) on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    ULTRASONIC_TRIG_PIN,
    ULTRASONIC_ECHO_PIN,
    ULTRASONIC_MODEL,
)
from gpiozero import DistanceSensor  # noqa: E402

# See the "IMPORTANT finding" note above for why these override gpiozero's
# own defaults (max_distance=1, partial=False).
DEFAULT_MAX_DISTANCE_M = 3.0


def get_ultrasonic_sensor(trigger_pin=ULTRASONIC_TRIG_PIN, echo_pin=ULTRASONIC_ECHO_PIN,
                           max_distance_m=DEFAULT_MAX_DISTANCE_M):
    """Create and return a DistanceSensor wired to TRIG/ECHO from config.py.

    partial=True so reads never block waiting for real echo data - see the
    module docstring's "IMPORTANT finding" note for why that matters even
    more than usual for this sensor.
    """
    return DistanceSensor(
        trigger=trigger_pin,
        echo=echo_pin,
        max_distance=max_distance_m,
        partial=True,
    )


def read_distance(sensor):
    """Return the current distance reading in meters (float). Never blocks.

    With nothing in range - including a completely unwired sensor - this
    reads back 0.0, NOT the "true" open-space distance. See the module
    docstring for why 0.0 ("something is very close") is the deliberate,
    fail-safe default rather than gpiozero's alternative of blocking
    forever waiting for a real reading.
    """
    return sensor.distance


def cleanup(sensor):
    """Release the GPIO pins. Call this when you are done with the sensor."""
    sensor.close()


if __name__ == "__main__":
    print(
        f"Ultrasonic smoke test: {ULTRASONIC_MODEL} on "
        f"TRIG=GPIO{ULTRASONIC_TRIG_PIN}, ECHO=GPIO{ULTRASONIC_ECHO_PIN}"
    )
    print(
        "SAFETY: ECHO outputs 5V and MUST go through a voltage divider "
        "before reaching GPIO21 - not yet wired. Never connect ECHO "
        "directly to the Pi. TRIG is 3.3V-safe to wire directly."
    )
    print(
        "Nothing is physically wired yet, so every reading below is "
        "expected to print 'Distance = 0.00 m' (the sensor's fail-safe "
        "'no echo yet' value), NOT a real measurement - see the module "
        "docstring for why."
    )

    sensor = get_ultrasonic_sensor()
    SAMPLE_COUNT = 5
    SAMPLE_INTERVAL_S = 1.0

    try:
        for i in range(SAMPLE_COUNT):
            distance_m = read_distance(sensor)
            print(f"Sample {i + 1}/{SAMPLE_COUNT}: Distance = {distance_m:.2f} m")
            time.sleep(SAMPLE_INTERVAL_S)
        print("Smoke test complete.")
    finally:
        cleanup(sensor)
        print("Ultrasonic sensor GPIO released.")
