#!/usr/bin/env python3
"""One small, deterministic context packet for a newly arrived agent."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import agentcontract

REPO = Path(__file__).resolve().parents[2]
REPORTS = REPO / "docs" / "development-log-progress-report"
QUOTAS = REPO / "fleet" / "workers" / "quotas.json"


def git(*args):
    result = subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                            text=True, timeout=10)
    return result.stdout.strip()


def latest_handoff():
    files = sorted(REPORTS.glob("handoff-*.md"), reverse=True)
    return files[0] if files else None


def handoff_context(path: Path) -> str:
    """Return operational state without an older handoff's copied rules."""
    text = path.read_text().strip()
    marker = "## Read first"
    if marker not in text:
        return text
    before, rest = text.split(marker, 1)
    next_section = rest.find("\n## ")
    if next_section < 0:
        return before.rstrip()
    return (before.rstrip() + "\n\n" + rest[next_section + 1:].lstrip()).strip()


def quota_line():
    try:
        card = json.loads(QUOTAS.read_text())
        return card.get("summary") or "unknown"
    except (OSError, ValueError):
        return "no pulse yet"


def render():
    handoff = latest_handoff()
    status = git("status", "--short")
    changed = len(status.splitlines()) if status else 0
    lines = [
        "# Command Control — agent brief",
        "",
        f"HEAD: {git('log', '-1', '--format=%h %s') or 'unknown'}",
        f"Working tree: {changed} changed paths; preserve concurrent work.",
        f"Quota routing: {quota_line()}",
        "",
        "## Operating contract",
        agentcontract.as_markdown(),
        "",
        # Named here because brief.py is the one thing every arriving agent
        # runs, and "where does work run" is the question they keep answering
        # wrong. On 2026-09-17 a session spent an afternoon trying to load
        # eight launch agents that were disabled on purpose, because the
        # answer lived only in a commit message from three weeks earlier.
        "## Where work runs",
        "Two machines, six roles: `docs/FLEET.md` is the single source of "
        "truth and overrules any plist, timer or README that disagrees. "
        "Scheduled jobs run on the NUC. Gaia serves the board. The eight "
        "`re.genesis.*` launch agents on Gaia are disabled deliberately -- "
        "do not load them.",
        "",
    ]
    if handoff:
        lines.extend([f"Source: {handoff.relative_to(REPO)}", "",
                      handoff_context(handoff)])
    else:
        lines.append("No handoff found. Read README.md.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(render(), end="")
