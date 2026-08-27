import shutil

import pytest

from app import main, ratelimit

# Every path main.py writes through. Missing one means tests mutate real data.
WRITE_PATHS = ("DATA_PATH", "INBOX_PATH", "HORIZONS_PATH", "EVENTS_PATH",
               "BRAINFARTS_PATH", "TRUSTED_NODES_PATH", "CONFLICTS_PATH")


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """The signals limiter is process-global by design.

    Without this, buckets drained by one test leak into the next and unrelated
    tests fail with 429 depending on execution order — which is exactly what
    happened when the limiter was introduced.
    """
    ratelimit.signals_limiter.reset()
    yield
    ratelimit.signals_limiter.reset()


@pytest.fixture(autouse=True)
def isolate_written_data(tmp_path, monkeypatch):
    """Never let a test write to the real data files.

    Tests post signals, touch projects and set horizons. Those writes were
    landing in the live data/*.json — and the fleet watchdog runs this suite
    hourly, so fake signals from `tester` were accumulating in the public queue
    indefinitely.

    Existing files are copied so behaviour is unchanged; absent ones are left
    absent rather than seeded with an invented shape. (Seeding produced a dict
    where sync_conflicts.json is a list, and the app's `extend` blew up.)
    """
    # The doorbell writes to the fleet's live events.jsonl via FLEET_PATH.
    # Without this, every suite run rang the real board — 11 fake "node
    # paired" lines on 2026-08-04, and the watchdog runs this suite hourly.
    fleet_dir = tmp_path / "fleet"
    fleet_dir.mkdir()
    monkeypatch.setenv("FLEET_PATH", str(fleet_dir))
    monkeypatch.setenv("POEMS_JSONL", str(tmp_path / "poems.jsonl"))
    monkeypatch.setenv("BRAINFARTS_JSONL", str(tmp_path / "brainfarts.jsonl"))

    for attr in WRITE_PATHS:
        real = getattr(main, attr, None)
        if real is None:
            continue
        copy = tmp_path / real.name
        if real.exists():
            shutil.copy(real, copy)
        monkeypatch.setattr(main, attr, copy, raising=False)

    oplog = getattr(main, "OPLOG_DIR", None)
    if oplog is not None:
        monkeypatch.setattr(main, "OPLOG_DIR", tmp_path / "oplog", raising=False)
    yield
