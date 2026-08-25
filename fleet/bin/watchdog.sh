#!/usr/bin/env bash
# Project watchdog: run a project's own checks, record the result, and write a
# digest when something breaks.
#
# Usage: watchdog.sh /path/to/project
#
# Deliberately does not modify the project. It observes and reports; proposing
# fixes is a separate, later step that should not share a process with the
# thing establishing ground truth.

set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-}"
[[ -z "$TARGET" || ! -d "$TARGET" ]] && { echo "usage: watchdog.sh <project-dir>"; exit 2; }

TARGET="$(cd "$TARGET" && pwd)"
NAME="$(basename "$TARGET")"
# Stamped when the run FINISHES, like every other worker. It used to be taken
# at start, so comparing freshness across workers compared a start time to a
# finish time — which made the staleness check invalid.
START_STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
FILE_STAMP="$(date +%Y-%m-%dT%H-%M-%S)"
OUT="$FLEET/workers/$NAME.json"
LOG="$FLEET/logs/$NAME-$FILE_STAMP.log"
mkdir -p "$FLEET/workers" "$FLEET/digests" "$FLEET/logs"

# --- pick the project's own test command ------------------------------------
# Prefer the venv the project already uses; fall back to its declared tooling.
cd "$TARGET" || exit 1
# Same lesson as pipeline.venv_pytest(), which #32 fixed: `.venv` was
# hardcoded, true on the Mac and false on the NUC, whose `.venv` is python
# 3.14 with no pytest and whose working environment is `.venv311`. The
# pipeline learned this; the watchdog did not, so on 2026-08-07 the NUC ran
# watchdogs hourly against a repo with 337 passing tests and reported
# "no test command detected" every time. A green board and no evidence.
CMD=""
VENV_PYTEST=""
for _v in .venv .venv311 .venv312 .venv313; do
  if [[ -x "$_v/bin/pytest" ]]; then VENV_PYTEST="$_v/bin/pytest"; break; fi
done
if   [[ -n "$VENV_PYTEST" ]];                     then CMD="$VENV_PYTEST -q"
elif [[ -f "pyproject.toml" ]] && command -v uv >/dev/null 2>&1; then CMD="uv run pytest -q"
elif [[ -f "package.json" ]] && grep -q '"test"' package.json 2>/dev/null; then CMD="npm test --silent"
elif [[ -f "Makefile" ]] && grep -q '^test:' Makefile 2>/dev/null; then CMD="make test"
fi

write_status() {  # status summary detail digest_path tests_passed tests_failed
  STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 - "$OUT" "$NAME" "$TARGET" "$STAMP" "$1" "$2" "$3" "$4" "$5" "$6" "$DURATION" "$HEAD" <<'PY'
import json, sys
(out, name, target, stamp, status, summary, detail,
 digest, passed, failed, duration, head) = sys.argv[1:13]
json.dump({
    "worker": name, "kind": "watchdog", "target": target,
    "last_run": stamp, "status": status, "summary": summary,
    "detail": detail[:1500], "digest": digest or None,
    "tests_passed": int(passed or 0), "tests_failed": int(failed or 0),
    "duration_s": round(float(duration or 0), 2),
    "head": head or None,
}, open(out, "w"), indent=2)
PY
}

if [[ -z "$CMD" ]]; then
  DURATION=0
  HEAD=""
  write_status "skip" "No test command detected" \
    "Looked for .venv*/bin/pytest, uv+pyproject, npm test, make test." "" 0 0
  echo "[$NAME] no test command detected"
  python3 "$FLEET/bin/events.py" "$NAME" warn "no test command detected" 2>/dev/null
  exit 0
fi

