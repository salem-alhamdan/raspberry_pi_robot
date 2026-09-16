# TEST_REPORT.md

QA pass by Agent 2 (Test/QA Engineer) on real hardware: Raspberry Pi 4 Model B
Rev 1.5 (4GB), Debian 11 bullseye, kernel 6.1.21-v8+ aarch64, Python 3.9.2,
reached via `ssh admin@192.168.0.130`.

Project copied via `rsync` from the dev laptop
(`/home/salem/AI_Car_workshop/raspberry_pi_robot/`) to the Pi's local
filesystem at `~/raspberry_pi_robot/` (i.e. `/home/admin/raspberry_pi_robot/`
on the Pi) and all commands below were run natively there over SSH, not over
a remote-mounted path.

Physical wiring state at time of testing: **only the Pi Camera Module v2
(CSI) is connected.** The plain LED (GPIO17), RGB LED, button, L298N +
motors, and ultrasonic sensor are NOT physically wired. Nothing below claims
visual/physical confirmation of anything that isn't wired.

---

### LED module import (direct-run)
Expected: `python3 src/hardware/led.py`, run from the
`~/raspberry_pi_robot/` directory on the Pi, runs to completion with no
exceptions, successfully constructs a `gpiozero.LED(17)` object, blinks 5x,
and releases the GPIO pin in its `finally` block.
Actual: Ran twice in a row (to also double as a re-run-safety check). Both
runs completed with exit code 0 and printed:
```
LED smoke test: using GPIO17
Blink 1/5: ON
Blink 1/5: OFF
... (through Blink 5/5)
Smoke test complete.
LED GPIO released.
```
No exceptions, no pin-factory errors, no "pin already in use" error on the
second run.
Status: PASS
Notes: None.

### LED module import (notebook-style)
Expected: From `~/raspberry_pi_robot/`, adding `src/` to `sys.path` and doing
`from hardware.led import get_led, led_on, led_off, cleanup` works, exactly
as Agent 3 will need to do from a Jupyter notebook later.
Actual: Ran
```
python3 -c "import sys; sys.path.insert(0, 'src'); from hardware.led import get_led, led_on, led_off, cleanup; led = get_led(); led_on(led); led_off(led); cleanup(led); print('notebook-style import OK')"
```
Output: `notebook-style import OK`, exit code 0.
Status: PASS
Notes: Confirms the `sys.path` manipulation in `led.py` (inserting
`Path(__file__).resolve().parent.parent`) correctly supports both the
direct-run and the "notebook added src/ to its own sys.path, then imports
hardware.led" cases described in the module's docstring.

### GPIO17 logic-level toggle (verified via raspi-gpio, not just print output)
Expected: GPIO17's actual electrical level and pin function change in sync
with `led_on()`/`led_off()` calls, independent of the script's own print
statements.
Actual: Backgrounded `python3 src/hardware/led.py` and polled
`raspi-gpio get 17` every 0.25s for 5s while it ran. Before the script
started: `GPIO 17: level=0 fsel=0 func=INPUT pull=DOWN`. During the run,
`fsel` switched to `1` (`func=OUTPUT`), and `level` alternated
`1,1,0,0,1,1,0,0,1,1,0,0,1,1,0,0,1,1,0,0` across the 20 polls — exactly
matching the script's 0.5s-per-state ON/OFF blink cadence (5 full
ON/OFF cycles). This is an independent cross-check via `raspi-gpio`, not
reliant on the script's print statements.
Status: PASS
Notes: This is the one behavior that IS genuinely verifiable without the LED
physically attached (driving the pin electrically is independent of whether
an LED is there to light up), and it was verified rigorously.

### GPIO cleanup / re-run safety
Expected: After the script exits, GPIO17 is released (not left claimed by
gpiozero/lgpio), and a second run of the script does not error with
"pin already in use" or similar.
Actual: `raspi-gpio get 17` immediately after script exit showed
`fsel=0 func=INPUT` (reverted from OUTPUT back to the default INPUT state,
confirming the pin was released via `led.close()` in the `finally` block).
Ran the full script a second time immediately after — completed successfully
with the same clean output and exit code 0, no pin-conflict error.
Status: PASS
Notes: None.

### Visual LED confirmation
Expected: N/A
Actual: N/A
Status: NOT TESTED — hardware not yet wired
Notes: No physical LED is connected to GPIO17 yet, so whether an LED would
actually visibly light up cannot be confirmed. Everything electrically
testable without the LED present (pin driven HIGH/LOW, correct timing, clean
release) was tested above and passed. This item must be re-verified once the
LED is physically wired.

### Install script: OpenCV install
Expected: Running `scripts/install_pi_dependencies.sh` results in
`python3 -c "import cv2; print(cv2.__version__)"` succeeding afterward
(via `apt-get install python3-opencv`, or the documented pip fallback to
`opencv-python-headless` if the apt path fails).
Actual (RE-TESTED after Agent 1's fix): Agent 1 guarded both
`sudo apt-get update` and `sudo apt-get install -y python3-opencv` with
`|| echo "WARNING: ..."` instead of leaving them to bare `set -e`, so a
failure now falls through to the `import cv2` check instead of aborting the
script. Re-synced the updated script to the Pi (md5sum-verified identical to
the dev-machine copy) and ran it fresh.
`sudo apt-get install -y python3-opencv` **still failed** with the exact
same `404 Not Found` errors from `security.debian.org` for the same 5
packages as before (`libheif1`, `mariadb-common`, `libmariadb3`, `libpq5`,
`libgdcm3.0`) — confirmed this is not transient by directly re-running
`sudo apt-get install -y python3-opencv` again afterward and getting
byte-for-byte identical 404s. This is a genuine, still-unresolved Debian
mirror-sync issue on `security.debian.org`, not something this project can
fix.
This time, however, the script **correctly fell through** instead of
aborting: after the apt failure it printed "apt package did not provide a
working cv2 import (or apt-get itself failed above)" and ran
`pip3 install --user opencv-python-headless`, which succeeded. Post-run:
`python3 -c "import cv2; print(cv2.__version__)"` → `5.0.0`. Confirmed via
`pip3 list --user | grep opencv` → `opencv-python-headless 5.0.0.93`, and
`apt list --installed | grep opencv` → empty (i.e. genuinely came from the
pip fallback path, not apt).
Status: PASS
Notes: The script bug reported in the previous pass is fixed — the pip
fallback is now actually reachable and does work. The underlying
`security.debian.org` 404s for those 5 packages are still present as of this
re-test (not resolved on their own); this remains a note for a human to
retry later, not a project bug. `sudo -n dpkg --audit` stayed clean
throughout (no broken/half-installed packages).

### Install script: JupyterLab install
Expected: Running the script results in `jupyter --version` (or
`~/.local/bin/jupyter-lab --version`) working afterward via
`pip3 install --user jupyterlab`.
Actual (RE-TESTED after Agent 1's fix): With the OpenCV step no longer
aborting the script, the JupyterLab section now executes regardless of what
happened above. `pip3 install --user jupyterlab` ran to completion (~3m38s
total script runtime, mostly this step downloading/building ~90 packages
from piwheels/PyPI) and exited 0. Post-run: `~/.local/bin/jupyter --version`
and `~/.local/bin/jupyter-lab --version` both work, reporting
`jupyterlab 4.5.10`, `ipykernel 6.31.0`, `jupyter_server 2.18.2`, etc. Note
the script's own final printed instructions about adding `~/.local/bin` to
PATH are accurate/necessary — `jupyter`/`jupyter-lab` are not on PATH by
default for this user until that's done (used the full path / exported PATH
inline to verify).
Status: PASS
Notes: None.

### Install script: idempotency (second run)
Expected: Running the script a second time detects OpenCV/JupyterLab are
already present and skips reinstalling, without erroring.
Actual (RE-TESTED after Agent 1's fix, now that both packages are actually
installed from run 1): Ran the script a second time immediately after.
Completed in ~8 seconds (vs. ~3m38s for the real install) with exit code 0
and this output:
```
=== AI Car workshop: Pi dependency installer ===

--- OpenCV ---
cv2 5.0.0
OpenCV already importable, skipping install.

--- JupyterLab ---
JupyterLab already installed, skipping install.

=== Done ===
...
```
Both "already installed, skipping" branches actually triggered this time
(previously untestable since nothing had installed successfully yet). No
apt or pip calls were made at all on the second run. `sudo -n dpkg --audit`
clean afterward.
Status: PASS
Notes: This is now a full, genuine idempotency confirmation — both the
"install" path (run 1) and the "detect already present, skip" path (run 2)
have been exercised and verified.

---

## RGB LED / Button / Notebook 1 (added in a later QA pass)

New files from Agent 1 (`src/hardware/rgb_led.py`, `src/hardware/button.py`)
and Agent 3 (`notebooks/01_gpio_led.ipynb`) re-synced to the Pi and
independently re-verified from scratch (not just trusting Agent 1's own
scratch-copy checks). Same physical wiring state as before: RGB LED and
button are NOT physically wired yet, only the camera is connected.

### rgb_led.py: direct-run
Expected: `python3 src/hardware/rgb_led.py` runs to completion with no
exceptions, constructs a `gpiozero.RGBLED` object on GPIO22/23/24, cycles
through 8 named colors, and releases all three pins in its `finally` block.
Actual: Ran twice back-to-back. Both runs exited 0 with clean output cycling
RED, GREEN, BLUE, YELLOW, CYAN, MAGENTA, WHITE, OFF, ending with
"RGB LED GPIO released."
Status: PASS
Notes: None.

### rgb_led.py: notebook-style import
Expected: `sys.path.insert(0, 'src')` then
`from hardware.rgb_led import get_rgb_led, set_red, ..., cleanup` works.
Actual: Ran the notebook-style import, called `get_rgb_led()`,
`set_red/green/blue/off`, `cleanup()` — printed
`rgb_led notebook-style import OK`, exit code 0.
Status: PASS
Notes: None.

### rgb_led.py: GPIO22/23/24 electrical cross-check (raspi-gpio)
Expected: Each named color drives the correct combination of R/G/B pins
HIGH/LOW (active_high=True per RGB_COMMON_CATHODE=True), independent of the
script's print output. At 100% duty cycle (255) a channel should read as a
constant HIGH, not toggling — that is expected PWM behavior at full
brightness, not a bug.
Actual: Backgrounded the script and polled `raspi-gpio get 22/23/24` every
0.2s for ~4.8s. Before the run: all three pins `fsel=0 func=INPUT`. During
the run, all three switched to `fsel=1 func=OUTPUT` and the level
combinations matched every named color exactly, in order:
- RED: R=1 G=0 B=0
- GREEN: R=0 G=1 B=0
- BLUE: R=0 G=0 B=1
- YELLOW: R=1 G=1 B=0
- CYAN: R=0 G=1 B=1
- MAGENTA: R=1 G=0 B=1
- WHITE: R=1 G=1 B=1
- OFF: R=0 G=0 B=0
Each channel read as a stable constant level within a color (not switching
during the poll window), consistent with Agent 1's note that a channel at
0 or 255 is 0%/100% duty cycle (i.e. not actually PWM-switching, just
constant HIGH or LOW) — confirmed this is what was observed, not flagged as
a PWM defect. After the script exited, all three pins reverted to
`fsel=0 func=INPUT`.
Status: PASS
Notes: This required fixing my own polling script mid-test (an earlier grep
pattern against `raspi-gpio`'s output format was wrong and returned empty
matches) — re-ran with a corrected capture and got the clean, fully
consistent color-by-color result above.

### rgb_led.py: GPIO cleanup / re-run safety
Expected: All three pins released after exit; a second run doesn't error.
Actual: Confirmed `fsel=0 func=INPUT` on GPIO22/23/24 immediately after the
first run's exit. Ran the full script a second time immediately after —
identical clean output, exit code 0, no pin-conflict errors.
Status: PASS
Notes: None.

### button.py: direct-run
Expected: `python3 src/hardware/button.py` runs the time-bounded (20s) demo
with no exceptions, constructs a `gpiozero.Button(27)` with `pull_up=True`,
polls `is_pressed`, and exits on its own after 20s without requiring a
press (since nothing is wired).
Actual: Ran twice back-to-back (each ~20.4s, confirmed via `time`). Both
exited 0, printed "Button released" once (initial state, no toggling since
nothing is wired to change it) and "Demo complete after 20s (no press
required)." / "Button GPIO released."
Status: PASS
Notes: None.

### button.py: notebook-style import
Expected: `sys.path.insert(0, 'src')` then
`from hardware.button import get_button, cleanup` works, `.is_pressed`
readable directly off the returned object.
Actual: Ran the notebook-style import; `button.is_pressed` read `False`
(expected — internal pull-up holds the unwired pin HIGH); `cleanup()`
succeeded; printed `button notebook-style import OK`, exit code 0.
Status: PASS
Notes: None.

### button.py: GPIO27 electrical cross-check (raspi-gpio)
Expected: While a `Button` object is alive, GPIO27 shows `pull=UP`
(internal pull-up enabled); after `cleanup()`/exit, that reverts.
Actual: Before the script ran: `GPIO 27: ... pull=NONE`. Backgrounded the
20s demo and polled `raspi-gpio get 27` twice while it was running (at ~1s
and ~2s in): both times showed `GPIO 27: level=1 fsel=0 func=INPUT
pull=UP`. Immediately after the script exited: reverted to
`GPIO 27: level=1 fsel=0 func=INPUT pull=NONE`.
Status: PASS
Notes: This is the one behavior genuinely verifiable for the button without
it being physically wired — confirms gpiozero actually enables the Pi's
internal pull-up resistor on this pin, and releases it cleanly on close.

### button.py: GPIO cleanup / re-run safety
Expected: Pin released after exit; a second run doesn't error.
Actual: Confirmed `pull` reverted to `NONE` after first run; ran the full
20s demo a second time immediately after — identical clean output, exit
code 0, no pin-conflict errors.
Status: PASS
Notes: None.

### RGB LED / Button: physical confirmation
Expected: N/A
Actual: N/A
Status: NOT TESTED — hardware not yet wired
Notes: No RGB LED or push button is physically connected yet, so actual
visible color output and actual physical button presses cannot be
confirmed. Same status pattern as the plain LED's visual confirmation.
Everything electrically testable without the hardware present (correct pin
combinations per color, pull-up enabled/released, clean timing, clean
release) was tested above and passed.

