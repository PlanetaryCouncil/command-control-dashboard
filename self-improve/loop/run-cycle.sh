#!/usr/bin/env bash
# One unattended self-improvement cycle.
#
# Defense in depth: the orchestrator prompt tells the agent what not to touch,
# a deny-list blocks it at the permission layer, and the checksum guard below
# catches it regardless of whether either held. The guard is the only layer
# that does not depend on the model behaving.

set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO" || exit 1

CLAUDE_BIN="${CLAUDE_BIN:-$(command -v claude || echo "$HOME/.local/bin/claude")}"
WINDOW_DAYS="${WINDOW_DAYS:-14}"
TIMEOUT_SECS="${TIMEOUT_SECS:-1800}"
STAMP="$(date +%Y-%m-%dT%H-%M-%S)"
LOG="$REPO/logs/cycle-$STAMP.log"
LOCK="$REPO/.cycle.lock"

mkdir -p "$REPO/logs" "$REPO/state" "$REPO/proposals"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

# --- single-instance lock (stale locks from crashed runs are reclaimed) ------
if ! mkdir "$LOCK" 2>/dev/null; then
  if [[ -f "$LOCK/pid" ]] && ! kill -0 "$(cat "$LOCK/pid" 2>/dev/null)" 2>/dev/null; then
    log "reclaiming stale lock"; rm -rf "$LOCK"; mkdir "$LOCK" || exit 1
  else
    log "cycle already running; exiting"; exit 0
  fi
fi
echo $$ > "$LOCK/pid"
trap 'rm -rf "$LOCK"' EXIT

# --- integrity guard: snapshot files the agent must never modify -------------
SETTINGS="$HOME/.claude/settings.json"
GUARD_DIR="$REPO/state/.guard"
mkdir -p "$GUARD_DIR"
[[ -f "$SETTINGS" ]] && cp "$SETTINGS" "$GUARD_DIR/settings.json.bak"

checksum() { [[ -f "$1" ]] && shasum -a 256 "$1" 2>/dev/null | awk '{print $1}' || echo "absent"; }
BEFORE_SETTINGS="$(checksum "$SETTINGS")"

python3 "$REPO/../fleet/bin/events.py" self-improve info "cycle started" 2>/dev/null
log "=== cycle $STAMP ==="

# main is what a human approved; an agent proposes on a branch and never merges.
ORIG_BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
CYCLE_BRANCH="self-improve/cycle-$STAMP"
if [[ -n "$(git -C "$REPO" status --porcelain -uno 2>/dev/null)" ]]; then
  log "tracked files are dirty — refusing to branch. Commit or stash first."
  exit 0
fi
git -C "$REPO" checkout -q -b "$CYCLE_BRANCH" 2>/dev/null \
  && log "proposing on $CYCLE_BRANCH (base $ORIG_BRANCH)" \
  || { log "could not create branch; aborting"; exit 1; }

# --- 1. observe --------------------------------------------------------------
log "mining transcripts (${WINDOW_DAYS}d window)"
if ! python3 "$REPO/loop/observe.py" "$WINDOW_DAYS" > "$REPO/state/observations.json" 2>>"$LOG"; then
  log "FATAL: observer failed"; exit 1
fi

read -r ERRORS DENIALS CORRECTIONS <<<"$(python3 - "$REPO/state/observations.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
print(len(d["recurring_tool_errors"]), len(d["permission_denials"]), len(d["user_corrections"]))
PY
)"
log "evidence: $ERRORS error clusters, $DENIALS denials, $CORRECTIONS corrections"
python3 "$REPO/../fleet/bin/events.py" self-improve info "mined $ERRORS error clusters, $CORRECTIONS corrections" 2>/dev/null

# No evidence means no work. Burning a run on an empty file invites invention.
if [[ "$ERRORS" -eq 0 && "$DENIALS" -eq 0 && "$CORRECTIONS" -eq 0 ]]; then
  python3 "$REPO/../fleet/bin/events.py" self-improve ok "no friction observed; nothing to do" 2>/dev/null
  log "no friction observed; skipping cycle"
  echo "$(date -u +%FT%TZ) no-evidence skip" >> "$REPO/state/cycles.log"
  exit 0
fi

# --- 2. run the orchestrator -------------------------------------------------
# Deny-list blocks the destructive paths at the permission layer. bypassPermissions
# is required for genuinely unattended operation; the deny rules and the guard
# below are what make that acceptable.
DENY_SETTINGS="$REPO/loop/deny.json"

log "running orchestrator (timeout ${TIMEOUT_SECS}s)"
PROMPT="$(cat "$REPO/loop/prompt.md")"

