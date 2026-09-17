"""Turning a job off happens in one place: config.json.

Council ran every three hours for weeks and produced 40 consecutive turns of
NOTHING TO ADD -- four agents, two rounds, zero substance. Suspending it by
hand on whichever box it happened to run on is how a fleet ends up with two
answers to "is this on". So `every_seconds: 0` means suspended, and the
generator removes the units instead of writing a timer systemd cannot honour.

Marsita, 2026-09-17: "Collapse / simplify / reduce.. I have real work to do,
not fluffing around admin."
"""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SH = (REPO / "fleet" / "bin" / "apply-config-systemd.sh").read_text()
CONFIG = json.loads((REPO / "fleet" / "config.json").read_text())


def test_a_zero_cadence_removes_the_units():
    assert 'OnUnitActiveSec=0s' in SH
    assert 'rm -f "$UNITS/fleet-$name.timer"' in SH


def test_a_suspended_job_is_disabled_not_just_unlinked():
    """Leaving the timer enabled would resurrect it on the next reboot."""
    assert 'systemctl --user disable --now "fleet-$name.timer"' in SH


def test_the_check_happens_before_anything_is_written():
    """Writing the service and then deleting it would race a running timer."""
    assert SH.index("OnUnitActiveSec=0s") < SH.index('cat > "$UNITS/fleet-$name.service"')


def test_council_is_suspended_and_says_why():
    c = CONFIG["council"]
    assert c["every_seconds"] == 0
    what = c.get("_what", "")
    assert "SUSPENDED" in what
    assert "40" in what, "the number that justified it is not recorded"
    assert "10800" in what, "no way back is written down"


def test_rota_is_the_surviving_proposer_and_slowed_down():
    """Two proposals in fourteen days did not need twenty-four looks a day."""
    assert CONFIG["rota"]["every_seconds"] == 10800


def test_no_other_job_was_suspended_by_accident():
    live = [k for k, v in CONFIG.items()
            if isinstance(v, dict) and v.get("every_seconds") == 0]
    assert live == ["council"], f"unexpectedly suspended: {live}"
