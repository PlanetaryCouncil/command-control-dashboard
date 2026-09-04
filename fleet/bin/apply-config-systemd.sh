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
PY="$REPO/.venv/bin/python3"

[[ -f "$CFG" ]] || { echo "no config.json at $CFG"; exit 1; }
python3 -c "import json;json.load(open('$CFG'))" || { echo "config.json is not valid JSON"; exit 1; }

read -r HB_EVERY HB_AGENTS HB_LAPS WD_EVERY SI_H SI_M CO_EVERY CO_AGENTS CO_ROUNDS E2_H E2_M RO_EVERY RO_AGENTS PL_EVERY BM_EVERY LV_H LV_M RP_H RP_M <<<"$(python3 - "$CFG" <<'PY'
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
      c.get("local_voice", {}).get("at_minute", 15),
      c.get("report", {}).get("at_hour", 19),
      c.get("report", {}).get("at_minute", 0))
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
TimeoutStartSec=${UNIT_TIMEOUT:-3600}
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

# Six units. There were eleven, and two of them ran the same command --
# fleet-pipeline and fleet-build both called pipeline.py run. Marsita,
# 2026-09-04, looking at the org chart: "seriously I have such a super duper
# architecture? [...] we don't need that many processes... If we could get
# down to 6 or 7 would be great."
#
# Each collapse also removes a way for two timers to race each other on a
# 14GB box, which is the class of bug that pinned six cores for a day.
#
#   rota      the loop, unchanged
#   build     backlog.sh -- absorbs pipeline, it already ran it
#   council   council.py + self-improve once a day
#   health    board-medic + watchdogs + heartbeat, gated by stamp files
#   e2e       daily. the only thing that can say the fleet still works
#   report    the daily page + the local-voice pulse
#
# The tests did not shrink. The processes did.

unit health      "Fleet health"           "$(every "$BM_EVERY")"  /bin/bash "$FLEET/bin/health.sh"
# rota.continuous_gap_seconds turns the rota from hourly into a loop: one
# agent at a time, next turn a breath after the last one ends. Absent, it
# stays on the shared hourly cadence, so Gaia is unaffected.
RO_GAP="$(python3 -c "import json;print(json.load(open('$CFG')).get('rota',{}).get('continuous_gap_seconds',''))")"
if [[ -n "$RO_GAP" ]]; then
  unit rota      "Fleet rota (continuous)" "$(after "$RO_GAP")"   "$PY" "$FLEET/bin/rota.py" --agents "$RO_AGENTS"
else
  unit rota      "Fleet rota"             "$(every "$RO_EVERY")"  "$PY" "$FLEET/bin/rota.py" --agents "$RO_AGENTS"
fi
unit council     "Fleet council"          "$(every "$CO_EVERY")"  /bin/bash "$FLEET/bin/council-cycle.sh"
unit e2e         "Fleet end-to-end tests" "$(daily "$E2_H" "$E2_M")" "$PY" "$FLEET/bin/e2e.py"
unit report      "Fleet daily report"     "$(daily "$RP_H" "$RP_M")" /bin/bash "$FLEET/bin/report-cycle.sh"
# The 09:00 Telegram message. Not merged into report: one is pushed to a
# phone at breakfast, the other is a page that waits until evening. It ran
# for weeks as a hand-written unit apply-config knew nothing about.
DY_H="$(python3 -c "import json;print(json.load(open('$CFG')).get('daily',{}).get('at_hour',9))")"
DY_M="$(python3 -c "import json;print(json.load(open('$CFG')).get('daily',{}).get('at_minute',0))")"
unit daily       "Fleet daily summary"    "$(daily "$DY_H" "$DY_M")" /bin/bash "$FLEET/bin/daily-summary.sh"

# The builder. ONE unit, not three template instances, and it absorbs the
# separate pipeline timer -- backlog.sh has always ended by calling
# pipeline.py run, so a second timer running the same command was two
# builders racing for one worktree.
#
# What was here before, hand-written and never generated from config:
#
#     fleet-build@{agy,claude,grok}.timer   OnUnitInactiveSec=30s
#     fleet-build@.service                  TimeoutStartSec=14400
#
# Three copies of a four-hour job restarted thirty seconds after finishing.
# Each ran autotriage AND pipeline, each of those called hermes, and hermes on
# the NUC was a 3B model on the CPU at 5 tokens/sec. Six callers, six cores,
# 6d05h of CPU burned in 25h of wall clock, the box 3GB into swap -- and the
# pipeline built nothing at all from 2026-09-01 to 2026-09-04 because every
# slot was queued behind the last one.
#
# The fix is structural, not a smaller number: one unit means one builder at a
# time and no instance can race another. backlog.sh already picks the name
# itself via next_builder.py when FLEET_BUILDER is unset, so the round-robin
# survives -- it just stops happening in parallel.
BD_GAP="$(python3 -c "import json;print(json.load(open('$CFG')).get('builders',{}).get('gap_seconds',300))")"
BD_MAX="$(python3 -c "import json;print(json.load(open('$CFG')).get('builders',{}).get('max_seconds',1800))")"
UNIT_TIMEOUT="$BD_MAX" \
  unit build     "Fleet builder"          "$(after "$BD_GAP")"    /bin/bash "$FLEET/bin/backlog.sh"

# Retire what was collapsed. A unit that is no longer generated but is still
# enabled keeps firing from the last time apply-config wrote it -- which is
# exactly how three hand-written fleet-build@ instances kept running long
# after nobody remembered creating them.
RETIRED="watchdogs board-medic heartbeat pipeline local-voice self-improve"
for name in $RETIRED; do
  if systemctl --user list-unit-files "fleet-$name.timer" 2>/dev/null | grep -q "fleet-$name"; then
    systemctl --user disable --now "fleet-$name.timer" >/dev/null 2>&1 || true
    rm -f "$UNITS/fleet-$name.timer" "$UNITS/fleet-$name.service"
    echo "  retired fleet-$name"
  fi
done
# The three template instances the collapse replaces.
for i in agy claude grok; do
  systemctl --user disable --now "fleet-build@$i.timer" >/dev/null 2>&1 || true
  rm -f "$UNITS/fleet-build@$i.timer"
done
rm -f "$UNITS/fleet-build@.service"

systemctl --user daemon-reload
# The sitting set. Writing units without enabling them is how NUC served
# the board for weeks while running none of the fleet. Load and quota
# pulse live on board-medic.
# report sits too: a summary that is written but never scheduled is a
# summary of the one day someone remembered to run it.
SITTING="rota council health e2e report build daily"
for name in $SITTING; do
  systemctl --user enable --now "fleet-$name.timer" >/dev/null
  echo "  enabled fleet-$name.timer"
done
echo
echo "units written to $UNITS"
echo "see them:     systemctl --user list-timers 'fleet-*'"
echo "read a run:   journalctl --user -u fleet-rota.service -n 50"
