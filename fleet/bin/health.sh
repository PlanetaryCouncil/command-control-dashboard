#!/usr/bin/env bash
# Is everything up, and if not, fix it.
#
# One unit where there were three. Marsita, 2026-09-04, looking at eleven
# timers: "watchdog = medic = heartbeat = same same, we don't want to
# overcomplicate."
#
# They are the same question asked of different things, and three separate
# timers asking it was three chances to race each other on a 14GB box. The
# cadences genuinely differ though -- the board wants a probe every five
# minutes, the project suites every hour, the comms relay once a day and it
# costs 960 seconds of wall clock -- so this runs on the fastest of them and
# gates the slower two behind a stamp file. Cheap check, expensive work.
set -uo pipefail
FLEET="$(cd "$(dirname "$0")/.." && pwd)"
STAMPS="$FLEET/logs/health"
mkdir -p "$STAMPS"

cfg() { python3 -c "import json;print(json.load(open('$FLEET/config.json'))$1)"; }

# Run "$@" only if $1 seconds have passed since it last ran.
due() {
  local name="$1" every="$2"; shift 2
  local stamp="$STAMPS/$name"
  if [[ -f "$stamp" ]]; then
    local age=$(( $(date +%s) - $(stat -f %m "$stamp" 2>/dev/null || stat -c %Y "$stamp") ))
    (( age < every )) && return 0
  fi
  # Stamp BEFORE running, not after. A job that hangs must not become a job
  # that starts again on the next tick -- that is the exact shape that pinned
  # six cores for a day on 2026-09-03.
  touch "$stamp"
  echo "--- $name"
  "$@"
}

# Every tick: the board itself. Two silent probes and it gets CPR.
/bin/bash "$FLEET/bin/board-medic.sh"

due watchdogs "$(cfg "['watchdogs']['every_seconds']")" \
    /bin/bash "$FLEET/bin/run-watchdogs.sh"

HB_AGENTS="$(python3 -c "import json;print(','.join(json.load(open('$FLEET/config.json'))['heartbeat']['agents']))")"
HB_LAPS="$(cfg "['heartbeat'].get('laps',1)")"
due heartbeat "$(cfg "['heartbeat']['every_seconds']")" \
    "$FLEET/../.venv/bin/python" "$FLEET/bin/comms-heartbeat.py" \
    --agents "$HB_AGENTS" --laps "$HB_LAPS"
