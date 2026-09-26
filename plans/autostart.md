# autostart — make the wheel bot a launchable executable that starts on boot

## Goal

Today the bot is started by hand: `cd` into the repo, activate `venv`, run
`python wheel_spy.py`. After a reboot (or a crash) nothing runs. Deliver:

1. **An executable launcher**, `run.sh`, at the repo root, that works from any
   current directory (double-click, `~/…/run.sh`, a symlink, or systemd).
2. **Start on boot / restart on exit** via a systemd *user* unit that runs the
   launcher, restarts it if it dies, and logs to the journal.

This mirrors the already-done sibling project
`/home/shreyas/projects/workspace/alpaca_spy_leaps` (`run.sh`,
`deploy/leaps-spy.service`, README "Run on startup", `plans/autostart.md`).
Read those files and copy their shape; change only names/paths and facts that
differ for this repo.

## Project rules / facts this task touches

There is no project `CLAUDE.md`/`AGENTS.md`. Facts from the code that constrain
the design:

- `wheel_spy.py` calls `load_dotenv()` for `.env`. Run it with cwd = repo root
  so this is unambiguous. **Do not change `wheel_spy.py` in this task.**
- Dependencies live in `venv/` (`venv/bin/python`, 3.14; `alpaca`, `dotenv`,
  `requests` import fine). Use it directly; don't `source activate`.
- The bot places orders (paper by default, `ALPACA_PAPER_TRADE="true"` in
  `.env`) and sends Telegram messages. **Two instances at once can double-sell
  options.** A manual instance is running right now (`pgrep -af wheel_spy` →
  `python wheel_spy.py`). **Verification must never start the real bot, and
  nothing in this task may start the service.**
- `print` output must reach the journal promptly → run python unbuffered (`-u`).
- `.gitignore` ignores `venv/`, `.env`, `*.log`, `__pycache__/`, `*.pyc` — new
  files (`run.sh`, `deploy/*.service`, `plans/`) are not ignored.
- Linger is enabled (`loginctl show-user $USER -p Linger` → `yes`), so a user
  unit with `WantedBy=default.target` starts at boot without a login.
- The user manager has no `network-online.target` (found in the sibling task):
  `After=/Wants=` on it are no-ops. `main()` in `wheel_spy.py` wraps each loop
  iteration in `try/except` and sleeps 360 s, so an offline start does not exit;
  it just retries. The README must not claim the unit waits for the network.

## Steps

### 1. Launcher script — [x]

- **May edit:** `run.sh` (new).
- **Done when:** same as the sibling's `run.sh`, with `wheel_spy.py` in place of
  `leaps_spy.py` and the header comment adjusted: `#!/usr/bin/env bash`,
  `set -euo pipefail`, `cd` to the directory containing itself (resolving
  symlinks), clear stderr error + exit 1 if `venv/bin/python` is not
  executable, then `exec venv/bin/python -u wheel_spy.py "$@"`. Mode 755.
- **Verify (must not start the bot):**
  - `bash -n run.sh`; `test -x run.sh`.
  - Missing-venv: copy `run.sh` into an empty scratch dir, run from another
    cwd → exit 1 with the error.
  - cwd resolution: scratch dir with `run.sh` + fake `venv/bin/python` that
    prints `$PWD` and its args; run via a symlink from another cwd → prints the
    scratch dir and `-u wheel_spy.py`.
  - Use only the session scratchpad for temp dirs.
- **Result:**
  - **Did:** created `run.sh` (mode 755), byte-identical to the sibling's
    except `leaps_spy.py` → `wheel_spy.py` and lines 2–4 of the header comment
    (says "SPY wheel bot"; says it runs from the repo root so the `.env` that
    `load_dotenv()` picks up and the interpreter are unambiguous; drops the
    sibling's `leaps_state.json`/git-info mention, which doesn't apply here).
  - **Verified** (scratchpad only; real venv / `wheel_spy.py` never run):
    `bash -n run.sh` ok, `test -x` ok, `stat` 755; copy in a dir without
    `venv/` run from another cwd → the stderr error + `exit=1`; copy with a
    fake `venv/bin/python` invoked via a symlink from another cwd with args
    `--foo bar` → `PWD=<scratch>/fakevenv`, `ARGS=-u wheel_spy.py --foo bar`, exit 0.
  - **Deliberately left:** no other files touched; did not stage/commit.
  - **For later steps:** nothing changes step 2–3. Note for README wording:
    python-dotenv's bare `load_dotenv()` searches upward from the *script's*
    directory, not cwd, so don't claim `.env` is resolved relative to cwd.

### 2. systemd user unit — [x]

- **May edit:** `deploy/wheel-spy.service` (new).
- **Done when:** same shape as the sibling's `deploy/leaps-spy.service`:
  header comment (double-buy warning with `pgrep -af wheel_spy`, install steps,
  logs command, "fix paths if you move the repo"), `After=/Wants=network-online.target`,
  `Type=simple`,
  `WorkingDirectory=/home/shreyas/projects/workspace/alpaca_spy_wheel`,
  `ExecStart=/home/shreyas/projects/workspace/alpaca_spy_wheel/run.sh`,
  `Restart=always` (with the "clean exit never intended" comment),
  `RestartSec=30`, `WantedBy=default.target`.
