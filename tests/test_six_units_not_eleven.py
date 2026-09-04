"""Eleven timers became six, and two of them had been the same command.

Marsita, 2026-09-04, looking at her own org chart: "seriously I have such a
super duper architecture? [...] watchdog = medic = heartbeat = same same [...]
If we could get down to 6 or 7 would be great."

She was right, and it was worse than the chart showed: fleet-pipeline and
fleet-build both ran `pipeline.py run`, so two timers raced for one worktree.

Every collapse here removes a way for two timers to overlap on a 14GB box,
which is the class of bug that pinned six cores for a day on 2026-09-03. The
tests did not shrink; the processes did.
"""

import re
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent / "fleet"
APPLY = (FLEET / "bin" / "apply-config-systemd.sh").read_text()

SEVEN = {"rota", "build", "council", "health", "e2e", "report", "daily"}


def generated() -> set[str]:
    names = set()
    for line in APPLY.splitlines():
        m = re.match(r'\s*unit\s+([a-z0-9-]+)\s', line)
        if m and not line.lstrip().startswith("#"):
            names.add(m.group(1))
    return names


def test_seven_units_are_generated():
    """Six from the collapse, plus `daily` -- the 09:00 Telegram message that
    had been a hand-written unit apply-config knew nothing about, so neither
    machine could be repaired from the repo. It is not merged into `report`:
    one is pushed to a phone at breakfast, the other is a page that waits."""
    assert generated() == SEVEN, generated() ^ SEVEN


def test_all_seven_actually_sit():
    """Writing a unit without enabling it is how the NUC served the board for
    weeks while running none of the fleet."""
    sitting = re.search(r'^SITTING="([^"]+)"', APPLY, re.M).group(1).split()
    assert set(sitting) == SEVEN


def test_the_collapsed_units_are_retired_not_orphaned():
    """A unit no longer generated but still enabled keeps firing from whenever
    apply-config last wrote it. That is how three hand-written fleet-build@
    instances outlived everyone's memory of creating them."""
    retired = re.search(r'^RETIRED="([^"]+)"', APPLY, re.M).group(1).split()
    for gone in ("watchdogs", "board-medic", "heartbeat", "pipeline",
                 "local-voice", "self-improve"):
        assert gone in retired, gone
    assert "fleet-build@$i.timer" in APPLY, "template instances not retired"


def test_no_unit_runs_the_pipeline_twice():
    """fleet-pipeline ran pipeline.py run. backlog.sh ends by running
    pipeline.py run. Two timers, one worktree."""
    live = [l for l in APPLY.splitlines()
            if re.match(r'\s*unit\s', l) and not l.lstrip().startswith("#")]
    assert not [l for l in live if "pipeline.py" in l]
    assert "backlog.sh" in "\n".join(live)


def test_the_wrappers_exist_and_are_executable():
    import os
    for name in ("health.sh", "council-cycle.sh", "report-cycle.sh",
                 "daily-summary.sh"):
        f = FLEET / "bin" / name
        assert f.exists(), name
        assert os.access(f, os.X_OK), f"{name} is not executable"


def test_health_stamps_before_it_runs():
    """A job that hangs must not start again on the next tick -- that is the
    exact shape that pinned six cores."""
    src = (FLEET / "bin" / "health.sh").read_text()
    body = src[src.index("due()"):src.index("# Every tick")]
    assert body.index("touch \"$stamp\"") < body.index('"$@"')


def test_health_covers_all_three_it_replaced():
    src = (FLEET / "bin" / "health.sh").read_text()
    for job in ("board-medic.sh", "run-watchdogs.sh", "comms-heartbeat.py"):
        assert job in src, job


def test_council_still_improves_itself_daily():
    src = (FLEET / "bin" / "council-cycle.sh").read_text()
    assert "council.py" in src
    assert "run-cycle.sh" in src
    assert "date -u +%Y-%m-%d" in src, "self-improve must be once a day"


def test_report_carries_the_local_voice():
    src = (FLEET / "bin" / "report-cycle.sh").read_text()
    assert "localvoice.py" in src
    assert "publish-report.sh" in src


def test_the_fleet_merges_without_a_human():
    """Already true before the collapse, and named here so it cannot quietly
    revert: land() runs unconditionally on an approved branch."""
    src = (FLEET / "bin" / "pipeline.py").read_text()
    assert re.search(r'^\s+land\(r\)\s*$', src, re.M), "land() not called"
    assert "No human in the loop" in src
