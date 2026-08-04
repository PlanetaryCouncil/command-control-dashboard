#!/usr/bin/env bash
# Take the site offline. The software version of closing the lid.
#
# Deliberately dumb: no arguments, no flags, no confirmation prompt. Anything you
# have to answer a question about is something you cannot run while panicking,
# and the whole value of this file is being usable in the worst thirty seconds.
#
# It stops the public surface and leaves everything else alone — the data stays,
# the fleet stays, nothing is deleted. Going dark and destroying evidence are
# different acts, and only one of them is ever the right one.
#
#   bash fleet/bin/panic.sh
#
# PANIC_DRY_RUN=1 prints what it would do and touches nothing. That exists for
# the tests, not for you — a panic button nobody exercises is a panic button
# nobody can trust, and this one was broken for hours without anyone noticing.
set -uo pipefail

log() { printf '%s\n' "$*"; }
stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
dry=${PANIC_DRY_RUN:-}

log "PANIC — taking the public surface down at $stamp"

# The CLI's default socket is not necessarily the daemon serving the funnel.
# On 2026-08-03 this machine had a dead 1.94.2 network extension still holding
# the default LocalAPI while brew's 1.98.10 tailscaled ran the actual funnel on
# /var/run/tailscaled.socket. `tailscale funnel reset` reached the corpse,
# reported success, and left the site on the public internet. So: pick the
# socket that has a serve config on it, and never trust the exit code alone.
ts_sock=""
for s in /var/run/tailscaled.socket /var/run/tailscale/tailscaled.sock; do
  [ -S "$s" ] || continue
  if tailscale --socket="$s" serve status 2>/dev/null | grep -q .; then
    ts_sock="$s"
    break
  fi
done
ts() { if [ -n "$ts_sock" ]; then tailscale --socket="$ts_sock" "$@"; else tailscale "$@"; fi; }

# 1. Close the tunnel first. Until this is gone the site is reachable no matter
#    what happens to the local process. This covers every port at once — the
#    cockpit on 443 and the fleet board on 8443 — because `reset` clears the
#    whole serve config, not one entry.
if command -v tailscale >/dev/null 2>&1; then
  if [ -n "$dry" ]; then
    log "  ·  DRY RUN: would run 'tailscale --socket=${ts_sock:-default} funnel reset'"
  else
    ts funnel reset >/dev/null 2>&1
    # Verify. The exit code lies when the CLI is talking to the wrong daemon,
    # and a false ✅ here is worse than no script at all: you walk away.
    if ts serve status 2>/dev/null | grep -qE "Funnel on|proxy"; then
      log "  ❌ TUNNEL IS STILL UP — the site is still public."
      log "     Try:  tailscale --socket=/var/run/tailscaled.socket funnel reset"
      log "     Or pull the plug: turn off wifi."
    else
      log "  ✅ tunnel closed (socket: ${ts_sock:-default})"
    fi
  fi
else
  log "  ·  tailscale not installed — skipped"
fi

# 2. Stop the cockpit and the fleet board. The board used to be localhost-only,
#    which is why it was left running; since 2026-08-03 it is funnelled on 8443,
#    so leaving it up leaves a public surface up.
for pat in "uvicorn app.main:app" "fleet.py serve"; do
  if [ -n "$dry" ]; then
    pgrep -f "$pat" >/dev/null 2>&1 \
      && log "  ·  DRY RUN: would stop '$pat'" \
      || log "  ·  DRY RUN: '$pat' is not running"
  elif pkill -f "$pat" 2>/dev/null; then
    log "  ✅ stopped: $pat"
  else
    log "  ·  not running: $pat"
  fi
done

# 3. Leave a mark. A site that went dark with no record of why is a mystery to
#    whoever looks later, including you.
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
# PANIC_EVENTS exists so the tests can exercise the real path without writing
# `panic.offline` into the live log. They did, twice, on 2026-08-03 — fake
# entries in the record of a safety event, which is the one log that has to be
# true. Nobody running this in anger ever sets it.
events="${PANIC_EVENTS:-$root/data/events.jsonl}"
if [ -n "$dry" ]; then
  log "  ·  DRY RUN: would record panic.offline in data/events.jsonl"
elif [ -w "$(dirname "$events")" ]; then
  printf '{"ts":"%s","kind":"panic.offline","by":"panic.sh"}\n' "$stamp" >> "$events"
  log "  ✅ recorded in data/events.jsonl"
fi

log ""
log "Public surface is down. Data is untouched — nothing was deleted."
log "If this was for prohibited content, read docs/MODERATION.md before"
log "touching anything: do not forward it, do not open links, report it."
log ""
log "To come back up:"
log "  TRUST_PROXY=1 uv run uvicorn app.main:app --port 8770"
log "  python3 fleet/bin/fleet.py serve 8787"
log "  tailscale --socket=/var/run/tailscaled.socket funnel --bg 8770"