# --- skip an identical tree --------------------------------------------------
# 310 seconds of four pegged cores, hourly, over a tree that has not changed a
# byte. On an 8GB laptop that swaps, that is an afternoon spent re-proving
# yesterday.
#
# The only safe version of this skip says what it is: "unchanged since <sha>",
# carrying forward the real result from when the code last moved. A skip that
# reported a fresh "pass" would be a green board with no evidence behind it,
# which is the exact failure this repo already ate when the NUC reported "no
# test command detected" for a week and nobody noticed.
#
# Re-run anyway when: the tree is dirty (uncommitted work is what most needs
# testing), there is no previous result, or the previous result was a FAILURE
# — a fail keeps shouting until the code changes. WATCHDOG_FORCE=1 overrides.
HEAD="$(git -C "$TARGET" rev-parse HEAD 2>/dev/null || true)"
DIRTY="$(git -C "$TARGET" status --porcelain 2>/dev/null | head -1)"
if [[ -n "$HEAD" && -z "$DIRTY" && -f "$OUT" && "${WATCHDOG_FORCE:-}" != "1" ]]; then
  PREV="$(python3 "$FLEET/bin/watchdog-prev.py" "$OUT")"
  if [[ -n "$PREV" ]]; then
    PREV_HEAD="$(echo "$PREV" | cut -f1)"
    PREV_SUMMARY="$(echo "$PREV" | cut -f2)"
    PREV_WHEN="$(echo "$PREV" | cut -f3)"
    if [[ "$PREV_HEAD" == "$HEAD" ]]; then
      DURATION=0
      write_status "pass" "$PREV_SUMMARY - unchanged since ${HEAD:0:7}" \
        "Tests not re-run: HEAD ${HEAD:0:7} is identical to the last green run at $PREV_WHEN and the tree is clean. Force with WATCHDOG_FORCE=1." \
        "" 0 0
      echo "[$NAME] skipped - unchanged since ${HEAD:0:7}"
      python3 "$FLEET/bin/events.py" "$NAME" info \
        "tests skipped - unchanged since ${HEAD:0:7} ($PREV_SUMMARY)" 2>/dev/null
      exit 0
    fi
  fi
fi

# --- run it ------------------------------------------------------------------
echo "[$NAME] running: $CMD" | tee -a "$LOG"
python3 "$FLEET/bin/events.py" "$NAME" info "running tests: $CMD" 2>/dev/null
START=$(python3 -c 'import time;print(time.time())')
# shellcheck disable=SC2086
OUTPUT="$($CMD 2>&1)"; RC=$?
END=$(python3 -c 'import time;print(time.time())')
DURATION=$(python3 -c "print($END-$START)")
echo "$OUTPUT" >> "$LOG"

# pytest prints e.g. "5 passed, 1 warning in 1.13s" / "2 failed, 3 passed in ..."
PASSED=$(echo "$OUTPUT" | grep -oE '[0-9]+ passed' | tail -1 | grep -oE '[0-9]+' || true)
FAILED=$(echo "$OUTPUT" | grep -oE '[0-9]+ (failed|error)' | tail -1 | grep -oE '[0-9]+' || true)
SUMMARY="$(echo "$OUTPUT" | grep -E '(passed|failed|error)' | tail -1 | sed 's/=*//g' | xargs || true)"
# "1 warning" with no identity makes a known-harmless warning indistinguishable
# from a new one. Name it.
WARN="$(echo "$OUTPUT" | grep -oE '[A-Za-z]*(Warning|Error):' | sort -u | head -2 | tr '\n' ',' | sed 's/,$//')"
[[ -n "$WARN" ]] && SUMMARY="$SUMMARY ($WARN)"
[[ -z "$SUMMARY" ]] && SUMMARY="exit code $RC"

DIGEST=""
if [[ $RC -ne 0 ]]; then
  # Only write a digest on failure — a green run needs no prose.
  DIGEST="digests/$NAME-$FILE_STAMP.md"
  {
    echo "# $NAME — checks failed"
    echo
    echo "- **When:** $STAMP"
    echo "- **Command:** \`$CMD\`"
    echo "- **Exit code:** $RC"
    echo "- **Result:** $SUMMARY"
    echo "- **Commit:** $(git -C "$TARGET" rev-parse --short HEAD 2>/dev/null || echo 'n/a')"
    echo
    echo '## Output'
    echo
    echo '```'
    echo "$OUTPUT" | tail -80
    echo '```'
  } > "$FLEET/$DIGEST"
  STATUS="fail"
  echo "[$NAME] FAIL — digest: $DIGEST"
  python3 "$FLEET/bin/events.py" "$NAME" needs_you "tests failed — $SUMMARY" 2>/dev/null
else
  STATUS="pass"
  echo "[$NAME] pass — $SUMMARY"
  python3 "$FLEET/bin/events.py" "$NAME" ok "$SUMMARY" 2>/dev/null
fi

write_status "$STATUS" "$SUMMARY" "$OUTPUT" "$DIGEST" "${PASSED:-0}" "${FAILED:-0}"

# Keep only the 20 most recent logs per project.
ls -1t "$FLEET/logs/$NAME-"*.log 2>/dev/null | tail -n +21 | while read -r f; do rm -f "$f"; done
exit 0
