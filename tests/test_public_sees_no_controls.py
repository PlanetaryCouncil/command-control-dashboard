"""A remote visitor is shown no control they are not allowed to use.

The server already refused them -- /api/kill and /api/build-gate are in
CONTROL_PATHS and 404 for anyone arriving through a proxy. But the buttons
still rendered, so the board offered a stranger a "kill fleet work" button
that did nothing. Safe and confusing is not the same as safe.
"""
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "fleet" / "bin"
sys.path.insert(0, str(BIN))
import oneview  # noqa: E402

ARGS = ("[]", "[]", "tok")
# `termbtn` is not here: the in-page terminal was retired on 2026-09-05 and
# its toggle went with it, but this list kept asking for the button and the
# operator assertion has been failing ever since. A control that no longer
# exists is not a control a remote visitor can be offered.
CONTROLS = ('<button id="kill"', '<button id="bgate"',
            '<button id="convenebtn"')


def test_the_second_panes_send_box_is_local_only():
    """The pane talks to a tmux session on this machine. A remote visitor
    getting the box would be offered a keystroke into the operator's laptop."""
    assert 'id="tellBox2"' not in oneview.page(*ARGS, remote=True)
    assert 'id="tellBox2"' in oneview.page(*ARGS, remote=False)


def test_a_remote_visitor_is_offered_no_controls():
    page = oneview.page(*ARGS, remote=True)
    for c in CONTROLS:
        assert c not in page, f"{c} rendered for a remote visitor"


def test_the_operator_still_gets_every_control():
    page = oneview.page(*ARGS, remote=False)
    for c in CONTROLS:
        assert c in page, f"{c} missing for the operator"


def test_remote_script_tolerates_the_missing_controls():
    """Rendering nothing is only safe if the code that paints them survives
    their absence -- otherwise the first null takes the whole poll down and
    the visitor gets a blank board instead of a read-only one."""
    page = oneview.page(*ARGS, remote=True)
    for guard in ('if (!kb) return;',
                  'if ($("#kill"))',
                  'if ($("#bgate"))'):
        assert guard in page, f"missing null-guard: {guard}"
