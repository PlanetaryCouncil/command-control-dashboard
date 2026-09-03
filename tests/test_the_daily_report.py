"""A quiet failure has to become a loud one somewhere.

On 2026-09-03 it emerged that the fleet had built nothing for two days, the
comms heartbeat had been dead for 31 hours, and the watchdog tier had never
run on the NUC since it was re-cloned. Three failures. Each was visible in
some log. None was visible anywhere a person looks.

So: one page, counted from the files the fleet writes while working, in the
three formats its three audiences need -- a person in a terminal, a person in
a browser, and a program.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))
import report                                              # noqa: E402

D = report.collect(hours=24)


def test_it_counts_rather_than_narrates():
    assert isinstance(D["commits"]["count"], int)
    assert isinstance(D["events"]["count"], int)
    assert D["window_hours"] == 24


def test_an_empty_day_says_so_instead_of_going_quiet():
    """A report that only appears when things went well is an advert."""
    empty = dict(D, commits={"count": 0, "list": []}, needs_you=[])
    assert "Nothing was merged" in report._headline(empty)
    assert "nothing" in report.as_text(empty).lower()
    assert "Nothing." in report.as_markdown(empty)


def test_the_three_renderings_carry_the_same_facts():
    for body in (report.as_text(D), report.as_markdown(D), report.as_html(D)):
        assert str(D["commits"]["count"]) in body
        assert "partnership" in body.lower()


def test_the_json_is_actually_json():
    assert json.loads(json.dumps(D))["window_hours"] == 24


def test_every_site_is_paired_with_the_org_that_builds_it():
    """Verified against the GitHub API before being written down, not copied
    from a note (2026-09-03)."""
    seen = {p["site"]: p["github"] for p in D["partnership"]}
    assert seen["PlanetaryCouncil.org"] == "https://github.com/PlanetaryCouncil"
    assert seen["IndependentTribunal.org"] == "https://github.com/independenttribunal"
    assert seen["BaseX.com"] == "https://github.com/basexhq"


def test_each_site_is_given_a_job():
    roles = {p["role"] for p in D["partnership"]}
    assert roles == {"decides", "contests", "deploys"}


def test_the_pairing_survives_into_every_format():
    for body in (report.as_markdown(D), report.as_html(D)):
        for org in ("PlanetaryCouncil", "independenttribunal", "basexhq"):
            assert org in body, org


def test_publishing_writes_an_index_not_only_a_named_file(tmp_path):
    """A Pages directory whose only entry is report.html 404s at its own
    address."""
    written = {f.name for f in report.publish(D, tmp_path)}
    assert {"index.html", "report.html", "report.json", "report.md"} <= written
    assert json.loads((tmp_path / "report.json").read_text())["window_hours"] == 24


def test_what_asked_for_a_person_is_the_headline():
    """needs_you is the fleet saying it is stuck; it must not be buried."""
    for body in (report.as_text(D), report.as_markdown(D), report.as_html(D)):
        assert "person" in body.lower() or "needs you" in body.lower()


def test_the_board_serves_it_to_everyone():
    """A summary only the operator can read never gets checked."""
    src = (ROOT / "fleet" / "bin" / "fleet.py").read_text()
    assert '"/report", "/report.json", "/report.md"' in src
    assert "/report" not in src.split("CONTROL_PATHS = frozenset({")[1].split("})")[0]


def test_the_report_lives_in_the_repo_it_describes():
    """Marsita, 2026-09-03: "report of the dashboard belongs to dashboard",
    said after I offered to put it on the main site or in a new repo -- two
    answers to a question nobody had asked."""
    sh = (ROOT / "fleet" / "bin" / "publish-report.sh").read_text()
    assert 'OUT="$REPO/docs/report"' in sh
    assert "planetarycouncil.org" not in sh


def test_the_first_run_actually_publishes():
    """git diff does not see untracked files, so the run where every file is
    new reported "unchanged" and published nothing."""
    sh = (ROOT / "fleet" / "bin" / "publish-report.sh").read_text()
    assert "git add -A docs/report" in sh
    assert sh.index("git add -A docs/report") < sh.index("git diff --cached")


def test_a_timestamp_alone_is_not_news():
    """A daily job that commits unconditionally turns the history into a
    heartbeat and buries the days something happened."""
    sh = (ROOT / "fleet" / "bin" / "publish-report.sh").read_text()
    assert 'CHANGED' in sh and '-le 8' in sh


def test_it_is_scheduled_on_both_machines():
    """A summary that is written but never scheduled is a summary of the one
    day someone remembered to run it."""
    systemd = (ROOT / "fleet" / "bin" / "apply-config-systemd.sh").read_text()
    launchd = (ROOT / "fleet" / "bin" / "apply-config.sh").read_text()
    assert "publish-report.sh" in systemd and "publish-report.sh" in launchd
    assert "report" in systemd.split('SITTING="')[1].split('"')[0]


def test_the_schedule_is_configured_not_hard_coded():
    cfg = json.loads((ROOT / "fleet" / "config.json").read_text())
    assert cfg["report"]["at_hour"] == 19
    assert cfg["report"]["_what"], "a schedule without a reason gets deleted"
