#!/usr/bin/env bash
# Reload the fleet server WITHOUT gambling the board on broken code.
#
# Born 2026-08-04 after a nested f-string compiled fine on python 3.14,
# was rejected by the server's 3.11, and took the live board down mid-
# session — Marsita, locked out: "possible to keep version online while
# you do magic?" This is that possibility:
#
#   1. compile every fleet module with THE SERVER'S interpreter
#   2. boot the new code on a scratch port and demand a real 200
#   3. only then restart the live server (the ~3s respawn is the whole
#      remaining downtime)
#
# Broken code now fails on the scratch port, and the board never blinks.
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$FLEET/../.venv/bin/python3"
SCRATCH=8790

echo "1/3 compile (with the server's own python)…"
"$PY" -m py_compile "$FLEET"/bin/*.py || { echo "REFUSED: fix before reload"; exit 1; }

echo "2/3 boot on scratch port ${SCRATCH} ..."
"$PY" "$FLEET/bin/fleet.py" serve "$SCRATCH" >/dev/null 2>&1 &
TRIAL=$!
ok=""
for _ in $(seq 1 40); do
  sleep 1
  if [ "$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$SCRATCH/workers.json")" = "200" ]; then
    ok=1; break
  fi
done
kill "$TRIAL" 2>/dev/null
[ -n "$ok" ] || { echo "REFUSED: new code never answered on $SCRATCH"; exit 1; }

echo "3/3 restarting the live server…"
launchctl kickstart -k "gui/$(id -u)/re.genesis.fleet-server"
for _ in $(seq 1 40); do
  sleep 1
  if [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8787/)" = "200" ]; then
    echo "live again"; exit 0
  fi
done
echo "WARNING: live server slow to return — check logs/server.err.log"
exit 1
