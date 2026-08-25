#!/usr/bin/env bash
# Let the rota agent build what it proposed — on its own branch, never on main.
#
# Marsita, 2026-08-02: "I want this system to be autonomous for anything that is
# not invasive... Each agent can work on their own branch and improve."
#
# This is fixer.sh's pattern pointed at improvement instead of repair, and it
# reuses its guards deliberately rather than inventing softer ones. The whole
# safety argument is that autonomy is bounded by *mechanism*, not by asking the
# agent nicely:
#
#   - The harness creates and switches the branch. The agent cannot: git branch,
#     checkout, commit, push, reset and rebase are all denied in fixer-deny.json,
#     along with sudo, ssh, curl, wget, launchctl, ~/.ssh, .env and
#     ~/.claude/settings.json.
#   - Tests are the scoreboard, so the agent may not edit them. Enforced by
#     diffing paths afterwards, not by instruction — an agent that "fixed" a
#     suite by deleting failing tests is exactly how this check was earned.
#   - The suite must be green afterwards. Red means the branch is deleted.
#   - Nothing reaches main from HERE. Ever. A rota turn proposes on a branch
#     and stops; landing is pipeline.land()'s job, behind its own checks
#     (approved, merges clean, suite green on the merge commit). This line
#     used to read "a human merges or nothing merges", which stopped being
#     true on 2026-08-07 when Marsita handed merging to the fleet — and the
#     stale sentence then got copied onto the public front page as a feature.
#
# "Non-invasive" is defined by what is left after all of that: a commit on a
# throwaway branch, in one repo, that passes the tests it did not write.
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$FLEET/.." && pwd)"
LEDGER="$FLEET/rota/proposals.jsonl"
NAME="rota"
STAMP="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
LOG="$FLEET/logs/rota-act-$STAMP.log"
TIMEOUT="${ROTA_ACT_TIMEOUT:-900}"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

mkdir -p "$FLEET/logs"
log() { printf '%s\n' "$*" | tee -a "$LOG"; }

cd "$REPO" || exit 1

# --- refuse to start on anything but a clean tree -----------------------------
# Switching branches under uncommitted work risks someone else's changes, and
# this runs unattended. A dirty tree is a human mid-thought.
if [[ -n "$(git status --porcelain -uno)" ]]; then
  log "working tree is dirty; not touching it"
  exit 0
fi
DEFAULT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# --- do not pile up branches --------------------------------------------------
EXISTING="$(git branch --list 'rota/*' --format='%(refname:short)' | head -1)"
if [[ -n "$EXISTING" ]]; then
  log "a rota branch is already awaiting review ($EXISTING); not making another"
  exit 0
fi

# --- the machine has to be able to afford it ----------------------------------
LOAD="$(python3 -c 'import os; print(f"{os.getloadavg()[0]:.1f}")')"
MAXL="${MAX_LOAD:-6}"
if (( $(echo "$LOAD > $MAXL" | bc -l) )); then
  log "load $LOAD over $MAXL; deferring"
  exit 0
fi

# --- what did the agent propose? ----------------------------------------------
[[ -f "$LEDGER" ]] || { log "no proposals yet"; exit 0; }
PROPOSAL="$(python3 - "$LEDGER" <<'PY'
import json, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip()]
rows = [r for r in rows if r.get("outcome") == "proposed" and not r.get("acted")]
print(json.dumps(rows[-1]) if rows else "")
PY
)"
[[ -n "$PROPOSAL" ]] || { log "no unacted proposal"; exit 0; }

AGENT="$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['agent'])" "$PROPOSAL")"
TEXT="$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['text'])" "$PROPOSAL")"
BRANCH="rota/${AGENT}-${STAMP}"

# --- baseline: only build on a green tree -------------------------------------
if   [[ -x ".venv/bin/pytest" ]]; then TEST_CMD=".venv/bin/pytest -q"
elif [[ -f "pyproject.toml" ]] && command -v uv >/dev/null 2>&1; then TEST_CMD="uv run pytest -q"
else log "no test command; nothing to verify against"; exit 0; fi

BEFORE="$($TEST_CMD 2>&1)"; BEFORE_RC=$?
if [[ $BEFORE_RC -ne 0 ]]; then
  log "tests are already red; that is the fixer's job, not this one"
  exit 0
fi

restore() {
  git checkout -q -- . 2>/dev/null
  git clean -qfd 2>/dev/null
  git checkout -q "$DEFAULT_BRANCH" 2>/dev/null
  git branch -D "$BRANCH" 2>/dev/null >/dev/null
}