### notebooks/01_gpio_led.ipynb: full top-to-bottom execution
Expected: All 36 cells execute in order with no errors via a real Jupyter
"Run All" (`jupyter nbconvert --to notebook --execute`), and the
`sys.path.insert(0, '../src')` cell (cell 29) correctly resolves
`hardware`/`config` imports given the notebook's actual location.
Actual: Ran `jupyter nbconvert --to notebook --execute
--output 01_gpio_led.executed.ipynb 01_gpio_led.ipynb` from inside
`~/raspberry_pi_robot/notebooks/` (JupyterLab 4.5.10, registered `python3`
kernelspec at `~/.local/share/jupyter/kernels/python3`). Completed in ~22s,
exit code 0. Parsed the executed notebook's cell outputs programmatically:
no `output_type: error` in any of the 36 cells. Key stdout confirms clean
execution: cell 22 (blink loop) printed all 5 "Blink N/5: ON/OFF" pairs plus
"Done blinking."; cell 29 (the `sys.path.insert(0, '../src')` + import cell)
printed `LED_PIN from config.py: 17`, confirming the relative path resolved
correctly — `nbconvert`'s `ExecutePreprocessor` runs with the notebook's own
directory as the kernel's working directory by default, so `../src` from
`notebooks/` correctly reached `src/`; cell 32 (module-based LED sequence
using `get_led()`) printed "Module-based LED sequence complete." with no
error, confirming cell-execution-order-dependent state (the earlier
`led.close()` in cell 25 on the raw `LED(17)` object, followed later by a
fresh `get_led()` in cell 32) behaves correctly under normal top-to-bottom
execution, exactly as Agent 3 described.
Status: PASS
Notes: One benign warning worth flagging to Agent 3 (not a failure, did not
affect execution or outputs): nbconvert printed
`MissingIDFieldWarning: Cell is missing an id field, this will become a
hard error in future nbformat versions.` This means the notebook's cells
were written without the nbformat 4.5+ `id` field. It runs fine today, but
per the warning text this "will become a hard error in future nbformat
versions" — Agent 3 may want to run `nbformat.validate()`/`normalize()` (or
just open-and-resave in current JupyterLab, which adds ids automatically)
to future-proof it, at their discretion; not blocking.
Cleaned up my own test artifacts (`01_gpio_led.executed.ipynb` and a
scratch checker script) from the Pi afterward — only the original
`01_gpio_led.ipynb` remains in `notebooks/` on the Pi.

### notebooks/01_gpio_led.ipynb: visual LED confirmation
Expected: N/A
Actual: N/A
Status: NOT TESTED — hardware not yet wired
Notes: Whether the LED actually visibly lights up during cells 13/19/22/32
cannot be confirmed since no LED is wired to GPIO17. All-cells-clean
execution and correct GPIO logic-level behavior for this same code path was
already verified separately in the `led.py` sections above.

---

## Motor driver (src/hardware/motor.py) and Notebook 02 (added in a later QA pass)

New file from Agent 1 (`src/hardware/motor.py`, L298N driver: `Motor(pwm=False)`
for direction on IN1-4, separate `PWMOutputDevice` on ENA/ENB for real PWM
speed) and from Agent 3 (`notebooks/02_rgb_pwm_button.ipynb`) re-synced to
the Pi and independently re-verified. L298N + motors are still NOT
physically wired (only the camera is connected), so every check below is
electrical/logical only. Given this module can actually move a real robot
once wired, this pass used deliberately more rigorous, timestamp-verified
tests than prior modules, especially for `stop()`.

### motor.py: direct-run (`__main__` smoke test)
Expected: `python3 src/hardware/motor.py` runs its bounded 14-step, 1s/step
demo (`left_forward`, `left_stop`, `right_forward`, `right_stop`, `forward`,
`stop`, `backward`, `stop`, `left` pivot, `stop`, `right` pivot, `stop`,
`set_speed(25,75)`, `stop`) with no exceptions and releases all 6 GPIO pins
in its `finally` block.
Actual: Ran end-to-end while background-polling all 6 pins (ENA=12, IN1=5,
IN2=6, ENB=13, IN3=19, IN4=26) at 0.2s intervals for the full run. Exit code
0, clean printed step-by-step output ending in "Motors stopped and all GPIO
released."
Status: PASS
Notes: None.

### motor.py: notebook-style import
Expected: `sys.path.insert(0, 'src')` then
`from hardware.motor import get_motors, left_forward, ..., cleanup` works.
Actual: Ran the notebook-style import, exercised `get_motors()`,
`forward(motors, 40)`, `left(motors, 40)`, `set_speed(motors, 10, 90)`,
`stop(motors)`, `cleanup(motors)` — printed `motor notebook-style import
OK`, exit code 0.
Status: PASS
Notes: None.

### motor.py: IN1-4 direction-pin electrical cross-check (raspi-gpio)
Expected: `left_forward()`→IN1 HIGH/IN2 LOW (reversed for
`left_backward()`); same pattern for IN3/IN4 via `right_forward()` /
`right_backward()`; `left_stop()`/`right_stop()` zero both that motor's
direction pins.
Actual: The full 14-step demo trace (0.2s-interval polling across the whole
~14s run, 70 samples per pin) reproduced every step's expected direction-pin
combination in order:
- `left_forward`: IN1=1, IN2=0 (right motor pins idle at 0)
- `left_stop`: IN1=0, IN2=0
- `right_forward`: IN3=1, IN4=0 (left motor pins idle at 0)
- `right_stop`: IN3=0, IN4=0
- `forward`: IN1=1,IN2=0 AND IN3=1,IN4=0 simultaneously (both motors forward)
- `stop`: all 4 direction pins 0
- `backward`: IN1=0,IN2=1 AND IN3=0,IN4=1 simultaneously (both motors
  reversed)
- `stop`: all 4 direction pins 0
- `set_speed(25,75)`: all 4 direction pins stayed at 0 the whole step
  (correct — direction was last set to "stop", and `set_speed()` only
  touches ENA/ENB, never direction, per the module's docstring)
Status: PASS
Notes: None.

### motor.py: left()/right() pivot-turn opposite-direction cross-check
Expected: `left(motors)` (pivot left) drives the left motor backward AND the
right motor forward simultaneously (opposite states between the two
motors); `right(motors)` (pivot right) is the mirror (left forward, right
backward).
Actual: From the same demo trace:
- `left(motors)` step: IN1=0,IN2=1 (left motor backward) simultaneous with
  IN3=1,IN4=0 (right motor forward) — confirmed opposite states between
  motors, matching the pivot-left docstring.
- `right(motors)` step: IN1=1,IN2=0 (left motor forward) simultaneous with
  IN3=0,IN4=1 (right motor backward) — confirmed opposite states, matching
  pivot-right.
Status: PASS
Notes: None.

### motor.py: ENA/ENB (GPIO12/13) genuine PWM duty-cycle tracking
Expected: ENA/ENB show real PWM switching (not a static level) whose duty
cycle tracks `set_speed()`/the default 50% used by bare movement calls, with
0% reading as constant LOW and 100% as constant HIGH (matching Agent 1's
note that full duty is 100% duty = no actual switching, by design, not a
bug).
Actual: Two complementary tests:
1. The 14-step demo trace showed ENA/ENB visibly toggling between 0 and 1
   across consecutive 0.2s samples during every active movement step (e.g.
   during `left_forward`: ENA read 0,0,1,1,0 across 5 consecutive samples —
   clearly switching, not static), while during every `stop()` step ENA/ENB
   read a constant 0 across all samples in that step.
2. A dedicated, tighter statistical test: called `set_speed(motors, D, D)`
   for D in [0, 25, 50, 75, 100], held each for 2.6s via a backgrounded
   Python process using the actual project module, and rapid-polled
   `raspi-gpio get 12`/`get 13` ~150 times per level (~1.5-1.8s of
   sampling). Results (measured HIGH-sample fraction vs. requested duty):
   `0%→0%/0%`, `25%→~2-3%/2-3%`, `50%→~32-34%/32-34%`, `75%→~60-81%`,
   `100%→100%/100%`. The 0% and 100% readings are exact, unambiguous
   matches (constant LOW / constant HIGH respectively, zero variance across
   150 samples each). The intermediate values are clearly non-zero,
   clearly switching, and increase monotonically with requested duty,
   proving genuine duty-cycle tracking — though the absolute mid-range
   percentages are skewed low relative to the true duty by this
   measurement method's own sampling bias (each `raspi-gpio` sample
   requires spawning an external process, which is slow and irregular
   relative to the ~10ms/100Hz PWM period, so it under-samples HIGH phases
   somewhat unevenly). This is a limitation of measuring fast software PWM
   via external polling, not a defect in the module under test.
Status: PASS
Notes: The 0%/100% exact boundary matches plus the monotonic trend across
25/50/75% conclusively demonstrate ENA/ENB are being genuinely PWM'd and
tracking `set_speed()`, consistent with Agent 1's redesign rationale
(`Motor(pwm=False)` for direction, separate `PWMOutputDevice` for ENA/ENB).

### motor.py: `stop()` safety-critical check — ENA/ENB AND IN1-4 all zeroed
Expected: `stop()` (and `left_stop()`/`right_stop()`) zero BOTH the PWM
enable value (ENA/ENB, GPIO12/13) AND the direction pins (IN1-4), so nothing
is left "armed" after a stop.
Actual: This needed two attempts to get an unambiguous result, documented
here in full since it's the most safety-critical check in this pass:
- **First attempt** (background process: `forward(motors, 90)`, sleep 1.5s,
  `stop(motors)`, sleep 2.5s, `cleanup(motors)`; bash polls 200 samples on
  all 6 pins starting ~1.9s in) came back showing ~60% HIGH on every pin,
  including the direction pins — which would be alarming if real, since
  direction pins should be a static, non-PWM 0 after `stop()`. Investigated
  before concluding anything: added explicit wall-clock timestamps to both
  the Python process (prints at START/STOP/CLEANUP) and the bash poll
  loop. This showed the 200-sample raspi-gpio poll loop was slower than
  estimated (~30ms/iteration, not ~10ms, because each iteration spawns 6
  separate `raspi-gpio` subprocesses) and had overrun past `cleanup()`
  before finishing — meaning the tail of the sampling window landed in the
  "pins just closed, floating HIGH" phase already characterized in every
  earlier module's cleanup test, not the "stopped but still held" phase.
  The overrun fraction (~21% of the loop's total duration, per the
  timestamps) matched the observed ~21% HIGH count almost exactly,
  confirming this was a test-timing artifact, not a code bug.
- **Confirmation attempt** (same structure, but a 12s gap between `stop()`
  and `cleanup()`, and only 100 samples starting 3s in): timestamps
  confirmed the entire poll window (3.00s-6.13s after start) fell
  comfortably inside the stop-to-cleanup gap (`stop()` at 1.50s,
  `cleanup()` at 13.51s). Result: **0/100 HIGH on all 6 pins** (ENA, ENB,
  IN1, IN2, IN3, IN4) — i.e. zero PWM activity and zero stuck direction
  pins, for the entire ~3.1s sampling window, while the motors had been
  confirmed running forward at 90% speed immediately beforehand.
Status: PASS
Notes: The real result is unambiguous once the sampling window is
correctly bounded: `stop()` genuinely zeroes ENA and ENB electrically (not
just at the gpiozero object level), together with all 4 direction pins,
with no lingering PWM or stuck-HIGH state. Flagging the test-methodology
pitfall here (not a motor.py bug) in case it's useful context for anyone
re-running similar electrical tests on fast-switching pins later: raspi-gpio
polling loops need generous timing margins/explicit timestamps, not just
estimated sleep durations, especially when polling multiple pins per
iteration.

### motor.py: GPIO cleanup / re-run safety
Expected: All 6 pins released after the smoke test exits; running it a
second time immediately after does not error.
Actual: Ran the full smoke test twice back-to-back. Both exited 0 with
identical clean output, no exceptions, no "pin already in use" or similar
errors in either run's log. All 6 pins (`raspi-gpio get`) read
`fsel=0 func=INPUT` after both runs.
Status: PASS
Notes: None.

### motor.py: physical wheel movement / actual spin direction
Expected: N/A
Actual: N/A
Status: NOT TESTED — hardware not yet wired
Notes: The L298N and motors are not physically connected yet, so actual
wheel movement and actual spin direction (which, per the module's
docstring, depends on each motor's lead-wiring polarity and may come out
mirrored on one side until physically corrected at the L298N terminals)
cannot be confirmed. Everything electrically testable without the hardware
present — correct direction-pin combinations, correct pivot-turn opposite
states, genuine PWM duty-cycle tracking on ENA/ENB, and rigorous
timestamp-verified confirmation that `stop()` truly zeroes every relevant
pin — was tested above and passed.

### notebooks/02_rgb_pwm_button.ipynb: full top-to-bottom execution
Expected: All 69 cells execute in order with no errors via
`jupyter nbconvert --to notebook --execute`, including a clean transition
at the cell that explicitly closes a raw `Button(27)` object before the
module's `get_button()` reopens GPIO27 later in the same notebook (no "pin
already in use" error).
Actual: Confirmed the notebook now has proper nbformat cell `id` fields
(the `MissingIDFieldWarning` seen on Notebook 01 does NOT appear here,
confirming Agent 3's nbformat fix). Ran
`jupyter nbconvert --to notebook --execute
--output 02_rgb_pwm_button.executed.ipynb 02_rgb_pwm_button.ipynb` from
`~/raspberry_pi_robot/notebooks/`. Completed in ~45.5s (in the right
ballpark of the expected ~35-40s, plus nbconvert/kernel startup overhead),
exit code 0. Parsed the executed notebook's outputs programmatically: zero
`error` outputs across all 69 cells. Specifically inspected the flagged
transition: cell 50 (`button = Button(27)`) printed "Button ready on
GPIO27."; cell 56 calls `button.close()` (no output expected, just
releases the pin); cell 59 (`from hardware.button import get_button; btn =
get_button()`) printed "Project button module ready." with no error —
confirming GPIO27 was cleanly reclaimed by the module's own `get_button()`
right after the raw object closed it, exactly the transition Agent 3 asked
to be double-checked. Cell 65 (final cleanup of both RGB LED and button)
printed "RGB LED and button GPIO released." with no error.
Status: PASS
Notes: Cleaned up my own test artifacts (executed-notebook copy, scratch
checker script) from the Pi afterward — only the two original notebooks
remain in `notebooks/` on the Pi. Confirmed all 11 pins used across every
hardware module so far (17, 22, 23, 24, 27, 12, 5, 6, 13, 19, 26) read a
clean released `fsel=0 func=INPUT` state after this run.

### notebooks/02_rgb_pwm_button.ipynb: visual RGB color output / actual button press
Expected: N/A
Actual: N/A
Status: NOT TESTED — hardware not yet wired
Notes: No RGB LED or button is physically connected yet, so actual visible
color output and actual physical button presses cannot be confirmed.
Consistent with the same status pattern used for every other unwired
component. All-cells-clean execution and the underlying GPIO logic-level
behavior for this code (rgb_led.py, button.py) were already verified
separately in their own sections above.

---

## Ultrasonic sensor, obstacle avoidance, and Notebook 03 (added in a later QA pass)

New files from Agent 1 (`src/hardware/ultrasonic.py`, `src/robot/obstacle_avoidance.py`)
and from Agent 3 (`notebooks/03_l298n_motor_control.ipynb`) re-synced to the
Pi and independently re-verified. Neither the HC-SR04 ultrasonic sensor nor
the L298N/motors are physically wired yet (only the camera is connected),
so every check below is electrical/logical only — but this batch includes
the first notebook where an unattended execute run drives real motor logic
end-to-end, and a genuinely safety-relevant finding from Agent 1 about
`gpiozero.DistanceSensor` blocking indefinitely, so this pass applied extra
rigor, including a real, physically-sent `SIGINT`/`KeyboardInterrupt` test
(not just code reading) for the most safety-critical claim.

