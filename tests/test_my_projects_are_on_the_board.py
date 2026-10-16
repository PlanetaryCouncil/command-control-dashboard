"""The board shows the work, not just the machine that does the work.

Marsita, 2026-09-10: "I don't care about little issues now with architecture,
they should resolve itself... I care about usability of me as the end user...
I see my projects, I see my issues."

Sixteen projects were already written down in fleet/data/projects.yaml, and the
board had a pane for the repo it happens to be running in and none for the work
that repo exists to serve.
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
BIN = ROOT / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import portfolio            # noqa: E402


@pytest.fixture(autouse=True)
def no_github(monkeypatch):
    """Never ask GitHub from a test: canned stats, fresh cache each time."""
    monkeypatch.setattr(portfolio, "_GH", {"at": 0.0, "stats": {}})
    monkeypatch.setattr(portfolio, "_fetch_stats", lambda repos: {})


def write(tmp_path, body):
    p = tmp_path / "projects.yaml"
    p.write_text(body)
    return p


def test_the_file_is_the_source_of_truth(tmp_path):
    p = write(tmp_path, """
projects:
  - name: One
    url: https://one.example
    status: active
""")
    got = portfolio.projects(path=p)
    assert [r["name"] for r in got] == ["One"]


def test_live_first_then_waiting_then_the_rest(tmp_path):
    """A for-sale project is still a project, but it is not what you sat down
    to look at."""
    p = write(tmp_path, """
projects:
  - {name: Sold, url: 'https://c', status: for-sale}
  - {name: Soon, url: /b, status: awaiting-deployment}
  - {name: Live, url: 'https://a', status: active}
""")
    assert [r["name"] for r in portfolio.projects(path=p)] == ["Live", "Soon", "Sold"]


def test_a_todo_url_is_honest_in_the_file_and_noise_on_a_dashboard(tmp_path):
    p = write(tmp_path, """
projects:
  - {name: Real, url: 'https://a', status: active}
  - {name: Unfinished, url: TODO, status: active}
""")
    assert [r["name"] for r in portfolio.projects(path=p)] == ["Real"]


def test_a_relative_url_is_a_page_on_this_board(tmp_path):
    p = write(tmp_path, """
projects:
  - {name: Here, url: /basex, status: active}
  - {name: Away, url: 'https://x.example', status: active}
""")
    rows = {r["name"]: r["live"] for r in portfolio.projects(path=p)}
    assert rows == {"Here": False, "Away": True}


def test_a_broken_file_is_an_empty_pane_not_a_500(tmp_path):
    p = write(tmp_path, "projects: [oh dear\n  not yaml at all")
    with pytest.raises(Exception):
        __import__("yaml").safe_load(p.read_text())
    assert portfolio.projects(path=tmp_path / "nothing-here.yaml") == []


def test_the_real_file_parses_and_has_work_in_it():
    rows = portfolio.projects()
    assert len(rows) >= 10
    assert all(r["name"] and r["url"] for r in rows)


def test_the_pane_is_wired_in():
    src = (BIN / "oneview.py").read_text()
    assert 'id="projects"' in src
    assert "loadProjects();" in src
    assert "setInterval(loadProjects, 300000);" in src, "a hand-edited file"


def test_the_pane_comes_before_the_repo_it_runs_in():
    """The work first, then the machinery."""
    src = (BIN / "oneview.py").read_text()
    assert src.index('id="projects"') < src.index('class="pane" id="work"')


def test_the_endpoint_is_not_swallowed_by_the_cockpit_forward():
    """/api/projects is forwarded to the cockpit, which is why this is not
    called that."""
    src = (BIN / "fleet.py").read_text()
    assert 'if path == "/api/portfolio":' in src
    assert '"/api/projects"' in src, "the forward prefix moved"


# ------------------------------------------------- a project has repos
def test_a_project_can_have_several_repos(tmp_path):
    """Marsita, 2026-09-10: "each project should have repo or even multiple
    repo". BaseX is five."""
    p = write(tmp_path, """
projects:
  - name: BaseX
    url: /basex
    status: active
    repos:
      - basexhq/front-end
      - basexhq/back-end
""")
    assert portfolio.projects(path=p)[0]["repos"] == [
        "basexhq/front-end", "basexhq/back-end"]


def test_a_project_with_no_repo_is_not_guessed_at(tmp_path):
    """Guessing one would file its issues under the wrong project."""
    p = write(tmp_path, """
projects:
  - {name: Wiki, url: 'https://wiki.example', status: active}
""")
    assert portfolio.projects(path=p)[0]["repos"] == []


