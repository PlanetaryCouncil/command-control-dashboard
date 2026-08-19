#!/usr/bin/env bash
# Is the board answering? If not — and only if the machine can actually
# help — CPR. Otherwise, wait.
#
# v1 of this file caused the outage it existed to prevent (2026-08-05):
# under memory pressure the server took longer than 8s to answer, so the
# medic kickstarted it, so a fresh FastAPI import began, so the next probe
# failed, so it kickstarted again — a restart loop that held the board down
# for twenty minutes and drove a 4-core box to load 189. Marsita: "dude who
# was supposed to be monitoring is killing it."
#
# So the medic now refuses to act in exactly the cases where acting hurts:
#
#   1. LOAD GATE. Above MAX_LOAD the box is thrashing, not wedged. A
#      starved machine needs fewer processes, never one more. Same gate the
#      rota, heartbeat and pipeline have had all along; the medic was the
#      one job that skipped it.
#   2. GRACE. A server that started moments ago is booting, not dead.
#   3. COOLDOWN. One kickstart per 30 minutes, whatever happens. Two
#      failures in a row mean something a restart cannot fix.
#   4. PATIENCE. 20s per probe, three probes, 15s apart — slow is not dead.
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$FLEET/../.venv/bin/python3"
STAMP="$FLEET/state/.medic-last-kick"
MAX_LOAD=8.0
GRACE=120          # seconds a fresh server is left alone
COOLDOWN=1800      # seconds between kickstarts, hard floor

say() { "$PY" "$FLEET/bin/events.py" board-medic "$1" "$2" >/dev/null 2>&1 || true; }
probe() { curl -s -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:8787/workers.json; }

# Vendor login + quota-shaped errors. Cheap, no agent turn. A dry
# scheduled vendor must not wait for the next council sitting to show.
"$PY" "$FLEET/bin/quotas.py" >/dev/null 2>&1 || true
"$PY" "$FLEET/bin/pressure.py" >/dev/null 2>&1 || true

ok=""
for _ in 1 2 3; do
  [ "$(probe)" = "200" ] && { ok=1; break; }
  sleep 15
done
[ -n "$ok" ] && exit 0

LOAD="$(uptime | sed -E 's/.*load averages?: *([0-9.]+).*/\1/')"
if awk "BEGIN{exit !($LOAD > $MAX_LOAD)}"; then
  say info "[medic] board silent but load is $LOAD — thrash, not wedge; waiting"
  exit 0
fi

PID="$(pgrep -f 'fleet.py serve 8787' | head -1)"
if [ -n "$PID" ]; then
  AGE="$(ps -o etimes= -p "$PID" 2>/dev/null | tr -d ' ')"
  if [ -n "$AGE" ] && [ "$AGE" -lt "$GRACE" ]; then
    say info "[medic] server is ${AGE}s old — still booting, leaving it alone"
    exit 0
  fi
fi

NOW="$(date +%s)"
LAST="$(cat "$STAMP" 2>/dev/null || echo 0)"
if [ $((NOW - LAST)) -lt "$COOLDOWN" ]; then
  say needs_you "[medic] board still down and a kickstart was tried $(( (NOW-LAST)/60 ))m ago — this needs your hands"
  exit 1
fi

mkdir -p "$FLEET/state"; echo "$NOW" > "$STAMP"
say warn "[medic] board silent, load $LOAD, server old enough — kickstarting"
launchctl kickstart -k "gui/$(id -u)/re.genesis.fleet-server"

for _ in $(seq 1 20); do
  sleep 3
  [ "$(probe)" = "200" ] && { say ok "[medic] board revived"; exit 0; }
done
say needs_you "[medic] kickstart did not revive the board — it needs your hands"
exit 1
