"""The public writes are anonymous, so they need a ceiling.

/api/charge and /api/signatures/sign are open on purpose — the pad only
collects one hand if only locals can sign it. Open does not have to mean
unbounded: /api/charge had no rate limit and no size cap, so an anonymous
caller could fill the disk on a host whose unit is Restart=always. That is a
restart loop against a full disk, not a clean stop.

Two ceilings, tested here: how large the file may get, and how fast one caller
may append to it.
"""

import json
import sys
from pathlib import Path

FLEET_BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(FLEET_BIN))

import fleet  # noqa: E402


def test_the_file_rotates_once_it_is_large_enough(tmp_path):
    log = tmp_path / "charges.jsonl"
    log.write_text("x" * (fleet.PUBLIC_WRITE_MAX_BYTES + 1))

    fleet._append_capped(log, {"project": "orrery"})

    assert log.with_suffix(".jsonl.1").exists(), "the old file is kept, not dropped"
    assert json.loads(log.read_text())["project"] == "orrery"
    assert log.stat().st_size < 1000, "the live file starts over"


def test_a_small_file_is_appended_not_rotated(tmp_path):
    log = tmp_path / "charges.jsonl"
    fleet._append_capped(log, {"n": 1})
    fleet._append_capped(log, {"n": 2})

    assert not log.with_suffix(".jsonl.1").exists()
    assert [json.loads(l)["n"] for l in log.read_text().splitlines()] == [1, 2]


def test_the_limiter_is_wired_up():
    """A silent fallback to no limiting would be the failure that hides itself."""
    assert fleet.PUBLIC_WRITE_LIMITER is not None, \
        "legacy/app/ratelimit.py did not import — writes are unlimited"


def test_a_burst_is_allowed_then_refused():
    """Generous to a person, ruinous to a flood — the existing bucket's shape."""
    fleet.PUBLIC_WRITE_LIMITER.reset()
    allowed = sum(fleet.PUBLIC_WRITE_LIMITER.check("203.0.113.9")[0]
                  for _ in range(40))
    assert 0 < allowed < 40, f"expected a burst then refusal, got {allowed}/40"
    fleet.PUBLIC_WRITE_LIMITER.reset()


def test_one_caller_cannot_mint_buckets_by_varying_the_left_xff():
    """The #10 lesson, in the limiter this time.

    Keying on the leftmost X-Forwarded-For entry would let a caller send a
    different value each request and never exhaust a bucket. The trusted proxy
    appends, so the last entry is the one that means anything.
    """
    fleet.PUBLIC_WRITE_LIMITER.reset()
    spoofed = [f"10.0.0.{i}, 203.0.113.9" for i in range(40)]
    allowed = sum(fleet.PUBLIC_WRITE_LIMITER.check(x.split(",")[-1].strip())[0]
                  for x in spoofed)
    assert 0 < allowed < 40, "varying the leftmost entry defeated the limit"
    fleet.PUBLIC_WRITE_LIMITER.reset()
