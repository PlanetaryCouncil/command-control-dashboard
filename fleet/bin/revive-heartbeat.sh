#!/usr/bin/env bash
# Restart the comms heartbeat when it has flatlined.
#
# On 2026-08-04 agent-comms had recorded nothing for 19 hours while the
# watchdog sweep reported the board green and moved on. Detection already
# existed twice over (the board's stale flag, the probe); the repair did not.
# The e2e kill at 14:31 proved a comms-heartbeat process can be alive while
# recording nothing — alive-but-stuck, exactly the case a restart fixes.
# launchd owns the process, so the repair is `launchctl kickstart -k`: it
# restarts the job whether it is stuck, dead, or merely idle.
#
# Usage: revive-heartbeat.sh [workers-json]
#        (default: fleet/workers/agent-comms.json)
#
# Env overrides, used by the tests:
#   HEARTBEAT_MAX_AGE_S  staleness threshold in seconds (default 7200)
#   EVENTS_PY            events script (default fleet/bin/events.py) — the
#                        watchdog runs the test suite hourly, so tests must
#                        be able to point this away from the live event log
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HB_JSON="${1:-$FLEET/workers/agent-comms.json}"
MAX_AGE_S="${HEARTBEAT_MAX_AGE_S:-7200}"
EVENTS_PY="${EVENTS_PY:-$FLEET/bin/events.py}"
LABEL="re.genesis.comms-heartbeat"

# No record yet — nothing to judge, and kickstarting on absence would restart
# the heartbeat on every fresh checkout.
[[ -f "$HB_JSON" ]] || exit 0

AGE="$(python3 - "$HB_JSON" <<'PY'
import json, sys
from datetime import datetime, timezone
try:
    ts = json.load(open(sys.argv[1])).get("last_run", "")
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    print(int((datetime.now(timezone.utc) - dt).total_seconds()))
except Exception:
    print(-1)
PY
)"

# An unreadable timestamp is its own bug; restarting on garbage input would
# turn every parse error into a process restart.
if [[ "$AGE" -lt 0 || "$AGE" -le "$MAX_AGE_S" ]]; then
  exit 0
fi

if launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  echo "[fleet] agent-comms ${AGE}s stale — kickstarted $LABEL"
  python3 "$EVENTS_PY" fleet warn \
    "agent-comms ${AGE}s stale — kickstarted $LABEL" 2>/dev/null || true
else
  echo "[fleet] agent-comms ${AGE}s stale — kickstart of $LABEL FAILED"
  python3 "$EVENTS_PY" fleet warn \
    "agent-comms ${AGE}s stale and kickstart of $LABEL failed" 2>/dev/null || true
fi
exit 0
