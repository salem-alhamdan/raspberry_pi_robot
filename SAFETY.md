# Safety Rules

These are the safety rules established so far for this project. This list
reflects decisions already made - it will grow as later phases (motors,
ultrasonic, etc.) are actually implemented and wired.

## Motors

- **Always lift the robot chassis off the ground/table before running any
  motor test**, so the wheels can spin freely without the car driving off
  and falling, hitting something, or pulling on its wiring/power supplies.
- Every motor-control code path must provide a **`stop()`** that sets both
  motors' enable/direction pins to a stopped state, and it must be callable
  reliably (e.g. on program exit, on error, on keyboard interrupt) - a
  motor should never be left running because a script exited unexpectedly.
- The Pi and the motors/L298N run on **separate power supplies**. Grounds
  are tied together, but never assume the Pi's 5V rail can or should power
  the motors.

## Ultrasonic sensor (HC-SR04)

- The ECHO pin outputs 5V, but Pi GPIO inputs are 3.3V-only. **ECHO must go
  through a voltage divider before connecting to the Pi.** Never wire ECHO
  directly to a GPIO pin - it can damage the Pi's input.
- TRIG is 3.3V-safe and can be driven directly from the Pi.

## Camera / motor independence

- Camera control (picamera2/libcamera) and motor control are independent
  subsystems and must not block each other - e.g. a camera capture or
  streaming loop should not prevent a motor `stop()` call from executing
  promptly, and vice versa.

## GPIO exclusivity — only run ONE GPIO-touching program at a time

- QA confirmed (see `tests/TEST_REPORT.md`) that gpiozero's default pin
  factory on this Pi (`RPiGPIOFactory`) does **not** enforce cross-process
  exclusivity on GPIO pins - unlike the camera (picamera2/libcamera), which
  correctly refuses a second concurrent open with a real "device busy"
  error. Two separate Python processes (e.g. a Jupyter notebook kernel left
  running from an earlier lesson, and `web/app.py` started afterward) can
  each successfully construct their own motor/LED/sensor handles on the
  *same* GPIO pins with **no error from either process** - they will then
  silently fight over the same physical pins, and one process closing its
  handle can silently release a pin out from under the other's still-running
  code.
- **Rule: never run two GPIO-touching programs at the same time.** Before
  starting `web/app.py` or `src/robot/ai_drive.py`, shut down any running
  notebook kernel (Jupyter's "Kernel -> Shut Down") and any other
  `python3 src/...` process that opened motor/LED/button/ultrasonic pins.
  Before opening a new notebook for hands-on GPIO work, stop the web server
  (Ctrl+C, or `systemctl stop` if it's been set up as a service) and any
  standalone script.
- This is a known, common limitation of `gpiozero`'s legacy RPi.GPIO-based
  pin factory, not a bug specific to this project - it was a deliberate
  choice to document rather than migrate every already-tested hardware
  module to a different GPIO backend this late in the project (which would
  require re-running the full real-hardware test suite). See
  `tests/TEST_REPORT.md`'s "Web control server" section for the full
  investigation.

## General

- No component described in this document as "not yet wired" should be
  assumed to be physically connected. Code can and should be written and
  pin-level-tested (toggling GPIO logic levels) ahead of wiring, but real
  hardware behavior is only confirmed once QA verifies it on the actual
  wired Pi.
- Avoid requiring `sudo` in any runtime code path. The project's confirmed
  hardware (plain GPIO for LEDs/button/motors/ultrasonic) does not need
  root access given the user's group memberships (`gpio`, `i2c`, `spi`,
  `video`, `dialout`).