# macOS ships no `timeout` binary, so an unbounded run would hang the loop
# until the next launchd fire. Use coreutils when present, else a bash watchdog.
run_bounded() {
  if command -v timeout >/dev/null 2>&1; then timeout "$TIMEOUT_SECS" "$@"; return $?; fi
  if command -v gtimeout >/dev/null 2>&1; then gtimeout "$TIMEOUT_SECS" "$@"; return $?; fi

  "$@" &
  local child=$!
  ( sleep "$TIMEOUT_SECS"
    if kill -0 "$child" 2>/dev/null; then
      echo "[watchdog] timeout after ${TIMEOUT_SECS}s; terminating $child" >> "$LOG"
      kill -TERM "$child" 2>/dev/null
      sleep 10
      kill -KILL "$child" 2>/dev/null
    fi ) &
  local watcher=$!
  wait "$child"; local rc=$?
  kill "$watcher" 2>/dev/null; wait "$watcher" 2>/dev/null
  return $rc
}

run_bounded "$CLAUDE_BIN" \
  --print \
  --permission-mode bypassPermissions \
  --settings "$DENY_SETTINGS" \
  --add-dir "$REPO" \
  --model opus \
  "$PROMPT" >> "$LOG" 2>&1
RC=$?
log "orchestrator exited rc=$RC"

# --- 3. integrity verification ----------------------------------------------
AFTER_SETTINGS="$(checksum "$SETTINGS")"
if [[ "$BEFORE_SETTINGS" != "$AFTER_SETTINGS" ]]; then
  python3 "$REPO/../fleet/bin/events.py" self-improve needs_you "settings.json was modified and restored" 2>/dev/null
  log "!! VIOLATION: settings.json was modified. Restoring from snapshot."
  [[ -f "$GUARD_DIR/settings.json.bak" ]] && cp "$GUARD_DIR/settings.json.bak" "$SETTINGS"
  echo "$(date -u +%FT%TZ) VIOLATION settings.json modified and restored" >> "$REPO/state/violations.log"
fi

# Symlinks are the agent's only channel to the live config; a replaced or
# dangling link means the loop has silently stopped taking effect.
for link in skills agents; do
  tgt="$HOME/.claude/$link"
  if [[ -e "$tgt" && ! -L "$tgt" ]]; then
    log "!! WARNING: ~/.claude/$link is no longer a symlink"
    echo "$(date -u +%FT%TZ) VIOLATION ~/.claude/$link delinked" >> "$REPO/state/violations.log"
  fi
done

# --- 4. commit anything the agent left uncommitted ---------------------------
if [[ -n "$(git status --porcelain 2>/dev/null)" ]]; then
  log "committing residual changes"
  git add -A && git commit -q -m "cycle $STAMP: residual changes

Committed by run-cycle.sh; the orchestrator left these uncommitted." \
    >> "$LOG" 2>&1
fi

# --- 5. refresh the dashboard ------------------------------------------------
# Regenerated after the commit step so the ledger it renders is already current.
if python3 "$REPO/loop/dashboard.py" > "$REPO/dashboard.html.tmp" 2>>"$LOG"; then
  mv "$REPO/dashboard.html.tmp" "$REPO/dashboard.html"
  log "dashboard refreshed"
else
  rm -f "$REPO/dashboard.html.tmp"
  log "WARNING: dashboard render failed (loop state is unaffected)"
fi

CHANGED=$(git -C "$REPO" rev-list --count "$ORIG_BRANCH".."$CYCLE_BRANCH" 2>/dev/null || echo 0)

# Hand the repo back on the branch it was found on. A cycle that changed nothing
# leaves no branch behind rather than one per night.
git -C "$REPO" checkout -q "$ORIG_BRANCH" 2>/dev/null
if [[ "$CHANGED" -eq 0 ]]; then
  git -C "$REPO" branch -D "$CYCLE_BRANCH" >/dev/null 2>&1
  log "cycle complete: no changes, branch discarded"
else
  log "cycle complete: $CHANGED commit(s) proposed on $CYCLE_BRANCH"
  python3 "$REPO/../fleet/bin/events.py" self-improve needs_you \
    "$CHANGED change(s) proposed on $CYCLE_BRANCH — review and merge" 2>/dev/null
fi
APPLIED=$(wc -l < "$REPO/state/applied.jsonl" 2>/dev/null | tr -d " ")
REFUTED=$(wc -l < "$REPO/state/rejected.jsonl" 2>/dev/null | tr -d " ")
python3 "$REPO/../fleet/bin/events.py" self-improve ok "cycle done — ${APPLIED:-0} applied, ${REFUTED:-0} refuted lifetime" 2>/dev/null
echo "$(date -u +%FT%TZ) rc=$RC commits=$CHANGED errors=$ERRORS" >> "$REPO/state/cycles.log"