- **Verify:** `systemd-analyze --user verify deploy/wheel-spy.service` reports
  nothing about this unit. Do **not** install, enable, or start it.
- **Result:**
  - **Did:** created `deploy/wheel-spy.service` from the sibling's
    `deploy/leaps-spy.service`. Only these lines differ: `leaps`→`wheel` in
    names/paths (`wheel-spy`, `wheel_spy`, `alpaca_spy_wheel`), the header
    and `Description=` say "SPY wheel trading bot", and the warning says
    "double-sell options" instead of "double-buy" (lines 2–3 rewrapped to stay
    under 80 columns). Directives are otherwise identical: `After=/Wants=
    network-online.target`, `Type=simple`, `WorkingDirectory=`/`ExecStart=` on
    this repo and `run.sh`, `Restart=always` with the "clean exit never
    intended" comment, `RestartSec=30`, `WantedBy=default.target`.
  - **Verified:** `diff` against the sibling shows only the lines above;
    `grep -ic leaps` → 0. `systemd-analyze --user verify
    deploy/wheel-spy.service` → exit 0; its only output is a line about the
    system's `/usr/lib/systemd/user/spice-vdagent.service`, nothing about this
    unit. `systemctl --user list-unit-files 'wheel*'` → "0 unit files listed."
    (not installed). The manual `python wheel_spy.py` instance is still running
    and untouched.
  - **Deliberately left:** did not copy to `~/.config/systemd/user`,
    daemon-reload, enable or start anything; did not stage/commit.
  - **For later steps:** step 3's install block must be copied verbatim from
    lines 4–10 of this unit's header. The unit keeps `network-online.target`
    lines (no-ops for the user manager, as in the sibling), so the README must
    not claim the unit waits for the network.

### 3. README — [x]

- **May edit:** `README.md`.
- **Done when:** "Running the Bot" leads with `./run.sh` (keeps
  `python wheel_spy.py` as the manual alternative), and the vague last
  paragraph about tmux/screen/systemd is replaced by a "Run on startup"
  section: what the unit does, the double-instance warning, the install block
  copied verbatim from the unit header, a manage block (status, stop, disable,
  `journalctl --user -u wheel-spy -f`), the move-the-repo note, and an accurate
  network sentence (no wait for network; an offline bot keeps retrying every
  6 minutes; `Restart=always` only covers a crash).
- **Verify:** `git diff README.md`; unit name, path and commands match steps 1–2;
  the network claim matches `main()` in `wheel_spy.py`.
- **Result:**
  - **Did:** replaced everything from "## Running the Bot" to EOF (that was
    the file's last section) with the sibling's "Usage" + "Run on startup"
    text adapted: heading kept as "Running the Bot"; leads with `./run.sh`,
    keeps `python wheel_spy.py` as the manual alternative ("see Setup" instead
    of "see Installation"); "Run on startup" uses `deploy/wheel-spy.service`,
    unit `wheel-spy`, "double-sell options", `pgrep -af wheel_spy`; manage
    block = status/stop/disable/`journalctl --user -u wheel-spy -f`; move-the-
    repo note unchanged. Network sentence rewritten for this bot (it has no
    Telegram polling, no startup Telegram message, no `/buy`): "does not wait
    for the network at boot … each check that fails is logged and retried 6
    minutes later; `Restart=always` only covers a crash". Also corrected the
    old "polling … once per hour" claim to "checking the market clock every 6
    minutes and evaluating positions whenever the market is open" (it was in
    the paragraph being rewritten). No `.env`/cwd claim made.
  - **Verified:** `git diff README.md` touches only that section. Install
    block diffed against unit header lines 5–10 (comment prefix stripped) →
    identical. `main()` checked: `get_clock()` and
    `check_positions_and_wheel()` are inside `try/except Exception` that
    prints `Error: …`, followed by `time.sleep(360)` = 6 min; the module-level
    Alpaca client constructors make no network calls, so offline start
    doesn't exit.
  - **Deliberately left:** the Disclaimer-less README (this repo has none;
    didn't add the sibling's); Setup section untouched; no commit.

### 4. Install (main agent, not a subagent) — [x]

Copy the unit to `~/.config/systemd/user/`, `daemon-reload`, `enable` (not
`--now`) so it starts on next boot. Starting now is left to the user, after they
stop the manual instance.

**Result (2026-09-25):** copied to `~/.config/systemd/user/wheel-spy.service`,
`daemon-reload`, `enable` → `is-enabled: enabled`, `is-active: inactive`.
Manual instance (PID 17402, `python wheel_spy.py`) left running and untouched.

## Found along the way

_(defects outside a step's scope go here, not into its diff)_

- (step 3) `wheel_spy.py` line 249: `time.sleep(360) # Check every 10 mins` —
  comment is wrong, 360 s is 6 minutes. Left untouched (this task must not edit
  `wheel_spy.py`).
