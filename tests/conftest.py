import shutil
from pathlib import Path

import pytest

from app import main, ratelimit

# Every path main.py writes through. Missing one means tests mutate real data.
WRITE_PATHS = ("DATA_PATH", "INBOX_PATH", "HORIZONS_PATH", "EVENTS_PATH",
               "BRAINFARTS_PATH", "TRUSTED_NODES_PATH", "CONFLICTS_PATH")

# Logs the fleet appends to while the suite runs. A test asserting on its own
# writes must not also be reading the fleet's.
APPEND_ONLY = ("EVENTS_PATH", "BRAINFARTS_PATH")


@pytest.fixture(autouse=True)
def no_ambient_proxy(monkeypatch):
    """A test must not care what was exported in the shell that started it.

    `TRUST_PROXY=1` tells the app "a tunnel is in front of you, read the
    caller from X-Forwarded-For instead of the socket". The TestClient sends
    no such header, so `steering_caller` returns "" and every local-only WRITE
    is refused: 28 tests across approvals, dashboard, inbox and sync failed
    with 403 where they expected 404 or 200.

    Nothing was wrong with the code. The suite had simply been inheriting the
    variable from whatever launched it -- on 2026-09-04 that was a tmux server
    started with it set, so every run under that terminal failed and every run
    elsewhere passed. A suite whose result depends on the shell it was started
    from cannot be used to decide anything.

    Cleared by default; the tests that mean it (test_public_tunnel,
    test_ratelimit) set it themselves and still do.
    """
    monkeypatch.delenv("TRUST_PROXY", raising=False)


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
        # Append-only ledgers start empty. Copying them made assertions about
        # what a test itself wrote depend on what the fleet happened to log
        # that morning -- six brainfart tests broke on 2026-09-02 because an
        # agent filed a real entry at 17:00 and "exactly one record" became
        # two. The other files are seeded, because absent ones have shapes
        # the app cannot invent.
        if attr not in APPEND_ONLY and real.exists():
            shutil.copy(real, copy)
        monkeypatch.setattr(main, attr, copy, raising=False)

    # fleet/bin/events.py resolves its log path at import time, from its own
    # __file__ -- so setting an env var in a fixture does nothing to a module
    # that is already imported, and FLEET_PATH is not the name it reads. Every
    # fleet worker exercised by a test therefore wrote to the LIVE stream.
    #
    # Marsita, 2026-09-02, seeing two contradictory lines a couple of minutes
    # apart all afternoon: "[local] llama3.2:1b answered in 0.0s -- alive" and
    # "failed in 0.0s -- NOT responding", same second, both from a model that
    # had not been asked anything since 19 August. They were the two
    # localvoice test cases, ok and failure, landing on the board every time
    # the hourly test worker ran. 0.0s because the model was mocked.
    monkeypatch.setenv("FLEET_EVENTS", str(tmp_path / "events.jsonl"))
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                               / "fleet" / "bin"))
        import events as fleet_events
        monkeypatch.setattr(fleet_events, "LOG", tmp_path / "events.jsonl")
    except Exception:
        pass

    oplog = getattr(main, "OPLOG_DIR", None)
    if oplog is not None:
        monkeypatch.setattr(main, "OPLOG_DIR", tmp_path / "oplog", raising=False)
    yield
