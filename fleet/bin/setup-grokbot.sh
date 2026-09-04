#!/usr/bin/env bash
# Give GrokBot its own desktop on this machine.
#
# GrokBot is an agent living in a datacenter. It needs to browse from a
# residential line rather than a datacenter range, driving a real Chrome it can
# see and click. Marsita weighed the IP-reputation cost and accepted it on
# 2026-09-04: "I'm going to use bots one way or another so may as well use it."
#
# xrdp, not RustDesk. RustDesk shares the one physical seat, which James is
# already using; xrdp gives each user an independent X session, so GrokBot
# browsing does not take the screen away from anyone.
#
# The line this does not cross: GrokBot browsing the web on Marsita's behalf
# from her line is the point. Turning the box into an exit node for other
# people's traffic is not, and nothing here installs a proxy.
#
# Run on the NUC as a user with sudo:   sudo bash setup-grokbot.sh
set -euo pipefail

USER_NAME="grokbot"
TEMPLATE="james"          # the working reference: desktop groups, no sudo

if [[ $EUID -ne 0 ]]; then
  echo "run me with sudo: sudo bash $0" >&2
  exit 1
fi

say() { printf '\n== %s\n' "$*"; }

say "user"
if id "$USER_NAME" >/dev/null 2>&1; then
  echo "  $USER_NAME already exists, leaving it alone"
  PASSWORD=""
else
  # A generated password, printed once. Nobody has to invent one, and it is
  # never weaker than whatever gets typed at 3am.
  PASSWORD="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 20)"
  adduser --disabled-password --gecos "GrokBot" "$USER_NAME"
  echo "$USER_NAME:$PASSWORD" | chpasswd
  echo "  created $USER_NAME"
fi

say "groups"
# Same set as the template account, and deliberately NOT sudo. An agent that
# executes code is a different risk class from a person on a remote desktop.
GROUPS_WANTED="$(id -nG "$TEMPLATE" 2>/dev/null | tr ' ' '\n' \
                 | grep -vx "$TEMPLATE" | grep -vx sudo | paste -sd, -)"
GROUPS_WANTED="${GROUPS_WANTED:-audio,video,plugdev,users}"
usermod -aG "$GROUPS_WANTED" "$USER_NAME"
echo "  $(id -nG "$USER_NAME")"
if id -nG "$USER_NAME" | tr ' ' '\n' | grep -qx sudo; then
  echo "  REFUSING: $USER_NAME ended up in sudo" >&2
  exit 1
fi

say "home is private"
# m's files are not readable from grokbot's session, and vice versa. The IP is
# shared; nothing else is.
chmod 750 "/home/$USER_NAME"

say "desktop"
echo "xfce4-session" > "/home/$USER_NAME/.xsession"
chown "$USER_NAME:$USER_NAME" "/home/$USER_NAME/.xsession"
chmod 644 "/home/$USER_NAME/.xsession"
echo "  xfce4-session"

say "xrdp"
systemctl enable --now xrdp
systemctl is-active xrdp
ss -ltnp 2>/dev/null | grep -E ':3389' || echo "  WARNING: nothing listening on 3389"

say "chrome"
command -v google-chrome-stable || echo "  WARNING: chrome not found on PATH"

say "done"
IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
cat <<TXT

  Hand GrokBot these four lines, nothing else:

    host      ${IP:-<the NUC's Tailscale IP>}
    port      3389 (RDP)
    user      $USER_NAME
    password  ${PASSWORD:-<unchanged — the account already existed>}

  Chrome is on the desktop. The profile is fresh: it shares the home IP and
  none of Marsita's logins.

  Kill switch, if it ever misbehaves:

    sudo pkill -u $USER_NAME; sudo usermod -L $USER_NAME

TXT