git checkout -q -b "$BRANCH" || { log "could not create branch"; exit 1; }
python3 "$FLEET/bin/events.py" "$NAME" info \
  "$AGENT is building its own proposal on $BRANCH" 2>/dev/null

PROMPT="You proposed this improvement to the fleet you run inside. Now build it.

YOUR PROPOSAL:
$TEXT

Implement the smallest, most concrete part of it. Rules, all mechanically checked
afterwards — breaking any of them throws the whole attempt away:

1. DO NOT modify, delete, weaken, skip or xfail any test. The tests are the
   criterion you are judged by. If a test is genuinely wrong, say so in your
   final message instead of touching it.
2. Add tests for what you change. A change with no test is a change nobody can
   keep.
3. Stay inside this repository. Nothing in \$HOME, nothing in LaunchAgents,
   nothing outside the tree.
4. Do not commit, branch, push or run git. The harness handles that.
5. Run the tests with: $TEST_CMD — they must be green when you finish.
6. If your proposal turns out to be wrong once you read the code, change nothing
   and say why. An honest no-change is worth more than a change that has to be
   reverted.

Leave your work uncommitted in the working tree."

log "running $AGENT (timeout ${TIMEOUT}s) on $BRANCH"
"$CLAUDE_BIN" --print \
  --permission-mode bypassPermissions \
  --settings "$FLEET/bin/fixer-deny.json" \
  --model opus \
  "$PROMPT" >> "$LOG" 2>&1
log "agent exited rc=$?"

# --- did it change anything? --------------------------------------------------
CHANGED="$(git status --porcelain | cut -c4- | sed 's/^"//; s/"$//')"
if [[ -z "$CHANGED" ]]; then
  log "no change — recorded as an honest no"
  python3 "$FLEET/bin/events.py" "$NAME" ok "$AGENT: no change on inspection" 2>/dev/null
  restore
  exit 0
fi

# --- the scoreboard guard -----------------------------------------------------
TOUCHED_TESTS="$(echo "$CHANGED" | grep -E '(^|/)tests?/|(^|/)test_[^/]*\.py$|_test\.py$' || true)"
MODIFIED_TESTS=""
for f in $TOUCHED_TESTS; do
  # New test files are the point of rule 2. Editing an existing one is not.
  if git cat-file -e "$DEFAULT_BRANCH:$f" 2>/dev/null; then
    MODIFIED_TESTS="$MODIFIED_TESTS$f"$'\n'
  fi
done
if [[ -n "${MODIFIED_TESTS// /}" ]]; then
  python3 "$FLEET/bin/events.py" "$NAME" error \
    "$AGENT's branch rejected: it edited existing tests" 2>/dev/null
  log "REJECTED — modified existing tests:"; echo "$MODIFIED_TESTS" | sed 's/^/  /' | tee -a "$LOG"
  restore
  exit 0
fi

# --- must be green ------------------------------------------------------------
AFTER="$($TEST_CMD 2>&1)"; AFTER_RC=$?
SUMMARY="$(echo "$AFTER" | grep -E '(passed|failed|error)' | tail -1 | xargs)"
if [[ $AFTER_RC -ne 0 ]]; then
  python3 "$FLEET/bin/events.py" "$NAME" warn \
    "$AGENT's branch discarded — tests red ($SUMMARY)" 2>/dev/null
  log "tests red ($SUMMARY) — discarding"
  restore
  exit 0
fi

git add -A
git reset -q -- '*.pyc' '__pycache__' '.pytest_cache' '*/__pycache__' 2>/dev/null || true
git commit -q -m "rota: $AGENT builds its own proposal

$SUMMARY — tests were not modified.

Proposed and implemented by $AGENT during its rota turn. Nothing was merged;
this branch exists for a human to read. See fleet/rota/proposals.jsonl."
SHA="$(git rev-parse --short HEAD)"

git checkout -q "$DEFAULT_BRANCH"
python3 "$FLEET/bin/events.py" "$NAME" needs_you \
  "$AGENT built its proposal on $BRANCH ($SHA, $SUMMARY) — review it" 2>/dev/null
log "branch $BRANCH ready for review at $SHA"

# Mark it acted so the next firing takes the next proposal rather than this one.
python3 - "$LEDGER" "$SHA" "$BRANCH" <<'PY'
import json, sys
path, sha, branch = sys.argv[1], sys.argv[2], sys.argv[3]
rows = [json.loads(l) for l in open(path) if l.strip()]
for r in reversed(rows):
    if r.get("outcome") == "proposed" and not r.get("acted"):
        r["acted"] = {"sha": sha, "branch": branch}
        break
with open(path, "w") as fh:
    for r in rows:
        fh.write(json.dumps(r) + "\n")
PY
