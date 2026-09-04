#!/usr/bin/env bash
# One 15-minute builder slot: triage, fill the pick queue, build one item.
# FLEET_BUILDER comes from systemd (fleet-build@grok / @agy) so two
# agents overlap. Default hard stop is 1 hour in Python; systemd
# ceiling is 4 hours for extra long = true. EXIT reverts
# unfinished worktrees so the next name gets a clean slot.
set -uo pipefail
export PATH="$HOME/.local/bin:$HOME/.local/share/mise/installs/node/lts/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH-}"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY=$REPO/.venv/bin/python
trap "$PY fleet/bin/pipeline.py discard-unfinished || true" EXIT
cd "$REPO"
# Run the code that is on main, not the code that was on main whenever
# someone last pulled by hand. pipeline.py already builds off origin/main via
# remote_main(), but next_builder.py, autotriage.py and this script are read
# from the checkout -- so on 2026-09-04 the NUC was choosing builders with a
# copy of next_builder.py that predated claude being added to the pool.
# --ff-only so a checkout with local work is left alone rather than merged.
if [[ -z "$(git status --porcelain)" ]]; then
  git fetch -q origin main 2>/dev/null && git merge -q --ff-only origin/main 2>/dev/null || true
fi
if [[ -z "${FLEET_BUILDER:-}" ]]; then
  FLEET_BUILDER=$($PY fleet/bin/next_builder.py)
fi
export FLEET_BUILDER
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) builder=$FLEET_BUILDER"
$PY fleet/bin/autotriage.py --batches 1 || true
$PY fleet/bin/autotriage.py --autopick 2 || true
$PY fleet/bin/pipeline.py run || true
