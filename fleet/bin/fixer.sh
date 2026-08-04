#!/usr/bin/env bash
# Propose a fix on a branch when a project's tests are red.
#
# The tests are the scoreboard, so the agent is not allowed to touch them.
# A fix that edits its own success criterion proves nothing, and that check is
# enforced here by diffing test paths rather than by asking the agent nicely.
#
# Usage: fixer.sh /path/to/project
#
# Never switches away from a dirty tree, never touches the default branch,
# never pushes. On failure the branch is deleted and the repo is restored.

set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-}"
[[ -z "$TARGET" || ! -d "$TARGET" ]] && { echo "usage: fixer.sh <project-dir>"; exit 2; }
TARGET="$(cd "$TARGET" && pwd)"
NAME="$(basename "$TARGET")"

CLAUDE_BIN="${CLAUDE_BIN:-$HOME/.local/bin/claude}"
FIX_TIMEOUT="${FIX_TIMEOUT:-900}"
STAMP="$(date +%Y-%m-%dT%H-%M-%S)"
LOG="$FLEET/logs/fix-$NAME-$STAMP.log"
PROPOSAL="$FLEET/proposals/$NAME-$STAMP.md"
mkdir -p "$FLEET/logs" "$FLEET/proposals"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

cd "$TARGET" || exit 1

# --- preconditions ------------------------------------------------------------
git rev-parse --git-dir >/dev/null 2>&1 || { log "not a git repo; skipping"; exit 0; }

# -uno: only *tracked* modifications matter. Untracked files (.venv, caches,
# scratch) survive a branch switch and are not at risk, but counting them as
# dirty would block the fixer on essentially every real project.
if [[ -n "$(git status --porcelain -uno)" ]]; then
  log "tracked files have uncommitted changes — refusing to touch them. Commit or stash first."
  exit 0
fi

ORIG_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
BASE_SHA="$(git rev-parse HEAD)"

# Locate the test command the same way the watchdog does.
if   [[ -x ".venv/bin/pytest" ]]; then TEST_CMD=".venv/bin/pytest -q"
elif [[ -f "pyproject.toml" ]] && command -v uv >/dev/null 2>&1; then TEST_CMD="uv run pytest -q"
elif [[ -f "package.json" ]] && grep -q '"test"' package.json 2>/dev/null; then TEST_CMD="npm test --silent"
else log "no test command; nothing to verify against"; exit 0; fi

# Only act on red. Green needs no fix, and running the agent anyway invites churn.
BEFORE_OUT="$($TEST_CMD 2>&1)"; BEFORE_RC=$?
if [[ $BEFORE_RC -eq 0 ]]; then
  log "tests already pass; nothing to fix"; exit 0
fi
log "baseline red: $(echo "$BEFORE_OUT" | grep -E '(failed|error)' | tail -1 | xargs)"

restore() {
  git checkout -q --force "$ORIG_BRANCH" 2>/dev/null
  git branch -D "$FIX_BRANCH" 2>/dev/null >/dev/null
  git reset -q --hard "$BASE_SHA" 2>/dev/null
}

# One unreviewed proposal at a time. The watchdog runs hourly; without this a
# repository left red overnight collects a near-identical branch every hour.
EXISTING="$(git branch --list 'fleet/fix-*' --format='%(refname:short)' | head -1)"
if [[ -n "$EXISTING" ]]; then
  log "a proposal is already waiting on $EXISTING — not making another"
  python3 "$FLEET/bin/events.py" "$NAME" needs_you \
    "still red; fix already waiting on $EXISTING" 2>/dev/null
  exit 0
fi

FIX_BRANCH="fleet/fix-$STAMP"
git checkout -q -b "$FIX_BRANCH" || { log "could not create branch"; exit 1; }
log "working on $FIX_BRANCH (base $ORIG_BRANCH @ ${BASE_SHA:0:8})"

# --- run the agent -------------------------------------------------------------
PROMPT="The test suite in this repository is failing. Diagnose the real cause and fix it.

Run the tests with: $TEST_CMD

Failing output:
---
$(echo "$BEFORE_OUT" | tail -60)
---

Rules, which are enforced mechanically after you finish:

1. DO NOT modify, delete, weaken, skip, or xfail any test. The tests are the
   criterion your work is judged by; editing them invalidates the result and the
   whole change will be thrown away. If you believe a test is genuinely wrong,
   stop and say so in your final message instead of changing it.
2. Fix the underlying cause, not the symptom. Do not wrap things in try/except
   to make an error disappear.
3. Change as little as possible.
4. Do not commit, do not create branches, do not push. Leave your work uncommitted
   in the working tree.
5. Stay inside this repository.

When done, state in one paragraph what was broken and what you changed."

run_bounded() {
  if command -v timeout >/dev/null 2>&1; then timeout "$FIX_TIMEOUT" "$@"; return $?; fi
  "$@" & local c=$!
  ( sleep "$FIX_TIMEOUT"; kill -0 "$c" 2>/dev/null && { kill -TERM "$c" 2>/dev/null; sleep 5; kill -KILL "$c" 2>/dev/null; } ) & local w=$!
  wait "$c"; local rc=$?; kill "$w" 2>/dev/null; wait "$w" 2>/dev/null; return $rc
}

