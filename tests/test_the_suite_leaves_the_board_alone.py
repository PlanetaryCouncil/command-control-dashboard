"""The test suite must not post to the live board.

2026-09-02: the stream carried two contradictory lines every couple of
minutes -- "[local] llama3.2:1b answered in 0.0s -- the offline fallback is
alive" and "failed in 0.0s -- NOT responding", stamped the same second. The
local model had not been asked anything since 19 August; its ledger and its
worker file both still said so. The lines were the two localvoice test cases,
one passing and one failing, writing to the real events log every time the
hourly test worker ran. 0.0s because the model was mocked.

The cause is general, not local to localvoice: fleet/bin/events.py resolves
its log path at import time from its own __file__, so it ignores both the
fixture's FLEET_PATH and any env var set after import. Every fleet module a
test exercises could ring the real board.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))
import events as fleet_events                              # noqa: E402

LIVE = ROOT / "fleet" / "events.jsonl"


def test_the_log_under_test_is_not_the_live_one():
    assert Path(fleet_events.LOG).resolve() != LIVE.resolve(), (
        "a test that emits would post to the board Marsita is reading")


def test_emitting_lands_in_the_sandbox():
    rec = fleet_events.emit("selftest", "info", "this must not reach the board")
    assert rec["msg"].startswith("this must not")
    body = Path(fleet_events.LOG).read_text()
    assert "this must not reach the board" in body


def test_the_live_log_never_sees_a_test_agent():
    """A standing check on the real file, so a future leak is caught by its
    contents rather than by someone noticing on the board."""
    if not LIVE.exists():
        return
    tail = LIVE.read_text(errors="replace").splitlines()[-500:]
    assert not any('"agent": "selftest"' in line for line in tail)


def test_the_fixture_patches_the_constant_not_just_the_env():
    """Setting FLEET_EVENTS alone fixes nothing: LOG is already bound."""
    conf = (ROOT / "tests" / "conftest.py").read_text()
    assert 'monkeypatch.setattr(fleet_events, "LOG"' in conf