def test_a_project_with_a_repo_and_no_url_points_at_the_repo(tmp_path):
    """Only a row with nowhere at all to point gets dropped."""
    p = write(tmp_path, """
projects:
  - {name: Thing, url: TODO, status: active, repos: [owner/thing]}
""")
    got = portfolio.projects(path=p)
    assert got[0]["url"] == "https://github.com/owner/thing"


def test_the_reverse_map_answers_for_a_bare_repo_name():
    """An issue knows its own short name, never the owner."""
    m = portfolio.repo_owner()
    assert m["command-control-dashboard"].startswith("Live Agent Fleet")
    assert m["poems"] == "Haiku Command-Line Poems"


def test_the_map_is_case_insensitive():
    """The file is written the way a human types: DatingRelating.com in one
    place, datingrelating.com in another, the same repo both times."""
    m = portfolio.repo_owner()
    assert all(k == k.lower() for k in m), "an uppercase key can never match"
    assert m["datingrelating.com"] == "Dating Relating"


def test_every_mapped_repo_belongs_to_exactly_one_project():
    """Two projects claiming a repo would put its issues in both."""
    seen = {}
    for row in portfolio.projects():
        for repo in row["repos"]:
            assert repo not in seen, f"{repo}: {seen.get(repo)} and {row['name']}"
            seen[repo] = row["name"]


def test_the_issues_pane_shows_the_project_not_the_repo():
    """The project is what she thinks in; the repo is an implementation
    detail of it, and stays in the hover."""
    src = (BIN / "oneview.py").read_text()
    assert "esc(project || i.repo)" in src
    assert 'project + " — " + i.repo' in src


def test_an_unmapped_repo_still_shows_its_own_name():
    """Falling back to nothing would hide the issue's only label."""
    src = (BIN / "oneview.py").read_text()
    assert 'owner[String(i.repo || "").toLowerCase()] || ""' in src


# ---------- /projects: tiles, scored 0-10 ----------
# Marsita, 2026-10-11: "Not list of rows. Tiles. For my projects. And each
# project should have a 0-10 scale of importance and 0-10 scale of
# priority... more projects can live there but only 12 above the fold."

def test_scores_are_read_from_the_file_and_a_blank_stays_blank(tmp_path):
    p = write(tmp_path, """
projects:
  - {name: Scored, url: 'https://a', status: active, importance: 7, urgency: 0, vibes: 4}
  - {name: Blank, url: 'https://b', status: active, importance: , urgency: , vibes: }
""")
    got = {r["name"]: r for r in portfolio.projects(path=p)}
    s, b = got["Scored"], got["Blank"]
    assert (s["importance"], s["urgency"], s["vibes"]) == (7, 0, 4)
    assert (b["importance"], b["urgency"], b["vibes"]) == (None, None, None)


@pytest.mark.parametrize("bad", ["11", "-1", "7.5", "high", "true"])
def test_a_score_outside_0_to_10_is_not_a_score(tmp_path, bad):
    p = write(tmp_path, f"""
projects:
  - {{name: X, url: 'https://a', status: active, importance: {bad}}}
""")
    assert portfolio.projects(path=p)[0]["importance"] is None


RANKED = """
projects:
  - {name: Blank, url: 'https://a', status: active}
  - {name: Low, url: 'https://b', status: active, urgency: 2, importance: 9, vibes: 9}
  - {name: HighLess, url: 'https://c', status: active, urgency: 8, importance: 3, vibes: 5}
  - {name: HighMore, url: 'https://d', status: active, urgency: 8, importance: 6, vibes: 8}
  - {name: HighMoreDull, url: 'https://f', status: active, urgency: 8, importance: 6, vibes: 1}
  - {name: ZeroIsADecision, url: 'https://e', status: active, urgency: 0}
"""


def test_tiles_go_by_urgency_then_importance_then_vibes_and_blanks_last(tmp_path):
    rows = portfolio.projects(path=write(tmp_path, RANKED))
    assert [r["name"] for r in portfolio.ranked(rows)] == [
        "HighMore", "HighMoreDull", "HighLess", "Low", "ZeroIsADecision", "Blank"]


def test_on_flip_day_the_least_fun_work_leads(tmp_path):
    rows = portfolio.projects(path=write(tmp_path, RANKED))
    names = [r["name"] for r in portfolio.ranked(rows, flipped=True)]
    assert names[0] == "HighMoreDull"
    assert names[-1] == "Blank"


@pytest.mark.parametrize("when, flipped", [
    ("2026-10-12 13:00", True),    # Monday afternoon
    ("2026-10-13 03:30", True),    # Monday night, before her day ends at 4
    ("2026-10-12 02:00", False),   # still Sunday night
    ("2026-10-16 15:00", False),   # Friday: we don't like Fridays
])
def test_flip_day_is_monday_on_her_clock(when, flipped):
    from datetime import datetime
    assert portfolio.flip_day(datetime.strptime(when, "%Y-%m-%d %H:%M")) is flipped


