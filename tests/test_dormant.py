"""The dormant drawer has an entry requirement and an exit requirement.

Entry: nothing that runs may reach it. A drawer that quietly contains a live
dependency is worse than no drawer, because it tells every reader the file is
safe to ignore.

Exit: every file in it must say what it is in one line. The whole point of
moving code here rather than deleting it is that a human can assess the drawer
in a minute and decide. A file with no summary cannot be assessed, so it
cannot be filed.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DORMANT = ROOT / "fleet" / "dormant"


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "fleet" / "bin" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


dormant = _load("dormant")
dormancy = _load("dormancy")


def test_the_drawer_is_not_empty_and_is_all_python():
    assert list(DORMANT.glob("*.py")), "the drawer exists because it has contents"


def test_every_dormant_file_explains_itself_in_one_line():
    """Read from the module's own docstring, so it cannot drift from the file."""
    missing = [r["module"] for r in dormant.build() if not r["summary"]]
    assert missing == [], (
        "these cannot be assessed without opening them: " + ", ".join(missing))


def test_summaries_are_one_line_and_short_enough_to_scan():
    for r in dormant.build():
        assert "\n" not in r["summary"]
        assert len(r["summary"]) <= 120, (
            f"{r['module']}: a summary nobody finishes reading is not a summary")


def test_nothing_that_runs_reaches_the_drawer():
    """The entry requirement, checked rather than trusted. dormancy.py walks
    from every launchd plist, systemd unit, shell script and cron entry."""
    report = dormancy.build()
    awake = {r["path"] for r in report["awake"]}
    live = sorted(p for p in awake if p.startswith("fleet/dormant/"))
    assert live == [], (
        "something that runs reaches these -- move them back to fleet/bin: "
        + ", ".join(live))