### ultrasonic.py: `partial=True` independently confirmed (not just trusted from source)
Expected: `get_ultrasonic_sensor()` constructs `gpiozero.DistanceSensor` with
`partial=True`, per Agent 1's finding that the default `partial=False`
blocks `.distance` indefinitely with nothing wired.
Actual: Inspected the actual constructed object's attribute directly (not
just read the source file): `sensor.partial` → `True`, `sensor.max_distance`
→ `3.0` (confirms the documented `DEFAULT_MAX_DISTANCE_M` override from
gpiozero's own 1m default is actually applied). Additionally, independently
reproduced Agent 1's underlying claim from scratch (rather than just trusting
their report): constructed a bare `gpiozero.DistanceSensor(..., partial=False)`
directly (bypassing this module) and called `.distance` under a `timeout 6`
wrapper — the process was killed by the timeout, confirming the hang is
real, reproducible, and not specific to how Agent 1 tested it.
Status: PASS
Notes: A `DistanceSensorNoEcho: no echo received` warning fires in the
background during the hang (and during every `partial=True` read), which is
expected/harmless — it's gpiozero's own diagnostic logging, not an
exception.

### ultrasonic.py: `read_distance()` never blocks (critical safety property)
Expected: Every call to `read_distance()` returns near-instantly (well under
1s), never hangs, even with nothing wired.
Actual: Timed 5 consecutive `read_distance()` calls directly with
`time.monotonic()` around each call: `0.05ms, 0.01ms, 0.01ms, 0.01ms, 0.01ms`
— i.e. genuinely instantaneous, not just "fast", confirming `partial=True`
is doing its job.
Status: PASS
Notes: None.

### ultrasonic.py: direct-run smoke test
Expected: `python3 src/hardware/ultrasonic.py` prints
`Distance = 0.00 m` for all 5 samples, no crash/hang, prominent SAFETY
warning about the ECHO voltage divider in the printed output.
Actual: Ran under a `timeout 15` safety net (unnecessary as it turned out —
completed in ~5.3s, matching the 5×1s sample interval). All 5 samples
printed exactly `Distance = 0.00 m`, exit code 0. The SAFETY warning
("ECHO outputs 5V and MUST go through a voltage divider before reaching
GPIO21 - not yet wired. Never connect ECHO directly to the Pi.") prints
prominently right after the header line, before any sampling starts. Also
confirmed the same warning is prominent in the module's docstring (read
directly, a whole dedicated `SAFETY` banner section near the top).
Status: PASS
Notes: None.

### ultrasonic.py: cleanup / re-run safety
Expected: GPIO20/21 released after exit; a second run doesn't error.
Actual: Ran the smoke test twice back-to-back, both exit 0, no exceptions.
`raspi-gpio get 20`/`get 21` read `fsel=0 func=INPUT` both before the first
run and after both runs.
Status: PASS
Notes: None.

### ultrasonic.py: notebook-style import
Expected: `sys.path.insert(0, 'src')` then
`from hardware.ultrasonic import get_ultrasonic_sensor, read_distance, cleanup` works.
Actual: Ran it; returned `distance=0.0`; printed `ultrasonic notebook-style
import OK`, exit code 0.
Status: PASS
Notes: None.

### ultrasonic.py: real distance measurements
Expected: N/A
Actual: N/A
Status: NOT TESTED — hardware not yet wired
Notes: The HC-SR04 is not physically connected (and its ECHO pin's mandatory
voltage divider is not wired either), so no real distance measurement can be
taken. Every reading observed above is the documented fail-safe `0.0` value,
not a real measurement.

### obstacle_avoidance.py: `auto_drive()` respects `max_duration_s`
Expected: Calling `auto_drive(motors, sensor, max_duration_s=2.5)` returns
at approximately 2.5s, not indefinitely.
Actual: Measured wall-clock elapsed time around the call: **3.31s** for a
requested 2.5s bound. This ~0.8s overshoot is expected and documented (see
below) — not a bug.
Status: PASS
Notes: See the overshoot-bound note below for why this isn't exactly 2.5s.

### obstacle_avoidance.py: `auto_drive()` respects a custom `stop_condition`
Expected: A `stop_condition` callable returning `True` causes `auto_drive()`
to exit early, independent of `max_duration_s`.
Actual: Called `auto_drive(motors, sensor, max_duration_s=10, stop_condition=stop_cond)`
where `stop_cond()` returns `True` on its 2nd call. Result: exited after
**1.10s** (vs. the 10s bound), `stop_condition` was called exactly twice,
and the printed stop reason correctly read `"stop_condition satisfied"` (not
the max-duration message).
Status: PASS
Notes: None.

