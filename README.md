# AI Car Workshop — Raspberry Pi Robot

A hands-on, progressive training lab for building a 4-wheel Raspberry Pi
robot car: GPIO basics → PWM → sensors → motor control → autonomous
obstacle avoidance → OpenCV → color detection → an SSD object-detection
model → a browser-based web controller. Every piece of hardware code is
written, taught, and verified on real Raspberry Pi hardware — nothing here
is simulated.

Students work through `notebooks/` cell-by-cell in Jupyter, executing real
code against real GPIO pins, a real camera, and (once wired) real motors
and sensors. The notebooks teach reusable modules under `src/`, not
throwaway inline code — what you learn in a notebook is the same code the
final autonomous robot and web controller actually run.

## Quick start — install everything with one command

On the Pi:

```bash
bash scripts/install_pi_dependencies.sh
```

That single, idempotent command installs (or fixes, if already broken/
mismatched) everything this project needs: OpenCV, the picamera2/numpy ABI
fixup, onnxruntime, JupyterLab, and Flask/Werkzeug — see the script for why
each step exists, and re-run it any time, it's safe. `requirements.txt`
documents every dependency/version pin for reference, but isn't meant to
be `pip install -r`'d directly — `picamera2` is apt-only (not
pip-installable at all), and a couple of others need a specific install
order to avoid ABI conflicts, both of which the script handles and a plain
`pip install -r` would not. See "Getting started — on the Pi" below for
what to run next once dependencies are installed.

## Project layout

```
raspberry_pi_robot/
├── notebooks/
│   ├── 01_gpio_led.ipynb                       GPIO basics with a plain LED
│   ├── 02_rgb_pwm_button.ipynb                 RGB LED + PWM + push button
│   ├── 03_l298n_motor_control.ipynb            L298N motor driver control
│   ├── 04_ultrasonic_obstacle_avoidance.ipynb  HC-SR04 + autonomous avoidance
│   ├── 05_opencv_introduction.ipynb            OpenCV, camera, color detection
│   ├── 06_ssd_training.ipynb                   SSD fine-tuning — runs in Google Colab, NOT locally
│   └── 07_ssd_raspberry_pi_deployment.ipynb    Deploy the trained ONNX model on the Pi
├── src/
│   ├── config.py           Central GPIO pin map + hardware/AI-drive constants
│   ├── hardware/           One small wrapper module per piece of hardware
│   │   └── led.py, rgb_led.py, button.py, motor.py, ultrasonic.py
│   ├── vision/             Camera + computer vision
│   │   └── camera.py, color_detection.py, object_detection.py (ONNX car detection)
│   └── robot/               Behavior layers composing hardware/vision modules
│       ├── obstacle_avoidance.py   Ultrasonic-based avoid/auto-drive
│       └── ai_drive.py             Autonomous color + object + obstacle driving loop
│           (`python3 src/robot/ai_drive.py` for a live verbose smoke test,
│           or `--detect-only` to just print car-detection results)
├── models/                 car_detection.onnx goes here (trained via notebook 06)
├── web/                    Flask web control server
│   ├── app.py               Manual driving, AI-mode toggle, live status, camera stream
│   ├── detect_preview.py    Standalone browser view of the camera with car-detection
│   │                        boxes drawn live (`python3 web/detect_preview.py` →
│   │                        http://<pi-ip>:5001/) — for checking detection accuracy;
│   │                        don't run at the same time as app.py (both need the camera)
│   ├── templates/, static/  Browser UI (D-pad, speed slider, keyboard control)
├── tests/
│   └── TEST_REPORT.md      Running PASS/FAIL log for every feature, real-hardware verified
├── scripts/
│   └── install_pi_dependencies.sh   Installs JupyterLab, OpenCV, onnxruntime, Flask on the Pi
├── HARDWARE.md             Bill of materials and current wiring status
├── PINOUT.md               GPIO pin table (BCM numbering)
├── SAFETY.md               Safety rules — READ THIS before running anything motor/GPIO-related
└── requirements.txt        Python dependencies for the whole project
```

## Status

All core modules are implemented and verified on real Raspberry Pi hardware
(see `tests/TEST_REPORT.md` for the full PASS/FAIL history, including real
`raspi-gpio` electrical verification and live SIGINT/SIGTERM safety tests):

- GPIO/LED, RGB LED + PWM, push button
- L298N motor control (direction + real PWM speed control)
- HC-SR04 ultrasonic sensing + obstacle avoidance
- Camera capture + OpenCV image processing + HSV color detection
- `AIDriveController` — an autonomous ~10Hz driving loop combining
  ultrasonic safety, ONNX car detection, and color-based steering
  (red = stop, green = forward, blue/yellow = calibratable turns)
