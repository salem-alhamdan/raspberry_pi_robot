#!/usr/bin/env bash
#
# install_web_service.sh
#
# Installs a systemd service ("ai-car-web") that runs web/app.py
# automatically on boot, so the browser control server is always up
# without needing to SSH in and start it by hand every time.
#
# IMPORTANT - run this ON THE PI ITSELF (e.g. `ssh admin@<pi-ip>`, copy
# this repo over, then `bash scripts/install_web_service.sh`). It uses
# sudo to write a unit file into /etc/systemd/system/ and enable it.
#
# ---------------------------------------------------------------------
# GPIO/camera exclusivity - READ THIS BEFORE ENABLING
# ---------------------------------------------------------------------
# Once enabled, this service holds the camera (and, once motors/sensors
# are wired, their GPIO handles too) from boot onward, continuously - see
# web/app.py's module docstring and SAFETY.md's "GPIO exclusivity"
# section for why a second process (e.g. a notebook kernel) touching the
# same camera/pins at the same time is unsafe. That means: **stop this
# service before running any notebook or other script that opens the
# camera or GPIO pins**, then start it again afterward. See README.md's
# "Stopping the web service" section for the exact commands.
# ---------------------------------------------------------------------
#
# The `admin` user is already in the gpio/video groups (see HARDWARE.md),
# so this service runs as that normal user, NOT root - no sudo is needed
# for GPIO/camera access, only for installing the systemd unit itself.
#
# Idempotent: safe to re-run (overwrites the unit file and re-enables).

set -euo pipefail

SERVICE_NAME="ai-car-web"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="$(whoami)"
PYTHON_BIN="$(command -v python3)"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "=== AI Car workshop: installing '$SERVICE_NAME' systemd service ==="
echo "Project dir: $PROJECT_DIR"
echo "Running as:  $RUN_USER"
echo "Python:      $PYTHON_BIN"

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=AI Car workshop - Flask web control server
After=network.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_BIN $PROJECT_DIR/web/app.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo
echo "=== Done ==="
echo "'$SERVICE_NAME' is enabled (starts automatically on every boot) and running now."
echo "Browse to http://<pi-ip>:5000/ to check it."
echo
echo "Useful commands:"
echo "  sudo systemctl status $SERVICE_NAME     # is it running?"
echo "  sudo journalctl -u $SERVICE_NAME -f     # live logs"
echo "  sudo systemctl stop $SERVICE_NAME       # stop it (needed before a notebook/GPIO script)"
echo "  sudo systemctl start $SERVICE_NAME      # start it again"
echo "  sudo systemctl disable $SERVICE_NAME    # stop auto-starting it on boot"
