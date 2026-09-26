#!/usr/bin/env bash
# Launch the SPY wheel bot from anywhere (double-click, a symlink, or systemd).
# wheel_spy.py calls load_dotenv() for .env; run it from the repo root with
# the repo's venv so which .env and which interpreter are used is unambiguous.
set -euo pipefail

cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")"

if [[ ! -x venv/bin/python ]]; then
    echo "run.sh: $PWD/venv/bin/python not found. Create it with:" >&2
    echo "  python3 -m venv venv && venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

exec venv/bin/python -u wheel_spy.py "$@"
