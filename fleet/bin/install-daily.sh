#!/usr/bin/env bash
# Install the daily summary as a systemd user timer (Linux) or a launchd
# agent (macOS). Idempotent: run it again to change the time.
#
# It belongs on whichever box is always awake — the NUC, which has linger on
# and cold-boots unattended. Scheduling it on the laptop would mean the one
# message Marsita reads arrives only on days the lid was open.
set -euo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(dirname "$FLEET")"
HOUR="${1:-09:00}"

# The venv that exists here, not the one that existed on someone else's
# machine — the same lesson as pipeline.venv_pytest().
PY=""
for v in .venv .venv311 .venv312 .venv313; do
  [[ -x "$REPO/$v/bin/python" ]] && { PY="$REPO/$v/bin/python"; break; }
done
[[ -n "$PY" ]] || { echo "no venv python under $REPO"; exit 1; }

if [[ "$(uname)" == "Linux" ]]; then
  UD="$HOME/.config/systemd/user"
  mkdir -p "$UD"
  cat > "$UD/fleet-daily.service" <<EOF
[Unit]
Description=Fleet daily summary — the one message the operator reads

[Service]
Type=oneshot
WorkingDirectory=$FLEET
ExecStart=$PY $FLEET/bin/daily.py --publish
ExecStart=$PY $FLEET/bin/daily.py --send
EOF
  cat > "$UD/fleet-daily.timer" <<EOF
[Unit]
Description=Fleet daily summary at $HOUR

[Timer]
OnCalendar=*-*-* $HOUR:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
  systemctl --user daemon-reload
  systemctl --user enable --now fleet-daily.timer
  systemctl --user list-timers fleet-daily.timer --no-pager
else
  PLIST="$HOME/Library/LaunchAgents/ai.fleet.daily.plist"
  H="${HOUR%%:*}"; M="${HOUR##*:}"
  cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>ai.fleet.daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$FLEET/bin/daily.py</string>
    <string>--publish-and-send</string>
  </array>
  <key>WorkingDirectory</key><string>$FLEET</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$((10#$H))</integer>
        <key>Minute</key><integer>$((10#$M))</integer></dict>
  <key>StandardOutPath</key><string>$FLEET/logs/daily.log</string>
  <key>StandardErrorPath</key><string>$FLEET/logs/daily.err.log</string>
</dict></plist>
EOF
  launchctl bootout "gui/$(id -u)/ai.fleet.daily" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "installed ai.fleet.daily at $HOUR"
fi
