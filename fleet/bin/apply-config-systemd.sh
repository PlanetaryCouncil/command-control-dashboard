#!/usr/bin/env bash
# Regenerate every fleet job as a systemd user timer from config.json.
#
# The Linux sibling of apply-config.sh, which writes launchd plists and does
# nothing at all on this box. That asymmetry is why nuc — the machine that is
# actually always on, in a cupboard, on fibre — served the dashboard for weeks
# while running none of the fleet.
#
# One schedule file, two backends. Change a cadence in config.json and run this.
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$FLEET/.." && pwd)"
CFG="$FLEET/config.json"
UNITS="$HOME/.config/systemd/user"
# Third place this same lesson has had to be learned: #32 fixed the pipeline,
# #33 fixed the watchdog, and the unit files still hardcoded `.venv`. On the
# NUC that is python 3.14 with none of the fleet's dependencies; the working
# environment is `.venv311`. Pick the venv that is actually furnished —
# pytest's presence is the marker — and fall back to the conventional path so
# a failure still names somewhere a reader expects to look.
PY="$REPO/.venv/bin/python3"
for _v in .venv .venv311 .venv312 .venv313; do
  if [[ -x "$REPO/$_v/bin/pytest" ]]; then PY="$REPO/$_v/bin/python3"; break; fi
done

[[ -f "$CFG" ]] || { echo "no config.json at $CFG"; exit 1; }
python3 -c "import json;json.load(open('$CFG'))" || { echo "config.json is not valid JSON"; exit 1; }

read -r HB_EVERY HB_AGENTS HB_LAPS WD_EVERY SI_H SI_M CO_EVERY CO_AGENTS CO_ROUNDS E2_H E2_M RO_EVERY RO_AGENTS PL_EVERY BM_EVERY LV_H LV_M <<<"$(python3 - "$CFG" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
hb = c["heartbeat"]
print(hb["every_seconds"], ",".join(hb["agents"]), hb.get("laps", 1),
      c["watchdogs"]["every_seconds"],
      c["self_improve"]["at_hour"], c["self_improve"].get("at_minute", 0),
      c.get("council", {}).get("every_seconds", 10800),
      ",".join(c.get("council", {}).get("agents", ["claude"])),
      c.get("council", {}).get("rounds", 2),
      c.get("e2e", {}).get("at_hour", 5), c.get("e2e", {}).get("at_minute", 30),
      c.get("rota", {}).get("every_seconds", 3600),
      ",".join(c.get("rota", {}).get("agents", ["claude"])),
      c.get("pipeline", {}).get("every_seconds", 7200),
      c.get("board_medic", {}).get("every_seconds", 300),
      c.get("local_voice", {}).get("at_hour", 6),
      c.get("local_voice", {}).get("at_minute", 15))
PY
)"

mkdir -p "$UNITS" "$FLEET/logs"

# A fleet job must never pile up on itself. launchd serialises by label; the
# systemd equivalent is Type=oneshot plus a timer that will not start a second
# run while the first is going, which is the default for oneshot services.
unit() {  # name, description, schedule-line, command...
  local name="$1" desc="$2" sched="$3"; shift 3
  # systemd parses ExecStart itself and does NOT run it through a shell, so
  # shell quoting is wrong here: printf %q escaped the commas in
  # "claude,hermes,openclaw" and the fleet went looking for an agent called
  # `claude\`. Double quotes are what systemd understands.
  local cmd="" a
  for a in "$@"; do
    a="${a//\\/\\\\}"; a="${a//\"/\\\"}"
    cmd+=" \"$a\""
  done
  cat > "$UNITS/fleet-$name.service" <<EOF
[Unit]
Description=$desc
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$FLEET
Environment=PATH=$HOME/.local/bin:$HOME/.local/share/mise/installs/node/lts/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
ExecStart=$cmd
# A job that hangs must not hold the timer forever.
TimeoutStartSec=3600
Nice=10
IOSchedulingClass=idle
EOF
  cat > "$UNITS/fleet-$name.timer" <<EOF
[Unit]
Description=$desc (schedule)

[Timer]
$sched
# Catch up after a reboot rather than silently skipping the window.
Persistent=true
# Stagger, so nine jobs do not all wake at once on a 4-core box.
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
EOF
  echo "  wrote fleet-$name"
}

every() { echo "OnBootSec=$((RANDOM % 300 + 120))
OnUnitActiveSec=${1}s"; }

# Round-robin, not a metronome. OnUnitActiveSec counts from when a run STARTS,
# so a job slower than its own interval silently queues against itself. This
# counts from when the previous run FINISHES: the next turn begins a short
# breath after the last one ends, forever, and two turns can never overlap.
# That is what "24/7 rota, non-stop" actually means on a box with 12 cores and
# a local model that takes 90s to think.
after() { echo "OnBootSec=120
OnUnitInactiveSec=${1}s"; }
daily() { printf 'OnCalendar=*-*-* %02d:%02d:00\n' "$1" "$2"; }

unit watchdogs   "Fleet watchdogs"        "$(every "$WD_EVERY")"  /bin/bash "$FLEET/bin/run-watchdogs.sh"
unit board-medic "Fleet board medic"      "$(every "$BM_EVERY")"  /bin/bash "$FLEET/bin/board-medic.sh"
unit pipeline    "Fleet build pipeline"   "$(every "$PL_EVERY")"  "$PY" "$FLEET/bin/pipeline.py" run
# rota.continuous_gap_seconds turns the rota from hourly into a loop: one
# agent at a time, next turn a breath after the last one ends. Absent, it
# stays on the shared hourly cadence, so Gaia is unaffected.
RO_GAP="$(python3 -c "import json;print(json.load(open('$CFG')).get('rota',{}).get('continuous_gap_seconds',''))")"
if [[ -n "$RO_GAP" ]]; then
  unit rota      "Fleet rota (continuous)" "$(after "$RO_GAP")"   "$PY" "$FLEET/bin/rota.py" --agents "$RO_AGENTS"
else
  unit rota      "Fleet rota"             "$(every "$RO_EVERY")"  "$PY" "$FLEET/bin/rota.py" --agents "$RO_AGENTS"
fi
unit council     "Fleet council"          "$(every "$CO_EVERY")"  "$PY" "$FLEET/bin/council.py" --agents "$CO_AGENTS" --rounds "$CO_ROUNDS"
unit heartbeat   "Fleet comms heartbeat"  "$(every "$HB_EVERY")"  "$PY" "$FLEET/bin/comms-heartbeat.py" --agents "$HB_AGENTS" --laps "$HB_LAPS"
unit e2e         "Fleet end-to-end tests" "$(daily "$E2_H" "$E2_M")" "$PY" "$FLEET/bin/e2e.py"
unit local-voice "Fleet local voice"      "$(daily "$LV_H" "$LV_M")" "$PY" "$FLEET/bin/localvoice.py"
unit self-improve "Self-improvement loop" "$(daily "$SI_H" "$SI_M")" /bin/bash "$REPO/self-improve/loop/run-cycle.sh"

systemctl --user daemon-reload
echo
echo "units written to $UNITS"
echo "enable one:   systemctl --user enable --now fleet-watchdogs.timer"
echo "see them:     systemctl --user list-timers 'fleet-*'"
echo "read a run:   journalctl --user -u fleet-watchdogs.service -n 50"
