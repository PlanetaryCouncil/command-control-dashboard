"""Several tabs on one session agree on a size instead of overwriting it.

Every tab attaches to the same pty, so `resize` was a decree: the tab you
touched most recently set the width for everyone, and the others drew at a
width they did not have. Marsita, 2026-09-04, asked for the simple thing --
"syncing seems simple enough" -- rather than a second mode or an "another tab
is open" warning.

The rule is the one tmux already uses for several attached clients: fit the
smallest window. A screen drawn wider than a viewer's window wraps into
nonsense there; drawn narrower it just leaves a margin.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fleet" / "bin"))

import terminal


def _session():
    """A Session with no fork behind it -- only the sizing surface."""
    s = terminal.Session.__new__(terminal.Session)
    s.lock = __import__("threading").Lock()
    s.sizes = {}
    s.applied = []
    s.resize = lambda c, r: s.applied.append((c, r))
    return s


def test_one_tab_gets_exactly_its_own_size():
    s = _session()
    s.set_size(1, 120, 40)
    assert s.applied[-1] == (120, 40)


def test_two_tabs_settle_on_the_smallest_of_them():
    s = _session()
    s.set_size(1, 200, 50)
    s.set_size(2, 100, 30)
    assert s.applied[-1] == (100, 30)


def test_the_smaller_tab_does_not_lose_to_whoever_resized_last():
    """The actual complaint: last write won, so the order decided the width."""
    s = _session()
    s.set_size(1, 100, 30)
    s.set_size(2, 200, 50)          # a wider tab arrives second
    assert s.applied[-1] == (100, 30), "the wide tab overruled the narrow one"


def test_each_axis_is_taken_from_the_smallest_independently():
    """A tall narrow tab and a short wide one must both fit."""
    s = _session()
    s.set_size(1, 80, 60)
    s.set_size(2, 200, 24)
    assert s.applied[-1] == (80, 24)


def test_closing_a_tab_gives_the_room_back():
    """A closed tab kept its vote, so shutting a narrow one left the rest
    cramped to a window nobody was looking at."""
    s = _session()
    s.set_size(1, 200, 50)
    s.set_size(2, 100, 30)
    s.drop_size(2)
    assert s.applied[-1] == (200, 50)


def test_the_last_tab_leaving_changes_nothing():
    """With nobody attached there is no size to agree on; keep the last fit
    rather than resizing the pty to a made-up default."""
    s = _session()
    s.set_size(1, 120, 40)
    before = len(s.applied)
    s.drop_size(1)
    assert len(s.applied) == before


def test_a_silly_size_cannot_collapse_the_pty():
    """A backgrounded tab can report 0 columns; a 0-wide pty is not a screen."""
    s = _session()
    s.set_size(1, 0, 0)
    assert s.applied[-1] == (2, 2)
