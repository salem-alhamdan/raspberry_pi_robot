#!/usr/bin/env bash
#
# install_pi_dependencies.sh
#
# Installs JupyterLab and OpenCV on the Raspberry Pi for this project.
#
# IMPORTANT: run this ON THE PI ITSELF (e.g. `ssh admin@192.168.0.130`, copy
# this script over, then `bash install_pi_dependencies.sh`). It is not meant
# to be invoked remotely by an agent over a single SSH command, and it is not
# run automatically by anything in this repo.
#
# Target: Raspberry Pi 4B (4GB), Debian 11 bullseye (Pi OS), Python 3.9.2.
#
# Design notes / why these install methods:
#   - OpenCV: we prefer `apt install python3-opencv` over pip-compiling
#     opencv-python from source. Building OpenCV from source on a 4GB Pi 4
#     is slow (can take well over an hour) and fragile (easy to run out of
#     memory without extra swap). Debian bullseye's apt repo ships a
#     pre-built OpenCV 4.x package for Python 3.9 that "just works" and is
#     good enough for this project's OpenCV + SSD object-detection phases.
#     If that apt version ever proves too old for a later phase, the
#     commented pip fallback below (opencv-python-headless, which has
#     pre-built aarch64 wheels available via piwheels on Pi OS) is the
#     documented alternative - the script will offer it automatically if
#     the apt package is missing or fails to import.
#   - picamera2/numpy ABI fixup (after the OpenCV step, regardless of which
#     path installed it): `pip3 install --user opencv-python-headless` pulls
#     in a modern numpy (2.x) into --user site-packages, which Python's
#     import resolution prefers over the Pi OS system apt numpy (1.19.5).
#     `python3-simplejpeg` (an apt-installed compiled dependency of
#     picamera2's JPEG encoder) is a C-extension built against the OLD
#     system numpy's ABI, so once the newer --user numpy shadows it,
#     `import picamera2` starts raising `ValueError: numpy.dtype size
#     changed, may indicate binary incompatibility`. Reproduced and fixed
#     live on this Pi: `pip3 install --user --force-reinstall
#     --no-cache-dir simplejpeg` pulls a prebuilt aarch64 wheel from
#     piwheels that is rebuilt against whatever numpy is actually active,
#     which resolves it. DO NOT remove this step just because
#     `import picamera2` currently works on a given Pi - it only works
#     because this fixup already ran; removing it re-introduces the crash
#     the next time opencv-python-headless (re)installs a newer numpy.
#   - onnxruntime (for the car object-detection phase, src/vision/object_detection.py):
#     verified live on this exact Pi (aarch64, Debian 11 bullseye, Python 3.9.2)
#     that `pip3 install --user onnxruntime` installs cleanly from a prebuilt
#     aarch64 wheel (onnxruntime 1.19.2 at verification time) with no compile
#     step, and that it imports and reports CPUExecutionProvider available.
#     Not all onnxruntime versions ship aarch64/py3.9 wheels, so this is
#     confirmed rather than assumed - if a future onnxruntime release drops
#     that combination, pip will simply fail to find a wheel and this step's
#     guard below reports it instead of aborting the script.
#   - JupyterLab: not available as a reasonably current apt package on
#     bullseye, so it is installed via pip with --user (no sudo needed,
#     keeps it out of system site-packages). Pinned alongside tornado<6.5:
#     tornado>=6.5 has a known regression with jupyter_server 2.18.2 that
#     breaks static JS/CSS serving and renders the JupyterLab UI completely
#     blank - confirmed and fixed live on this Pi (see the JupyterLab
#     section below for the full explanation).
#   - Flask (web/app.py control server): VERIFIED LIVE ON THIS PI that the
#     apt-installed Flask 1.1.2 (from requirements.txt's "[on Pi]" baseline)
#     is CURRENTLY BROKEN, not just old: `import flask` raises
#     `ImportError: cannot import name 'escape' from 'jinja2'`. Root cause,
#     same shape as the numpy/simplejpeg ABI issue above: some earlier
#     --user pip install (most likely a JupyterLab/nbconvert dependency)
#     pulled in Jinja2 3.1.6 + MarkupSafe 3.0.3 into --user site-packages,
#     which Python's import resolution prefers over the apt python3-jinja2
#     2.11.3 that Flask 1.1.2 actually needs (Flask 1.1.2 does
#     `from jinja2 import escape`, an API Jinja2 3.x removed). Downgrading
#     Jinja2 back to 2.x to match Flask 1.1.2 was rejected as the fix,
#     since JupyterLab/nbconvert (already installed/working, see above)
#     wants Jinja2>=3. Instead, verified live on this Pi: `pip3 install
#     --user "flask~=2.2.5" "werkzeug~=2.2.3"` gives a Flask version that
#     wants Jinja2>=3 (already satisfied) and actually works - confirmed by
#     round-tripping a real request through app.test_client(). NOTE:
#     `pip3 install --user flask~=2.2.5` ALONE is not enough - pip resolves
#     an unpinned Werkzeug to the newest 3.x, which Flask 2.2.5 cannot use
#     (`AttributeError: module 'werkzeug' has no attribute '__version__'`,
#     confirmed live) - the werkzeug~=2.2.3 pin in the SAME command is
#     required, same "pin it in the same install command" lesson as
#     tornado above. Functionally, Flask 1.1.2 would very likely have been
#     "new enough" for this project's simple control server (basic routing,
#     jsonify, and an MJPEG multipart streaming Response all exist in
#     1.1.2) - this upgrade is driven by the current environment being
#     broken, not by a feature requirement.
#
# This script is idempotent: it checks what is already installed/importable
# before doing anything, so it is safe to re-run.

