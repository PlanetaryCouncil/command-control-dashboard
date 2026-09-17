"""The single source of truth has to stay true, or it is worse than nothing.

`docs/FLEET.md` says which of six roles runs where. This conversation has now
been had more than once -- most recently by a session that spent an afternoon
trying to load eight launch agents that were switched off on purpose -- so the
doc exists to end it. A doc that quietly goes stale would end it wrongly.

These tests pin the doc against the repo, not against prose. If a cadence is
added to config.json, or a role is renamed, one of these fails and the doc gets
updated in the same change.
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DOC = (REPO / "docs" / "FLEET.md").read_text()
CONFIG = json.loads((REPO / "fleet" / "config.json").read_text())

ROLES = ("ROTA", "BUILD", "HEALTH", "COUNCIL", "REPORT", "E2E")


def test_every_role_is_named():
    for r in ROLES:
        assert r in DOC, f"{r} is not in docs/FLEET.md"


def test_every_cadence_in_config_is_accounted_for():
    """A schedule nobody can point at a runner for is the exact confusion the
    doc exists to kill: thirteen cadences read as thirteen processes."""
    missing = [k for k in CONFIG
               if k != "_comment" and isinstance(CONFIG[k], dict)
               and k.replace("_", "-") not in DOC and k not in DOC]
    assert not missing, (
        f"cadences in config.json that docs/FLEET.md never mentions: {missing}")


def test_the_doc_says_not_to_load_gaias_launch_agents():
    """The instruction that would have saved the afternoon."""
    low = DOC.lower()
    assert "do not load them" in low
    assert "disable" in low


def test_the_doc_claims_to_be_the_source_of_truth():
    """Without that claim a reader has no way to break a tie with a plist."""
    assert "single source of truth" in DOC.lower()


def test_the_absorptions_are_recorded():
    """Which old job lives inside which runner -- the thing you need to know
    before reporting a job as missing."""
    for old, runner in (("watchdogs", "health"), ("pipeline", "build"),
                        ("self_improve", "council"), ("local_voice", "report")):
        assert old in DOC, f"{old} is not mentioned"
        assert runner in DOC.lower(), f"{runner} is not mentioned"


def test_agents_md_points_at_it():
    """Agents read AGENTS.md; a truth nobody is sent to is not a truth."""
    assert "docs/FLEET.md" in (REPO / "AGENTS.md").read_text()


def test_the_brief_every_agent_runs_points_at_it():
    assert "docs/FLEET.md" in (REPO / "fleet" / "bin" / "brief.py").read_text()


def test_the_readme_no_longer_claims_there_is_no_always_on_host():
    """It said "No always-on host" while the NUC had been running the fleet
    for weeks. A stale limitation reads as a current one."""
    assert "No always-on host" not in (REPO / "README.md").read_text()
