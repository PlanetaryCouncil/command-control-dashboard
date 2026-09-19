"""Six public routes 502 for the first ~20 seconds of every boot.

/about, /auth, /llms.txt, /health, /api/fleet and /api/signals are served by
the legacy cockpit, which runs as a thread inside the board. Its import chain
-- FastAPI, pydantic, the app -- takes seconds cold and far longer on a loaded
box. Until it binds, those routes forward to nothing.

That is by design; the board binds first on purpose so a restart is not a
blackout. What was NOT by design is that the log said the cockpit was up the
moment the thread was handed off, so a boot where it never bound looked
identical to one where it did -- which is how it stayed unnoticed on
2026-09-19 until six routes had been down long enough for someone to ask.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = (REPO / "fleet" / "bin" / "fleet.py").read_text()


def _cockpit():
    i = SRC.index("def start_legacy_cockpit(")
    return SRC[i:SRC.index("\ndef ", i + 10)]


def test_the_up_line_means_bound_not_dispatched():
    """The first attempt polled the port, which happily confirmed a DIFFERENT
    process's bind -- it printed "cockpit up" in a log where uvicorn had said
    "address already in use" two lines earlier. Uvicorn reports its own
    startup now."""
    fn = _cockpit()
    assert "bound = threading.Event()" in fn
    assert "bound.wait(" in fn
    assert "create_connection" not in fn, "back to guessing from outside"


def test_a_cockpit_that_never_binds_says_so():
    fn = _cockpit()
    assert "never bound" in fn
    # and names what the reader will actually notice
    assert "/llms.txt" in fn


def test_the_thread_cannot_die_silently():
    """uvicorn.Server.run in a bare thread loses its own exception: the thread
    dies and the only symptom is six routes answering 502 hours later."""
    fn = _cockpit()
    run = fn[fn.index("def run():"):fn.index("threading.Thread(target=run")]
    assert "except Exception" in run
    assert "died" in run


def test_a_scratch_boot_does_not_take_the_cockpit_port():
    """reload.sh boots the new code on a scratch port to check it before
    swapping, and that instance was also binding :8770 -- two processes racing
    for one port on every reload, with the loser dying silently. A rehearsal
    does not get to take the stage."""
    # serve() is the last function in the file, so there is no following
    # "\ndef " to slice to -- the naive bound raised ValueError.
    i = SRC.index("def serve(port):")
    fn = SRC[i:]
    assert "port == CANONICAL_PORT" in fn
    assert "not starting the cockpit" in fn


def test_the_canonical_port_is_the_one_launchd_serves():
    assert re.search(r"^CANONICAL_PORT = 8787$", SRC, re.M)


def test_the_cockpit_port_can_be_moved_for_a_test():
    """A test that has to evict the real cockpit from :8770 is a test nobody
    runs twice."""
    assert 'os.environ.get("FLEET_COCKPIT_PORT")' in SRC