### obstacle_avoidance.py: `max_duration_s` overshoot is bounded to ~1 maneuver, not unbounded
Expected (per Agent 1's note): since nothing is wired, `read_distance()`
always returns `0.0`, so `auto_drive()` always takes the "obstacle detected"
branch (~1s backup+turn maneuver) rather than the fast "clear path" branch —
so actual stop latency after `max_duration_s` can overshoot by up to ~1
maneuver's duration (~1s with default `backup_seconds`/`turn_seconds`), not
just the 0.1s loop interval. This is expected/documented, not a bug.
Actual: The 2.5s-bound test above overshot by 0.81s — comfortably within
the expected ~1s (one maneuver) ceiling, not unbounded or open-ended.
Status: PASS
Notes: Confirms Agent 1's characterization is accurate and the overshoot is
genuinely bounded, not a symptom of a runaway loop.

### obstacle_avoidance.py: real `KeyboardInterrupt` test — the safety-critical check
Expected: Sending a real `SIGINT` (Ctrl+C) to a running `auto_drive()` call
triggers its `finally: motor_stop(motors)` block, leaving GPIO12/13 (ENA/ENB)
electrically zero afterward — not just at the Python-object level.
Actual: This required two attempts to get an unambiguous, correctly-targeted
signal delivery, documented in full since it's the single most
safety-critical claim in this pass:
- **First attempt** (bash `python3 driver.py &`, capture `$!`, `kill -INT
  $PID` after 3s): the driver's log showed `auto_drive: stopping
  (max_duration_s=10s reached).` — i.e. it ran to its own natural time bound
  and never printed the `KeyboardInterrupt`-caught marker, meaning the
  signal was not actually delivered as an interrupt. Investigated rather
  than assumed: a plain `sleep 20 &` diagnostic in the same bash/SSH context
  also survived `kill -INT` untouched. Root cause: POSIX shells set `SIGINT`
  (and `SIGQUIT`) to `SIG_IGN` for background (`&`) jobs launched from a
  non-interactive script when job control is off (exactly this SSH/bash
  context) — and CPython, per its own startup behavior, leaves `SIGINT` as
  `SIG_IGN` (does not install its `KeyboardInterrupt`-raising handler) if it
  inherits that disposition already ignored. This is a test-harness
  artifact of how I originally launched the process, unrelated to
  `auto_drive()`/`motor.py`'s actual code — in real usage (an interactive
  terminal, or a notebook's "interrupt kernel" button), `SIGINT` is not
  pre-ignored this way.
- **Confirmation attempt**: relaunched via `subprocess.Popen(...)` from a
  small Python "runner" script instead of shell `&`-backgrounding, and used
  `proc.send_signal(signal.SIGINT)` — a direct OS-level signal send that
  bypasses shell job-control's automatic ignore-for-background-jobs
  behavior. Result: the driver's log now showed
  `CAUGHT_KEYBOARD_INTERRUPT_IN_DRIVER` (i.e. the exception was genuinely
  raised inside `auto_drive()`, propagated through its `finally` block, and
  was caught by the caller). Polled GPIO12, GPIO13, GPIO5, GPIO6, GPIO19,
  GPIO26 about 1s after sending the signal, **while the driver process was
  still alive and had not yet called `cleanup()`** (so pin state reflects
  active gpiozero-held values, not floating-after-close): **all 6 pins read
  `level=0`** — ENA and ENB (the actual safety-critical pins) both
  electrically zero, and all 4 direction pins zero too.
Status: PASS
Notes: The real result is unambiguous once the signal is delivered
correctly: `auto_drive()`'s `finally: motor_stop(motors)` genuinely fires on
a real `KeyboardInterrupt` and genuinely zeroes ENA/ENB electrically, not
just at the object level. Flagging the test-methodology lesson (not an
obstacle_avoidance.py bug) for future reference: testing signal-handling
behavior over SSH requires either an interactive-shell-equivalent process
launch or `subprocess.Popen`/`os.kill` from a controller script — plain
bash `command &` backgrounding in a non-interactive script silently ignores
SIGINT/SIGQUIT for the child, which can produce a false "it didn't work"
result that has nothing to do with the code under test.

### obstacle_avoidance.py: `avoid_obstacle()` pin-behavior spot-check
Expected: The backup+turn-right sequence inside `avoid_obstacle()` produces
the same IN1-4 pin patterns already verified individually for
`motor_backward()`/`right()` in the motor.py pass (composing them shouldn't
break anything) — a sanity spot-check, not a full statistical PWM re-test.
Actual: First attempt (naive bash-sleep-based polling) gave an ambiguous
result inconsistent with the code's declared execution order, so it was
redone properly: a small Python "runner" read the child process's stdout
live, captured the exact wall-clock timestamp of a `READY` marker printed
right before `avoid_obstacle()` was called, then polled GPIO5/6/19/26 at
precisely `READY+0.25s` (mid-backup, given the default 0.5s backup
duration) and `READY+0.75s` (mid-turn, given the default 0.5s turn
duration). Results:
- At +0.25s (backup phase): IN1=0,IN2=1 (left backward) and IN3=0,IN4=1
  (right backward) — both motors reversed, as expected.
- At +0.75s (turn-right phase): IN1=1,IN2=0 (left forward) and IN3=0,IN4=1
  (right backward) — exactly the `right()`/pivot-right pattern already
  verified in the motor.py pass.
Status: PASS
Notes: The initial ambiguous naive-polling attempt (not included in the
PASS determination) was a sampling-timing artifact from imprecise
Python-startup-latency assumptions, not a real inconsistency — resolved by
switching to timestamp-anchored polling, same lesson as the `stop()` test
in the motor.py pass.

### obstacle_avoidance.py: real obstacle detection/avoidance behavior
Expected: N/A
Actual: N/A
Status: NOT TESTED — hardware not yet wired
Notes: Neither the ultrasonic sensor nor the motors are physically
connected, so real obstacle detection and real avoidance maneuvers cannot
be confirmed. `read_distance()` always returns the documented fail-safe
`0.0`, so `avoid_obstacle()`/`auto_drive()` always take the "obstacle
detected" branch — everything reachable/testable at the software and
electrical-logic level in that branch was verified above.

### notebooks/03_l298n_motor_control.ipynb: movement/stop cell pairing (verified by reading actual cell source, not trusting the notebook's own claims)
Expected: Every movement cell (`left_forward`, `left_backward`,
`right_forward`, `right_backward`, `forward`, `backward`, `left`, `right`,
`set_speed`+`forward`) is paired with its own stop cell (or is
self-contained with a built-in `stop()` call), `motors = get_motors()` runs
once near the top and is reused throughout via kernel state, and the
notebook has a prominent safety warning before the first cell that actually
spins a motor.
Actual: Parsed the notebook's actual cell source (not the coordinator's
description) programmatically. Confirmed: `motors = get_motors()` appears
exactly once, in cell 5, alongside the full set of imports; every one of
the 9 movement cells (cells 9, 15, 21, 26, 32, 37, 42, 47, 53) is followed
by a dedicated stop cell (12, 17, 23, 28, 34, 39, 44, 49, 55 respectively)
with matching semantics (`left_stop`/`right_stop`/`stop` as appropriate) —
except the final movement cell (58: `set_speed(motors, 80, 30); forward(motors);
time.sleep(1); stop(motors)`), which is self-contained with its own
built-in `stop()` rather than relying on a following cell, exactly as its
own adjacent markdown cell (59) describes ("the first cell in this notebook
to include its own timed stop"). A prominent `SAFETY WARNING — READ BEFORE
RUNNING ANY CELL BELOW` markdown cell (cell 7) appears immediately before
the first movement cell, telling the reader to lift the chassis and keep it
lifted for the whole notebook.
Status: PASS
Notes: None.

### notebooks/03_l298n_motor_control.ipynb: full top-to-bottom execution
Expected: All 65 cells execute in order via
`jupyter nbconvert --to notebook --execute` with no errors; `cleanup(motors)`
at the end leaves everything stopped and released.
Actual: Confirmed proper nbformat cell `id` fields present (consistent with
Notebook 02's fix). Polled all 6 motor pins immediately before and after the
run to bookend it. Ran
`jupyter nbconvert --to notebook --execute --output
03_l298n_motor_control.executed.ipynb 03_l298n_motor_control.ipynb` from
`~/raspberry_pi_robot/notebooks/` under a `timeout 90` safety net (completed
comfortably within it, in ~17.2s), exit code 0. Parsed the executed
notebook's outputs programmatically: zero `error` outputs across all 65
cells. Cell 5 printed "Motors ready. Both enable pins at 0% - nothing should
be moving."; cell 61 (final `cleanup(motors)`) printed "Motors stopped and
all GPIO released." with no error. All 6 pins (ENA=12, IN1=5, IN2=6, ENB=13,
IN3=19, IN4=26) read `fsel=0 func=INPUT` both before the run started and
after it finished, confirming a clean release.
Status: PASS
Notes: Since this notebook's movement/stop cell pairs have no artificial
delay between them (nbconvert executes consecutive cells back-to-back,
typically within milliseconds of each other, unlike a student manually
pausing between cells to observe), each "motor on" state in an unattended
`--execute` run only persists for on the order of milliseconds before the
paired stop cell runs — meaning even once physically wired, running this
specific notebook via unattended batch execution (as opposed to interactive
cell-by-cell use, which is its actual intended use per the SAFETY WARNING
cell) would not leave a motor energized for any physically meaningful
duration between cells. Not a bug, just a favorable side effect worth
noting. Cleaned up my own test artifacts (executed-notebook copy, scratch
checker script) from the Pi afterward — only the three original notebooks
remain in `notebooks/` on the Pi.

---

## Notebook 04 — ultrasonic_obstacle_avoidance (closes out the 01-04 arc)

New notebook from Agent 3 (`notebooks/04_ultrasonic_obstacle_avoidance.ipynb`,
36 cells) re-synced to the Pi and executed. This is the highest-stakes
unattended-execution notebook in the arc so far: its `auto_drive()` demo
cell (`auto_drive(motors, sensor, max_duration_s=5)`) deliberately overrides
the 30s default down to 5s for a faster classroom demo, and — since nothing
is wired and `read_distance()` always returns the fail-safe `0.0` — every
single call in this notebook sees "an obstacle," so the whole notebook is
continuous motor activity from the moment `get_motors()` is called through
the end of `auto_drive()`'s 5-second window, not the calmer "drive straight,
rarely react" case. Treated this run with the same care as Notebook 03.

### Full top-to-bottom execution + continuous pin-trace monitoring
Expected: All 36 cells execute in order via
`jupyter nbconvert --to notebook --execute` with no errors; proper unique
nbformat cell `id` fields (consistent with 01-03 post-fix); the `auto_drive()`
demo actually stops at ~5s (+ up to ~1 maneuver's overshoot, per the bound
already characterized in the obstacle_avoidance.py pass), with all motor
pins electrically zero afterward — not just "no error printed."
Actual: Confirmed `id` fields present on all 36 cells before running.
Backgrounded `jupyter nbconvert --execute` and continuously polled all 6
motor pins (ENA=12, ENB=13, IN1=5, IN2=6, IN3=19, IN4=26) every ~0.34s for
the entire run via a `while kill -0 $PID` loop with real timestamps, rather
than just checking before/after. Total run: 28.1s, exit code 0. The pin
trace showed: floating-HIGH on all 6 pins (expected — unclaimed) for the
first ~18s while the notebook works through the ultrasonic-only cells
(sensor setup, single read, 8×0.5s sample loop, `cleanup_sensor()`, none of
which touch motor pins); then, starting at the `motors = get_motors()` cell,
a continuous ~7-second window of genuinely switching, non-static
direction/PWM pin combinations (covering the `forward()`+obstacle-check
loop, the `avoid_obstacle()` call, and the `auto_drive(max_duration_s=5)`
call all running back-to-back with no notebook-level pause between them,
so their individual sub-windows blend together in a continuous trace at
this sampling resolution — but this matches the earlier, already-verified
finding that these calls run seamlessly and bounded, not open-ended); then
a clean, distinct **all-six-pins-exactly-zero** sample; then, one sample
later, all six pins flip to the floating-HIGH pattern (released via
`cleanup_motors()`/`cleanup_sensor()` in the final cell). This is exactly
the same "genuine stop, then release" signature already verified rigorously
(with SIGINT and exact timing) for the underlying `motor.py`/
`obstacle_avoidance.py` functions in the prior pass — here it's confirmed
to also hold when those same functions are driven from the actual notebook,
not just from a standalone script.
Status: PASS
Notes: None.

### auto_drive() demo cell: confirmed stopped via its own time bound, not truncated by anything else
Expected: Cell 29 (`auto_drive(motors, sensor, max_duration_s=5)`) prints
its own stopping reason, confirming it exited via the 5s bound rather than,
say, an exception or an early unrelated break.
Actual: Cell 29's captured output reads exactly
`auto_drive: stopping (max_duration_s=5s reached).` — the same message
format already verified in the standalone obstacle_avoidance.py pass, now
confirmed to fire correctly when called from within the notebook with the
overridden 5s value.
Status: PASS
Notes: None.

### "0.00m until wired = fail-safe, not an error" — output stays consistent, no false errors
Expected: Every reading shows the documented `0.00 m` fail-safe value; the
background `PWMSoftwareFallback`/`DistanceSensorNoEcho`-style gpiozero
warnings (if any appear) don't get mistaken for real errors, and no cell
actually raises an exception because of the always-0.0 reading.
Actual: Cell 8 (`Distance = 0.00 m`) and all 8 samples in cell 11
(`Sample N/8: Distance = 0.00 m`) are consistent. Cell 21's obstacle-check
loop detected an obstacle on check 1/20 and broke immediately (`Check
1/20: obstacle detected = True` / `Done.`) — consistent with the documented
behavior, not a hang or an error. Cell 25's `avoid_obstacle()` reported
`Obstacle handled this call: True`. Programmatically confirmed zero
`output_type: error` entries across all 36 cells — the `PWMSoftwareFallback`
gpiozero warning that appears in cell 5's output is captured as a `stream`
(stdout/stderr text) output, not an `error` output, and does not represent
an exception or failure.
Status: PASS
Notes: None.

### Sensor close-then-reopen transition (cell 14 → cell 18)
Expected: `cleanup_sensor(sensor)` (cell 14, closing the first
`DistanceSensor`) followed later by `sensor = get_ultrasonic_sensor()`
inside cell 18 (opening a fresh one, alongside `motors = get_motors()`)
executes cleanly, same pattern as the `Button(27)`→`close()`→`get_button()`
transition already verified in Notebook 02.
Actual: Cell 14 printed `Sensor GPIO released.` with no error; cell 18
printed `Motors and sensor ready.` with no error — confirming GPIO20/21
were cleanly reclaimed by the fresh `get_ultrasonic_sensor()` call right
after the first sensor object released them, with no "pin already in use"
or similar conflict.
Status: PASS
Notes: None.

### Real sensor readings / real obstacle avoidance behavior
Expected: N/A
Actual: N/A
Status: NOT TESTED — hardware not yet wired
Notes: Neither the HC-SR04 nor the L298N/motors are physically connected,
so real distance measurements and real reactive-avoidance behavior cannot
be confirmed. Every reading and every "obstacle detected" branch observed
in this run reflects the documented fail-safe `0.0` default, already
characterized in the ultrasonic.py and obstacle_avoidance.py sections
above.

---

## Vision module (`src/vision/`) and install script's picamera2/numpy ABI
## fixup (added in a later QA pass — picking up fresh after an environment
## restart; this pass independently re-verified everything below rather
## than trusting Agent 1's own prior report of it)

Physical/environmental state at time of this pass: same Pi, same
`~/raspberry_pi_robot/` checkout (confirmed byte-identical to the dev
laptop's `src/vision/*.py` via `md5sum` before testing). Only the Pi Camera
Module v2 is relevant hardware here, and it is physically connected. The
room this Pi sits in had **no usable ambient or artificial light** at the
time of testing (confirmed below) despite testing during Pi-local daytime
hours (~11:13 AM) — this blocked the two highest-priority "real object,
real light" checks the task asked for; see those sections' NOT TESTED
entries for detail, and the "Needs human attention" note at the end of
this file.

### Install script: picamera2/numpy ABI fixup (simplejpeg reinstall)
Expected: Per Agent 1's design-notes comment in
`install_pi_dependencies.sh`, if `import picamera2` fails (e.g. because a
newer `--user` numpy from the OpenCV pip fallback shadows the system numpy
that apt's `python3-simplejpeg` was compiled against), the script should
detect this, run
`pip3 install --user --force-reinstall --no-cache-dir simplejpeg`, and
re-check, printing a WARNING (not aborting) if still broken. Re-running the
script afterward should print "picamera2 already importable, skipping
simplejpeg fixup." (idempotent).
Actual: Independently reproduced the bug from a clean-ish state rather than
trusting Agent 1's prior report: confirmed `numpy 2.0.2` was the active
`--user` numpy, then `pip3 uninstall -y simplejpeg` on the Pi. Confirmed
`python3 -c "import picamera2"` then failed with the exact documented
error:
```
ValueError: numpy.dtype size changed, may indicate binary incompatibility.
Expected 96 from C header, got 88 from PyObject
```
(traceback confirmed the failure path is genuinely through
`simplejpeg/_jpeg.pyx` via `picamera2/encoders/jpeg_encoder.py`, not some
unrelated error.) Copied the current `install_pi_dependencies.sh` to the Pi
and ran it: the "picamera2/numpy ABI check" section correctly detected the
broken import, ran the `simplejpeg` force-reinstall (pulled a prebuilt
`simplejpeg-1.9.0` aarch64 wheel from piwheels, alongside a matching
`numpy-2.0.2` wheel — no version change), and its own post-fix re-check
printed "picamera2 now imports successfully after simplejpeg fixup."
Independently confirmed with a fresh `python3 -c "import picamera2"` call
(exit 0). Re-ran the full script a second time immediately after: printed
"picamera2 already importable, skipping simplejpeg fixup." with no
reinstall attempted — confirming idempotency, matching the pattern already
established for the OpenCV and JupyterLab sections of this same script.
Status: PASS
Notes: Genuinely reproduced-and-fixed, not just trusted from Agent 1's
report. Nothing needs to go back to Agent 1 for this fix.

### camera.py: direct-run smoke test
Expected: `python3 src/vision/camera.py`, run from
`~/raspberry_pi_robot/` on the Pi, configures/starts a `Picamera2`,
captures one frame, prints its shape/dtype, saves it to
`/tmp/camera_smoke_test.jpg`, and cleanly releases the camera.
Actual: Ran successfully, exit code 0. Printed
`Captured frame: shape=(480, 640, 3), dtype=uint8` and
`Saved to /tmp/camera_smoke_test.jpg`, followed by `Camera released.`. File
retrieved via `scp` and confirmed to be a valid, readable JPEG matching
that shape.
Status: PASS
Notes: The captured scene was very dark (see the color-order section
below) — that is an environmental issue, not a pipeline issue; the
capture/save mechanics themselves worked correctly.

### camera.py: notebook-style import
Expected: From a `notebooks/`-style working directory, adding `src/` to
`sys.path` and doing
`from vision.camera import get_camera, capture_frame, cleanup` works, same
pattern already established for every `src/hardware/` module.
Actual: Ran from `~/raspberry_pi_robot/notebooks/` with
`sys.path.insert(0, str(Path.cwd().parent / "src"))`, then imported both
`vision.camera` and `vision.color_detection` and exercised the full
pipeline (`get_camera` → `capture_frame` → `bgr_to_hsv`/`detect_color`/
`largest_blob` → `cleanup`) in one process. Completed with no exceptions;
printed correct shapes for the frame `(480, 640, 3)`, the HSV image
`(480, 640, 3)`, and the mask `(480, 640)`.
Status: PASS
Notes: None.

### camera.py: cleanup / re-run safety
Expected: `cleanup(camera)` genuinely releases the camera device, and a
second `get_camera()`/`capture_frame()`/`cleanup()` cycle in the same
process does not error with a "device busy"/resource-in-use error.
Actual: Ran two sequential full cycles
(`get_camera()` → `capture_frame()` → `cleanup()`, print, repeat) in a
single Python process. Both cycles completed cleanly with correct frame
shape/dtype and no exception; explicit success message printed at the end.
Status: PASS
Notes: None.

### camera.py: BGR/RGB color-order visual confirmation (real object, real light)
Expected: Per the task and per `camera.py`'s own module docstring
(the "CAVEAT FOR QA" note), this needed to be confirmed by eye against a
real, identifiably-colored object under real lighting — not just by pixel
statistics, since Agent 1's own prior verification was done in a room too
dark (~1 lux) to do this visually.
Actual: Attempted this directly. `python3 src/vision/camera.py`'s default
capture was still essentially pure black
(`mean BGR ≈ [2.1, 2.1, 1.1]`, max pixel value 46 out of 255) — visually
confirmed as a fully black frame, no discernible content of any kind, let
alone color. This was not simply "dim room lighting": to rule out a
lighting-not-object problem, also ran a manual capture with
`AnalogueGain=16.0` and `ExposureTime=200000` (200ms, 16x gain — a very
aggressive low-light setting) and got `mean ≈ 6.3/255`, still visually
indistinguishable from black when viewed. This was checked at ~11:13 AM
Pi-local time (confirmed via `date` on the Pi), i.e. during daytime, so
the lack of any signal even at extreme exposure/gain indicates either no
ambient light reaches the sensor at all in this location, or the lens is
obstructed/covered — not merely "needs brighter lighting." No colored
object was available to place in frame either way.
Status: **NOT TESTED — no usable light source available in the test
environment; confirmed the room (or camera's view) has effectively zero
light even at 200ms exposure / 16x gain during Pi-local daytime, ruling
out "just needs brighter light" as an easy fix from here.**
Notes: **This is the single highest-priority open item from this QA
pass.** The BGR-vs-RGB channel-order logic in `capture_frame()` has NOT
been visually confirmed correct against a real color, despite that being
the explicit point of this check (pixel-statistics verification, which
Agent 1 already did, cannot by itself rule out a channel swap producing a
plausible-looking but wrong result on a real photo — only eyes on a real
photo of a real known color can). Needs a human to physically bring a
light source to the Pi's camera (or move the Pi/camera to a lit area) and
place a distinctly-colored object (red/green/blue paper, clothing,
anything identifiable) in frame, then re-run
`python3 src/vision/camera.py` and visually inspect the resulting
`/tmp/camera_smoke_test.jpg` to confirm colors are NOT swapped.

### color_detection.py: direct-run smoke test
Expected: `python3 src/vision/color_detection.py` captures one real frame
via `vision.camera`, runs `detect_color()`/`largest_blob()` for RED,
GREEN, and YELLOW, and prints either a detected blob or a
"no blob detected" line for each, then cleanly releases the camera.
Actual: Ran successfully, exit code 0. Printed
`Captured frame: shape=(480, 640, 3), dtype=uint8`, then for each of RED,
GREEN, YELLOW: `no blob >= 200px detected`, then `Camera released.`. This
is the correct, expected output for a black/empty scene (no false
positives on a scene with no actual color content) — consistent with the
camera section above.
Status: PASS
Notes: None.

### color_detection.py: notebook-style import
Expected: `from vision.color_detection import bgr_to_hsv, detect_color,
largest_blob` works from a notebook-style `sys.path` setup, same as
`vision.camera`.
Actual: Covered in the same combined run as camera.py's notebook-style
import test above — imported and called `bgr_to_hsv()`, `detect_color()`,
and `largest_blob()` successfully in one process, correct return
shapes/types.
Status: PASS
Notes: None.

### color_detection.py: synthetic-image logic sanity check (supplementary check I added — NOT a substitute for real-object testing)
Expected: N/A — this was not one of the requested checks, but was added
as a partial mitigation given the real-object check below could not be
completed, to at least separate "is the HSV threshold/contour/moment code
logic correct" from "are the tuned HSV ranges correct for a real
object/sensor/lighting", since both would otherwise be equally unverified.
Actual: On the Pi, using the actual installed `cv2`/`numpy` and the actual
`detect_color()`/`largest_blob()` functions (not reimplemented logic),
built synthetic BGR test frames: a 200x200 pure-color rectangle
(BGR `(0,0,255)` red, `(0,255,0)` green, `(0,255,255)` yellow) on a gray
background. All three were correctly detected with the expected centroid
`(300, 250)`, bbox, and area (~40000px, matching the 200x200 square).
Additionally, specifically targeted the documented RED hue-wraparound
gotcha: built two more synthetic frames directly from HSV values at each
edge of the wraparound (`H=178`, near the top of the range, and `H=3`,
near the bottom) via `cv2.cvtColor(..., COLOR_HSV2BGR)`, then ran them
through `detect_color(frame, "RED")`. Both were correctly detected
(correct centroid/bbox/area), confirming the two-range-OR'd mask in
`HSV_RANGES["RED"]` genuinely covers both ends of the wraparound in the
real running code, not just in the module's documentation/theory.
Status: PASS (algorithm/logic only)
Notes: This confirms the HSV-threshold/contour/moment code itself has no
bugs, and specifically that the RED hue-wraparound handling genuinely
works end-to-end in the real installed code. It does **not** confirm the
specific tuned H/S/V numeric ranges in `HSV_RANGES` actually match real
red/green/yellow objects as seen through the real imx219 sensor/ISP color
pipeline under real lighting — that is a distinct, still-open question,
covered by the NOT TESTED item immediately below. Do not read this PASS
as covering that.

### color_detection.py: detection against real RED/GREEN/YELLOW objects
Expected: Per the task and per `color_detection.py`'s own module
docstring's QA note, real red, green, and yellow objects (construction
paper, toys, anything on hand) needed to be placed in front of the camera
under real lighting to confirm `detect_color()`/`largest_blob()` actually
detect each one with a reasonable bounding box/centroid, since the
`HSV_RANGES` values are unvalidated reference defaults.
Actual: Blocked by the same environmental issue as the camera color-order
check above — the scene visible to the camera is effectively pure black
even at 200ms exposure/16x gain, so there is no visible content of any
color for `detect_color()` to be meaningfully tested against, and no
colored object was available to place in frame regardless of lighting.
Status: **NOT TESTED — no light source and no colored object were
available in the test environment.**
Notes: This must be re-run once lighting/an object are available:
point the camera at real red, green, and yellow objects and run
`python3 src/vision/color_detection.py` (or the notebook-style
equivalent), and check whether each color is actually detected with a
sane bbox/centroid. Per Agent 1's own guidance (repeated here for
whoever does this next): if a color fails to detect, widen/narrow the S
and V bounds first (lighting/washout issues) before touching the H
bounds (the actual hue) — and per this pass's synthetic check above, the
underlying detection code itself is already confirmed logically correct,
so any real-object failure found later is much more likely to be an
`HSV_RANGES` tuning issue than a code bug.

---

## AI Drive Controller (`src/robot/ai_drive.py`) and Object Detection
## (`src/vision/object_detection.py`) — the most safety-critical module in
## the project so far (added in a later QA pass)

This module continuously drives real motors from live camera input at
~10Hz, with ultrasonic obstacle-avoidance as the top-priority safety
check. Agent 1 reported substantial prior verification of this module
(priority-branch unit tests, a 5s/50-iteration real loop run at ~9.98Hz,
real SIGINT/SIGTERM tests). Per this project's standing QA convention,
none of that was taken on trust — everything below was independently
re-derived from scratch on the real Pi. Physical state unchanged from the
rest of this file: nothing is physically wired except the camera, so
every GPIO-level claim below is electrical/logical, not a claim about
real wheel movement (see "Needs human attention" for the standing note on
this). `models/car_detection.onnx` does not exist (confirmed and left in
that same state after testing) and `src/config.py`/`ai_drive.py` were
confirmed byte-identical between the dev laptop and the Pi via `md5sum`
before testing began.

### Sticky-RED state machine: direct method-level testing of `_decide_and_act()`
Expected: Per the module docstring and this task's brief, `RED` should
set `_stopped_for_red` and stop the robot; the robot should stay
**stopped** through a subsequent ambiguous/colorless (`None`) frame; and
the sticky state should clear on `GREEN` specifically, and also on "RED
no longer detected" more generally (some other definite color, or `None`)
— not only on `GREEN`.
Actual: Called `_decide_and_act()` directly with controlled
`(distance_m, color, car_result)` inputs (same approach Agent 1 used) and
asserted on both `controller._stopped_for_red` and `controller.status`
after each call:
- `RED` → `_stopped_for_red=True`, `action="stop"`. Confirmed.
- `RED` then `None` → **`action` stays `"stop"`** (confirmed — the robot
  never resumes on an ambiguous frame), **but `_stopped_for_red` itself
  flips to `False`** on that same `None` frame, not just on `GREEN`. This
  is because the actual guard is
  `if color == "GREEN" or color != "RED": self._stopped_for_red = False`
  — since `None != "RED"` is `True`, `None` clears the flag exactly like
  any other non-RED color would. The robot still shows `action="stop"`
  for that frame only because case 7's safe-default ("nothing
  recognized") independently also stops — not because the sticky flag
  protected it.
- `RED` then `GREEN` → flag clears, `action="forward"`. Confirmed.
- `RED` then `YELLOW` (a definite non-RED, non-GREEN color, no `None` in
  between) → flag clears, robot attempts the YELLOW turn (aborted
  instantly by the fail-safe `0.00m` ultrasonic reading, unrelated - see
  the SIGTERM section for why 0.00m always aborts turns with nothing
  wired). Confirms "RED no longer detected, non-GREEN color" also clears
  the flag as intended.
- `RED` `x3` in a row → flag stays `True`, stays stopped throughout.
  Confirmed.
- **The scenario that actually matters**: `RED` → `None` → `BLUE`, three
  separate `_decide_and_act()` calls. Because the sticky flag already
  cleared on the middle (`None`) call, the third call (`BLUE`) is
  evaluated as a **fresh, non-sticky** decision and genuinely attempts the
  BLUE turn (`motor_turn_left` was called) — i.e. the robot can resume
  driving/turning immediately after a single ambiguous frame, without
  ever having seen an explicit `GREEN`.
Status: PASS for the specific three behaviors this task asked to confirm
(RED sets the flag and the robot stays stopped through one ambiguous
frame; GREEN clears it; a non-GREEN/non-RED color or `None` also clears
it) — all three hold exactly as asked, and this also technically matches
the module docstring's own literal wording ("...GREEN, or RED is no
longer detected at all" — `None` **is** "RED no longer detected").
Notes: **Flagging back to Agent 1 as worth a second look, not a hard
bug**: the docstring's plain-English framing ("stays stopped ... even
through a momentarily ambiguous/colorless frame") reads, to a first-time
reader, as "the STICKY PROTECTION persists through an ambiguous frame,"
but what's actually implemented is "the ROBOT'S ACTION happens to stay
stop for that one frame, because the safe-default also stops — but the
protection itself is gone the instant a `None`/ambiguous frame is seen."
The practical consequence: if the camera reports one noisy/ambiguous
frame immediately after a real RED sighting (very plausible - a
motion-blurred frame, a hand briefly obscuring the lens, a lighting
flicker), and the very next frame reports BLUE, YELLOW, or GREEN, the
robot will act on it immediately - turn or drive forward - without ever
having explicitly seen GREEN. Whether that one-frame gap is an acceptable
design tradeoff or should require an explicit GREEN (or N consecutive
non-RED frames) to fully clear is a product decision for Agent 1/the
user, not something this pass unilaterally changed - noting the exact
mechanics here so it's a fully-informed decision either way.

### SIGTERM: real signal sent to a genuinely-driving process, GPIO12/13 polled through shutdown
Expected: Sending a real `SIGTERM` to a running `AIDriveController.run()`
process (launched via `subprocess.Popen`, signalled via
`proc.send_signal()` — not shell `&`-backgrounding, per this project's
own documented SIGINT/background-job pitfall) triggers `request_stop()`,
the loop exits at its next iteration boundary, and `run()`'s `finally:
motor_stop(...)` genuinely zeroes GPIO12/GPIO13 (ENA/ENB) — not just at
the Python-object level — while the process is still alive, before
`cleanup()` even runs.
Actual: This needed a real, *actively driving* process to be a meaningful
test — with nothing physically wired, the ultrasonic's fail-safe `0.00m`
reading makes priority-1 ("obstacle too close") fire on every single
iteration, so the loop would just idle in `stop` forever and never
exercise a real "was moving, now stopped" transition. To get a genuine
test, `read_distance` was monkeypatched to always return a safe `1.0m`
and `_detect_dominant_color` was monkeypatched to always return
`"GREEN"` — both are pure *input* patches on real, unmodified
`ai_drive.py`/`motor.py`/GPIO code; nothing under test was reimplemented
or bypassed. Launched via `subprocess.Popen`, confirmed via live status
prints that the loop was genuinely commanding `action="forward"` for 3
consecutive iterations (~200ms of real, GPIO-level PWM-driven motion) at
t=2.035s, then sent `SIGTERM`. To get an unambiguous read on the pins
(a single snapshot can't distinguish "genuinely stopped" from "caught
mid-low-phase of an active 50%-duty-cycle PWM cycle" — the same pitfall
already documented in this file for `motor.py`'s own `stop()` test), the
test harness (not `ai_drive.py` itself) inserted a deliberate 3-second
sleep between `run()` returning and `cleanup()` being called, creating a
wide, unambiguous window where the motors are definitely already stopped
by `run()`'s own `finally` block but the pins are definitely not yet
released. Results, with real wall-clock timestamps:
- t=2.035s: confirmed actively driving forward (3rd consecutive
  `action=forward`).
- SIGTERM sent immediately after.
- t=2.047s-2.106s (~60-90ms window): a handful of mixed 0/1 samples on
  both GPIO12 and GPIO13, still `fsel=OUTPUT`. This is expected, not a
  bug: `SIGTERM`'s handler only sets a flag (`request_stop()`); per
  PEP 475, CPython automatically retries an interrupted `time.sleep()`
  rather than aborting it early, so the current iteration's PWM output
  can legitimately still be active for up to ~1 loop period
  (`AI_DRIVE_LOOP_HZ`=10 → ~100ms) after the signal arrives, before the
  loop next checks `_stop_requested` and exits. `forward()`'s default
  speed is 50%, so a single snapshot during this window is close to a
  coin flip - consistent with what was observed.
- t=2.115s through t=5.098s (**~3.0 continuous seconds, ~80+ samples**):
  GPIO12 and GPIO13 **both read `level=0`, `fsel=OUTPUT`, on every single
  sample, with zero exceptions** - this is the unambiguous window
  (motors definitely already stopped by `run()`'s `finally` block, pins
  definitely not yet released) and it is completely clean.
- t=5.157s: `cleanup()` called (matches the harness's own log line); both
  pins' `fsel` flips to `INPUT` in the very next sample.
- t=5.213s onward: both pins read `level=1`, `fsel=INPUT` - floating HIGH
  after release, the same already-documented pattern seen throughout this
  file for every other module's cleanup path (no pull-down, expected).
- Process exited with code 0; `cleanup()`'s own print confirmed it ran to
  completion.
Status: PASS
Notes: The brief ~60-90ms mixed-reading window right after the signal is
a real, expected, and safe artifact of SIGTERM's flag-based
(not syscall-interrupting) stop mechanism combined with PEP 475's
sleep-retry behavior - not a bug, and not a safety gap, since the
`finally` block is still guaranteed to run within one loop period and the
subsequent 3-second window proves it genuinely did. This is the single
most safety-critical property in the project and it held up rigorously.

### SIGINT: same test, for completeness
Expected/Actual: Same harness, same monkeypatches, `SIGINT` instead of
`SIGTERM`. Confirmed driving forward at t=2.040s, sent `SIGINT`. Result
was, if anything, cleaner than SIGTERM: **from t=2.049s (9ms after the
signal) through t=5.040s (~3.0 continuous seconds, ~140+ samples), both
GPIO12 and GPIO13 read `level=0`, `fsel=OUTPUT` with zero exceptions** -
no ambiguous transient at all, consistent with `KeyboardInterrupt` being
raised synchronously (interrupting the current operation immediately)
rather than only being checked at the next loop-top like the SIGTERM
flag. `cleanup()` ran at t=5.099s, pins floated HIGH afterward as
expected. Process exited 0.
Status: PASS
Notes: Confirms the module docstring's own claim that SIGINT works when
delivered as a real OS-level signal (via `Popen`/`send_signal`, not shell
`&`-backgrounding) even though this was launched non-interactively over
SSH - consistent with Agent 1's and the earlier `obstacle_avoidance.py`
pass's finding that the *actual* SIGINT pitfall is shell job-control
ignoring it for background jobs, not "must be a literal interactive
terminal."

### `_timed_turn()`: obstacle-abort-mid-turn, controlled/monkeypatched sensor
Expected: `_timed_turn()` should call `read_distance()` repeatedly at the
loop's cadence *during* a turn (not just once at the start), and abort
the turn immediately (stopping the motors, setting an "obstacle ...
turn aborted" status) if the sensor reports a too-close reading partway
through - not just run the full commanded duration regardless.
Actual: Monkeypatched `read_distance` with a stateful fake: returns a
safe `1.0m` for the first 5 calls, then `0.05m` (well under the default
`0.25m` threshold) from the 6th call onward - simulating an obstacle
appearing mid-turn. This only patches the sensor's *input*; the real
`_timed_turn()` method (real polling loop, real `motor_stop()` calls) was
called directly, unmodified.
- **Obstructed case**: `_timed_turn(motor_turn_left, duration_s=2.0, ...)`
  actually returned after **0.501s**, not the full 2.0s -
  `read_distance` was called 6 times (i.e. genuinely polled repeatedly at
  the loop cadence, not just once up front) before the abort triggered on
  the 6th call. Final status: `action="stop"`,
  `stop_reason="obstacle at 0.05m (turn aborted)"`.
- **Unobstructed control case**: with `read_distance` returning `1.0m`
  unconditionally, `_timed_turn(motor_turn_left, duration_s=1.0, ...)`
  ran for the full **1.002s** (matching the commanded duration, not
  cut short), with `stop_reason=None` (a normal, non-aborted turn end) -
  confirming the abort logic doesn't fire spuriously when nothing is
  actually close.
Status: PASS
Notes: This confirms `_timed_turn()` is a genuine safety sub-loop, not a
blind `time.sleep(duration_s)` with a single check bolted on - exactly as
the module docstring claims. Nothing needs to go back to Agent 1 here.

### `object_detection.py`: missing and corrupt model handling
Expected: `get_car_detector()` returns `None` (never raises) for both a
missing model file and a present-but-corrupt one; `detect_cars(None,
frame)` never raises and is cheap (this path runs ~10x/second in the real
loop and must not add real latency with no model loaded).
Actual: Confirmed `models/car_detection.onnx` did not exist (matching the
project's real current state), called `get_car_detector()` → `None`,
logged one clear warning as documented. Ran `detect_cars(None,
dummy_frame)` 200 times back-to-back and timed it: **average 0.0011ms per
call** - i.e. genuinely a cheap no-op, nowhere near the ~100ms/iteration
loop budget. Then wrote 400 bytes of garbage (not a valid protobuf) to
the model path and called `get_car_detector()` again: it caught the
resulting `onnxruntime.capi.onnxruntime_pybind11_state.InvalidProtobuf`
exception internally (visible in the log as a full traceback under a
`WARNING`-level `logger.warning(..., exc_info=True)` call - this is
`object_detection.py` logging the caught exception on purpose, not an
uncaught crash) and returned `None` cleanly, same as the missing-file
case. `detect_cars(None, frame)` after that was still correct and safe.
Removed the garbage file afterward, confirmed `models/car_detection.onnx`
does not exist again (project left in its original state).
Status: PASS
Notes: None - matches Agent 1's own prior report exactly, independently
reproduced.

### Standard checks: direct-run, notebook-style import, cleanup/re-run safety
Expected: `python3 src/robot/ai_drive.py` (its own `__main__` bounds
itself to `max_duration_s=30`) runs to completion and exits cleanly;
`from robot.ai_drive import AIDriveController` works from a
notebook-style `sys.path` setup; constructing and cleaning up the full
controller (camera + motors + rgb LED + ultrasonic all at once) twice in
a row in the same process does not hit a "device busy"/resource-in-use
error on any of the four hardware handles.
Actual:
- Direct-run: ran the real, unmodified `python3 src/robot/ai_drive.py`.
  Ran the full 30s, logged
  `ai_drive: max_duration_s=30 reached, stopping.`, then
  `Camera stopped` / `Camera closed successfully.` and the script's own
  `AI drive controller cleaned up, all GPIO/camera released.` — exit code
  0.
- Notebook-style import: from `~/raspberry_pi_robot/notebooks/`, with
  `sys.path.insert(0, str(Path.cwd().parent / "src"))`,
  `from robot.ai_drive import AIDriveController` succeeded with no
  exceptions.
- Cleanup/re-run safety: constructed a full `AIDriveController()` (all
  four hardware handles: camera, motors, rgb LED, ultrasonic, plus the
  (missing) car detector), ran one real `_decide_and_act()` call, called
  `cleanup()`, then repeated the entire cycle a second time in the same
  process - both cycles completed with no exceptions and no "already in
  use"/"device busy" errors of any kind.
Status: PASS
Notes: None.

---

## Web control server (`web/app.py`) — the last major piece before the
## project is feature-complete (added in a later QA pass)

This is Flask-based manual/AI mode-switching control server, tested by a
second, web-focused Agent 1 instance and independently re-verified here
per this project's standing convention. Confirmed `web/app.py` and
`src/robot/ai_drive.py` (which now carries the sticky-RED fix - `if color
== "GREEN":` - applied directly by the coordinator, spot-checked below,
not re-derived from scratch since the coordinator already did a direct
unit-level re-verification) were byte-identical between the dev laptop
and the Pi via `md5sum` before testing. Physical state unchanged: nothing
is physically wired except the camera, so every GPIO-level claim below is
electrical, not real wheel movement.

### Install script: Flask/Werkzeug fixup, independently reproduced
Expected: `install_pi_dependencies.sh`'s Flask self-test step (build a
real `Flask` app, route a request through `test_client()`, not just
`import flask`) should detect the documented apt-Flask-1.1.2 /
pip-Jinja2-3.1.6 `ImportError: cannot import name 'escape'` breakage,
fix it by pinning `flask~=2.2.5`/`werkzeug~=2.2.3` together, and be
idempotent on a second run.
Actual: Confirmed apt still has `python3-flask 1.1.2-2+deb11u1`
installed underneath the working pip `flask~=2.2.5`. `pip3 uninstall -y
flask werkzeug` to fall back to the apt version, then
`python3 -c "from flask import Flask; Flask(__name__)"` reproduced the
exact documented error:
`ImportError: cannot import name 'escape' from 'jinja2'`. Ran the real
`install_pi_dependencies.sh`: it detected the break ("Flask is not
working"), reinstalled `flask~=2.2.5`/`werkzeug~=2.2.3` via pip, and its
own post-fix self-test confirmed "Flask now works (import + real request
round-trip) after the fixup." Independently confirmed
`flask.__version__`/`werkzeug.__version__` → `2.2.5`/`2.2.3`. Ran the
script a second time: printed "Flask already working (import + real
request round-trip), skipping install." - idempotency confirmed.
Status: PASS
Notes: Genuinely reproduced-and-fixed, matching the same rigor as the
picamera2/simplejpeg and tornado fixups earlier in this file.

### Server starts and responds; POST /api/command electrically verified via raspi-gpio
Expected: `python3 web/app.py` starts and serves `GET /` (200) and
`GET /api/status` (valid JSON); `POST /api/command {"action": "forward",
"speed": N}` should produce the exact same IN1/IN2/IN3/IN4/ENA/ENB
pattern already verified for `motor.py`'s own `forward()` in this file's
motor.py section, cross-checked via `raspi-gpio`, not just the HTTP
response.
Actual: Launched via `nohup ... &` (a real detached OS process, checked
independently via `ps aux`, not relied upon for signal-handling tests
later). `GET /` → HTTP 200. `GET /api/status` → valid JSON
(`{"action":"stop","camera_available":true,"mode":"manual",
"speed_percent":50}`). `POST /api/command {"action":"forward",
"speed":80}` → `{"ok":true,...}`, and polling immediately afterward
(within the 1.5s watchdog window) showed GPIO5(IN1)=HIGH,
GPIO6(IN2)=LOW, GPIO19(IN3)=HIGH, GPIO26(IN4)=LOW - exactly the
`Motor(forward=IN1, backward=IN2, pwm=False).forward()` pattern already
verified directly against `motor.py` earlier in this file - and
GPIO12/13 (ENA/ENB) showed ~80% HIGH across 10 rapid samples, consistent
with the commanded 80% speed.
Status: PASS
Notes: None.

### Mode-switch resource exclusivity - WITHIN the server process: PASS; ACROSS processes: real gap found, flagged to both Agent 1 instances
Expected: Per the module docstring, exactly one of "manual handles" or
"an AIDriveController" should ever hold the motor/camera GPIO at once,
enforced so that gpiozero/picamera2 "will raise a pin/resource-already-
in-use style error" if two handle sets ever try to coexist.
Actual, WITHIN-process (what `HardwareManager`'s lock actually
protects): switched manual→ai→manual several times via `POST /api/mode`
independently (not just re-trusting Agent 1's 6-rapid-switch report).
`POST /api/command` while in AI mode correctly returned HTTP 409
(`"AI mode active - manual commands disabled"`), and `raspi-gpio`
immediately afterward showed all 4 direction pins at a clean, static 0 -
confirming the rejected command never reached a motor call (if it had,
IN1/IN3 would show HIGH from `forward()` regardless of what the AI loop
itself was doing). Each mode switch's own HTTP response also succeeded
cleanly every time, which is itself informative: had manual's old
handles still been alive, `AIDriveController.__init__()`'s own
`get_motors()` call would have raised a pin-conflict error and the
switch would have failed - it never did, across several manual↔ai
cycles.

**Actual, ACROSS processes - a real, significant finding, not covered by
the above**: to test the module docstring's own stated assumption
directly (a resource conflict "will raise a pin/resource-already-in-use
style error"), attempted `get_motors()` from a completely separate
Python process while AI mode was active in the server. **It succeeded
with no error at all** - not the expected conflict. Investigated further
rather than stopping there, since this contradicts a documented safety
assumption: confirmed the second handle could **actually drive the
pins** (`motor_forward()` on it genuinely moved GPIO5/19 HIGH), and,
more importantly, **closing the second process's handle silently
deconfigured the GPIO pins the first process's `AIDriveController` was
still using** - `raspi-gpio` showed all 6 motor pins revert to floating
`INPUT` immediately after the second process's `cleanup()`, while the
server's own `GET /api/status` continued reporting `"mode":"ai",
"running":true` with **no exception logged anywhere** - the server's own
Python objects have no way to know their hardware was just pulled out
from under them. Root-caused via
`type(motors.left_enable.pin_factory)` → `gpiozero.pins.rpigpio.
RPiGPIOFactory` - gpiozero's default pin factory on this Pi is the
`RPi.GPIO`-backed one, which (unlike the camera path - see below)
provides **no cross-process exclusivity at all**; gpiozero's own
"pin already in use" protection is only an in-process Python object
registry, not an OS-level lock. **By contrast, the camera path IS
genuinely cross-process exclusive**: a separate `get_camera()` call
while the server held its own camera handle failed immediately with
`RuntimeError: Camera __init__ sequence did not complete.`, and the
underlying libcamera log showed the real reason -
`V4L2 ... Unable to set controls: Device or resource busy` /
`Pipeline handler in use by another process` - i.e. this specific
concern is real for camera, not for GPIO, and the module docstring's
"gpiozero (and picamera2) will raise..." claim is only half-true on this
Pi: true for picamera2, false for gpiozero/GPIO.
Status: PASS for everything the module's OWN single-instance discipline
is designed to prevent (a second manual/AI handle set from *this same
server process*) - that mechanism (the `HardwareManager` lock +
single-instance-per-process design) works correctly and was verified
rigorously. **FLAGGING BACK, not a hard fail**: the module docstring's
stated justification for why a second handle set can never coexist is
factually incorrect for GPIO on this Pi's default pin factory
(`RPiGPIOFactory` provides zero cross-process protection) - it happens
to work today only because nothing else on this Pi currently tries to
open a second GPIO handle while the server runs. A stray second
`python3 web/app.py`, a notebook left with an open `get_motors()`
handle, or a manually-run `src/hardware/motor.py` smoke test, all
running *while the server is up*, would silently and dangerously
conflict - two drivers commanding the same L298N inputs simultaneously
once real hardware is attached, or one process's cleanup silently
undoing the other's active state, exactly as reproduced here. Worth
Agent 1's attention: either accept this as a documented operational
constraint ("only ever run one thing that touches GPIO on this Pi at a
time" - reasonable for a single-owner hobby robot, but should be stated
as an assumption, not implied to be enforced), or consider gpiozero's
`PiGPIOFactory` (via the `pigpiod` daemon, which does mediate exclusive
access, at the cost of an extra system service) if genuine enforcement
is wanted.

### Watchdog: independently re-verified, motors stop on their own with zero further requests
Expected: After one `forward` command with no further commands sent, the
motors should electrically zero out on their own within
`COMMAND_WATCHDOG_TIMEOUT_S` (1.5s) + one `WATCHDOG_POLL_INTERVAL_S`
(0.25s) of polling granularity, with nothing else sent to the server.
Actual: Sent one `POST /api/command {"action":"forward","speed":70}`,
then polled `raspi-gpio get 5`/`get 19` every 0.15s with wall-clock
timestamps, sending **no further requests of any kind**. IN1/IN3 stayed
`HIGH` continuously from the command through t=1.63s after it, then
dropped to `LOW` and stayed there for the remainder of the ~3s
observation window - the transition landed at 1.63-1.79s after the
command, squarely inside the expected 1.5s-1.75s window
(`COMMAND_WATCHDOG_TIMEOUT_S` + one poll interval of slop).
Status: PASS
Notes: Genuinely confirmed via GPIO polling with zero further HTTP
requests sent, not inferred from logs alone (though the server's own
"Watchdog: no manual command for over 1.5s, stopping motors." log line
also appeared at the matching time).

### Emergency stop: idle-AI case and genuine mid-`_timed_turn()` case
Expected: `POST /api/estop` should stop the motors immediately in
whichever mode is active and, if AI mode was active, fully exit back to
manual - confirmed via `raspi-gpio`, and specifically tested while a
real `_timed_turn()` (BLUE/YELLOW turn) is genuinely in progress, not
just while AI mode is idling in its fail-safe stop state.
Actual: Two scenarios:
1. **AI mode idling** (the real, unwired state - ultrasonic fail-safe
   `0.00m` keeps `_decide_and_act()` in `stop` every iteration): switched
   to AI mode, called `/api/estop` 5 times in a row. First call took
   **1.66s** (the real cost of `_stop_ai_locked()`'s thread-join +
   `AIDriveController.cleanup()`, plus `_acquire_manual_locked()`'s own
   ~1s deliberate camera-warmup sleep - see `camera.py`'s
   `_WARMUP_SECONDS`), subsequent calls ~26ms each (idempotent no-op once
   already in manual mode). Final state: `mode: "manual"`, all 6 motor
   pins electrically zero.
2. **Genuine mid-turn** (the scenario the task specifically asked for):
   launched a *separate* test instance of the real server with only
   `read_distance`/`_detect_dominant_color` monkeypatched (inputs only,
   real `ai_drive.py`/`web/app.py` code otherwise) so BLUE is always
   "detected" and the ultrasonic never reports an obstacle - this
   reliably puts the AI loop into a genuine, sustained
   `_timed_turn(motor_turn_left, ...)` call. Confirmed via
   `GET /api/status` (`"action":"turning_left","detected_color":"BLUE"`)
   and via `raspi-gpio` (left motor `IN1=LOW/IN2=HIGH`, right motor
   `IN3=HIGH/IN4=LOW` - the differential pivot-turn pattern already
   verified for `motor.py`'s `left()`) that a real turn was genuinely
   in progress, then called `/api/estop`. **This call took 2.83s** - at
   first glance slow, but this is fully explained and was already
   anticipated by `web/app.py`'s own `AI_STOP_JOIN_TIMEOUT_S=5.0`
   comment: **`_timed_turn()`'s inner polling loop does not check
   `_stop_requested` at all** - it only checks the ultrasonic obstacle
   condition and the turn's own duration bound, so `request_stop()`
   (and therefore `/api/estop`, and therefore a real SIGTERM/SIGINT to
   `ai_drive.py` too) cannot interrupt an in-progress BLUE/YELLOW turn
   any faster than the turn's own remaining duration (up to
   `TURN_LEFT_SECONDS`/`TURN_RIGHT_SECONDS`, 2.0s default) - confirmed
   here empirically for the first time (0.7s already into the turn when
   estop was called, so ~1.3s of turn remained + ~1.5s of the same
   mode-switch/camera-warmup cost as scenario 1 ≈ the observed 2.83s).
   After that, all 6 motor pins confirmed electrically zero and
   `mode: "manual"`.
Status: PASS
Notes: Scenario 2 is not a newly-discovered bug - `web/app.py`'s own
`AI_STOP_JOIN_TIMEOUT_S` comment already correctly anticipates this
exact worst case and sizes its join timeout well above it (5.0s vs. an
observed 2.83s) - but it's now been empirically measured on real
hardware rather than only inferred from reading the source. **Worth
flagging for whenever real motors/speeds are tuned**: a 2-second-long
"blind" turn (blind specifically to any external stop signal, though
still ultrasonic-obstacle-aware via its own internal check) is a real
physical safety consideration for a genuine panic-stop button once the
robot is moving for real - not a defect in this pass's scope, but worth
the user/Agent 1 knowing this number precisely rather than approximately.

### Crash safety: safely simulated unhandled exception in a request handler
Expected: An unhandled exception inside a request handler should be
caught by the global `@app.errorhandler(Exception)`, which calls
`hw.stop_motors_only()` (stopping whatever was actively moving) and
returns HTTP 500, without crashing the server process.
Actual: Since no genuine bug could be found to trigger this naturally,
safely simulated one per the task's own suggestion: launched a separate
test instance of the real server with `_MOVE_FUNCS["forward"]` (one
dict entry only) replaced by a function that raises
`RuntimeError("SIMULATED CRASH...")` - everything else (including
`left`/`right`/`backward`/`stop` and all other routes) untouched. Sent a
real, unpatched `POST /api/command {"action":"left","speed":60}` first
and confirmed via `raspi-gpio` the motors were genuinely turning left
(`IN1=LOW/IN2=HIGH/IN3=HIGH/IN4=LOW`). Then sent
`POST /api/command {"action":"forward","speed":50}`, which hit the
patched function and raised. Result: **HTTP 500** with
`{"error":"internal server error, motors stopped for safety","ok":false}`
exactly as coded; `raspi-gpio` immediately after showed **all 4
direction pins at a clean 0** - confirming the previously-active LEFT
TURN was genuinely stopped by the error handler, not just that the
failed command itself did nothing; the server's log showed the full
traceback logged via `logger.exception(...)` as designed; and
`GET /api/status` immediately afterward confirmed the server process was
still alive and healthy (not crashed).
Status: PASS
Notes: None.

### Server shutdown: real SIGTERM, GPIO/camera released fast and cleanly
Expected: Sending a real `SIGTERM` to the running server process (via
`subprocess.Popen`+`send_signal`, not shell `&`-backgrounding) should
trigger `main()`'s signal handler, which calls `hw.shutdown()`
synchronously and `sys.exit(0)` - releasing the camera and all 6 motor
GPIO pins, confirmed via `raspi-gpio` while/after the process exits.
Actual: Launched the real server via `subprocess.Popen`, sent a real
`POST /api/command {"action":"forward","speed":65}` and confirmed via
`raspi-gpio` the motors were genuinely driving (IN1/ENA/ENB/IN3 HIGH),
then sent `SIGTERM`. Result: **all 6 motor pins transitioned from
actively-driven `OUTPUT` to floating `INPUT` within ~30ms** of the
signal (t=2.257s driving → t=2.286s already released) - much faster than
`ai_drive.py`'s own SIGTERM path, because `web/app.py`'s signal handler
calls `_shutdown()` synchronously and immediately, rather than only
setting a flag checked at the next ~100ms loop iteration. Server log
confirmed `Received signal 15, shutting down.`, `Camera stopped`,
`Camera closed successfully.`, and process exit code 0.
Status: PASS
Notes: `_shutdown()` was observed running three times in the log (once
from the signal handler directly, once via `main()`'s `try/finally` as
the `SystemExit` from `sys.exit(0)` propagates through it, and once more
via the `atexit` registration at interpreter exit) - harmless, since
`HardwareManager.shutdown()`/`_release_manual_locked()` are guarded
(`if self.motors is not None`) and genuinely idempotent; no errors
resulted. Not a bug, just a minor redundancy worth Agent 1 knowing about
if it's ever worth trimming.

### Sticky-RED fix: quick spot-check (coordinator already re-verified this directly)
Expected: Per the coordinator, `if color == "GREEN":` (replacing `if
color == "GREEN" or color != "RED":`) now means the sticky flag clears
ONLY on an explicit GREEN, not on any non-RED color/`None`.
Actual: Confirmed the exact source line on both the dev laptop and Pi
(`src/robot/ai_drive.py` line 394: `if color == "GREEN":`, byte-identical
checksums between machines). Did not re-run the full unit-test matrix
myself since the coordinator already did a direct, real unit-level
re-verification on the Pi (`RED → None → BLUE` stays stopped; `RED →
GREEN` clears and goes forward) - re-doing the identical test would add
no new information. The BLUE-turn monkeypatch used for the estop mid-turn
test above (which forces `_detect_dominant_color` to always return
"BLUE", bypassing the sticky-RED path entirely) does not touch or
exercise this fix either way.
Status: PASS (spot-check only, per the coordinator's own note that this
did not need independent re-testing).
Notes: None.

---

## Summary

| Feature | Status |
|---|---|
| LED module import (direct-run) | PASS |
| LED module import (notebook-style) | PASS |
| GPIO17 logic-level toggle (raspi-gpio verified) | PASS |
| GPIO cleanup / re-run safety | PASS |
| Visual LED confirmation | NOT TESTED — hardware not wired |
| Install script: OpenCV install | PASS (via pip fallback; re-tested after Agent 1's fix) |
| Install script: JupyterLab install | PASS (re-tested after Agent 1's fix) |
| Install script: idempotency | PASS (both install and skip paths now confirmed) |
| rgb_led.py: direct-run | PASS |
| rgb_led.py: notebook-style import | PASS |
| rgb_led.py: GPIO22/23/24 electrical cross-check | PASS |
| rgb_led.py: cleanup / re-run safety | PASS |
| button.py: direct-run | PASS |
| button.py: notebook-style import | PASS |
| button.py: GPIO27 pull=UP electrical cross-check | PASS |
| button.py: cleanup / re-run safety | PASS |
| RGB LED / Button: physical confirmation | NOT TESTED — hardware not wired |
| notebooks/01_gpio_led.ipynb: full execution | PASS |
| notebooks/01_gpio_led.ipynb: visual LED confirmation | NOT TESTED — hardware not wired |
| motor.py: direct-run | PASS |
| motor.py: notebook-style import | PASS |
| motor.py: IN1-4 direction-pin electrical cross-check | PASS |
| motor.py: left()/right() pivot opposite-direction cross-check | PASS |
| motor.py: ENA/ENB genuine PWM duty-cycle tracking | PASS |
| motor.py: stop() zeroes ENA/ENB AND IN1-4 (safety-critical) | PASS |
| motor.py: cleanup / re-run safety | PASS |
| motor.py: physical wheel movement / spin direction | NOT TESTED — hardware not wired |
| notebooks/02_rgb_pwm_button.ipynb: full execution | PASS |
| notebooks/02_rgb_pwm_button.ipynb: visual RGB / button press | NOT TESTED — hardware not wired |
| ultrasonic.py: partial=True confirmed (object + independent hang repro) | PASS |
| ultrasonic.py: read_distance() never blocks | PASS |
| ultrasonic.py: direct-run smoke test + SAFETY warning | PASS |
| ultrasonic.py: cleanup / re-run safety | PASS |
| ultrasonic.py: notebook-style import | PASS |
| ultrasonic.py: real distance measurements | NOT TESTED — hardware not wired |
| obstacle_avoidance.py: auto_drive() respects max_duration_s | PASS |
| obstacle_avoidance.py: auto_drive() respects stop_condition | PASS |
| obstacle_avoidance.py: max_duration_s overshoot is bounded (~1 maneuver) | PASS |
| obstacle_avoidance.py: real KeyboardInterrupt → ENA/ENB zeroed | PASS |
| obstacle_avoidance.py: avoid_obstacle() pin-behavior spot-check | PASS |
| obstacle_avoidance.py: real obstacle detection/avoidance | NOT TESTED — hardware not wired |
| notebooks/03_l298n_motor_control.ipynb: movement/stop cell pairing | PASS |
| notebooks/03_l298n_motor_control.ipynb: full execution | PASS |
| notebooks/04: full execution + continuous pin-trace monitoring | PASS |
| notebooks/04: auto_drive() 5s demo stopped via its own time bound | PASS |
| notebooks/04: 0.00m fail-safe consistent, no false errors | PASS |
| notebooks/04: sensor close-then-reopen transition | PASS |
| notebooks/04: real sensor readings / real obstacle avoidance | NOT TESTED — hardware not wired |
| Install script: picamera2/numpy ABI fixup (simplejpeg reinstall) | PASS |
| camera.py: direct-run smoke test | PASS |
| camera.py: notebook-style import | PASS |
| camera.py: cleanup / re-run safety | PASS |
| camera.py: BGR/RGB color-order visual confirmation (real object, real light) | NOT TESTED — no usable light source available |
| color_detection.py: direct-run smoke test | PASS |
| color_detection.py: notebook-style import | PASS |
| color_detection.py: synthetic-image logic sanity check (supplementary) | PASS |
| color_detection.py: detection against real RED/GREEN/YELLOW objects | NOT TESTED — no light source/colored object available |
| ai_drive.py: sticky-RED state machine (RED/None/GREEN/YELLOW paths) | PASS (see Notes - one design nuance flagged for Agent 1) |
| ai_drive.py: SIGTERM stops a genuinely-driving process (GPIO12/13 verified) | PASS |
| ai_drive.py: SIGINT stops a genuinely-driving process (GPIO12/13 verified) | PASS |
| ai_drive.py: _timed_turn() obstacle-abort-mid-turn (monkeypatched sensor) | PASS |
| object_detection.py: missing model file handling | PASS |
| object_detection.py: corrupt model file handling | PASS |
| object_detection.py: detect_cars(None, frame) is cheap (~0.001ms/call) | PASS |
| ai_drive.py: direct-run (python3 src/robot/ai_drive.py) | PASS |
| ai_drive.py: notebook-style import | PASS |
| ai_drive.py: cleanup / re-run safety (all 4 hardware handles) | PASS |
| ai_drive.py: real color detection against physical objects | NOT TESTED — camera lighting issue (see vision module section) |
| ai_drive.py: real car detection accuracy | NOT TESTED — no real model file yet |
| ai_drive.py: real physical obstacle-abort during turn (object in front of sensor) | NOT TESTED — hardware not wired |
| Install script: Flask/Werkzeug fixup, independently reproduced | PASS |
| web/app.py: server starts, GET /, GET /api/status | PASS |
| web/app.py: POST /api/command forward -> raspi-gpio cross-check | PASS |
| web/app.py: mode-switch exclusivity WITHIN server process | PASS |
| web/app.py: mode-switch exclusivity ACROSS separate OS processes (GPIO) | FLAGGED — no cross-process protection, see Notes |
| web/app.py: camera cross-process exclusivity | PASS (correctly rejected) |
| web/app.py: POST /api/command returns 409 in AI mode, verified motors untouched | PASS |
| web/app.py: watchdog auto-stops motors with zero further requests | PASS |
| web/app.py: /api/estop while AI mode idle | PASS |
| web/app.py: /api/estop during genuine mid-_timed_turn() | PASS (2.83s latency, by design - see Notes) |
| web/app.py: crash safety (simulated unhandled exception) | PASS |
| web/app.py: SIGTERM shutdown, GPIO/camera released | PASS |
| ai_drive.py: sticky-RED fix spot-check | PASS |

**Overall: LED code (Agent 1's `src/hardware/led.py` + `src/config.py`
LED_PIN usage) is solid — 4/4 testable items PASS, rigorously verified at
the electrical level via independent `raspi-gpio` polling, not just trusting
the script's own print output.**

**`scripts/install_pi_dependencies.sh` — Agent 1's fix confirmed working.**
The previous run's script bug (`set -euo pipefail` + unguarded
`sudo apt-get install` aborting the whole script on any apt failure, before
the pip fallback or the JupyterLab section could run) is fixed: both
`apt-get` calls are now guarded with `|| echo "WARNING: ..."`, so the script
falls through correctly. Re-tested end-to-end on the real Pi:
- `security.debian.org` is **still** 404ing on the same 5 packages
  (`libheif1`, `mariadb-common`, `libmariadb3`, `libpq5`, `libgdcm3.0`) as
  last time — confirmed not transient by a direct standalone
  `sudo apt-get install -y python3-opencv` retry giving byte-identical 404s.
  This remains a Debian mirror-sync issue outside the project's control.
- With that fixed, the script correctly fell through to the pip fallback
  (`opencv-python-headless`), which succeeded: `cv2.__version__` → `5.0.0`.
- JupyterLab installed successfully (`jupyterlab 4.5.10`), since the script
  no longer dies before reaching that section.
- Second run confirmed true idempotency: both "already
  importable/installed, skipping" branches triggered, no reinstall attempted
  (~8s vs. ~3m38s for the real install), exit code 0.

**RGB LED (`rgb_led.py`), Button (`button.py`), and Notebook 1 — all PASS
on independent re-verification.** All electrically-testable behavior
(correct per-color R/G/B pin combinations, pull-up enable/release, clean
timing, clean cleanup/re-run safety, and a genuine full top-to-bottom
Jupyter execution with programmatic error-checking of every cell's outputs)
checked out. Nothing here needs to go back to Agent 1. One minor,
non-blocking, future-proofing note for Agent 3: the notebook triggers a
`MissingIDFieldWarning` from nbformat (missing per-cell `id` fields, will
become a hard error in a future nbformat version, not today) — worth an
optional resave in current JupyterLab or an `nbformat.normalize()` pass at
Agent 3's discretion.

**Motor driver (`motor.py`) and Notebook 02 — all PASS on rigorous,
timestamp-verified re-testing.** This was treated as the highest-stakes
module tested so far since it can actually move a real robot once wired,
so extra care went into it: direction pins (IN1-4) were traced through all
14 demo steps confirming every documented HIGH/LOW combination including
the pivot-turn opposite-direction behavior; ENA/ENB were confirmed to be
under genuine PWM (not static) with duty cycle tracking `set_speed()`
(exact 0%/100% boundary matches, monotonic scaling in between); and the
safety-critical `stop()` zeroing of ENA/ENB *and* IN1-4 was confirmed with
0/100 HIGH samples across a timestamp-verified window guaranteed to fall
between `stop()` and `cleanup()`. One early test run gave a misleading
~60% HIGH reading on `stop()`'d pins — root-caused to my own poll loop
overrunning into the post-`cleanup()` floating-pin phase (a test-timing
bug, not a motor.py bug), then re-run with proper margins to get the clean
0/100 result. Notebook 02 executed all 69 cells cleanly (no nbformat
warning this time, confirming Agent 3's fix held), and the specifically-
flagged `Button(27)` → `close()` → `get_button()` transition was confirmed
error-free. **Nothing needs to go back to either Agent 1 or Agent 3 from
this pass** — both are clean.

**Ultrasonic sensor, obstacle avoidance, and Notebook 03 — all PASS, with a
real safety-critical finding independently verified.** Agent 1's
`DistanceSensor(partial=False)`-blocks-forever finding was independently
reproduced from scratch (not just trusted): a bare `gpiozero.DistanceSensor`
with `partial=False` genuinely hangs past a 6s timeout with nothing wired,
and the module's actual constructed object confirms `partial=True` is
really in effect (checked the object's attribute, not just the source).
`read_distance()` is genuinely instant (hundredths of a millisecond) across
every call. For `obstacle_avoidance.py`, the `max_duration_s` bound and
custom `stop_condition` both work as documented, and the bounded overshoot
matches Agent 1's own characterization exactly. The single most important
test in this pass — a real `SIGINT`/`KeyboardInterrupt` sent to a running
`auto_drive()` — needed two attempts: the first gave a false negative
because of a `bash &`-backgrounding quirk (POSIX shells ignore `SIGINT` for
non-interactive background jobs) that had nothing to do with the code under
test; once delivered correctly via `subprocess.Popen`, the result was
unambiguous — `auto_drive()`'s `finally` block genuinely fires and GPIO12/13
(ENA/ENB) read electrically zero afterward. Notebook 03 (the first one that
actually drives real motor-control logic end-to-end) executed all 65 cells
cleanly, and its movement/stop cell pairing was independently verified by
reading the actual cell source, not by trusting the notebook's own claims.
**Nothing needs to go back to Agent 1 or Agent 3 from this pass either** —
all three deliverables are clean. One methodology note worth keeping in
mind for future signal-handling tests (not a code issue): testing
`KeyboardInterrupt`/`SIGINT` behavior over SSH needs `subprocess.Popen` +
`send_signal`/`os.kill`, not plain `command &` shell backgrounding, or the
test itself produces a misleading result.

**Notebook 04 (ultrasonic_obstacle_avoidance) — PASS, closes out the
01-04 GPIO→LED→RGB→button→motor→ultrasonic→obstacle-avoidance arc.** This
was the highest-stakes unattended-execution run yet — because nothing is
wired, `read_distance()`'s fail-safe `0.0` means every single check in this
notebook reports "an obstacle," so from `get_motors()` onward it's
continuous, unbroken motor activity (not the calmer "drives straight most
of the time" case), for a genuine ~7-second window including the
deliberately-shortened `auto_drive(max_duration_s=5)` demo. Monitored the
entire `nbconvert --execute` run with continuous pin-trace polling (not
just before/after snapshots): confirmed floating-HIGH (unclaimed) for the
ultrasonic-only cells, then a bounded window of genuinely switching pin
activity once motors are claimed, then one clean **all-six-pins-exactly-zero**
sample, then release — the exact "real stop, then real release" signature
already established with SIGINT-level rigor for the underlying functions in
the prior pass, now confirmed to hold from the actual notebook too. Zero
errors across all 36 cells; `auto_drive()`'s own printed message confirms it
stopped via its 5s time bound; the sensor close-then-reopen transition
(cell 14 → cell 18) was clean, same pattern as Notebook 02's button
transition. **Nothing needs to go back to Agent 1 or Agent 3.**

**Vision module (`src/vision/camera.py`, `src/vision/color_detection.py`)
and the install script's picamera2/numpy ABI fixup — install fix and every
software-only check PASS; the two real-hardware-in-real-light checks are
NOT TESTED, not skipped.** Independently reproduced the picamera2/numpy/
simplejpeg ABI bug from scratch (uninstalled `simplejpeg`, confirmed the
exact documented `ValueError`, confirmed `install_pi_dependencies.sh`'s
fixup step detects and repairs it, confirmed idempotency on a second run)
rather than trusting Agent 1's prior report of it — genuinely works.
`camera.py`'s and `color_detection.py`'s direct-run smoke tests,
notebook-style imports, and cleanup/re-run safety all PASS with no
exceptions. Added a supplementary synthetic-image logic check (not one of
the requested items) confirming `detect_color()`/`largest_blob()` and
specifically the RED hue-wraparound two-range logic are bug-free in
isolation. However, the two checks this task explicitly prioritized —
visually confirming `capture_frame()`'s BGR channel order against a real
colored object, and confirming `HSV_RANGES` actually detects real red/
green/yellow objects — could **not** be completed: the test environment's
camera view is effectively pure black even at an aggressive 200ms-
exposure/16x-gain manual capture during Pi-local daytime, so there was no
visible scene of any color for either check to be performed against, and
no physical colored object was available regardless. **Flagging back: the
camera's BGR-vs-RGB channel order remains visually unconfirmed on a real
photo of a real color** — Agent 1's own pixel-statistics-only verification
was explicitly caveated as needing this follow-up, and this pass still
could not provide it. See "Needs human attention" below.

**AI Drive Controller (`src/robot/ai_drive.py`) and Object Detection
(`src/vision/object_detection.py`) — the most safety-critical module in
the project, and it held up under independent, rigorous re-verification.**
Every priority-logic and safety-critical claim was re-derived from
scratch rather than trusted from Agent 1's report. Headline result: **a
real SIGTERM sent to a genuinely-driving process (motors confirmed
actively commanding forward via 3 consecutive live status reads, not
idling) was followed by GPIO12/GPIO13 reading electrically zero for a
continuous, unambiguous ~3-second window while the process was still
alive and the pins still claimed** - the single most safety-critical
property in this project, confirmed as solid as `obstacle_avoidance.py`'s
equivalent SIGINT guarantee earlier in this file. A supplementary SIGINT
test came back even cleaner (no transient at all). `_timed_turn()`'s
mid-turn obstacle-abort was confirmed with a controlled/monkeypatched
sensor to genuinely poll repeatedly during a turn (6 real calls before
aborting at 0.501s of a commanded 2.0s turn) rather than checking once
up front, with a control case confirming it runs the full duration when
never obstructed. `object_detection.py`'s missing/corrupt-model handling
and cheap-no-op guarantee (`detect_cars(None, frame)` averaged
0.0011ms/call across 200 calls) both re-confirmed exactly as Agent 1
reported. Direct-run, notebook-style import, and cleanup/re-run safety
(two full four-handle lifecycles back-to-back) all PASS. **One finding
flagged back to Agent 1, not a hard bug**: the sticky-RED state
machine's `_stopped_for_red` flag technically clears on ANY non-RED
frame - including a `None`/ambiguous one - not only on `GREEN`; the
robot's actual stop *action* still holds through one ambiguous frame
(the safe-default case independently also stops), but the sticky
*protection* is already gone by the next frame, meaning a RED sighting
followed immediately by one noisy/ambiguous frame and then a real
BLUE/YELLOW/GREEN reading will act on it right away, without an explicit
GREEN ever having been seen. This matches the module docstring's literal
wording but not necessarily its intent - see the detailed section above
for the full mechanics and a concrete repro. As with the vision module,
real color detection, real car detection, and real physical
obstacle-during-turn behavior remain NOT TESTED for lack of lighting, a
real model file, and physical hardware respectively - not skipped, just
blocked by the same standing environmental gaps noted elsewhere in this
file.

**Update (later QA pass): the sticky-RED flag-clearing issue flagged just
above has been fixed.** The coordinator applied and directly re-verified
the fix (`if color == "GREEN":` replacing `if color == "GREEN" or color
!= "RED":`) with a real unit-level test on the Pi (`RED → None → BLUE`
now correctly stays stopped throughout; `RED → GREEN` still correctly
clears and goes forward). Confirmed via `md5sum` that this pass's copy of
`ai_drive.py` (dev laptop and Pi, byte-identical) carries the fix at line
394. Not independently re-tested from scratch in this pass per the
coordinator's own note that it wasn't necessary - this update note exists
so a reader of the paragraph above doesn't mistake it for still-open.

**Web control server (`web/app.py`) — the last major piece of the project
before SSD training/deployment, tested to the same rigor as the
motor/ai_drive modules and holding up well, with one real cross-process
GPIO finding flagged for Agent 1's attention.** Independently reproduced
the Flask/Werkzeug/Jinja2 install-fixup bug from scratch (same
apt-vs-pip-dependency-shadowing pattern as the numpy/simplejpeg and
tornado fixups earlier in this project) and confirmed the install
script's new self-test step detects, fixes, and is idempotent about it.
`POST /api/command` was electrically cross-checked via `raspi-gpio`
against the exact same IN1-4/ENA/ENB pattern already verified for
`motor.py` directly. The watchdog was confirmed to genuinely
self-stop the motors with zero further HTTP requests sent (not inferred
from logs), `/api/estop` was confirmed both while AI mode idles AND -
going further than the task's minimum ask - while a real
`_timed_turn()` BLUE turn was genuinely in progress (via a
monkeypatched-input test instance of the real server), crash safety was
confirmed by safely simulating a real unhandled exception in a request
handler (not just code-reading), and a real SIGTERM was confirmed to
release all GPIO/camera resources within ~30ms. **The one finding
worth flagging**: the module docstring's assumption that "gpiozero (and
picamera2) will raise a pin/resource-already-in-use style error" if two
handle sets coexist is only true for the camera (genuinely, robustly
cross-process exclusive via libcamera/V4L2) - for GPIO, gpiozero's
default `RPiGPIOFactory` pin factory on this Pi provides **no
cross-process protection at all**, empirically confirmed: a second,
completely independent Python process was able to construct its own
`get_motors()` handle and actually drive the same pins while the server's
AI mode was actively using them, and closing that second process's
handle silently released the GPIO pins out from under the server's still
-running `AIDriveController`, with no exception raised on either side.
This is not a bug introduced by this project's own code - `HardwareManager`'s
own single-instance-per-process discipline is correctly designed and
verified working - but the module's stated justification for why a
conflict "can't happen" is not accurate for the GPIO path on this Pi,
and is worth an explicit decision (documented operational constraint
vs. `pigpiod`-backed enforcement) rather than being left as an implicit,
partially-incorrect assumption in a safety-relevant comment. Also worth
noting for whoever tunes real speeds/turn durations later: `/api/estop`
(and any other stop signal, including SIGTERM/SIGINT to `ai_drive.py`
directly) cannot interrupt an in-progress BLUE/YELLOW turn faster than
the turn's own remaining duration (empirically measured here as
contributing ~1.3s to a 2.83s total estop latency) - already correctly
anticipated by `web/app.py`'s own `AI_STOP_JOIN_TIMEOUT_S=5.0` comment,
now confirmed with a real number rather than an estimate.

### Overall arc health assessment (Notebooks 01-04 + all underlying src/ modules)
Every module in this arc — `led.py`, `rgb_led.py`, `button.py`, `motor.py`,
`ultrasonic.py`, `obstacle_avoidance.py` — and every notebook built on top
of them (01 through 04) is electrically and logically verified to the
fullest extent possible without physical hardware attached: correct pin-level
behavior confirmed independently via `raspi-gpio` (not just trusting print
statements) for every digital I/O, PWM duty cycle, and pull-up/pull-down
claim; every cleanup path confirmed to genuinely release pins rather than
leave them claimed; and — for the two modules where a bug could actually be
dangerous once wired (`motor.py`'s `stop()` and `obstacle_avoidance.py`'s
`auto_drive()`) — the safety guarantees were confirmed with the highest
available rigor: a real `KeyboardInterrupt` sent to a live running process,
with GPIO state read while the process was still alive (not just at the
Python-object level). Two genuine issues surfaced and were both resolved
upstream during this arc: the `install_pi_dependencies.sh` script's
apt-failure-aborts-everything bug (fixed and re-verified by Agent 1) and
`gpiozero.DistanceSensor`'s default blocking-forever behavior (caught by
Agent 1 before it ever shipped, fixed with `partial=True`, and independently
reproduced from scratch in this pass to confirm the underlying claim was
real). No open issues remain against Agent 1 or Agent 3's work at the close
of this arc. The one meaningful gap, by necessity, is that nothing has been
visually or physically confirmed — no LED has been seen to light up, no
motor has been seen to spin, no real distance has ever been measured —
because none of this hardware is physically wired yet; everything marked
PASS here is a ceiling on "correct as far as software and electrical logic
can prove," not a substitute for a first real hardware-wiring pass, which
should re-exercise this exact same test matrix (especially `motor.py`'s
direction/speed correctness with real motors attached, per its own
docstring's warning that a mirrored/reversed motor is fixed by re-wiring
leads, not by editing code) once wiring begins.

## Needs human attention
- None for sudo/passwords: passwordless sudo (`sudo -n`) IS configured for
  `admin` on the Pi, so no manual password entry was needed anywhere in this
  pass.
- Optional/low-priority: `security.debian.org`'s bullseye-security mirror is
  still missing the `.deb` files for `libheif1`, `mariadb-common`,
  `libmariadb3`, `libpq5`, and `libgdcm3.0` as of this re-test (confirmed on
  two separate occasions, not transient). This no longer blocks anything —
  the pip fallback covers OpenCV fine — but a human could retry
  `sudo apt-get update && sudo apt-get install -y python3-opencv` later if
  they'd prefer the apt-packaged OpenCV over the pip one, or just leave it
  as-is since the pip fallback is working and sufficient for this project.
- **Fixed live, outside the normal QA-task flow**: the user reported
  JupyterLab loading as a blank page in the browser even with the correct
  URL/token/tunnel. Root cause: `pip3 install --user jupyterlab` (via
  `install_pi_dependencies.sh`) had resolved the newest available
  **tornado 6.5.9**, which has a known incompatibility with the installed
  `jupyter-server 2.18.2` — every static JS/CSS asset request failed with
  `AttributeError: 'FileFindHandler' object has no attribute
  'allowed_symlink_directory'` (HTTP 500), so the page shell loaded but the
  actual UI never rendered. Fixed by pinning
  `pip3 install --user --upgrade "tornado<6.5"` (now `tornado==6.4.2` on
  the Pi); verified the main JS bundle now returns 200 with real content
  instead of a 500 error page. **Follow-up worth considering for Agent 1**:
  pin `tornado<6.5` (or a specific known-good version) in
  `requirements.txt`/`install_pi_dependencies.sh`, since re-running the
  install script as currently written could re-resolve the newest tornado
  and reintroduce this exact bug.
- **Fixed live, outside the normal QA-task flow**: the user reported
  `01_gpio_led.ipynb` (and, more broadly, "all the lab") throwing errors
  after editing the notebook by hand in JupyterLab. Two separate issues,
  both fixed:
  1. `01_gpio_led.ipynb` on the Pi had shrunk from 36 cells to 33, and its
     `from hardware.led import ...` cell had been overwritten with
     unrelated experimental code. Restored the whole notebook from the
     untouched, already-QA-tested copy on the dev machine (rsync'd over
     the Pi's copy) rather than patching the edit in place.
  2. The actual root cause of the *project-wide* "error in all the lab"
     symptom: `src/config.py` on the Pi had been corrupted at line 61 to
     `ULTRASONIC_TRIG_PIN = dasd` (an undefined name — `NameError`).
     Since `config.py` is imported by every hardware module (`led.py`,
     `motor.py`, `rgb_led.py`, `button.py`, `ultrasonic.py`), this single
     line broke imports across the whole project, not just one notebook.
     `diff` against the clean local copy confirmed this was the *only*
     difference — an unambiguous accidental typo, not a design change — so
     restored it to `ULTRASONIC_TRIG_PIN = 20` (the original, already-
     verified value). No other pin assignments in `config.py` were
     touched (confirmed via `diff`).
  Verified the fix by re-running `01_gpio_led.ipynb` end-to-end via
  `jupyter nbconvert --execute`: exit code 0, zero errors across all
  cells. Advised the user that any already-open browser tabs still hold
  the broken in-memory versions and need to be closed without saving and
  reopened from disk, or Jupyter's autosave could re-clobber the restored
  files.
- **Fixed live, ahead of the OpenCV/vision phase**: the user asked about
  the camera feed + OpenCV session. `python3 -c "import picamera2"`
  failed with
  `ValueError: numpy.dtype size changed, may indicate binary
  incompatibility. Expected 96 from C header, got 88 from PyObject`.
  Root cause: `python3-simplejpeg` (an apt-installed, compiled
  dependency of `picamera2`'s JPEG encoder) was built against the
  system's apt numpy (`1.19.5`), but the earlier `install_pi_dependencies.sh`
  pip-fallback install of `opencv-python-headless` had pulled in
  `numpy==2.0.2` into `--user` site-packages, which takes import
  precedence over the system numpy for all Python code on this Pi —
  breaking `simplejpeg`'s compiled C extension's ABI compatibility. Camera
  hardware itself was confirmed fine throughout (`libcamera-hello
  --list-cameras` correctly detects the imx219 sensor). Fixed by
  `pip3 install --user --force-reinstall --no-cache-dir simplejpeg`,
  which fetched a prebuilt `simplejpeg 1.9.0` aarch64 wheel from
  piwheels — this pulled in the *same* `numpy==2.0.2` already installed
  (no version change), so `cv2` and `numpy` were unaffected; confirmed via
  re-import after the fix. Did **not** touch `requirements.txt` or
  `install_pi_dependencies.sh` — this is a note for whoever builds the
  camera module (`src/hardware/camera.py`, not yet started) that this
  apt/pip numpy ABI mismatch pattern can recur for any other apt-installed
  compiled package that depends on numpy (same class of issue as the
  tornado one above, different package).
  **Verified the full capture pipeline end-to-end, not just imports**:
  captured a real frame via `Picamera2().capture_array()` (640x480x3
  uint8), ran real `cv2.cvtColor()` (RGB→grayscale) and `cv2.imwrite()` on
  it, and visually inspected the resulting JPEG — it showed genuine sensor
  noise (faint color speckling), not a flat/synthetic array, confirming
  the pipeline is genuinely working. The frame itself was near-black
  (`mean=0.99, std=1.23` out of 0-255) — this is an **environmental**
  observation, not a software issue: the camera is either covered or the
  room is dark. Flagging for whoever tests the camera module for real:
  point it at something lit before assuming a capture failed.
- **Still open, re-confirmed in this pass (`src/vision/` QA)**: the dark-
  room condition noted just above by the prior pass has not been resolved.
  Re-checked directly in this pass at ~11:13 AM Pi-local time (daytime, via
  `date` on the Pi) — the default capture was still effectively pure black
  (`mean BGR ≈ [2.1, 2.1, 1.1]`/255), and even a deliberately aggressive
  manual capture (`AnalogueGain=16.0`, `ExposureTime=200000`, i.e. 200ms
  exposure at 16x gain — well beyond the default auto-exposure settings)
  only reached `mean ≈ 6.3/255`, still visually black. That a maximal-gain/
  exposure capture during daytime shows essentially nothing suggests this
  is not just "the room happens to be dim" but possibly the lens being
  capped/obstructed, or the camera pointed at an enclosed/dark space — a
  human should physically check the camera's lens and surroundings, not
  just turn on a light. This is now actively blocking two specific,
  explicitly-requested QA checks that only a human with physical access
  can unblock:
  1. Visually confirming `src/vision/camera.py`'s `capture_frame()` BGR
     channel order is correct against a real, identifiable colored object
     (currently only verified via pixel statistics by Agent 1, in an
     equally dark room — never actually confirmed by eye against a known
     color, despite that being the whole point of this check).
  2. Confirming `src/vision/color_detection.py`'s `HSV_RANGES` for RED/
     GREEN/YELLOW actually detect real objects of those colors (currently
     only reference/tutorial values, plus this pass's synthetic-image
     logic check — never tested against a real object).
  Next step for a human: physically inspect the camera (confirm the lens
  cap/protective film is off, confirm it isn't pointed into an enclosure),
  bring genuine light to the scene, place a red/green/yellow object in
  frame, then re-run `python3 src/vision/camera.py` and
  `python3 src/vision/color_detection.py` and check the results per the
  "Vision module" section above.
