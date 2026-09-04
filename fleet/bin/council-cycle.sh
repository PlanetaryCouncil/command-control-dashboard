#!/usr/bin/env bash
# The board deliberates, and once a day it rewrites itself.
#
# Marsita, 2026-09-04: "council and self-improve should be same as well ---->
# board decides how to improve itself... And possible to merge without me,
# just report on the change log."
#
# They were two timers because they were written months apart, not because
# they are two things. A council that proposes improvements and a loop that
# implements them are the same loop with a gap in the middle.
#
# Council runs every sitting. The self-improvement cycle is expensive and
# mines a day of transcripts, so it runs at most once per calendar day --
# whichever sitting happens to be the first one after it is due.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
FLEET="$REPO/fleet"
PY="$REPO/.venv/bin/python"
cd "$REPO"

cfg() { python3 -c "import json;print(json.load(open('$FLEET/config.json'))$1)"; }

AGENTS="$(python3 -c "import json;print(','.join(json.load(open('$FLEET/config.json'))['council']['agents']))")"
"$PY" "$FLEET/bin/council.py" --agents "$AGENTS" \
      --rounds "$(cfg "['council'].get('rounds',2)")" || true

# Once a day. The stamp is written before the run: a cycle that hangs must not
# come back on the next sitting.
STAMP="$FLEET/logs/self-improve.day"
TODAY="$(date -u +%Y-%m-%d)"
if [[ "$(cat "$STAMP" 2>/dev/null || true)" != "$TODAY" ]]; then
  mkdir -p "$(dirname "$STAMP")"
  echo "$TODAY" > "$STAMP"
  echo "--- self-improve"
  /bin/bash "$REPO/self-improve/loop/run-cycle.sh" || true
fi
