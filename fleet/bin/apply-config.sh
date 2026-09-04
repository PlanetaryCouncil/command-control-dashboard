#!/usr/bin/env bash
# Regenerate and reload every launchd job from config.json.
#
# The schedule lives in one readable file rather than scattered across four
# property lists, because changing a cadence should not mean hand-editing XML in
# ~/Library/LaunchAgents and remembering to reload it.

set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$FLEET/.." && pwd)"
CFG="$FLEET/config.json"
AGENTS_DIR="$HOME/Library/LaunchAgents"
PY="$REPO/.venv/bin/python3"
PATH_LINE="/Users/$USER/.local/bin:/opt/homebrew/bin:/usr/local/opt/node@22/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

[[ -f "$CFG" ]] || { echo "no config.json at $CFG"; exit 1; }
python3 -c "import json,sys; json.load(open('$CFG'))" || { echo "config.json is not valid JSON"; exit 1; }

read -r HB_EVERY HB_AGENTS HB_LAPS WD_EVERY SI_H SI_M CO_EVERY CO_AGENTS CO_ROUNDS E2_H E2_M RP_H RP_M RO_EVERY RO_AGENTS PL_EVERY BM_EVERY LV_H LV_M <<<"$(python3 - "$CFG" <<'PY'
import json, sys
c = json.load(open(sys.argv[1]))
hb = c["heartbeat"]
print(hb["every_seconds"], ",".join(hb["agents"]), hb.get("laps", 1),
      c["watchdogs"]["every_seconds"],
      c["self_improve"]["at_hour"], c["self_improve"].get("at_minute", 0),
      c.get("council", {}).get("every_seconds", 10800),
      ",".join(c.get("council", {}).get("agents", ["claude", "hermes"])),
      c.get("council", {}).get("rounds", 2),
      c.get("e2e", {}).get("at_hour", 5), c.get("e2e", {}).get("at_minute", 30),
      c.get("report", {}).get("at_hour", 19),
      c.get("report", {}).get("at_minute", 0),
      c.get("rota", {}).get("every_seconds", 3600),
      ",".join(c.get("rota", {}).get("agents", ["claude", "hermes", "openclaw"])),
      c.get("pipeline", {}).get("every_seconds", 7200),
      c.get("board_medic", {}).get("every_seconds", 300),
      c.get("local_voice", {}).get("at_hour", 6),
      c.get("local_voice", {}).get("at_minute", 15))
PY
)"

CHANGED_JOBS=()

write_plist() {  # label, interval_or_calendar_xml, program args...
  local label="$1" schedule="$2"; shift 2
  local before=""
  [[ -f "$AGENTS_DIR/$label.plist" ]] && before="$(shasum -a 256 "$AGENTS_DIR/$label.plist" | awk '{print $1}')"
  local args=""
  for a in "$@"; do args+="        <string>$a</string>"$'\n'; done
  cat > "$AGENTS_DIR/$label.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$label</string>
    <key>ProgramArguments</key>
    <array>
$args    </array>
    <key>WorkingDirectory</key><string>$FLEET</string>
    <key>EnvironmentVariables</key>
    <dict><key>PATH</key><string>$PATH_LINE</string></dict>
$schedule
    <key>StandardOutPath</key><string>$FLEET/logs/$label.out.log</string>
    <key>StandardErrorPath</key><string>$FLEET/logs/$label.err.log</string>
    <key>ProcessType</key><string>Background</string>
    <key>LowPriorityIO</key><true/>
</dict>
</plist>
EOF
  # Reload only what actually changed. macOS posts a "Background Items Added"
  # notification on every launchctl load, so blindly reloading six jobs on every
  # config run produced six notifications and told the user nothing.
  local after
  after="$(shasum -a 256 "$AGENTS_DIR/$label.plist" | awk '{print $1}')"
  if [[ "$before" != "$after" ]] || ! launchctl list | grep -q "$label"; then
    CHANGED_JOBS+=("$label")
  fi
}

mkdir -p "$FLEET/logs"

write_plist re.genesis.comms-heartbeat \
  "    <key>StartInterval</key><integer>$HB_EVERY</integer>" \
  "$PY" "$FLEET/bin/comms-heartbeat.py" --agents "$HB_AGENTS" --laps "$HB_LAPS"

write_plist re.genesis.watchdogs \
  "    <key>StartInterval</key><integer>$WD_EVERY</integer>" \
  /bin/bash "$FLEET/bin/run-watchdogs.sh"