set -euo pipefail

echo "=== AI Car workshop: Pi dependency installer ==="

# ---------------------------------------------------------------------------
# 1. OpenCV (prefer apt, fall back to pip if needed)
# ---------------------------------------------------------------------------
echo
echo "--- OpenCV ---"
if python3 -c "import cv2; print('cv2', cv2.__version__)" 2>/dev/null; then
    echo "OpenCV already importable, skipping install."
else
    echo "OpenCV not found. Installing python3-opencv via apt (requires sudo password)..."
    # Guard every apt-get call with `|| echo ...` so a failure here (e.g. a
    # transient Debian mirror/dependency issue) does NOT abort the whole
    # script under `set -e`. The import check right below is what actually
    # decides whether to fall back to pip, and the rest of the script
    # (JupyterLab included) must still run even if apt fails outright.
    sudo apt-get update || echo "WARNING: apt-get update failed, continuing anyway..."
    sudo apt-get install -y python3-opencv || echo "WARNING: apt-get install python3-opencv failed, will try pip fallback..."

    if python3 -c "import cv2; print('cv2', cv2.__version__)" 2>/dev/null; then
        echo "OpenCV installed successfully via apt."
    else
        echo "apt package did not provide a working cv2 import (or apt-get itself failed above)."
        echo "Falling back to pip: pip3 install --user opencv-python-headless"
        if pip3 install --user opencv-python-headless; then
            python3 -c "import cv2; print('cv2', cv2.__version__)" \
                || echo "WARNING: cv2 still not importable after pip fallback - install OpenCV manually later."
        else
            echo "WARNING: pip fallback also failed - OpenCV is not installed. Install manually later."
        fi
    fi
fi

# ---------------------------------------------------------------------------
# 2. picamera2/numpy ABI fixup (see the design-notes comment above for the
#    full root cause). Runs regardless of which OpenCV path was taken above,
#    since either an apt OR a pip numpy upgrade elsewhere could shadow the
#    system numpy that python3-simplejpeg was compiled against. Idempotent:
#    only touches anything if `import picamera2` is currently broken.
# ---------------------------------------------------------------------------
echo
echo "--- picamera2/numpy ABI check ---"
if python3 -c "import picamera2" 2>/dev/null; then
    echo "picamera2 already importable, skipping simplejpeg fixup."
else
    echo "picamera2 import failed - likely the numpy/simplejpeg ABI mismatch"
    echo "described above. Reinstalling simplejpeg against the active numpy..."
    pip3 install --user --force-reinstall --no-cache-dir simplejpeg \
        || echo "WARNING: simplejpeg reinstall failed - picamera2 may remain broken, fix manually later."

    if python3 -c "import picamera2" 2>/dev/null; then
        echo "picamera2 now imports successfully after simplejpeg fixup."
    else
        echo "WARNING: picamera2 still fails to import after the simplejpeg fixup."
        echo "Investigate manually (check 'python3 -c \"import picamera2\"' for the exact error)."
    fi
fi

