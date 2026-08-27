"""A missed hop on the board must carry the error text, not just the ID.

2026-08-07: agent-comms said `missed: openclaw lap1 (22275->None, error)`
while already_proposed separately held `openclaw [error] [Errno 2] No such
file or directory`. The outcome word is still the split; the errno is why
anyone looking at the card can act.
"""

import importlib.util
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
spec = importlib.util.spec_from_file_location(
    "comms_heartbeat", BIN / "comms-heartbeat.py")
comms = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comms)


HOP = {
    "agent": "openclaw", "lap": 1, "received": 22275, "got": None,
    "ok": False, "outcome": "error",
    "raw": "[error] [Errno 2] No such file or directory: 'openclaw'",
}


def test_an_error_hop_carries_the_errno_on_the_card():
    line = comms.miss_line(HOP)
    assert "openclaw lap1 (22275->None, error" in line
    assert "[Errno 2] No such file or directory" in line
    assert "[error]" not in line


def test_a_wrong_or_silent_hop_stays_a_short_id():
    """Do not inflate every miss with raw prose — only errors hide a cause."""
    wrong = dict(HOP, outcome="wrong", got=22277, raw="I think 22277")
    silent = dict(HOP, outcome="silent", raw="no idea, sorry")
    timeout = dict(HOP, outcome="timeout",
                   raw="[timed out after 150s; no output]")
    assert comms.miss_line(wrong) == "openclaw lap1 (22275->22277, wrong)"
    assert comms.miss_line(silent) == "openclaw lap1 (22275->None, silent)"
    assert comms.miss_line(timeout) == "openclaw lap1 (22275->None, timeout)"


def test_an_error_with_no_raw_still_identifies_the_hop():
    line = comms.miss_line(dict(HOP, raw=""))
    assert line == "openclaw lap1 (22275->None, error)"
