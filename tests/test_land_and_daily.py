"""Landing branches without a human, and the one message that reports it.

The risk of auto-merge is not a bad branch — those are caught by verify. It
is two branches that are each green and break each other, which no per-branch
verdict can see. So the test that matters is: the suite runs again on the
merge commit, and a failure rolls main back rather than pushing.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import pipeline  # noqa: E402


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=str(cwd),
                          capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A tiny real repo: main, plus a branch that adds a file."""
    r = tmp_path / "repo"
    r.mkdir()
    git("init", "-q", "-b", "main", cwd=r)
    git("config", "user.email", "t@t", cwd=r)
    git("config", "user.name", "t", cwd=r)
    (r / "a.txt").write_text("one\n")
    git("add", "-A", cwd=r)
    git("commit", "-qm", "first", cwd=r)
    git("checkout", "-q", "-b", "feature", cwd=r)
    (r / "b.txt").write_text("two\n")
    git("add", "-A", cwd=r)
    git("commit", "-qm", "second", cwd=r)
    git("checkout", "-q", "main", cwd=r)

    monkeypatch.setattr(pipeline, "REPO", r)
    monkeypatch.setattr(pipeline, "STATE", tmp_path / "pipeline.jsonl")
    monkeypatch.setattr(pipeline, "WORKTREES", tmp_path / "wt")
    monkeypatch.setattr(pipeline.ev, "emit", lambda *a, **k: None)
    return r


def _fake_pytest(tmp_path, exit_code):
    p = tmp_path / f"pytest{exit_code}"
    p.write_text(f"#!/bin/sh\necho '3 passed'\nexit {exit_code}\n")
    p.chmod(0o755)
    return p


def test_green_merge_lands(repo, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "venv_pytest",
                        lambda: _fake_pytest(tmp_path, 0))
    monkeypatch.setattr(pipeline, "run", _no_push(repo))
    r = pipeline.land({"branch": "feature", "proposal_ts": "t1"})
    assert r["ok"] is True
    assert r["sha"], "the merge commit is recorded"


def test_the_shared_checkout_is_never_moved(repo, tmp_path, monkeypatch):
    """The operator's tree — or another agent's — must be exactly where it
    was. On 2026-08-07 the Nuc was sitting on someone else's branch mid-task
    and a checkout here would have taken it away from them."""
    before = git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo).stdout.strip()
    head_before = git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    monkeypatch.setattr(pipeline, "venv_pytest",
                        lambda: _fake_pytest(tmp_path, 0))
    monkeypatch.setattr(pipeline, "run", _no_push(repo))
    pipeline.land({"branch": "feature", "proposal_ts": "t1"})
    assert git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo).stdout.strip() == before
    assert git("rev-parse", "HEAD", cwd=repo).stdout.strip() == head_before


def test_red_merge_rolls_back(repo, tmp_path, monkeypatch):
    """Green alone, red merged — the case auto-merge exists to survive."""
    before = git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    monkeypatch.setattr(pipeline, "venv_pytest",
                        lambda: _fake_pytest(tmp_path, 1))
    monkeypatch.setattr(pipeline, "run", _no_push(repo))
    r = pipeline.land({"branch": "feature", "proposal_ts": "t1"})
    assert r["ok"] is False
    assert git("rev-parse", "HEAD", cwd=repo).stdout.strip() == before
    assert git("rev-parse", "main", cwd=repo).stdout.strip() == before, \
        "main is exactly where it was"


def test_conflict_is_not_a_crash(repo, tmp_path, monkeypatch):
    (repo / "b.txt").write_text("conflicting\n")
    git("add", "-A", cwd=repo)
    git("commit", "-qm", "main moved", cwd=repo)
    monkeypatch.setattr(pipeline, "venv_pytest",
                        lambda: _fake_pytest(tmp_path, 0))
    monkeypatch.setattr(pipeline, "run", _no_push(repo))
    r = pipeline.land({"branch": "feature", "proposal_ts": "t1"})
    assert r["ok"] is False
    assert "conflict" in str(r.get("detail", "")).lower()


def _no_push(repo):
    """Real git for everything except the push — the test has no remote, and
    a landing that only works with a remote attached is untestable."""
    original = pipeline.run

    def run(cmd, cwd=None, timeout=300, stdin_text=None):
        if cmd[:2] == ["git", "push"]:
            return 0, "pushed (stubbed)"
        return original(cmd, cwd=cwd, timeout=timeout, stdin_text=stdin_text)
    return run


def test_land_fetch_does_not_update_checked_out_main():
    src = (BIN / "pipeline.py").read_text()
    assert '["git", "fetch", "origin", "main:main"]' not in src
    assert "def remote_main" in src


def test_land_runs_even_when_building_is_off():
    """A machine that handed compiling to its brother still merges what it
    verified. Asserted on the source: the landing loop must come before the
    build gate."""
    src = (BIN / "pipeline.py").read_text()
    body = src[src.index("def _cycle("):]
    assert body.index("land(r)") < body.index("buildgate.enabled()")


def test_daily_pipeline_state_uses_the_latest_row(tmp_path, monkeypatch):
    import daily, json
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = [
        {"ts": now, "proposal_ts": "t1", "stage": "verify", "ok": False,
         "branch": "rota/brainfarts", "review": "REJECT mass update"},
        {"ts": now, "proposal_ts": "t1", "stage": "land", "ok": True,
         "branch": "rota/brainfarts", "detail": "pushed"},
        {"ts": now, "proposal_ts": "t2", "stage": "land", "ok": False,
         "branch": "rota/old", "detail": "conflict: unrelated histories"},
    ]
    (tmp_path / "rota").mkdir()
    (tmp_path / "rota" / "pipeline.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")
    monkeypatch.setattr(daily, "FLEET", tmp_path)
    stuck, rejected = daily.pipeline_state()
    assert rejected == []
    assert any("unrelated" in s for s in stuck)
    assert not any("brainfarts" in s for s in stuck)


def test_daily_report_is_short_and_has_the_sections():
    import daily
    txt = daily.report()
    assert "landed on main:" in txt
    assert "needs you:" in txt
    assert len(txt.splitlines()) < 60, "a summary that long is a report"
