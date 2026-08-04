"""The circuit breaker, and the two ways it could be worse than useless.

Council, 2026-08-02: three relays produced byte-identical outcomes, each costing
~16 minutes of wall clock to reproduce a result already known. On four cores that
is the entire capacity argument.

The failure modes to guard against are opposite. Trip too eagerly and a flapping
job — which is still producing information — goes quiet. Trip too quietly and the
fleet has a job that stopped running with nobody noticing, which is the exact
"a silent worker looks identical to a healthy one" fault this fleet has already
been bitten by.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fleet" / "bin"))
import breaker  # noqa: E402


def hops(*spec):
    return {"status": "alert",
            "hops": [{"agent": a, "lap": 1, "outcome": o, "ok": o == "ok"}
                     for a, o in spec]}


SAME = hops(("claude", "ok"), ("hermes", "timeout"), ("openclaw", "timeout"))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(breaker, "STATE_DIR", tmp_path)


def test_it_does_not_trip_before_the_third_identical_failure():
    """Two is a coincidence. The cost of one more run is lower than the cost of
    going blind to a problem that was about to change shape."""
    for expected in (1, 2):
        state = breaker.record("relay", SAME, healthy=False)
        assert state["streak"] == expected
        assert state["tripped"] is False
        assert breaker.should_skip("relay")[0] is False


def test_the_third_identical_failure_trips_it():
    for _ in range(3):
        state = breaker.record("relay", SAME, healthy=False)
    assert state["tripped"] is True
    assert breaker.should_skip("relay")[0] is True
    assert "reset" in state["reason"]


def test_a_flapping_job_keeps_running():
    """Different failures each time are still information, so keep paying for it.

    This is the property that stops the breaker becoming a way to silence
    anything intermittent — which is most real faults.
    """
    breaker.record("relay", hops(("claude", "ok"), ("hermes", "timeout")), healthy=False)
    breaker.record("relay", hops(("claude", "wrong"), ("hermes", "ok")), healthy=False)
    state = breaker.record("relay", hops(("claude", "ok"), ("hermes", "wrong")), healthy=False)
    assert state["tripped"] is False
    assert state["streak"] == 1


def test_a_healthy_run_clears_everything():
    """The job proving it works is the only evidence worth an automatic reset."""
    for _ in range(2):
        breaker.record("relay", SAME, healthy=False)
    state = breaker.record("relay", {"status": "pass", "hops": []}, healthy=True)
    assert state["streak"] == 0 and state["tripped"] is False


def test_timing_noise_does_not_reset_the_streak():
    """A failure two seconds slower is the same failure. If durations counted,
    the breaker would never trip on anything real."""
    a = dict(SAME); a["hops"] = [dict(h, seconds=300.1) for h in SAME["hops"]]
    b = dict(SAME); b["hops"] = [dict(h, seconds=441.9) for h in SAME["hops"]]
    assert breaker.fingerprint(a) == breaker.fingerprint(b)


def test_a_different_agent_failing_is_a_different_failure():
    assert breaker.fingerprint(hops(("hermes", "timeout"))) != \
           breaker.fingerprint(hops(("openclaw", "timeout")))


def test_resetting_is_manual():
    """A breaker that resets itself on a timer is a slower retry loop, and would
    hand back the cost it was built to save."""
    for _ in range(3):
        breaker.record("relay", SAME, healthy=False)
    assert breaker.should_skip("relay")[0] is True
    breaker.reset("relay")
    assert breaker.should_skip("relay")[0] is False


def test_a_missing_state_file_does_not_skip_the_job():
    """Fail toward running. An unreadable breaker must not silently suspend a
    healthy job — the failure mode here is worse than an extra run."""
    assert breaker.should_skip("never-seen")[0] is False
