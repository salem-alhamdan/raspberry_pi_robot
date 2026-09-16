// Frontend for the robot control server (web/app.py).
//
// Command repeat / watchdog interaction: while a movement button or
// movement key is held down, we resend the SAME command every
// REPEAT_INTERVAL_MS. This both (re-)executes the command (harmless - the
// server's motor functions are idempotent) and refreshes the server's
// watchdog timer (config.COMMAND_WATCHDOG_TIMEOUT_S, 1.5s by default) - see
// web/app.py's module docstring. REPEAT_INTERVAL_MS is comfortably below
// that timeout so normal held-button/held-key driving never trips it.
const REPEAT_INTERVAL_MS = 400;
const STATUS_POLL_INTERVAL_MS = 1000;

const KEY_TO_ACTION = { w: "forward", s: "backward", a: "left", d: "right", " ": "stop" };

let currentSpeed = 50;
let heldAction = null;
let repeatTimer = null;
let currentMode = "manual"; // authoritative value comes back from every API response / status poll

const el = (id) => document.getElementById(id);
const controlsPanel = el("controls-panel");
const modeToggle = el("mode-toggle");
const speedSlider = el("speed-slider");
const speedValue = el("speed-value");
const statusIndicator = el("status-indicator");
const statusText = el("status-text");

async function postJSON(url, body) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    const data = await res.json().catch(() => ({}));
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    // Network error (server down, connection dropped, etc.) - never throw
    // out of a caller; just report failure so the UI can reflect it.
    console.error("request failed:", url, err);
    return { ok: false, status: 0, data: { error: String(err) } };
  }
}

function setControlsEnabled(enabled) {
  controlsPanel.classList.toggle("disabled", !enabled);
}

function applyMode(mode) {
  currentMode = mode;
  modeToggle.checked = mode === "ai";
  setControlsEnabled(mode === "manual");
}

// ---------------------------------------------------------------------
// Movement commands
// ---------------------------------------------------------------------

async function sendCommand(action) {
  if (currentMode !== "manual") return; // client-side guard; server enforces this too
  await postJSON("/api/command", { action, speed: currentSpeed });
}

function startHolding(action) {
  if (currentMode !== "manual") return;
  if (heldAction === action) return; // already repeating this exact action
  stopHolding(); // clear any previous action's timer first
  heldAction = action;
  sendCommand(action);
  if (action !== "stop") {
    repeatTimer = setInterval(() => sendCommand(action), REPEAT_INTERVAL_MS);
  }
}

function stopHolding() {
  if (repeatTimer) {
    clearInterval(repeatTimer);
    repeatTimer = null;
  }
  heldAction = null;
}

function releaseToStop() {
  if (heldAction && heldAction !== "stop") {
    stopHolding();
    sendCommand("stop");
  } else {
    stopHolding();
  }
}

document.querySelectorAll(".dpad-btn").forEach((btn) => {
  const action = btn.dataset.action;
  btn.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    startHolding(action);
  });
  btn.addEventListener("pointerup", releaseToStop);
  btn.addEventListener("pointerleave", releaseToStop);
  btn.addEventListener("pointercancel", releaseToStop);
});

// Keyboard control (W/A/S/D + SPACE)
const activeKeys = new Set();
window.addEventListener("keydown", (e) => {
  const tag = document.activeElement && document.activeElement.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return; // don't hijack typing in the speed slider etc.
  const action = KEY_TO_ACTION[e.key.toLowerCase()];
  if (!action || activeKeys.has(e.key)) return;
  activeKeys.add(e.key);
  e.preventDefault();
  startHolding(action);
});
window.addEventListener("keyup", (e) => {
  const action = KEY_TO_ACTION[e.key.toLowerCase()];
  if (!action) return;
  activeKeys.delete(e.key);
  if (activeKeys.size === 0) {
    releaseToStop();
  }
});
// Safety net: if the tab/window loses focus while a key is held (e.g.
// alt-tab), the browser will never fire keyup - stop driving immediately
// rather than relying solely on the 1.5s server watchdog.
window.addEventListener("blur", () => {
  activeKeys.clear();
  releaseToStop();
});

// ---------------------------------------------------------------------
// Speed slider
// ---------------------------------------------------------------------

speedSlider.addEventListener("input", () => {
  currentSpeed = parseInt(speedSlider.value, 10);
  speedValue.textContent = currentSpeed;
});

// ---------------------------------------------------------------------
// Mode toggle
// ---------------------------------------------------------------------

modeToggle.addEventListener("change", async () => {
  const target = modeToggle.checked ? "ai" : "manual";
  modeToggle.disabled = true; // guard against rapid double-toggling while a switch is in flight
  stopHolding();
  const { ok, data } = await postJSON("/api/mode", { mode: target });
  if (ok && data.mode) {
    applyMode(data.mode);
  } else {
    // Switch failed server-side - resync to whatever the server actually
    // reports rather than trusting the checkbox's optimistic state.
    console.error("mode switch failed:", data);
    refreshStatus();
  }
  modeToggle.disabled = false;
});

// ---------------------------------------------------------------------
// Emergency stop
// ---------------------------------------------------------------------

el("btn-estop").addEventListener("click", async () => {
  stopHolding();
  const { data } = await postJSON("/api/estop", {});
  if (data && data.mode) applyMode(data.mode);
});

// ---------------------------------------------------------------------
// Status polling
// ---------------------------------------------------------------------

function fmt(value, digits) {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number" && digits !== undefined) return value.toFixed(digits);
  return String(value);
}

function refreshStatus() {
  fetch("/api/status")
    .then((res) => res.json())
    .then((s) => {
      if (s.mode && s.mode !== currentMode) applyMode(s.mode);

      el("s-mode").textContent = fmt(s.mode);
      el("s-action").textContent = fmt(s.action);
      el("s-stop-reason").textContent = fmt(s.stop_reason);
      el("s-color").textContent = fmt(s.detected_color);
      el("s-car").textContent =
        s.car_detected === undefined ? "-" : (s.car_detected ? `yes (${fmt(s.car_confidence, 2)})` : "no");
      el("s-distance").textContent = fmt(s.distance_m, 2);

      statusIndicator.className = "status-indicator " + (s.action === "stop" ? "status-warn" : "status-ok");
      statusText.textContent = s.mode === "ai" ? `AI - ${s.action}` : `Manual - ${s.action}`;
    })
    .catch((err) => {
      console.error("status poll failed:", err);
      statusIndicator.className = "status-indicator status-bad";
      statusText.textContent = "disconnected";
    });
}

setInterval(refreshStatus, STATUS_POLL_INTERVAL_MS);
refreshStatus();
