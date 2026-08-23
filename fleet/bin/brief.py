#!/usr/bin/env python3
"""One small, deterministic context packet for a newly arrived agent."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

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
    ]
    if handoff:
        lines.extend([f"Source: {handoff.relative_to(REPO)}", "",
                      handoff.read_text().strip()])
    else:
        lines.append("No handoff found. Read README.md.")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print(render(), end="")
