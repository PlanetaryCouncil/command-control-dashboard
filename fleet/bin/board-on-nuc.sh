#!/usr/bin/env bash
# Local window onto the NUC board. Gaia keeps :8787. NUC is :8788.
#
# Same-port hijack was the first version — the habit URL became the
# cupboard and the laptop board vanished. A second port is the whole
# point of two machines.
#
# Uses ssh Host `nuc` from ~/.ssh/config. No LAN login in this file.
set -euo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS="$HOME/Library/LaunchAgents"
LABEL=re.genesis.board-tunnel
PLIST="$AGENTS/$LABEL.plist"
LOG="$FLEET/logs"
LOCAL_PORT=8788

mkdir -p "$LOG" "$AGENTS"

echo "1/3 Gaia back on :8787, tunnel moves to :${LOCAL_PORT}..."
launchctl unload "$PLIST" 2>/dev/null || true
for _ in 1 2 3 4 5 6 7 8; do
  if ! lsof -nP -iTCP:8787 -sTCP:LISTEN >/dev/null 2>&1; then
    break
  fi
  sleep 0.3
done
launchctl load "$AGENTS/re.genesis.fleet-server.plist" 2>/dev/null || true
launchctl load "$AGENTS/re.genesis.board-medic.plist" 2>/dev/null || true

echo "2/3 writing ${LABEL}..."
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/ssh</string>
        <string>-N</string>
        <string>-o</string><string>BatchMode=yes</string>
        <string>-o</string><string>ExitOnForwardFailure=yes</string>
        <string>-o</string><string>ServerAliveInterval=30</string>
        <string>-o</string><string>ServerAliveCountMax=3</string>
        <string>-L</string><string>127.0.0.1:${LOCAL_PORT}:127.0.0.1:8787</string>
        <string>nuc</string>
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>StandardOutPath</key><string>$LOG/board-tunnel.out.log</string>
    <key>StandardErrorPath</key><string>$LOG/board-tunnel.err.log</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "3/3 waiting for NUC on :${LOCAL_PORT}..."
ok=""
for _ in $(seq 1 20); do
  if [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:${LOCAL_PORT}/workers.json)" = "200" ]; then
    ok=1; break
  fi
  sleep 0.5
done
if [ -z "$ok" ]; then
  echo "WARNING: tunnel loaded but :${LOCAL_PORT} did not answer yet"
  echo "  logs: $LOG/board-tunnel.err.log"
  exit 1
fi
echo "Gaia  http://127.0.0.1:8787"
echo "NUC   http://127.0.0.1:${LOCAL_PORT}"
exit 0