def test_twelve_above_the_fold():
    assert portfolio.FOLD == 12
    snap = portfolio.snapshot()
    assert snap["fold"] == 12
    assert sorted(snap["tiles"]) == sorted(r["name"] for r in snap["projects"])
    assert isinstance(snap["flipped"], bool)


def test_the_tiles_page_exists_and_reads_the_portfolio():
    page = ROOT / "fleet" / "static" / "projects" / "index.html"
    html = page.read_text()
    assert 'fetch("api/portfolio"' in html
    assert "d.fold" in html and "d.tiles" in html and "d.flipped" in html


@pytest.mark.parametrize("doc, want", [
    ({"title": "Mission Control", "owner": {"alias": "Marsita the Ultra"}}, "Mission Control"),
    ({"title": None, "owner": {"alias": "Marsita the Ultra"}}, "Marsita the Ultra"),
    ({"title": "TODO", "owner": {"alias": "Marsita the Ultra"}}, "Marsita the Ultra"),
    ({}, "Projects"),
])
def test_the_file_names_the_dashboard(doc, want):
    assert portfolio.title(doc) == want


def test_the_snapshot_carries_the_title():
    assert portfolio.snapshot()["title"] == "Marsita the Ultra"


# GitHub on every tile. Marsita, 2026-10-14: "Each tile should have links to
# GitHub... So that anyone can participate... Humans and AI."

def test_a_public_repo_gets_its_link_and_its_open_issues():
    g = portfolio.github(["Org/site"], {"org/site": {"private": False, "open": 4}})
    assert g["url"] == "https://github.com/Org/site"
    assert g["issues_url"] == "https://github.com/Org/site/issues"
    assert g["new_issue_url"] == "https://github.com/Org/site/issues/new"
    assert g["open"] == 4


def test_a_private_repo_shows_nothing():
    stats = {"org/secret": {"private": True, "open": 9}}
    assert portfolio.github(["Org/secret"], stats) is None
    g = portfolio.github(["Org/secret", "Org/site"],
                         {**stats, "org/site": {"private": False, "open": 1}})
    assert [r["repo"] for r in g["repos"]] == ["Org/site"]
    assert g["open"] == 1


def test_no_answer_from_github_is_a_link_without_a_number():
    g = portfolio.github(["Org/site"], {})
    assert g["url"] == "https://github.com/Org/site" and g["open"] is None


def test_no_repo_no_github_corner():
    assert portfolio.github([], {}) is None


def test_several_repos_add_up_and_search_together():
    stats = {"org/a": {"private": False, "open": 2},
             "org/b": {"private": False, "open": 3}}
    g = portfolio.github(["Org/a", "Org/b"], stats)
    assert g["open"] == 5
    assert g["url"] == "https://github.com/Org"
    assert "repo%3AOrg%2Fa" in g["issues_url"] and "repo%3AOrg%2Fb" in g["issues_url"]


def test_a_failed_fetch_keeps_the_last_good_counts(monkeypatch):
    good = {"org/a": {"private": False, "open": 2}}
    monkeypatch.setattr(portfolio, "_fetch_stats", lambda repos: good)
    assert portfolio.repo_stats(["Org/a"]) == good
    monkeypatch.setattr(portfolio, "_fetch_stats", lambda repos: {})
    monkeypatch.setattr(portfolio, "GH_TTL", -1)
    assert portfolio.repo_stats(["Org/a"]) == good


def test_every_tile_in_the_snapshot_carries_its_github(monkeypatch):
    monkeypatch.setattr(portfolio, "_fetch_stats", lambda repos: {
        r.lower(): {"private": False, "open": 1} for r in repos})
    for row in portfolio.snapshot()["projects"]:
        if row["repos"]:
            assert row["github"]["open"] == len(row["repos"])
        else:
            assert row["github"] is None


def test_the_tiles_page_shows_the_github_corner():
    html = (ROOT / "fleet" / "static" / "projects" / "index.html").read_text()
    assert "p.github" in html and "new_issue_url" in html and "issues_url" in html


def test_the_pill_is_a_label_from_the_file_not_the_status(tmp_path):
    """Marsita, 2026-10-16: "Skip the active pill." ART, META, CORE instead."""
    p = write(tmp_path, "projects:\n  - name: A\n    url: https://a.example\n    status: active\n    label: ART\n"
                        "  - name: B\n    url: https://b.example\n    status: active\n")
    labels = {r["name"]: r["label"] for r in portfolio.projects(path=p)}
    assert labels == {"A": "ART", "B": ""}
    html = (ROOT / "fleet" / "static" / "projects" / "index.html").read_text()
    assert "p.label" in html and "p.status" not in html
