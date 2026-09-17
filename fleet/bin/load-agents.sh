#!/usr/bin/env bash
# Load the re.genesis launch agents into the GUI session.
#
# This cannot be run from the board's terminal: that tmux was started by
# launchd with PPID 1, so it lives in macOS's `Background` session, and
# bootstrapping into gui/<uid> from there fails with `Input/output error`.
# Run it from Terminal.app on the desktop.
#
# None of these plists has RunAtLoad, so loading starts nothing immediately —
# each waits for its own schedule.
set -u

AGENTS=(comms-heartbeat council e2e local-voice pipeline rota self-improve watchdogs)
UID_="$(id -u)"

# No sudo. A LaunchAgent belongs to a user, and under sudo `id -u` is 0, so
# this asks to bootstrap into gui/0 -- a domain that does not exist. macOS
# answers "Domain does not support specified action", which sounds like a
# broken plist and is really just the wrong user (2026-09-17).
if [[ "$UID_" == "0" ]]; then
  echo "Do not run this with sudo. Launch agents belong to your user, not root."
  echo "Run it again as yourself:"
  echo "  ~/projects/command-control-dashboard/fleet/bin/load-agents.sh"
  exit 1
fi

if [[ "$(launchctl managername 2>/dev/null)" != "Aqua" ]]; then
  echo "This shell is in the '$(launchctl managername 2>/dev/null)' session."
  echo "Launch agents live in Aqua. Run this from Terminal.app on the desktop."
  exit 1
fi

for n in "${AGENTS[@]}"; do
  plist="$HOME/Library/LaunchAgents/re.genesis.$n.plist"
  if [[ ! -f "$plist" ]]; then
    printf '  %-16s no plist\n' "$n"; continue
  fi
  if launchctl print "gui/$UID_/re.genesis.$n" >/dev/null 2>&1; then
    printf '  %-16s already loaded\n' "$n"; continue
  fi
  if out="$(launchctl bootstrap "gui/$UID_" "$plist" 2>&1)"; then
    printf '  %-16s loaded\n' "$n"
  else
    printf '  %-16s FAILED: %s\n' "$n" "$out"
  fi
done
