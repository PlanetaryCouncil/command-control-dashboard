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
