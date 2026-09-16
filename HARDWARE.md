# Hardware

## Bill of materials

| Component | Detail | Status |
|---|---|---|
| Raspberry Pi 4 Model B Rev 1.5 | 4GB RAM | In use |
| Chassis | 4-wheel, 2 DC motors (left/right, each driving 2 wheels) | Not yet wired |
| Motor driver | L298N | Not yet wired |
| RGB LED module | 4-pin, common cathode | `src/hardware/rgb_led.py` implemented. Not yet wired |
| Plain LED | Single LED, for Notebook 1 GPIO basics | Not yet wired |
| Push button | Simple digital input | `src/hardware/button.py` implemented. Not yet wired |
| Ultrasonic sensor | HC-SR04 | Not yet wired |
| Camera | Pi Camera Module v2 (imx219 sensor), CSI | **Connected and working** |
| Pi power supply | Separate from motor power | In use |
| Motor power supply | Separate from Pi power, grounds tied together | Voltage TBD |

## Current state (as of this phase)

- Only the **camera** is physically connected, and it is confirmed working
  via picamera2/libcamera.
- The plain LED, RGB LED, push button, L298N + motors, and ultrasonic
  sensor are **not yet wired** to the Pi. Their GPIO pins are assigned and
  documented in `PINOUT.md` / `src/config.py`, and code can be written
  against those pins now, but no physical behavior beyond raw GPIO
  pin-level logic-level toggling can be verified until wiring happens.
- The exact motor battery voltage is still to be determined by the user.

## Software environment (Raspberry Pi)

- OS: Debian 11 bullseye (Pi OS), kernel 6.1.21-v8+ aarch64
- Python: 3.9.2, system-wide (no virtual environment)
- Already installed: gpiozero 1.6.2, RPi.GPIO 0.7.0, pigpio 1.78,
  picamera2 0.3.12, Flask 1.1.2, numpy 1.19.5
- Not yet installed: JupyterLab, OpenCV (see `scripts/install_pi_dependencies.sh`)
- I2C and SPI are disabled in `/boot/config.txt` and are being left disabled,
  since this project's confirmed hardware (L298N over plain GPIO, RGB LED
  over plain GPIO, HC-SR04 over plain GPIO) does not need either bus.
- The `admin` user is in the `gpio`, `i2c`, `spi`, `video`, and `dialout`
  groups, so no `sudo` is required for GPIO or camera access in this
  project's runtime code.

## RGB LED and button modules (Phase 6)

- `src/hardware/rgb_led.py` wraps `gpiozero.RGBLED`. `active_high` is derived
  from `RGB_COMMON_CATHODE` in `config.py` (`True` -> `active_high=True`),
  so the common-cathode wiring lights each channel by driving it HIGH.
  Public functions (`set_rgb`, `set_red`, ...) take 0-255 ints per channel
  and convert to gpiozero's native 0.0-1.0 internally. Verified on the real
  Pi via `raspi-gpio`: `active_high=True`, pin fsel correctly switches to
  OUTPUT while a color is held and reverts to INPUT after `cleanup()`.
- `src/hardware/button.py` wraps `gpiozero.Button` on GPIO27 with the
  gpiozero default `pull_up=True` (internal pull-up), matching a button
  wired between GPIO27 and GND with no external resistor. Verified on the
  real Pi via `raspi-gpio`: pull state shows `pull=UP` while the module
  holds the pin and reverts to `pull=NONE` after `cleanup()`; `is_pressed`
  correctly reads `False` while unwired (pulled HIGH).

## Access

- SSH: `ssh admin@192.168.0.130` (key-based auth already configured)
