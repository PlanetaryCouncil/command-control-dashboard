#!/usr/bin/env bash
# Legacy filename: this reuses the existing ccd-hub tunnel for the NUC board.
# It must never retarget hub.planetarycouncil.org, which is the porch.
# Target: nuc.planetarycouncil.org → 127.0.0.1:8787 on the NUC.
#
# Funnel cannot wear a custom domain (Tailscale certs are *.ts.net only).
# Cloudflare Tunnel can, and the origin never gets a public IP.
#
# One-time, on a machine with a browser (Gaia is fine):
#   cloudflared tunnel login
#   copy ~/.cloudflared/cert.pem to the NUC at the same path
#
# Then, only after explicit approval for machine changes:
#   bash fleet/bin/hub-tunnel.sh --apply
#
# DNS is deliberately not changed here. planetarycouncil.org must first be a
# Cloudflare zone, then nuc. can be routed as a separate approved external act.
set -euo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${HOME}/.local/bin"
CF="${HOME}/.cloudflared"
NAME="ccd-hub"
HOST="nuc.planetarycouncil.org"
ORIGIN="http://127.0.0.1:8787"
UNITS="${HOME}/.config/systemd/user"

if [[ "${1:-}" != "--apply" ]]; then
  echo "plan only: reuse tunnel $NAME for $HOST → $ORIGIN"
  echo "no files, services, downloads, tunnel, or DNS changed"
  echo "after approval: bash fleet/bin/hub-tunnel.sh --apply"
  exit 0
fi

mkdir -p "$BIN" "$CF" "$UNITS"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "installing cloudflared to $BIN"
  arch="$(uname -m)"
  case "$arch" in
    x86_64|amd64) asset="cloudflared-linux-amd64" ;;
    aarch64|arm64) asset="cloudflared-linux-arm64" ;;
    *) echo "unknown arch $arch"; exit 1 ;;
  esac
  curl -fsSL -o "$BIN/cloudflared" \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/${asset}"
  chmod +x "$BIN/cloudflared"
fi
export PATH="$BIN:$PATH"

if [[ ! -f "$CF/cert.pem" ]]; then
  echo "no $CF/cert.pem"
  echo "on a laptop with a browser: cloudflared tunnel login"
  echo "then copy cert.pem here and re-run this script"
  exit 2
fi

if ! cloudflared tunnel list 2>/dev/null | grep -q "$NAME"; then
  cloudflared tunnel create "$NAME"
fi

TID="$(cloudflared tunnel list -o json | python3 -c "
import json,sys
rows=json.load(sys.stdin)
hit=next((t for t in rows if t.get('name')=='$NAME'), None)
print(hit['id'] if hit else '')
")"
[[ -n "$TID" ]] || { echo "could not read tunnel id"; exit 1; }

cat > "$CF/config.yml" <<EOF
tunnel: $TID
credentials-file: $CF/${TID}.json
ingress:
  - hostname: $HOST
    service: $ORIGIN
  - service: http_status:404
EOF

cat > "$UNITS/hub-tunnel.service" <<EOF
[Unit]
Description=Cloudflare tunnel for $HOST
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=$BIN/cloudflared tunnel --config $CF/config.yml run
Restart=always
RestartSec=5
Nice=5

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now hub-tunnel.service

echo
echo "tunnel $NAME ($TID) → $ORIGIN"
echo "DNS unchanged. After the Cloudflare zone exists and approval is given:"
echo "  cloudflared tunnel route dns $NAME $HOST"
echo
echo "status:  systemctl --user status hub-tunnel.service"
echo "probe:   curl -sI https://$HOST/ | head"