python3 "$FLEET/bin/events.py" "$NAME" info "tests are red — attempting a fix on a branch" 2>/dev/null
log "running agent (timeout ${FIX_TIMEOUT}s)"
run_bounded "$CLAUDE_BIN" --print \
  --permission-mode bypassPermissions \
  --settings "$FLEET/bin/fixer-deny.json" \
  --model opus \
  "$PROMPT" >> "$LOG" 2>&1
log "agent exited rc=$?"

# --- integrity check: did it touch the scoreboard? ----------------------------
# Untracked files ARE included here, unlike the precondition check above: the
# commit below uses `git add -A`, so anything the agent creates gets committed.
# Checking -uno here would let a brand-new file under tests/ slip past the guard.
# cut -c4- keeps paths containing spaces intact.
CHANGED="$(git status --porcelain | cut -c4- | sed 's/^"//; s/"$//')"
if [[ -z "$CHANGED" ]]; then
  log "agent made no changes"; restore
  echo "$NAME|no-change|" >> "$FLEET/state-fixes.log" 2>/dev/null
  exit 0
fi

TOUCHED_TESTS="$(echo "$CHANGED" | grep -E '(^|/)tests?/|(^|/)test_[^/]*\.py$|_test\.py$|\.spec\.[jt]s$|\.test\.[jt]s$' || true)"
if [[ -n "$TOUCHED_TESTS" ]]; then
  python3 "$FLEET/bin/events.py" "$NAME" error "fix rejected: agent edited the tests" 2>/dev/null
  log "REJECTED: agent modified test files:"
  echo "$TOUCHED_TESTS" | sed 's/^/  /' | tee -a "$LOG"
  restore
  {
    echo "# $NAME — fix rejected"
    echo
    echo "- **When:** $STAMP"
    echo "- **Reason:** the agent modified test files, which are the criterion it is judged by."
    echo
    echo '## Files it tried to change'
    echo
    echo '```'; echo "$TOUCHED_TESTS"; echo '```'
  } > "$PROPOSAL"
  exit 0
fi

# --- verify against the untouched scoreboard ----------------------------------
AFTER_OUT="$($TEST_CMD 2>&1)"; AFTER_RC=$?
SUMMARY="$(echo "$AFTER_OUT" | grep -E '(passed|failed|error)' | tail -1 | xargs)"

if [[ $AFTER_RC -ne 0 ]]; then
  python3 "$FLEET/bin/events.py" "$NAME" warn "attempted fix did not work ($SUMMARY); discarded" 2>/dev/null
  log "fix did not work ($SUMMARY) — discarding branch"
  restore
  exit 0
fi

git add -A
# Build artifacts are noise in a diff a human has to review, and pytest/python
# regenerate them anyway. Keep them out of the proposed commit.
git reset -q -- '*.pyc' '*.pyo' '*.pyd' '__pycache__' '.pytest_cache' \
                '*/__pycache__' '*/.pytest_cache' 2>/dev/null || true
git commit -q -m "fleet: propose fix for failing tests

Baseline: $(echo "$BEFORE_OUT" | grep -E '(failed|error)' | tail -1 | xargs)
After:    $SUMMARY

Proposed by the fleet fixer. Tests were not modified. Review before merging."
FIX_SHA="$(git rev-parse --short HEAD)"

# Hand the repo back exactly as it was found; the branch stays for review.
git checkout -q "$ORIG_BRANCH"
log "PROPOSED: $FIX_BRANCH @ $FIX_SHA — $SUMMARY"
python3 "$FLEET/bin/events.py" "$NAME" needs_you "fix ready to review on $FIX_BRANCH ($SUMMARY)" 2>/dev/null

{
  echo "# $NAME — fix proposed"
  echo
  echo "- **Branch:** \`$FIX_BRANCH\` (commit \`$FIX_SHA\`)"
  echo "- **Base:** \`$ORIG_BRANCH\` @ \`${BASE_SHA:0:8}\`"
  echo "- **Before:** $(echo "$BEFORE_OUT" | grep -E '(failed|error)' | tail -1 | xargs)"
  echo "- **After:** $SUMMARY"
  echo "- **Tests modified:** no (enforced)"
  echo
  echo '## Diff'
  echo
  echo '```diff'
  git diff "$BASE_SHA".."$FIX_SHA" | head -200
  echo '```'
  echo
  echo '## Review'
  echo
  echo '```bash'
  echo "cd $TARGET"
  echo "git diff $ORIG_BRANCH..$FIX_BRANCH     # inspect"
  echo "git merge $FIX_BRANCH                  # accept"
  echo "git branch -D $FIX_BRANCH              # reject"
  echo '```'
} > "$PROPOSAL"

echo "$PROPOSAL"
