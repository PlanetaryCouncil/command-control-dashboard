#!/usr/bin/env bash
# Every five minutes: is the board actually answering? If not, CPR.
#
# Born 2026-08-04 after a memory storm wedged the server with 83 piled
# threads — process alive, port silent, operator staring at a spinner
# ("WTF — why offline — annoying"). The heartbeat medic the fleet built
# for agent-comms, applied to the board itself. Marsita set the cadence:
# "maybe ping watchdog every 5 minutes?"
#
# Two failed probes ten seconds apart = wedged (one blip is just load).
# The kickstart is cheap; a silent board is not.
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$FLEET/../.venv/bin/python3"

probe() {
  curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8787/workers.json
}

[ "$(probe)" = "200" ] && exit 0
sleep 10
[ "$(probe)" = "200" ] && exit 0

"$PY" "$FLEET/bin/events.py" board-medic warn \
  "[medic] board silent on two probes - kickstarting fleet-server" || true
launchctl kickstart -k "gui/$(id -u)/re.genesis.fleet-server"

for _ in $(seq 1 15); do
  sleep 2
  if [ "$(probe)" = "200" ]; then
    "$PY" "$FLEET/bin/events.py" board-medic ok \
      "[medic] board revived by kickstart" || true
    exit 0
  fi
done
"$PY" "$FLEET/bin/events.py" board-medic needs_you \
  "[medic] kickstart did not revive the board - it needs your hands" || true
exit 1
