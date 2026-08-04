#!/usr/bin/env bash
# Have a different vendor read the branch an agent built.
#
# The rota's shape is now: one agent proposes, the same agent builds it on a
# branch, and a DIFFERENT agent — from a different company where one is
# available — reads the diff and says what is wrong with it.
#
# The vendor split is the whole point. An agent reviewing its own work is the
# same machinery that produced the error, which is why the brain-farts log is
# fourteen entries all caught by a human. claude is Anthropic, hermes and
# openclaw are OpenAI: different training, different failure profiles. When two
# of them agree the claim is much stronger than one model saying it twice, and
# when they disagree that disagreement is the most useful thing on the board.
#
# This step is deliberately the safe one. The reviewer READS a diff and WRITES
# an opinion — no edits, no commits, no branch operations, nothing outside the
# repo. That is why it can run unattended while the building half still waits
# for a human to enable it.
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$FLEET/.." && pwd)"
REVIEWS="$FLEET/rota/reviews.jsonl"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
LOG="$FLEET/logs/rota-review-$(date -u +%Y%m%dT%H%M%SZ).log"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"

mkdir -p "$FLEET/logs" "$FLEET/rota"
log() { printf '%s\n' "$*" | tee -a "$LOG"; }
cd "$REPO" || exit 1

# --- is there a branch to read? -----------------------------------------------
BRANCH="$(git branch --list 'rota/*' --format='%(refname:short)' | head -1)"
if [[ -z "$BRANCH" ]]; then
  log "no rota branch to review"; exit 0
fi

# rota/<agent>-<stamp> — the author is encoded in the branch name because the
# commit author is the harness, not the agent.
AUTHOR="$(printf '%s' "$BRANCH" | sed 's|^rota/||; s|-[0-9].*$||')"

# Already reviewed? A second opinion from the same reviewer is not a second
# opinion, and re-running costs an agent turn for nothing.
if [[ -f "$REVIEWS" ]] && grep -q "\"branch\": \"$BRANCH\"" "$REVIEWS" 2>/dev/null; then
  log "$BRANCH already has a review"; exit 0
fi

# --- pick someone independent -------------------------------------------------
POOL="${ROTA_AGENTS:-claude,hermes,openclaw}"
read -r REVIEWER INDEPENDENT <<<"$(python3 - "$AUTHOR" "$POOL" <<'PY'
import sys
sys.path.insert(0, __import__("os").path.dirname(__file__) or ".")
sys.path.insert(0, "fleet/bin")
import vendors
author, pool = sys.argv[1], [a.strip() for a in sys.argv[2].split(",") if a.strip()]
picks = vendors.independent_of(author, pool)
if not picks:
    print("none no")
else:
    best = picks[0]
    print(best, "yes" if vendors.vendor(best) != vendors.vendor(author) else "no")
PY
)"
if [[ "$REVIEWER" == "none" ]]; then
  log "no reviewer available"; exit 0
fi
[[ "$INDEPENDENT" == "yes" ]] && NOTE="different vendor" || NOTE="SAME vendor — weaker review"
log "$BRANCH by $AUTHOR → reviewer $REVIEWER ($NOTE)"

# --- the machine has to be able to afford it ----------------------------------
LOAD="$(python3 -c 'import os; print(f"{os.getloadavg()[0]:.1f}")')"
MAXL="${MAX_LOAD:-6}"
if (( $(echo "$LOAD > $MAXL" | bc -l) )); then
  log "load $LOAD over $MAXL; deferring"; exit 0
fi

DEFAULT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
DIFF="$(git diff "$DEFAULT_BRANCH...$BRANCH" | head -c 12000)"
MSG="$(git log -1 --format=%B "$BRANCH")"
if [[ -z "$DIFF" ]]; then
  log "branch has no diff against $DEFAULT_BRANCH"; exit 0
fi

PROMPT="Another agent built this on a branch. You are reviewing it. You did not
write it and you are from a different vendor, which is the point: an agent
checking its own work is the same machinery that produced the error.

BRANCH: $BRANCH
BUILT BY: $AUTHOR

COMMIT MESSAGE:
$MSG

DIFF:
$DIFF

Answer four things, briefly, grounded in the diff itself:

1. Does it do what the commit message claims? Quote the line that shows it, or
   say where the claim and the code part company.
2. What is wrong with it? Be specific — a file and a line beats an adjective.
   If nothing is wrong, say so plainly rather than inventing a concern.
3. What would break that its tests do not cover?
4. MERGE or HOLD, and one sentence why.

You are advising a human who will decide. You cannot merge, edit or commit
anything, and should not try."

log "asking $REVIEWER"
OUT="$("$CLAUDE_BIN" --print \
        --permission-mode bypassPermissions \
        --settings "$FLEET/bin/fixer-deny.json" \
        --model opus \
        "$PROMPT" 2>>"$LOG")"
RC=$?
log "reviewer exited rc=$RC"

# A harness failure is not a review — the same distinction the relay and the
# council both had to learn after timeouts were recorded as things agents said.
case "$(printf '%s' "$OUT" | head -c 20)" in
  "[timed out"*|"[error"*|"")
    python3 "$FLEET/bin/events.py" rota warn \
      "review of $BRANCH failed — $REVIEWER did not answer" 2>/dev/null
    log "no usable review"; exit 0 ;;
esac

VERDICT=HOLD
printf '%s' "$OUT" | grep -qiE '(^|[^A-Za-z])MERGE([^A-Za-z]|$)' && VERDICT=MERGE
# HOLD wins a tie: a review that says both is not a review that says merge.
printf '%s' "$OUT" | grep -qiE '(^|[^A-Za-z])HOLD([^A-Za-z]|$)' && VERDICT=HOLD

python3 - "$REVIEWS" "$BRANCH" "$AUTHOR" "$REVIEWER" "$INDEPENDENT" "$VERDICT" "$STAMP" "$OUT" <<'PY'
import json, sys
path, branch, author, reviewer, indep, verdict, ts, text = sys.argv[1:9]
with open(path, "a") as fh:
    fh.write(json.dumps({
        "ts": ts, "branch": branch, "built_by": author, "reviewed_by": reviewer,
        "cross_vendor": indep == "yes", "verdict": verdict,
        "text": " ".join(text.split()),
    }) + "\n")
PY

python3 "$FLEET/bin/events.py" rota needs_you \
  "$REVIEWER reviewed $AUTHOR's $BRANCH → $VERDICT ($NOTE)" 2>/dev/null
log "verdict: $VERDICT — recorded in rota/reviews.jsonl"
