#!/usr/bin/env bash
# The one message the operator reads, at 09:00, on their phone.
#
# Two ExecStart lines in one unit is a systemd feature that hides an
# ordering assumption: --publish must finish before --send has anything to
# send. A script says so out loud, and can be run by hand to test it.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$REPO/.venv/bin/python"
cd "$REPO"
"$PY" "$REPO/fleet/bin/daily.py" --publish || true
"$PY" "$REPO/fleet/bin/daily.py" --send
