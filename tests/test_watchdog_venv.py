"""The watchdog must find the venv that exists on THIS machine.

#32 taught the pipeline this and left the watchdog behind. The result on the
NUC, 2026-08-07: watchdogs ran hourly against a repo with 337 passing tests
and wrote "no test command detected" every time. Not a failure — a `skip`,
which is worse, because a board that says "skip" reads as nothing-to-do rather
than as evidence-not-collected.

Pinned here as source assertions rather than by executing watchdog.sh, because
the bug is a hardcoded path in a branch that only runs on a machine where that
path is wrong — the exact case a test on the developer's own box never reaches.
"""

from pathlib import Path

WATCHDOG = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "watchdog.sh"
SRC = WATCHDOG.read_text()


def test_more_than_one_venv_is_considered():
    """The whole bug: `.venv` was the only candidate."""
    for name in (".venv311", ".venv312", ".venv313"):
        assert name in SRC, f"{name} is not searched; a 3.11 box reports no tests"


def test_no_bare_hardcoded_venv_pytest_test():
    """`-x ".venv/bin/pytest"` as the sole gate is what broke it."""
    assert '-x ".venv/bin/pytest"' not in SRC, \
        "watchdog.sh hardcodes .venv again — see pipeline.venv_pytest()"


def test_plain_venv_is_still_tried_first():
    """Order matters: the conventional location wins where it works, so this
    changes nothing on the Mac. A fix that reorders machines is not a fix."""
    order = [SRC.index(f'{n}/bin/pytest') for n in (".venv", ".venv311")
             if f'{n}/bin/pytest' in SRC]
    assert order == sorted(order), ".venv must be tried before .venv311"


def test_the_skip_message_matches_what_is_actually_searched():
    """The message said `.venv/bin/pytest` while searching four paths. A
    diagnostic that misreports its own search sends the reader to the wrong
    place — which is how this survived a night of correct bug reports."""
    assert ".venv*/bin/pytest" in SRC
