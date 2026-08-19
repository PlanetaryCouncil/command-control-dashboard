#!/usr/bin/env bash
# Run the watchdog over every project registered in projects.txt.
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LIST="$FLEET/projects.txt"
[[ -f "$LIST" ]] || { echo "no projects.txt"; exit 1; }
PY="${PY:-$FLEET/../.venv/bin/python3}"
if ! "$PY" -c "import sys; sys.path.insert(0, '$FLEET/bin'); import pressure; raise SystemExit(pressure.too_hot())"; then
  python3 "$FLEET/bin/events.py" fleet warn \
    "watchdog deferred — machine hot (load or compressor)" 2>/dev/null || true
  echo "watchdog deferred — machine hot"
  exit 0
fi

# Repair before observing: a flatlined comms heartbeat gets a restart, not a
# report. This runs before the lock check below on purpose — an alive-but-stuck
# heartbeat can be the very process holding the plus-one lock, and a sweep that
# defers to a corpse would never reach the repair.
bash "$FLEET/bin/revive-heartbeat.sh" || true

# Defer to an agent already in flight. This is the largest job on the board —
# 167 tests, ~309s of a saturated four-core machine — and it was the only
# scheduled job not honouring the lock that comms-heartbeat.py, council.py and
# e2e.py all take. The rota traced the consequence on 2026-08-02: two council
# turns ran entirely inside a pytest sweep and were recorded as
# "[timed out after 300s]" from an agent that answers the same prompt in 25s.
# 601 seconds of agent capacity spent on two empty turns.
#
# The watchdog is the one that yields, not the agent. Tests re-run in an hour and
# the answer is unchanged; an agent turn in flight is burning a core right now
# and cannot be resumed.
LOCK="$FLEET/logs/.plusone-any.lock"
if [[ -f "$LOCK" ]]; then
  LOCKPID="$(cat "$LOCK" 2>/dev/null || echo 0)"
  if [[ -n "$LOCKPID" ]] && kill -0 "$LOCKPID" 2>/dev/null; then
    python3 "$FLEET/bin/events.py" fleet warn \
      "watchdog deferred — agent work in flight (pid $LOCKPID)" 2>/dev/null
    echo "watchdog deferred: pid $LOCKPID holds the lock"
    exit 0
  fi
fi

python3 "$FLEET/bin/events.py" fleet info "watchdog sweep started" 2>/dev/null

while IFS= read -r line; do
  line="${line%%#*}"                      # strip comments
  line="$(echo "$line" | xargs)"          # trim whitespace
  [[ -z "$line" ]] && continue
  if [[ ! -d "$line" ]]; then
    echo "skip (missing): $line"; continue
  fi
  bash "$FLEET/bin/watchdog.sh" "$line"

  # Red tests get one repair attempt, on a branch, never merged. The fixer
  # re-checks everything itself (clean tree, still red, tests untouched) and
  # exits harmlessly if any precondition fails.
  name="$(basename "$line")"
  status="$(python3 -c "import json,sys
try: print(json.load(open('$FLEET/workers/$name.json'))['status'])
except Exception: print('')" 2>/dev/null)"
  if [[ "$status" == "fail" && "${FLEET_AUTOFIX:-1}" == "1" ]]; then
    bash "$FLEET/bin/fixer.sh" "$line" || true
  fi
done < "$LIST"

# Refresh the static snapshot too, so index.html is current even if the
# always-on server happens to be down.
python3 "$FLEET/bin/events.py" fleet info "watchdog sweep finished" 2>/dev/null
python3 "$FLEET/bin/fleet.py" render >/dev/null 2>&1 || true

# A rota turn deferred for load gets one retry now — the sweep ending is the
# idle window its pending marker was waiting for. No-op if nothing is pending,
# and rota's own load gate still applies if the machine is somehow still busy.
python3 "$FLEET/bin/rota.py" --retry-deferred || true
