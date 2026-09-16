"""
LED control for the single status LED on GPIO17 (see src/config.py).

Small, single-purpose functions so each one can be taught and used in its
own notebook cell:

    led = get_led()
    led_on(led)
    led_off(led)
    toggle_led(led)
    cleanup(led)

Run this file directly on the Pi for a standalone smoke test:
    python3 src/hardware/led.py
"""

import sys
import time
from pathlib import Path

# Make `from config import LED_PIN` work whether this file is run directly
# (`python3 src/hardware/led.py`) or imported as `hardware.led` after a
# notebook has added the `src/` folder to sys.path. Either way, this puts
# the `src/` directory (this file's parent's parent) on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import LED_PIN  # noqa: E402
from gpiozero import LED  # noqa: E402


def get_led(pin=LED_PIN):
    """Create and return an LED object on the given GPIO pin (default: LED_PIN)."""
    return LED(pin)


def led_on(led):
    """Turn the LED on."""
    led.on()


def led_off(led):
    """Turn the LED off."""
    led.off()


def toggle_led(led):
    """Flip the LED between on and off."""
    led.toggle()


def cleanup(led):
    """Release the GPIO pin. Call this when you are done with the LED."""
    led.close()


if __name__ == "__main__":
    print(f"LED smoke test: using GPIO{LED_PIN}")
    led = get_led()

    try:
        for i in range(5):
            print(f"Blink {i + 1}/5: ON")
            led_on(led)
            time.sleep(0.5)

            print(f"Blink {i + 1}/5: OFF")
            led_off(led)
            time.sleep(0.5)

        print("Smoke test complete.")
    finally:
        cleanup(led)
        print("LED GPIO released.")
