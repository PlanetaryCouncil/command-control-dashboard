"""A repair that only knows one machine's init system is not a repair.

revive-heartbeat.sh exists because detection without repair is useless: on
2026-08-04 agent-comms recorded nothing for 19 hours while the board reported
green. The fix restarted the job -- via launchd, because Gaia is a Mac.

Both machines run this script. On 2026-09-03 the NUC's agent-comms had been
dead for 31 hours, and the hourly watchdog had been logging

    [fleet] agent-comms 114555s stale — kickstart of
    re.genesis.comms-heartbeat FAILED

once an hour the whole time. Detection worked perfectly. The repair called
`launchctl` on a systemd box. The exact failure this file was written to
prevent, reintroduced by assuming one machine's scheduler.
"""
from pathlib import Path

SH = (Path(__file__).resolve().parent.parent
      / "fleet" / "bin" / "revive-heartbeat.sh").read_text()


def test_it_knows_both_names_for_one_job():
    assert 'LABEL="re.genesis.comms-heartbeat"' in SH   # launchd, Gaia
    assert 'UNIT="fleet-heartbeat.service"' in SH       # systemd, NUC


def test_it_can_restart_under_systemd():
    assert 'systemctl --user restart "$UNIT"' in SH


def test_it_checks_the_tool_exists_before_using_it():
    """`launchctl kickstart` failing and launchctl being absent are different
    facts, and only one of them means the restart did not happen."""
    assert "command -v launchctl" in SH
    assert "command -v systemctl" in SH


def test_it_reports_which_scheduler_actually_did_it():
    assert 'kickstarted $WHO' in SH
    assert "no scheduler could restart it" in SH


def test_it_does_not_branch_on_the_operating_system():
    """uname would put a third arrangement -- a cron, a container -- into
    whichever branch it resembles least."""
    code = "\n".join(l for l in SH.splitlines() if not l.lstrip().startswith("#"))
    assert "uname" not in code
