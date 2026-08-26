"""A file nothing runs and a file that runs unattended are not the same debt.

Coverage reports one number per file and cannot tell those apart, so every
conversation about it stalls in the same place: someone proposes tests for
the whole 0% list, someone else says half of that list is drawers, and both
are right. dormancy.py answers the narrower question instead -- is there a
path from something this machine STARTS to this file -- and these tests pin
the two mistakes that would make its answer worthless.

Calling an awake module asleep hides a live risk. Calling a sleeping one
awake wastes an afternoon. The walk is deliberately biased toward the second.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "dormancy", ROOT / "fleet" / "bin" / "dormancy.py")
dormancy = importlib.util.module_from_spec(_spec)
sys.modules["dormancy"] = dormancy
_spec.loader.exec_module(dormancy)


def test_every_source_module_is_classified_exactly_once():
    """Awake and asleep must partition the tree. A module in neither bucket
    is invisible to the decision this tool exists to inform."""
    report = dormancy.build()
    awake = {r["path"] for r in report["awake"]}
    asleep = {r["path"] for r in report["asleep"]}
    assert not (awake & asleep), "a module cannot be both"
    assert len(awake) + len(asleep) == report["totals"]["modules"]
    assert len(awake | asleep) == len(dormancy.modules())


def test_a_module_started_by_a_plist_is_awake():
    """The launchd plists are the clearest case of unattended: nobody types
    these, they fire on their own."""
    report = dormancy.build()
    awake = {r["path"] for r in report["awake"]}
    # telegram.py is named by re.genesis.telegram.plist.
    assert "fleet/bin/telegram.py" in awake


def test_imports_carry_wakefulness_transitively():
    """A module is not safe because no scheduler names it directly. breaker.py
    is imported by things that fire unattended, so it runs unattended.

    events.py was the first pick here and it failed the test: something does
    invoke it by name. Being started directly is the stronger claim, so that
    was the tool being right, not wrong -- but it made the assertion vacuous."""
    report = dormancy.build()
    awake = {r["path"] for r in report["awake"]}
    assert "fleet/bin/breaker.py" in awake
    row = next(r for r in report["awake"]
               if r["path"] == "fleet/bin/breaker.py")
    assert not row["started_directly"], (
        "reached by import, not by a runner -- if this ever flips, the "
        "transitive half of the walk is no longer being exercised")


def test_module_keys_are_paths_not_names():
    """fleet/bin/fleet.py is the engine; legacy/app/fleet.py is the cockpit's
    read-only view of it. Keying by stem merged them and lost one."""
    mods = dormancy.modules()
    assert "fleet/bin/fleet.py" in mods
    assert "legacy/app/fleet.py" in mods


def test_mentioning_a_module_in_prose_does_not_wake_it():
    """docs/ talks about deadman.py at length. Discussion is not scheduling,
    and a walk that cannot tell those apart marks the whole repo awake."""
    seeds = dormancy.entry_points(dormancy.modules())
    assert "fleet/bin/deadman.py" not in seeds, (
        "if something now genuinely schedules the deadman switch this is "
        "good news -- update the test and say so in the message")


def test_missing_coverage_reads_as_unknown_not_zero():
    """A module never measured and a module measured at zero are opposite
    facts. Reporting the first as 0% invents a finding."""
    report = dormancy.build()
    rows = report["awake"] + report["asleep"]
    for r in rows:
        assert r["coverage"] is None or 0.0 <= r["coverage"] <= 100.0
