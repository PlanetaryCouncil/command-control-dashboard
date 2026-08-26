"""Cheap autopilot closes noise without building anything."""

import json
import sys
from pathlib import Path

import pytest

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))
import autotriage  # noqa: E402
import pipeline    # noqa: E402


@pytest.fixture
def pile(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PROPOSALS", tmp_path / "proposals.jsonl")
    monkeypatch.setattr(pipeline, "STATE", tmp_path / "pipeline.jsonl")
    monkeypatch.setattr(pipeline, "WORKER", tmp_path / "pipeline.json")
    monkeypatch.setattr(autotriage, "FLEET", tmp_path)
    # pipeline reads build.txt through its OWN FLEET. Patching only
    # autotriage's let a test read the operator's real queue -- which is how
    # the first autopick test failed: it saw a pick made on this machine.
    monkeypatch.setattr(pipeline, "FLEET", tmp_path)
    (tmp_path / "rota").mkdir()
    monkeypatch.setattr(pipeline, "ev",
                        type("E", (), {"emit": staticmethod(lambda *a, **k: None)}))
    monkeypatch.setattr(autotriage, "ev", pipeline.ev)
    return tmp_path


def write_props(pile, rows):
    pipeline.PROPOSALS.write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n")


def _fresh_ts(minutes=5):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat(
        timespec="seconds")


def test_errors_and_nothing_drop_without_a_model(pile, monkeypatch):
    monkeypatch.setattr(autotriage, "ask_cheap", lambda p: (_ for _ in ()).throw(
        AssertionError("model should not run on drain-only")))
    err, nothing, keep = _fresh_ts(9), _fresh_ts(8), _fresh_ts(7)
    write_props(pile, [
        {"ts": err, "agent": "codex",
         "outcome": "error", "text": "[unknown agent codex]"},
        {"ts": nothing, "agent": "hermes",
         "outcome": "nothing", "text": "NOTHING TO ADD"},
        {"ts": keep, "agent": "grok",
         "outcome": "proposed", "text": "Add a stale-but-pass worker state"},
    ])
    res = autotriage.run(drain_only=True)
    seen = pipeline.by_proposal()
    assert seen[err]["stage"] == "drop"
    assert seen[nothing]["stage"] == "drop"
    assert keep not in seen
    assert res["open"] == 1


def test_duplicate_gists_collapse(pile, monkeypatch):
    monkeypatch.setattr(autotriage, "ask_cheap", lambda p: "")
    a, b = _fresh_ts(6), _fresh_ts(5)
    write_props(pile, [
        {"ts": a, "agent": "hermes",
         "outcome": "proposed", "text": "Make staleness a warn not a footnote"},
        {"ts": b, "agent": "grok",
         "outcome": "proposed",
         "text": "Make   staleness a warn not a footnote"},
    ])
    autotriage.run(drain_only=True)
    seen = pipeline.by_proposal()
    assert a not in seen
    assert seen[b]["detail"].startswith("duplicate")


def test_parse_verdicts_matches_prefix():
    batch = {"2026-08-20T10:24:46+00:00", "2026-08-20T09:00:00Z"}
    blob = "2026-08-20T10:24 | DROP | restatement\n2026-08-20T09:00 | KEEP | real gap\n"
    v = autotriage.parse_verdicts(blob, batch)
    assert v["2026-08-20T10:24:46+00:00"] == "DROP"
    assert v["2026-08-20T09:00:00Z"] == "KEEP"


def test_unparsed_model_output_does_not_drop(pile, monkeypatch):
    monkeypatch.setattr(autotriage, "ask_cheap", lambda p: "sure whatever")
    ts = _fresh_ts(4)
    write_props(pile, [
        {"ts": ts, "agent": "agy",
         "outcome": "proposed", "text": "Publish /submit for the xprize"},
    ])
    autotriage.run(batches=1, drain_only=False)
    assert ts not in pipeline.by_proposal()


def test_parse_keep_stamps():
    batch = {"2026-08-07T13:00:00+00:00", "2026-08-07T14:05:11Z"}
    blob = "KEEP 2026-08-07T13:00\nnope\nKEEP 2026-08-07T14:05\n"
    hits = autotriage.parse_keep_stamps(blob, batch)
    assert hits == batch


def _old_ts(hours=36):
    from datetime import datetime, timedelta, timezone
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(
        timespec="seconds")


def test_unique_stale_skips_narration(pile):
    old = _old_ts()
    write_props(pile, [
        {"ts": old, "agent": "hermes", "outcome": "proposed",
         "text": "I'll answer the three questions based on the prompt"},
    ])
    pipeline.record(proposal_ts=old, stage="drop", ok=True,
                    detail="stale>24h", agent="autotriage", branch="")
    assert autotriage.unique_stale(12) == []


def test_unique_stale_skips_session_limit(pile):
    old = _old_ts()
    write_props(pile, [
        {"ts": old, "agent": "claude", "outcome": "proposed",
         "text": "You've hit your session limit · resets 7:40pm"},
    ])
    pipeline.record(proposal_ts=old, stage="drop", ok=True,
                    detail="stale>24h", agent="autotriage", branch="")
    assert autotriage.unique_stale(12) == []


def test_unique_stale_keeps_wrapped_file_write(pile):
    old = _old_ts()
    write_props(pile, [
        {"ts": old, "agent": "hermes", "outcome": "proposed",
         "text": "Here are the answers: 1. **basex** — write `static/basex/index.html`"},
    ])
    pipeline.record(proposal_ts=old, stage="drop", ok=True,
                    detail="stale>24h", agent="autotriage", branch="")
    assert [p["ts"] for p in autotriage.unique_stale(12)] == [old]


def test_unique_stale_collapses_same_static_path(pile):
    a = _old_ts(40)
    b = _old_ts(36)
    write_props(pile, [
        {"ts": a, "agent": "claude", "outcome": "proposed",
         "text": "**1. basex** — write `static/basex/index.html`: a one-pager"},
        {"ts": b, "agent": "hermes", "outcome": "proposed",
         "text": "Here are the answers: write `static/basex/index.html` again"},
    ])
    for ts in (a, b):
        pipeline.record(proposal_ts=ts, stage="drop", ok=True,
                        detail="stale>24h", agent="autotriage", branch="")
    reps = autotriage.unique_stale(12)
    assert [p["ts"] for p in reps] == [b]


def test_unique_stale_skips_pick_one_project(pile):
    old = _old_ts()
    write_props(pile, [
        {"ts": old, "agent": "hermes", "outcome": "proposed",
         "text": "I'll answer the questions according to the rules. "
                 "**1. pick one project from the list and name it**"},
    ])
    pipeline.record(proposal_ts=old, stage="drop", ok=True,
                    detail="stale>24h", agent="autotriage", branch="")
    assert autotriage.unique_stale(12) == []


def test_unique_stale_keeps_a_real_action(pile):
    old = _old_ts()
    write_props(pile, [
        {"ts": old, "agent": "agy", "outcome": "proposed",
         "text": "Add a named title to the NUC board tab"},
    ])
    pipeline.record(proposal_ts=old, stage="drop", ok=True,
                    detail="stale>24h", agent="autotriage", branch="")
    reps = autotriage.unique_stale(12)
    assert [p["ts"] for p in reps] == [old]


def test_drain_does_not_re_stale_a_reopen(pile, monkeypatch):
    monkeypatch.setattr(autotriage, "ask_cheap", lambda p: (_ for _ in ()).throw(
        AssertionError("drain-only")))
    old = _old_ts()
    write_props(pile, [
        {"ts": old, "agent": "grok", "outcome": "proposed",
         "text": "Show quota pulse as login plus 24h failure shapes"},
    ])
    pipeline.record(proposal_ts=old, stage="reopen", ok=True,
                    detail="unique stale, two vendors KEEP",
                    agent="autotriage", branch="")
    res = autotriage.run(drain_only=True)
    rec = pipeline.by_proposal()[old]
    assert rec["stage"] == "reopen"
    assert res["open"] == 1


def test_review_old_needs_two_vendor_keep(pile, monkeypatch):
    old = _old_ts()
    write_props(pile, [
        {"ts": old, "agent": "agy", "outcome": "proposed",
         "text": "Cap autotriage picks at one so the pile cannot flood"},
    ])
    pipeline.record(proposal_ts=old, stage="drop", ok=True,
                    detail="stale>24h", agent="autotriage", branch="")

    def one_vendor(batch, who):
        return {old} if who == "agy" else set()

    monkeypatch.setattr(autotriage, "vote_keep", one_vendor)
    res = autotriage.review_old(limit=12, pick=1)
    assert res["picked"] == 0
    assert not (pile / "rota" / "build.txt").exists()


def test_review_old_picks_intersection(pile, monkeypatch):
    old = _old_ts()
    write_props(pile, [
        {"ts": old, "agent": "grok", "outcome": "proposed",
         "text": "Tunnel the NUC board on 8788 so Gaia keeps 8787"},
    ])
    pipeline.record(proposal_ts=old, stage="drop", ok=True,
                    detail="stale>24h", agent="autotriage", branch="")
    monkeypatch.setattr(autotriage, "vote_keep", lambda batch, who: {old})
    res = autotriage.review_old(limit=12, pick=1)
    assert res["picked"] == 1
    assert pipeline.by_proposal()[old]["stage"] == "reopen"
    body = (pile / "rota" / "build.txt").read_text()
    assert old[:19] in body


def test_triage_agent_reads_config(pile, monkeypatch):
    monkeypatch.delenv("FLEET_TRIAGE", raising=False)
    (pile / "config.json").write_text(
        '{"pipeline": {"triage_agent": "grok"}}\n')
    assert autotriage.triage_agent() == "grok"


def test_already_built_skips_drop_not_reopen():
    done = {
        "2026-08-07T13:00:00+00:00": {"stage": "drop"},
        "2026-08-07T14:00:00+00:00": {"stage": "reopen"},
        "2026-08-07T15:00:00+00:00": {"stage": "land"},
    }
    assert pipeline.already_built("2026-08-07T13:00", done) is True
    assert pipeline.already_built("2026-08-07T14:00:00", done) is False
    assert pipeline.already_built("2026-08-07T15:00:00+00:00", done) is True
    assert pipeline.already_built("2026-08-07T16:00", done) is False


def test_already_built_preserves_seconds_when_proposals_share_a_minute():
    done = {
        "2026-08-07T13:00:05+00:00": {"stage": "land"},
        "2026-08-07T13:00:45+00:00": {"stage": "reopen"},
    }
    assert pipeline.already_built("2026-08-07T13:00:05", done) is True
    assert pipeline.already_built("2026-08-07T13:00:45", done) is False


def test_age_alone_never_closes_a_proposal(pile, monkeypatch):
    """A proposal filed 36 hours ago is exactly as valid as one filed now.

    This used to close on age and it was the single biggest consumer of the
    queue: 140 proposals in one day, more than half of everything the
    pipeline touched, none of them ever read. Age describes the queue's
    throughput, not the idea -- charging the idea for the queue's backlog is
    how a fleet quietly discards its own best work.
    """
    from datetime import datetime, timedelta, timezone
    monkeypatch.setattr(autotriage, "ask_cheap", lambda p: (_ for _ in ()).throw(
        AssertionError("drain must not call a model")))
    old = (datetime.now(timezone.utc) - timedelta(hours=36)).isoformat(
        timespec="seconds")
    fresh = datetime.now(timezone.utc).isoformat(timespec="seconds")
    write_props(pile, [
        {"ts": old, "agent": "hermes", "outcome": "proposed",
         "text": "Write static/basex/index.html"},
        {"ts": fresh, "agent": "grok", "outcome": "proposed",
         "text": "A fresh unique action for today"},
    ])
    autotriage.run(drain_only=True)
    seen = pipeline.by_proposal()
    assert old not in seen, "the old proposal must still be waiting, not closed"
    assert fresh not in seen


def test_model_drop_closes_without_building(pile, monkeypatch):
    ts = _fresh_ts(3)
    monkeypatch.setattr(
        autotriage, "ask_cheap",
        lambda p: f"{ts[:16]} | DROP | already shipped\n")
    write_props(pile, [
        {"ts": ts, "agent": "grok", "outcome": "proposed",
         "text": "Tag E2E traffic out of visitors"},
    ])
    autotriage.run(batches=1)
    rec = pipeline.by_proposal()[ts]
    assert rec["stage"] == "drop"
    assert rec.get("branch") == ""


def test_unexpire_reopens_only_what_the_clock_closed(pile):
    """Age-closures come back. Judgement-closures do not.

    The distinction is the whole point: a proposal a model actually read and
    dropped was assessed, and reopening it would relitigate a decision. A
    proposal closed for being late was never read at all.
    """
    from datetime import datetime, timedelta, timezone
    old = (datetime.now(timezone.utc) - timedelta(hours=40)).isoformat(
        timespec="seconds")
    judged = (datetime.now(timezone.utc) - timedelta(hours=41)).isoformat(
        timespec="seconds")
    write_props(pile, [
        {"ts": old, "agent": "hermes", "outcome": "proposed",
         "text": "An idea nobody ever read"},
        {"ts": judged, "agent": "grok", "outcome": "proposed",
         "text": "An idea a model read and rejected"},
    ])
    pipeline.record(proposal_ts=old, stage="drop", ok=True,
                    detail="stale>24h", agent="autotriage", branch="")
    pipeline.record(proposal_ts=judged, stage="drop", ok=True,
                    detail="cheap-model DROP", agent="triage-hermes", branch="")

    assert autotriage.unexpire(dry_run=True)["unexpired"] == 1
    assert autotriage.unexpire()["unexpired"] == 1

    seen = pipeline.by_proposal()
    assert seen[old]["stage"] == "reopen", "the clock's victim comes back"
    assert seen[judged]["stage"] == "drop", "a real judgement is not relitigated"


def test_unexpire_is_idempotent():
    """Running it twice must not stack reopen records. The second run finds
    nothing still closed for age, because the first one reopened them."""
    assert autotriage.unexpire()["unexpired"] == 0


def test_autopick_takes_the_oldest_and_never_overwrites_a_human_pick(pile):
    """Automating the pick changes how much gets built, not who decides what
    ships: the builder works in a throwaway worktree and a human still lands
    every branch.

    Oldest first, because a queue that always takes the newest is how a
    backlog becomes permanent -- 1715 proposals sat behind a build.txt whose
    last pick was a week old.
    """
    from datetime import datetime, timedelta, timezone
    older = (datetime.now(timezone.utc) - timedelta(hours=50)).isoformat(
        timespec="seconds")
    newer = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(
        timespec="seconds")
    write_props(pile, [
        {"ts": newer, "agent": "grok", "outcome": "proposed",
         "text": "A recent idea"},
        {"ts": older, "agent": "agy", "outcome": "proposed",
         "text": "An idea that has waited two days"},
    ])
    res = autotriage.autopick(1)
    assert res["picked"] == 1
    assert res["oldest"] == older, "the one that waited longest goes first"

    # A pick is now queued; running again must not clobber it.
    again = autotriage.autopick(1)
    assert again["picked"] == 0
    assert "queue" in again["reason"]
