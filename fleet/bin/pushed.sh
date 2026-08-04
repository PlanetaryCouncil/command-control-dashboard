#!/usr/bin/env bash
# Print the push receipt: commit link, subject, live URL.
#
# Run it after every push so the report is generated from the repo rather than
# written from memory. That is the whole point — a hand-typed hash or a
# remembered URL is a claim, and this file exists because a claim was not enough.
#
# Usage:  bash ~/.claude/pushed.sh [repo-path]
set -euo pipefail

cd "${1:-.}"

remote=$(git remote | head -1)
url=$(git remote get-url "$remote")
slug=$(printf '%s' "$url" | sed -E 's|^git@github\.com:||; s|^https://github\.com/||; s|\.git$||')
branch=$(git rev-parse --abbrev-ref HEAD)
sha=$(git rev-parse HEAD)
short=${sha:0:7}
subject=$(git log -1 --format=%s)

# Verify rather than assume: fetch, then compare. Push output from earlier in the
# turn says a transfer was attempted, not that the remote is now this commit.
git fetch -q "$remote" 2>/dev/null || true
remote_sha=$(git rev-parse "$remote/$branch" 2>/dev/null || echo "none")

if [ "$remote_sha" = "$sha" ]; then
  state="✅ PUSHED"
elif [ "$remote_sha" = "none" ]; then
  state="⚠️  NO REMOTE BRANCH — committed locally only"
else
  ahead=$(git rev-list --count "$remote/$branch..HEAD" 2>/dev/null || echo "?")
  state="⚠️  NOT PUSHED — $ahead commit(s) ahead of $remote/$branch"
fi

# Live URL comes only from a CNAME that is actually committed. An earlier version
# fell back to guessing a github.io address whenever the repo contained any HTML,
# which invented a live link for a repo that is not a website at all. A wrong URL
# in a receipt is worse than no URL: the receipt exists to be trusted.
live=""
[ -f CNAME ] && live="https://$(tr -d '[:space:]' < CNAME)/"

echo "$state"
echo "  repo    $slug ($branch)"
echo "  commit  https://github.com/$slug/commit/$sha"
echo "  message $subject"
if [ -n "$live" ]; then echo "  live    $live"; fi
# Explicit `if`, not `[ -n "$live" ] && echo`. As the last line of the script that
# short-circuit makes the exit status 1 whenever there is no live URL, so a
# perfectly successful receipt reports failure to whatever ran it.
