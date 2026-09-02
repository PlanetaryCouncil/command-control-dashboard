"""A vendor spending its allowance must not ring the red bar.

Marsita, 2026-09-02: "Grok running out of credits is routine, don't make it
red." It is weather: it happens on a schedule, it clears on a schedule, and
`eligible()` routes around it without being asked. An alert offering no action
teaches you to stop reading the channel it arrives on -- and that channel is
the same one a real outage uses.

What still shouts: a logged-out vendor (needs hands on a keyboard) and a lost
quorum (the council cannot sit).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))

SRC = (ROOT / "fleet" / "bin" / "quotas.py").read_text()


def test_dry_is_a_warning_not_an_alert():
    branch = SRC.split("    if dry:")[1].split("elif logged_out:")[0]
    assert 'status = "warn"' in branch
    assert 'status = "alert"' not in branch


def test_a_dry_vendor_is_not_something_you_can_act_on():
    assert "needs_you = [a for a in down_scheduled if a not in dry]" in SRC


def test_being_logged_out_still_shouts():
    branch = SRC.split("    elif logged_out:")[1].split("elif")[0]
    assert 'status = "alert"' in branch


def test_losing_quorum_still_shouts():
    """The consequence of everyone being dry at once is a real emergency even
    though each cause on its own is not."""
    assert "needs_you = needs_you or [\"quorum\"]" in SRC