write_plist re.genesis.council \
  "    <key>StartInterval</key><integer>$CO_EVERY</integer>" \
  "$PY" "$FLEET/bin/council.py" --agents "$CO_AGENTS" --rounds "$CO_ROUNDS"

# One agent, in rotation, asking what would be better rather than what is broken.
# Scheduled like everything else so it runs whether or not anyone is at a
# terminal — the point is the loop, not the invocation.
write_plist re.genesis.rota \
  "    <key>StartInterval</key><integer>$RO_EVERY</integer>" \
  "$PY" "$FLEET/bin/rota.py" --agents "$RO_AGENTS"

# Proposals become branches; a different vendor verifies; a human merges.
# The rota writes, this reads — before it existed the rota was write-only.
write_plist re.genesis.pipeline \
  "    <key>StartInterval</key><integer>$PL_EVERY</integer>" \
  "$PY" "$FLEET/bin/pipeline.py" run

# The board's own pulse check. Cheap curl, so a five-minute cadence costs
# nothing; a wedged server costs the whole front door.
write_plist re.genesis.board-medic \
  "    <key>StartInterval</key><integer>$BM_EVERY</integer>" \
  /bin/bash "$FLEET/bin/board-medic.sh"

# One ping a day so the offline fallback is known-good, not assumed good.
write_plist re.genesis.local-voice \
  "    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>$LV_H</integer><key>Minute</key><integer>$LV_M</integer></dict>" \
  "$PY" "$FLEET/bin/localvoice.py"

# The day's summary, published to this repo's own Pages. Gaia runs it rather
# than the NUC because Gaia is the box with the push credentials.
write_plist re.genesis.report \
  "<key>StartCalendarInterval</key><dict><key>Hour</key><integer>$RP_H</integer><key>Minute</key><integer>$RP_M</integer></dict>" \
  /bin/bash "$FLEET/bin/publish-report.sh"

write_plist re.genesis.e2e \
  "    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>$E2_H</integer><key>Minute</key><integer>$E2_M</integer></dict>" \
  "$PY" "$FLEET/bin/e2e.py"

write_plist re.genesis.self-improve \
  "    <key>StartCalendarInterval</key>
    <dict><key>Hour</key><integer>$SI_H</integer><key>Minute</key><integer>$SI_M</integer></dict>" \
  /bin/bash "$REPO/self-improve/loop/run-cycle.sh"

HEAVY=1
if ! "$PY" -c "import sys; sys.path.insert(0, '$FLEET/bin'); import heavygate; raise SystemExit(0 if heavygate.enabled() else 1)"; then
  HEAVY=0
fi

if [[ "$HEAVY" -eq 0 ]]; then
  echo "  heavy work off on $(hostname -s) — unloading council/rota/heartbeat"
  for label in re.genesis.council re.genesis.rota re.genesis.watchdogs \
               re.genesis.pipeline re.genesis.comms-heartbeat \
               re.genesis.e2e re.genesis.self-improve re.genesis.local-voice; do
    launchctl unload "$AGENTS_DIR/$label.plist" 2>/dev/null || true
    echo "  unloaded $label"
  done
elif [[ ${#CHANGED_JOBS[@]} -eq 0 ]]; then
  echo "  no schedule changes — nothing reloaded"
else
  for label in "${CHANGED_JOBS[@]}"; do
    launchctl unload "$AGENTS_DIR/$label.plist" 2>/dev/null
    launchctl load "$AGENTS_DIR/$label.plist" 2>/dev/null && echo "  reloaded $label"
  done
fi

echo
echo "schedule now:"
echo "  heartbeat    every ${HB_EVERY}s  ($HB_AGENTS)"
echo "  watchdogs    every ${WD_EVERY}s"
echo "  council      every ${CO_EVERY}s  ($CO_AGENTS, $CO_ROUNDS rounds)"
echo "  rota         every ${RO_EVERY}s  ($RO_AGENTS — one per firing)"
echo "  pipeline     every ${PL_EVERY}s  (build claude → verify a different vendor → human merges)"
echo "  board-medic  every ${BM_EVERY}s  (probe :8787, kickstart if silent)"
echo "  local-voice  daily at $(printf '%02d:%02d' "$LV_H" "$LV_M")  (offline fallback pulse)"
echo "  e2e          daily at $(printf '%02d:%02d' "$E2_H" "$E2_M")"
echo "  self-improve daily at $(printf '%02d:%02d' "$SI_H" "$SI_M")"
