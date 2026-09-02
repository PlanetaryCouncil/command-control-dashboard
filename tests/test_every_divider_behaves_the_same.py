"""Five symptoms, one cause: three dividers with three different models.

Marsita, 2026-09-02:
  1) on the left cannot [drag] all the way down (can all the way up)
  2) can go all the way up in the middle, cannot go all the way down (jumpy)
  3) on the right cannot go up and down at all
  4) left-right does not collapse fully on both left and right
  5) collapsing all the way up works on the left but does not work in the
     middle

They are related. The left divider clamped against `window.innerHeight`
instead of its own column, so it ran out of travel early. The middle returned
early from its paint when a pane collapsed, so the drag stopped dead under the
cursor. The right column had no divider element at all. Columns clamped at
180px so they could never shut. And collapse was configured per-divider
instead of being one rule.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))
import oneview                                             # noqa: E402

SRC = (ROOT / "fleet" / "bin" / "oneview.py").read_text()
PAGE = oneview.page("[]", "{}", "tok", remote=False)
DRAG = SRC.split("function dragGripV(")[1].split("\nfunction reopenOnHeading")[0]


def test_the_right_column_has_a_divider():
    assert 'id="gripP"' in PAGE
    assert '$("#gripP")' in SRC


def test_every_column_is_wired_to_the_same_drag():
    for grip in ('$("#gripA")', '$("#gripP")', '$("#gripT")'):
        assert f"dragGripV({grip}" in SRC, grip


def test_a_divider_measures_its_own_column_not_the_window():
    """The left one clamped against the viewport, which is taller than the
    column, so it stopped before the bottom."""
    assert "grip.parentElement.getBoundingClientRect().height" in DRAG
    assert "window.innerHeight" not in DRAG


def test_the_paint_never_returns_without_applying_a_height():
    """Returning early when a pane collapsed is what read as jumpy."""
    paint = DRAG.split("const paint = ()")[1].split("const move =")[0]
    assert "return;" not in paint, "an early return stops the drag dead"
    assert "applyHeight(" in paint


def test_both_panes_either_side_can_be_collapsed():
    for opts in ('other: "#goals"', 'other: "#procs"', 'other: "#stream"'):
        assert opts in SRC, opts


def test_columns_collapse_to_nothing_not_to_a_stub():
    widths = SRC.split("function setWidths(")[1].split("\n}")[0]
    assert "Math.max(180" not in widths, "180px stub instead of collapsing"
    assert "SHUT" in widths


def test_one_threshold_serves_panes_and_columns():
    assert SRC.count("const SHUT =") == 1
    assert SRC.count("const REOPEN =") == 1


def test_the_threshold_exists_before_the_layout_is_restored():
    """setWidths runs during load; a const used before its declaration is a
    ReferenceError, not a fallback."""
    assert SRC.index("const SHUT =") < SRC.index("setWidths(saved.l")


def test_any_collapsed_pane_reopens_from_its_heading():
    """Wired for the stream alone before, so shutting anything else made it
    unrecoverable without a reload."""
    assert "reopenOnHeading" in SRC
    assert '.pane[data-open="0"] h2{cursor:pointer;}' in SRC


def test_saved_sizes_are_read_back_for_every_column():
    restore = SRC.split('if (saved.l !== undefined')[1].split("} catch")[0]
    for var in ("--hArt", "--hTerm", "--hCredit"):
        assert var in restore, var


def test_a_pane_cannot_be_dragged_below_the_grid():
    """"on the right goes waaay tooo low" -- the sized pane was handed the
    whole column, but the divider and the neighbour's heading live in that
    column too."""
    assert "const room = Math.max(80, col - grip.offsetHeight - shutH);" in SRC
    paint = DRAG.split("const paint = ()")[1].split("const move =")[0]
    assert "Math.min(pending, room)" in paint
    assert "Math.min(pending, col)" not in paint


def test_the_column_clips_whatever_the_arithmetic_gets_wrong():
    assert ".col{display:flex;flex-direction:column;gap:0;min-height:0;min-width:0;" in SRC
    assert "overflow:hidden;}" in SRC


def test_both_directions_use_the_same_gap():
    """The vertical dividers occupy a 6px grid column; the horizontal ones
    were 2px with a gap either side, so they did not match."""
    assert ".griph{cursor:row-resize;position:relative;flex:none;height:6px;}" in SRC
    assert "6px 1fr 6px" in SRC
    assert "gap:var(--gap);min-height:0;min-width:0" not in SRC


def test_a_collapsed_column_still_lights_its_grip():
    assert '#grid[data-l="0"] #gripL:hover::after' in SRC
    assert '#grid[data-r="0"] #gripR:hover::after' in SRC


def test_expanding_a_collapsed_column_does_not_jump():
    """`parseInt(...) || 290` read a collapsed column's 0 as unset, so the
    first pixel of expansion snapped the divider to the default width."""
    widths = SRC.split("function dragGrip(grip, which)")[1].split("\n}")[0]
    assert 'parseInt(cs.getPropertyValue("--wL")) || 290' not in widths
    assert "isNaN(n) ? d : n" in widths
