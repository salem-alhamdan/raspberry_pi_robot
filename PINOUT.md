# Pinout

All GPIO numbers are **BCM numbering** (not physical board pin numbers). These
are also defined as named constants in `src/config.py` - import from there
instead of copying numbers out of this table.

| Function | BCM GPIO | Notes |
|---|---|---|
| Plain LED (Notebook 1) | 17 | Not yet wired |
| RGB Red | 22 | Common cathode module; drive HIGH (PWM) to light. `src/hardware/rgb_led.py` (`active_high=True`, verified via `raspi-gpio`). Not yet wired |
| RGB Green | 23 | Common cathode module; drive HIGH (PWM) to light. `src/hardware/rgb_led.py` (`active_high=True`, verified via `raspi-gpio`). Not yet wired |
| RGB Blue | 24 | Common cathode module; drive HIGH (PWM) to light. `src/hardware/rgb_led.py` (`active_high=True`, verified via `raspi-gpio`). Not yet wired |
| Push Button | 27 | Digital input, uses internal pull-up (`pull_up=True`, gpiozero default). `src/hardware/button.py`. Wire between GPIO27 and GND, no external resistor. Not yet wired |
| L298N ENA (left motor speed) | 12 | Hardware PWM0. Not yet wired |
| L298N IN1 (left motor direction) | 5 | Not yet wired |
| L298N IN2 (left motor direction) | 6 | Not yet wired |
| L298N ENB (right motor speed) | 13 | Hardware PWM1. Not yet wired |
| L298N IN3 (right motor direction) | 19 | Not yet wired |
| L298N IN4 (right motor direction) | 26 | Not yet wired |
| Ultrasonic TRIG | 20 | HC-SR04, 3.3V-safe to drive directly. Not yet wired |
| Ultrasonic ECHO | 21 | HC-SR04, outputs 5V - **requires a voltage divider** before this GPIO. Not yet wired |
| Camera | CSI port (not GPIO) | Pi Camera Module v2 (imx219). **Connected and working** via picamera2/libcamera |

## Status legend

- **Connected and working**: camera only, as of this phase.
- **Not yet wired**: pin is assigned/reserved in software but no physical
  component is attached. Toggling these pins from code is safe (nothing is
  connected to be damaged), but has no observable real-world effect yet.

## Voltage notes

- Pi GPIO pins are **3.3V logic only** - never connect a 5V signal directly.
- HC-SR04 ECHO pin outputs 5V and must go through a voltage divider (e.g. a
  simple two-resistor divider, ~1kΩ/2kΩ) to bring it down to a safe ~3.3V
  before reaching GPIO 21. TRIG is fine to drive directly from the Pi's 3.3V
  GPIO output.
- The RGB LED is a **common-cathode** module: GND is the shared pin, and each
  color channel is lit by driving its pin HIGH (no logic inversion needed,
  unlike a common-anode module).
- Motors (via L298N) and the Pi are on **separate power supplies**; grounds
  are tied together. Exact motor battery voltage is still TBD.