# ---------------------------------------------------------------------------
# 3. onnxruntime (pip, --user, no sudo) - for car object detection
# ---------------------------------------------------------------------------
echo
echo "--- onnxruntime ---"
if python3 -c "import onnxruntime; print('onnxruntime', onnxruntime.__version__)" 2>/dev/null; then
    echo "onnxruntime already importable, skipping install."
else
    echo "Installing onnxruntime via pip (--user, no sudo required)..."
    # See the design-notes comment above: confirmed on this Pi to install
    # from a prebuilt aarch64 wheel, no compilation needed.
    pip3 install --user onnxruntime \
        || echo "WARNING: onnxruntime pip install failed - install manually later (pip3 install --user onnxruntime). src/vision/object_detection.py degrades gracefully without it (car detection is skipped, not required for the rest of the project)."

    if python3 -c "import onnxruntime" 2>/dev/null; then
        echo "onnxruntime installed successfully."
    else
        echo "WARNING: onnxruntime still not importable after install - car object detection will be skipped until this is resolved."
    fi
fi

# ---------------------------------------------------------------------------
# 4. JupyterLab (pip, --user, no sudo)
# ---------------------------------------------------------------------------
echo
echo "--- JupyterLab ---"
if command -v jupyter-lab >/dev/null 2>&1 || python3 -c "import jupyterlab" 2>/dev/null; then
    echo "JupyterLab already installed, skipping install."
else
    echo "Installing JupyterLab via pip (--user, no sudo required)..."
    # Pin tornado<6.5 in the SAME install command as jupyterlab: tornado
    # 6.5+ has a known regression with jupyter_server 2.18.2
    # (AttributeError: 'FileFindHandler' object has no attribute
    # 'allowed_symlink_directory') that 500s every static JS/CSS asset and
    # renders the whole JupyterLab UI blank. Reproduced and fixed live on
    # this Pi (pip3 install --user --upgrade "tornado<6.5", landed on
    # 6.4.2). Pinning it here, in the same command, stops a fresh install
    # from letting pip silently re-resolve the broken tornado version.
    pip3 install --user "jupyterlab" "tornado<6.5" \
        || echo "WARNING: JupyterLab/tornado pip install failed - install manually later (pip3 install --user \"jupyterlab\" \"tornado<6.5\")."
fi

# ---------------------------------------------------------------------------
# 5. Flask/Jinja2/Werkzeug fixup (pip, --user, no sudo) - see the design-notes
#    comment above for the full root cause. The check below actually
#    exercises Flask (build an app, route a request through test_client())
#    rather than just `import flask`, because the broken states observed on
#    this Pi (missing jinja2.escape, and separately werkzeug.__version__
#    missing after installing an unpinned Werkzeug) can both leave a bare
#    `import flask` succeeding while Flask is still unusable.
# ---------------------------------------------------------------------------
echo
echo "--- Flask ---"
FLASK_SELF_TEST='
from flask import Flask
app = Flask(__name__)
@app.route("/__check")
def _c():
    return "ok"
r = app.test_client().get("/__check")
assert r.status_code == 200 and r.data == b"ok"
'
if python3 -c "$FLASK_SELF_TEST" 2>/dev/null; then
    echo "Flask already working (import + real request round-trip), skipping install."
else
    echo "Flask is not working (broken import or broken request handling.)"
    echo "Installing pip3 install --user \"flask~=2.2.5\" \"werkzeug~=2.2.3\" (see design notes above for why both are pinned together)..."
    pip3 install --user "flask~=2.2.5" "werkzeug~=2.2.3" \
        || echo "WARNING: Flask/Werkzeug pip install failed - install manually later (pip3 install --user \"flask~=2.2.5\" \"werkzeug~=2.2.3\")."

    if python3 -c "$FLASK_SELF_TEST" 2>/dev/null; then
        echo "Flask now works (import + real request round-trip) after the fixup."
    else
        echo "WARNING: Flask still not working after the fixup - investigate manually (run the FLASK_SELF_TEST snippet in install_pi_dependencies.sh directly to see the real traceback). web/app.py will not run until this is resolved."
    fi
fi

echo
echo "=== Done ==="
echo "If this is the first time installing user-site pip packages, make sure"
echo "\$HOME/.local/bin is on your PATH so the 'jupyter-lab' command is found:"
echo '  echo '"'"'export PATH="$HOME/.local/bin:$PATH"'"'"' >> ~/.bashrc && source ~/.bashrc'
