#!/usr/bin/env bash
# The one message a day worth reading, plus the pulse check that proves the
# offline fallback still answers.
#
# local-voice was its own timer at 06:15 asking the local model one short
# question, so the day the wifi dies we already know whether it works. That is
# a fact the daily report should carry anyway, so it moves in here rather than
# holding a timer of its own. It now runs at report o'clock instead of dawn --
# the answer does not depend on the hour.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
FLEET="$REPO/fleet"
PY="$REPO/.venv/bin/python"
cd "$REPO"

"$PY" "$FLEET/bin/localvoice.py" || true
/bin/bash "$FLEET/bin/publish-report.sh"
