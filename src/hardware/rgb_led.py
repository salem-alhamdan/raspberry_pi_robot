"""
RGB LED control for the 4-pin common-cathode RGB LED module on
GPIO22 (red) / GPIO23 (green) / GPIO24 (blue) (see src/config.py).

Wraps gpiozero.RGBLED, which is gpiozero's built-in class for exactly this
kind of 3-channel (+ common) RGB LED - it already does per-channel PWM
brightness control and handles the active_high flag for us, so there is no
need to manage three separate PWMLED objects by hand.

Color values: this module's public functions (set_rgb, set_red, ...) take
0-255 ints per channel, like the color values beginners already know from
Arduino tutorials / CSS / paint programs. gpiozero.RGBLED itself wants
0.0-1.0 floats per channel, so set_rgb() divides by 255 internally before
handing the values to gpiozero. If you ever call the underlying gpiozero
RGBLED object directly, remember IT wants 0.0-1.0, not 0-255.

Common cathode vs common anode ("active_high"):
    - Common CATHODE (this module, RGB_COMMON_CATHODE=True in config.py):
      the shared pin is GND, and each color channel lights up when its GPIO
      pin is driven HIGH. That is gpiozero's normal/default behavior, so
      active_high=True.
    - Common ANODE modules are wired the opposite way: the shared pin is
      3.3V, and each channel lights up when its GPIO pin is driven LOW
      (sunk to ground). That would need active_high=False so gpiozero
      inverts its PWM output.
    This module derives active_high directly from RGB_COMMON_CATHODE in
    config.py rather than hard-coding it, so changing that one config flag
    is enough to support a common-anode module too.

Small, single-purpose functions so each one can be taught and used in its
own notebook cell:

    rgb = get_rgb_led()
    set_rgb(rgb, 255, 0, 0)   # custom color, 0-255 per channel
    set_red(rgb)
    set_green(rgb)
    set_blue(rgb)
    set_yellow(rgb)
    set_cyan(rgb)
    set_magenta(rgb)
    set_white(rgb)
    set_off(rgb)
    cleanup(rgb)

Run this file directly on the Pi for a standalone smoke test:
    python3 src/hardware/rgb_led.py
"""

import sys
import time
from pathlib import Path

# Make `from config import ...` work whether this file is run directly
# (`python3 src/hardware/rgb_led.py`) or imported as `hardware.rgb_led`
# after a notebook has added the `src/` folder to sys.path. Either way,
# this puts the `src/` directory (this file's parent's parent) on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    RGB_RED_PIN,
    RGB_GREEN_PIN,
    RGB_BLUE_PIN,
    RGB_COMMON_CATHODE,
)
from gpiozero import RGBLED  # noqa: E402


def get_rgb_led(red_pin=RGB_RED_PIN, green_pin=RGB_GREEN_PIN, blue_pin=RGB_BLUE_PIN):
    """Create and return an RGBLED object on the given GPIO pins (default: config pins)."""
    # active_high=True for common cathode, False for common anode - see the
    # module docstring for why.
    return RGBLED(
        red=red_pin,
        green=green_pin,
        blue=blue_pin,
        active_high=RGB_COMMON_CATHODE,
    )


def set_rgb(rgb, r, g, b):
    """Set the LED color. r, g, b are each 0-255 (like Arduino/CSS color values)."""
    rgb.color = (r / 255, g / 255, b / 255)


def set_red(rgb):
    """Set the LED to solid red."""
    set_rgb(rgb, 255, 0, 0)


def set_green(rgb):
    """Set the LED to solid green."""
    set_rgb(rgb, 0, 255, 0)


def set_blue(rgb):
    """Set the LED to solid blue."""
    set_rgb(rgb, 0, 0, 255)


def set_yellow(rgb):
    """Set the LED to yellow (red + green)."""
    set_rgb(rgb, 255, 255, 0)


def set_cyan(rgb):
    """Set the LED to cyan (green + blue)."""
    set_rgb(rgb, 0, 255, 255)


def set_magenta(rgb):
    """Set the LED to magenta (red + blue)."""
    set_rgb(rgb, 255, 0, 255)


def set_white(rgb):
    """Set the LED to white (red + green + blue)."""
    set_rgb(rgb, 255, 255, 255)


def set_off(rgb):
    """Turn the LED off."""
    set_rgb(rgb, 0, 0, 0)


def cleanup(rgb):
    """Release the GPIO pins. Call this when you are done with the RGB LED."""
    rgb.close()


if __name__ == "__main__":
    print(
        f"RGB LED smoke test: using GPIO{RGB_RED_PIN} (red), "
        f"GPIO{RGB_GREEN_PIN} (green), GPIO{RGB_BLUE_PIN} (blue), "
        f"common_cathode={RGB_COMMON_CATHODE}"
    )
    rgb = get_rgb_led()

    named_colors = [
        ("RED", set_red),
        ("GREEN", set_green),
        ("BLUE", set_blue),
        ("YELLOW", set_yellow),
        ("CYAN", set_cyan),
        ("MAGENTA", set_magenta),
        ("WHITE", set_white),
        ("OFF", set_off),
    ]

    try:
        for name, set_fn in named_colors:
            print(f"Setting color: {name}")
            set_fn(rgb)
            time.sleep(0.5)

        print("Smoke test complete.")
    finally:
        cleanup(rgb)
        print("RGB LED GPIO released.")