- A Flask web control server: manual driving (D-pad/keyboard/speed slider),
  an AI-mode toggle, live status display, MJPEG camera streaming, a command
  watchdog, and emergency stop

Notebooks 01-05 are built and tested end-to-end (`jupyter nbconvert
--execute`, zero errors) on the real Pi. Notebooks 06-07 (SSD training and
deployment) exist but notebook 06 must be run in **Google Colab** (see
below) — it cannot be executed locally or verified ahead of time the way
the other notebooks were.

**Physical wiring status**: only the camera is currently connected. The
LED, RGB LED, button, L298N + motors, and ultrasonic sensor are pin-mapped
and fully tested at the GPIO-electrical level (via `raspi-gpio`) but not
physically wired yet — see `HARDWARE.md`. The `car_detection.onnx` model
file has not been trained/provided yet; `src/vision/object_detection.py`
degrades gracefully (skips car detection, never crashes) until it exists.

**Before running more than one GPIO-touching program at once**, read
`SAFETY.md`'s "GPIO exclusivity" section — e.g. don't leave a notebook
kernel running while also starting `web/app.py`. This matters even more
if you've installed the auto-start service below, since then `web/app.py`
is running continuously from boot onward unless you stop it first — see
"Stopping the web service" below.

## Hardware target

Raspberry Pi 4 Model B Rev 1.5 (4GB), Debian 11 bullseye, Python 3.9.2. See
`HARDWARE.md` for the full environment and bill of materials, and
`PINOUT.md` for the GPIO pin map.

## Getting started — on the Pi

1. Install project-wide Python dependencies not already on the Pi:
   ```
   bash scripts/install_pi_dependencies.sh
   ```
   (installs JupyterLab, OpenCV, onnxruntime, and fixes a couple of known
   apt/pip package-shadowing conflicts along the way — see the script's
   comments for why each step exists.)

2. Work through `notebooks/01` to `05` in order. Each is self-contained,
   explains the hardware wiring it needs, and builds on the previous one.

3. Read `SAFETY.md` before wiring or running anything involving motors or
   the ultrasonic sensor — motor/obstacle-avoidance notebooks move real
   hardware once wired.

4. Once everything's wired and tested, `python3 web/app.py` starts the
   browser control server (`http://<pi-ip>:5000`) for a single foreground
   session. To have it start automatically on every boot instead, see the
   next section.

## Running the web server automatically on boot

`scripts/install_web_service.sh` installs a systemd service
(`ai-car-web`) that starts `web/app.py` on every boot, so the browser
controller is always available without SSHing in and starting it by hand.

```bash
bash scripts/install_web_service.sh
```

This installs/enables/starts the service in one step (safe to re-run).
It runs as the `admin` user (already in the `gpio`/`video` groups — see
`HARDWARE.md`), not root, and restarts automatically if it crashes.

Check it's working:
```bash
sudo systemctl status ai-car-web      # is it running?
sudo journalctl -u ai-car-web -f      # live logs, Ctrl+C to stop watching
```

### Stopping the web service

**Stop it before running any notebook or other script that opens the
camera or GPIO pins** — `web/app.py` and a notebook kernel can't safely
hold the same camera/GPIO handles at once (see "GPIO exclusivity" above
and `SAFETY.md`).

```bash
sudo systemctl stop ai-car-web        # stop it now (for this boot)
```

Start it again when you're done with the notebook:
```bash
sudo systemctl start ai-car-web
```

To stop it AND prevent it from starting again on the next boot:
```bash
sudo systemctl disable --now ai-car-web
```
(`bash scripts/install_web_service.sh` re-enables and starts it again
later, if you want it back.)

## Training the SSD car-detection model — on your PC, via Google Colab

`notebooks/06_ssd_training.ipynb` fine-tunes a pretrained SSD (MobileNetV3)
to detect cars and exports it to ONNX. It's designed to run in **Google
Colab** (free GPU, no local install needed) rather than on your laptop or
the Pi:

1. Open **https://colab.research.google.com**, **File → Upload notebook**,
   select `notebooks/06_ssd_training.ipynb`.
2. **Runtime → Change runtime type → GPU** (T4 is fine, free tier).
3. Run all cells top to bottom.
4. Download the resulting `car_detection.onnx` and place it at
   `models/car_detection.onnx` in this repo, then copy it to the Pi:
   ```
   scp models/car_detection.onnx admin@<pi-ip>:~/raspberry_pi_robot/models/car_detection.onnx
   ```
5. Run `notebooks/07_ssd_raspberry_pi_deployment.ipynb` on the Pi to load
   and test it against the real camera, with measured (not assumed) FPS.

See `models/README.md` for what `src/vision/object_detection.py` currently
assumes about the model's input/output format — these are best-effort
placeholders until a real trained model confirms them.
