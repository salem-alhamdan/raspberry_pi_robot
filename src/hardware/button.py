"""
Push button input on GPIO27 (see src/config.py).

Wiring assumption (physical wiring not done yet - see HARDWARE.md): the
button is a simple 2-leg push button wired between GPIO27 and GND, with NO
external resistor. This relies on the Pi's internal pull-up resistor, which
gpiozero.Button enables by default (pull_up=True). With that wiring:
    - Button NOT pressed -> internal pull-up holds the pin HIGH -> is_pressed
      is False.
    - Button pressed -> pin is pulled down to GND -> is_pressed is True.
This is the standard, simplest way to wire a push button to a Pi GPIO and
is why this module does not change the pull_up default.

This module is a thin wrapper - once you have a Button object, gpiozero's
own `.is_pressed` property (True/False) IS the teaching example, so it is
exposed directly rather than hidden behind another function:

    button = get_button()
    if button.is_pressed:
        ...

gpiozero.Button also has `.wait_for_press()` / `.wait_for_release()` and
`.when_pressed` / `.when_released` callbacks, used in the smoke test below.

Run this file directly on the Pi for a standalone, TIME-BOUNDED demo (it
exits on its own after a timeout since nothing is physically wired yet and
no one can press an unwired button):
    python3 src/hardware/button.py
"""

import sys
import time
from pathlib import Path

# Make `from config import BUTTON_PIN` work whether this file is run
# directly (`python3 src/hardware/button.py`) or imported as
# `hardware.button` after a notebook has added the `src/` folder to
# sys.path. Either way, this puts the `src/` directory (this file's
# parent's parent) on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import BUTTON_PIN  # noqa: E402
from gpiozero import Button  # noqa: E402


def get_button(pin=BUTTON_PIN):
    """Create and return a Button object on the given GPIO pin (default: BUTTON_PIN).

    Uses gpiozero's default pull_up=True (internal pull-up enabled), which
    matches the "button wired between the pin and GND" assumption described
    in this module's docstring.
    """
    return Button(pin)


def cleanup(button):
    """Release the GPIO pin. Call this when you are done with the button."""
    button.close()


if __name__ == "__main__":
    DEMO_SECONDS = 20

    print(f"Button smoke test: using GPIO{BUTTON_PIN}, pull_up=True")
    print(
        "Nothing is physically wired yet, so this demo will just poll "
        f"is_pressed for {DEMO_SECONDS}s and then exit on its own - it will "
        "not block forever waiting for a press."
    )

    button = get_button()
    last_state = None

    try:
        start = time.monotonic()
        while time.monotonic() - start < DEMO_SECONDS:
            state = button.is_pressed
            if state != last_state:
                print("Button PRESSED" if state else "Button released")
                last_state = state
            time.sleep(0.05)

        print(f"Demo complete after {DEMO_SECONDS}s (no press required).")
    finally:
        cleanup(button)
        print("Button GPIO released.")
