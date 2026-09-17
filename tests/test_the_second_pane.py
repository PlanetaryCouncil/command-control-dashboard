"""Two conversations on one board: this one, and the one doing the work.

Marsita, 2026-09-17: "Meanwhile 2nd panel here for multitasking ---> love it",
against twelve projects that are all real work.

A pane is pinned to a DIRECTORY, not just a session name. Claude Code files
its transcript per working directory, so two conversations in one directory
land in the same folder and `stream.newest()` picks between them by mtime --
the panes would swap contents at random. Different project, different folder,
nothing to disambiguate.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "fleet" / "bin"))

SRC = (REPO / "fleet" / "bin" / "oneview.py").read_text()
SERVER = (REPO / "fleet" / "bin" / "fleet.py").read_text()

import fleet as fleetmod


# ------------------------------------------------------------ the server side
def test_a_bare_project_name_resolves():
    assert fleetmod.workspace("command-control-dashboard") is not None


def test_traversal_is_refused():
    """The browser names a directory, so the server decides what that means."""
    for bad in ("..", "../..", "../../etc", "/etc", "a/b", "..\\..", ""):
        assert fleetmod.workspace(bad) is None, f"{bad!r} was accepted"


def test_a_hidden_directory_is_refused():
    assert fleetmod.workspace(".ssh") is None
    assert fleetmod.workspace(".config") is None


def test_a_project_that_does_not_exist_is_refused():
    assert fleetmod.workspace("definitely-not-a-project-9e3f") is None


def test_a_symlink_out_of_projects_is_refused(tmp_path, monkeypatch):
    """resolve() follows the link, so the check must be on the real location.

    A symlink named like a project would otherwise point the pane -- and the
    tmux session it spawns -- at any directory on the disk.
    """
    projects = tmp_path / "projects"
    projects.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (projects / "sneaky").symlink_to(outside)
    monkeypatch.setattr(fleetmod, "PROJECTS", projects)
    assert fleetmod.workspace("sneaky") is None


def test_a_real_directory_under_projects_is_allowed(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    (projects / "real").mkdir(parents=True)
    monkeypatch.setattr(fleetmod, "PROJECTS", projects)
    assert fleetmod.workspace("real") == (projects / "real").resolve()


def test_the_picker_is_ordered_by_recent_activity(tmp_path, monkeypatch):
    """The project you touched today is the one you want, not whichever
    sorts first alphabetically."""
    import os, time
    projects = tmp_path / "projects"
    for n in ("aaa", "zzz"):
        (projects / n).mkdir(parents=True)
    now = time.time()
    os.utime(projects / "aaa", (now - 9999, now - 9999))
    os.utime(projects / "zzz", (now, now))
    monkeypatch.setattr(fleetmod, "PROJECTS", projects)
    assert fleetmod.workspaces()[0] == "zzz"


def test_hidden_directories_are_not_offered(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    (projects / ".git").mkdir(parents=True)
    (projects / "shown").mkdir()
    monkeypatch.setattr(fleetmod, "PROJECTS", projects)
    assert fleetmod.workspaces() == ["shown"]


def test_the_stream_route_takes_a_workspace():
    assert 'parse_qs(urlparse(self.path).query).get("w", [""])[0]' in SERVER
    assert 'out["workspaces"] = workspaces()' in SERVER


def test_tell_sends_to_the_projects_own_session():
    """Without this the second pane would type into the board conversation."""
    i = SERVER.index('if path == "/api/tell"')
    tell = SERVER[i:SERVER.index('if path == "/api/selfies"', i)]
    assert 'ws = workspace(body.get("w"))' in tell
    assert 'ws.name if ws else "board"' in tell


# -------------------------------------------------------------- the page side
def test_the_pane_exists_with_its_own_box_and_picker():
    for bit in ('id="termpane2"', 'id="tellBox2"', 'id="ws2"', 'id="tell2"'):
        assert bit in SRC, f"{bit} is missing"


def test_the_choice_survives_a_reload():
    assert 'WS_KEY = "pane2.workspace"' in SRC
    assert "localStorage.setItem(WS_KEY" in SRC


def test_storage_failure_does_not_break_the_pane():
    """localStorage throws in a private window."""
    i = SRC.index("function ws2()")
    assert "catch (e) { return \"\"; }" in SRC[i:i + 200]


def test_switching_project_clears_the_old_conversation():
    """Leaving one project's words under another's heading would be a lie."""
    i = SRC.index("function setWs2(")
    fn = SRC[i:SRC.index("\n}", i)]
    assert 'stream2Seen = ""' in fn
    assert "innerHTML" in fn


def test_the_send_carries_the_project():
    i = SRC.index('const form = $("#tell2")')
    fn = SRC[i:SRC.index("})();", i)]
    assert 'JSON.stringify({text, w: ws2()})' in fn


def test_a_failed_send_keeps_your_words():
    i = SRC.index('const form = $("#tell2")')
    fn = SRC[i:SRC.index("})();", i)]
    # the box is only cleared on success
    assert fn.index("if (d.ok){ box.value = \"\"") > fn.index("await r.json()")
    assert "could not send" in fn
