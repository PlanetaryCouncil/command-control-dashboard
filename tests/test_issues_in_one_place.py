"""Eighteen open issues across eight repos, on one screen, filed in one line.

Marsita, 2026-09-04: "I need to get disciplined to be creating issues and then
sorting them out." Discipline is the wrong lever. These tests hold the two
things that replace it: one call that fetches everything, and a filing path
short enough that it is never the reason an issue does not exist.
"""
import json
import pathlib
import sys
from datetime import datetime, timedelta, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import issues            # noqa: E402


# ---------------------------------------------------------------- one call
def test_every_owner_is_asked_in_a_single_search(monkeypatch):
    """Eight repos used to mean eight round trips. One search covers them."""
    seen = []
    monkeypatch.setattr(issues, "_gh",
                        lambda *a, **k: (seen.append(a), "[]")[1])
    issues.fetch()
    assert seen[0][0] == "search"
    for owner in issues.OWNERS:
        assert owner in seen[0]


def test_a_broken_gh_is_an_empty_list_not_an_exception(monkeypatch):
    monkeypatch.setattr(issues, "_gh", lambda *a, **k: "not json at all")
    assert issues.fetch() == []


def test_newest_first(monkeypatch):
    rows = [{"repository": {"name": "a"}, "number": 1, "title": "old",
             "createdAt": "2026-01-01T00:00:00Z", "url": "", "labels": []},
            {"repository": {"name": "b"}, "number": 2, "title": "new",
             "createdAt": "2026-09-01T00:00:00Z", "url": "", "labels": []}]
    monkeypatch.setattr(issues, "_gh", lambda *a, **k: json.dumps(rows))
    assert [r["title"] for r in issues.fetch()] == ["new", "old"]


# ----------------------------------------------------------------- the age
def test_age_is_days_because_a_date_needs_arithmetic():
    then = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    assert issues.age_days(then.replace("+00:00", "Z")) == 31


def test_a_junk_date_does_not_take_the_pane_down():
    assert issues.age_days("whenever") is None


# --------------------------------------------------------------- the cache
def test_a_fresh_cache_is_not_refetched(monkeypatch, tmp_path):
    c = tmp_path / "issues.json"
    c.write_text(json.dumps({"at": 1000.0, "issues": [], "count": 0}))
    monkeypatch.setattr(issues, "fetch",
                        lambda: (_ for _ in ()).throw(AssertionError("refetched")))
    assert issues.snapshot(cache=c, now=1010.0)["at"] == 1000.0


def test_a_failed_fetch_serves_the_old_list_and_says_so(monkeypatch, tmp_path):
    """An empty pane reads as "you have no work". Yesterday's list is truer."""
    c = tmp_path / "issues.json"
    c.write_text(json.dumps({"at": 1.0, "issues": [{"title": "x"}], "count": 1}))
    monkeypatch.setattr(issues, "fetch", lambda: [])
    got = issues.snapshot(cache=c, now=99999.0)
    assert got["count"] == 1 and got["stale"] is True


def test_a_real_fetch_replaces_the_cache_and_carries_ages(monkeypatch, tmp_path):
    c = tmp_path / "issues.json"
    monkeypatch.setattr(issues, "fetch", lambda: [
        {"repo": "ux", "number": 3, "title": "t", "url": "u",
         "created": "2026-08-01T00:00:00Z", "labels": []}])
    got = issues.snapshot(cache=c, now=5.0)
    assert got["repos"] == ["ux"]
    assert got["issues"][0]["age_days"] >= 0
    assert json.loads(c.read_text())["count"] == 1


# --------------------------------------------------------------- one line
def test_a_short_repo_name_is_resolved_against_the_owners(monkeypatch):
    """"issue ux ..." is what gets typed. Guessing one owner would file into
    the wrong account, so GitHub is asked which one has it."""
    calls = []

    def gh(*a, **k):
        calls.append(a)
        if a[0] == "repo":
            return '{"name":"ux"}' if a[2].startswith("PlanetaryCouncil") else ""
        return "https://github.com/PlanetaryCouncil/ux/issues/1"

    monkeypatch.setattr(issues, "_gh", gh)
    assert issues.create("ux", "the nav wraps") .endswith("/issues/1")
    assert calls[-1][:2] == ("issue", "create")
    assert "PlanetaryCouncil/ux" in calls[-1]


def test_an_unknown_repo_files_nothing_rather_than_guessing(monkeypatch):
    monkeypatch.setattr(issues, "_gh", lambda *a, **k: "")
    assert issues.create("nope", "x") == ""


def test_a_full_name_is_used_as_given(monkeypatch):
    calls = []
    monkeypatch.setattr(issues, "_gh",
                        lambda *a, **k: (calls.append(a), "url")[1])
    issues.create("someone/else", "x")
    assert calls[0][0] == "issue" and "someone/else" in calls[0]


# ------------------------------------------------------------- not published
def test_the_pane_is_local_only():
    """An open issue is a to-do list. The board publishes what the fleet DID."""
    src = (BIN / "fleet.py").read_text()
    i = src.index('if path == "/api/issues":')
    assert "self._remote()" in src[i:i + 500]
    assert '"local_only": True' in src[i:i + 500]


def test_the_pane_is_wired_into_the_board():
    src = (BIN / "oneview.py").read_text()
    assert 'id="issues"' in src
    assert "loadIssues();" in src
    assert "setInterval(loadIssues, 300000);" in src, "must not poll hot"


def test_the_one_line_filer_exists_and_runs():
    f = ROOT / "fleet" / "bin" / "issue"
    assert f.exists() and f.stat().st_mode & 0o111, "not executable"
    body = f.read_text()
    assert 'REPO="command-control-dashboard"' in body, "no default repo"
    assert 'FLEET_BIN=' in body, "path guessed; would break on the NUC"
