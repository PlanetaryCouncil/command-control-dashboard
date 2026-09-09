"""A verified branch waits for Marsita now. It does not merge itself.

Marsita, 2026-09-09: "STOP automerge to main -----> I need to review
changes... It then takes too much time to undo."

This reverses her own instruction of 2026-08-07 -- "fleet can merge... I don't
want to worry about infra / pr / code / issues" -- and the reason is worth
keeping, because it is not that she changed her mind about reading diffs. It
is the asymmetry: a branch that waits costs the fleet some latency, and a
merge that was wrong costs HER an evening of undoing it. The cheap failure and
the expensive one are not on the same side.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import pipeline            # noqa: E402


def test_autoland_is_off():
    cfg = json.loads((ROOT / "fleet" / "config.json").read_text())
    assert cfg["pipeline"]["autoland"] is False
    assert pipeline.autoland_on() is False


def test_the_switch_is_read_every_time_not_at_import():
    """Turning it back on should be an edit to config.json, not a restart."""
    src = (BIN / "pipeline.py").read_text()
    i = src.index("def autoland_on(")
    assert "config.json" in src[i:i + 900]


def test_an_unreadable_config_never_merges(monkeypatch, tmp_path):
    """The failure that costs her an evening must not be the default."""
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    assert pipeline.autoland_on() is False


def test_a_config_that_says_true_is_obeyed(monkeypatch, tmp_path):
    (tmp_path / "fleet").mkdir(exist_ok=True)
    (tmp_path / "fleet" / "config.json").write_text(
        json.dumps({"pipeline": {"autoland": True}}))
    monkeypatch.setattr(pipeline, "REPO", tmp_path)
    assert pipeline.autoland_on() is True


def test_land_records_a_wait_instead_of_merging(monkeypatch):
    """It must not reach git at all -- not merge and roll back, not merge and
    not push. The branch is left exactly where it is."""
    calls = []
    monkeypatch.setattr(pipeline, "autoland_on", lambda: False)
    monkeypatch.setattr(pipeline, "state", lambda: [])
    monkeypatch.setattr(pipeline, "run",
                        lambda *a, **k: calls.append(a) or (0, ""))
    written = {}
    monkeypatch.setattr(pipeline, "record",
                        lambda **kw: written.update(kw) or kw)
    monkeypatch.setattr(pipeline.ev, "emit", lambda *a, **k: None)

    pipeline.land({"branch": "rota/x", "proposal_ts": "2026-09-09T00:00:00"})
    assert written["stage"] == "await"
    assert written["branch"] == "rota/x"
    assert not calls, "it touched git"


def test_waiting_is_recorded_once_not_once_an_hour(monkeypatch):
    """The pipeline runs hourly; four waiting branches would file ninety-six
    identical rows a day into the ledger the board reads."""
    monkeypatch.setattr(pipeline, "autoland_on", lambda: False)
    monkeypatch.setattr(pipeline, "state", lambda: [
        {"proposal_ts": "2026-09-09T00:00:00", "stage": "await"}])
    monkeypatch.setattr(pipeline, "record",
                        lambda **kw: (_ for _ in ()).throw(AssertionError("filed twice")))
    monkeypatch.setattr(pipeline.ev, "emit", lambda *a, **k: None)
    assert pipeline.land({"branch": "rota/x",
                          "proposal_ts": "2026-09-09T00:00:00"}) == {}


def test_a_waiting_branch_is_not_rebuilt():
    """Done, but not finished. The queue must leave it alone."""
    assert "await" in pipeline.CLOSED_STAGES
    prop = {"ts": "2026-09-09T00:00:00", "text": "do a thing"}
    seen = {"2026-09-09T00:00:00": {"stage": "await"}}
    assert pipeline.is_waiting(prop, seen) is False
