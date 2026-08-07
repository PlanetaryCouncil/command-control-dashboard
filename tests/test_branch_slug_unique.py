"""Each proposal gets its own branch.

2026-08-07: three proposals from three agents on 2026-08-06 all landed on
`rota/2026-08-06-auto-rerun-stale-but-passing-workers-on-` — different content,
one branch, so one rejection read as a rejection of all. The branch name now
carries the proposal's time, and the pipeline refuses to build onto a branch
that already exists.
"""

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import pipeline  # noqa: E402


def test_same_title_same_day_different_branches():
    a = {"ts": "2026-08-06T10:13", "text": "Auto-rerun stale but passing workers on the hour"}
    b = {"ts": "2026-08-06T11:13", "text": "Auto-rerun stale but passing workers on the hour"}
    assert pipeline.branch_name(a) != pipeline.branch_name(b)
    assert pipeline.branch_name(a) == "rota/2026-08-06-1013-auto-rerun-stale-but-passing-workers-on-"


def test_missing_time_falls_back_to_the_date():
    assert pipeline.branch_name({"ts": "2026-08-06", "text": "Hi"}) == "rota/2026-08-06-hi"


def test_build_refuses_to_reuse_an_existing_branch(monkeypatch):
    prop = {"ts": "2026-08-06T11:13", "text": "Something", "agent": "hermes"}
    monkeypatch.setattr(pipeline, "branch_exists", lambda b: True)
    monkeypatch.setattr(pipeline, "record", lambda **kw: kw)
    monkeypatch.setattr(pipeline, "run", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("must not touch git")))
    out = pipeline.build(prop)
    assert out["ok"] is False
    assert "refusing to reuse" in out["detail"]
