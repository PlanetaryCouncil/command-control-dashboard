#!/usr/bin/env bash
# Restart the comms heartbeat when it has flatlined.
#
# On 2026-08-04 agent-comms had recorded nothing for 19 hours while the
# watchdog sweep reported the board green and moved on. Detection already
# existed twice over (the board's stale flag, the probe); the repair did not.
# The e2e kill at 14:31 proved a comms-heartbeat process can be alive while
# recording nothing — alive-but-stuck, exactly the case a restart fixes.
# The repair restarts the job whether it is stuck, dead, or merely idle.
#
# It used to speak only launchd. Both machines run this script, and the NUC
# runs systemd -- so on the NUC the detection worked perfectly and the repair
# could never fire. agent-comms sat dead for 31 hours on 2026-09-03 with the
# watchdog dutifully logging "kickstart FAILED" once an hour, which is the
# exact failure this file was written to prevent, reintroduced by assuming
# one machine's init system (2026-09-03).
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
# One job, two names, because the two machines schedule it differently.
LABEL="re.genesis.comms-heartbeat"          # launchd, on Gaia
UNIT="fleet-heartbeat.service"              # systemd, on the NUC

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

# Whichever scheduler this box actually has. Trying both in turn rather than
# branching on `uname` keeps a third arrangement (a plain cron, a container)
# from silently landing in the launchd branch.
WHO=""
if command -v launchctl >/dev/null 2>&1 \
   && launchctl kickstart -k "gui/$(id -u)/$LABEL" >/dev/null 2>&1; then
  WHO="$LABEL"
elif command -v systemctl >/dev/null 2>&1 \
     && systemctl --user restart "$UNIT" >/dev/null 2>&1; then
  WHO="$UNIT"
fi

if [[ -n "$WHO" ]]; then
  echo "[fleet] agent-comms ${AGE}s stale — kickstarted $WHO"
  python3 "$EVENTS_PY" fleet warn \
    "agent-comms ${AGE}s stale — kickstarted $WHO" 2>/dev/null || true
else
  echo "[fleet] agent-comms ${AGE}s stale — no scheduler could restart it"
  python3 "$EVENTS_PY" fleet warn \
    "agent-comms ${AGE}s stale and no scheduler could restart it" 2>/dev/null || true
fi
exit 0
