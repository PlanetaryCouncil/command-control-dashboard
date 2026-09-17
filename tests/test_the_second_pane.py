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


# ------------------------------------------- one keyboard, two panes, 1-6
def test_pane_two_is_offset_by_three():
    """Marsita, 2026-09-17: "For pane 2 we will use 4 5 (possibly 6)"."""
    assert "PANE2_OFFSET = 3" in SRC


def test_pane_two_shows_the_offset_number_but_sends_the_agents_own():
    """The agent in that pane offered 1/2/3. Answering with 4 would be
    answering a question it never asked."""
    i = SRC.index("async function loadStream2()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert 'data-pick="${esc(pk.n)}"' in fn          # sent: the agent's number
    assert 'PANE2_OFFSET + Number(pk.n)' in fn       # shown: the key


def test_pane_one_keys_are_its_own_numbers():
    i = SRC.index("async function loadStream()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert 'data-key="${esc(p.n)}"' in fn


def test_a_digit_typed_into_a_box_is_just_a_digit():
    """"Outside of the text area, obviously." Hijacking every digit would make
    the compose boxes unusable for anything containing a number."""
    assert "function typingNow()" in SRC
    i = SRC.index("function typingNow()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    for tag in ('"TEXTAREA"', '"INPUT"', '"SELECT"'):
        assert tag in fn, f"{tag} does not stand the listener down"
    assert "isContentEditable" in fn


def test_the_listener_checks_focus_before_acting():
    i = SRC.index('addEventListener("keydown", e => {\n  if (e.metaKey')
    fn = SRC[i:SRC.index("});", i)]
    assert fn.index("typingNow()") < fn.index("b.click()")


def test_modifiers_are_left_to_the_browser():
    """cmd+1 switches tabs; that is not ours to take."""
    i = SRC.index('addEventListener("keydown", e => {\n  if (e.metaKey')
    fn = SRC[i:SRC.index("});", i)]
    for m in ("e.metaKey", "e.ctrlKey", "e.altKey", "e.shiftKey"):
        assert m in fn


def test_only_one_to_six_are_taken():
    i = SRC.index('addEventListener("keydown", e => {\n  if (e.metaKey')
    fn = SRC[i:SRC.index("});", i)]
    assert "/^[1-6]$/" in fn


def test_a_disabled_option_cannot_be_pressed():
    """An answered menu is a decision taken, and a keystroke is exactly how
    you would answer it again by accident."""
    i = SRC.index('addEventListener("keydown", e => {\n  if (e.metaKey')
    fn = SRC[i:SRC.index("});", i)]
    assert ":not([disabled])" in fn


def test_clicking_in_pane_two_disables_that_panes_set_only():
    i = SRC.index('const form = $("#tell2")')
    fn = SRC[i:SRC.index("})();", i)]
    assert 'p2.querySelectorAll(".pick")' in fn


# --------------------------------------------------------- side by side, not stacked
def test_the_two_panes_share_a_row():
    """Stacked, the second pane pushed the first off the screen and only one
    could be watched. Marsita, 2026-09-17: "vertical split... And 2 different
    panes for multitasking"."""
    assert 'class="split" id="split"' in SRC
    assert "#termpane" in SRC and "#termpane2" in SRC
    # the grip sits BETWEEN them in the markup
    i, g, j = (SRC.index('id="termpane"'), SRC.index('id="gripSplit"'),
               SRC.index('id="termpane2"'))
    assert i < g < j


def test_the_split_is_a_grid_with_a_draggable_right_column():
    assert "grid-template-columns:1fr 6px var(--wPane2,1fr)" in SRC


def test_neither_pane_can_be_squeezed_to_nothing():
    """Dragging past the end used to leave a pane at zero width with no way
    back without clearing storage."""
    i = SRC.index("function dragSplit(")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert "Math.max(MIN, Math.min(px, total - MIN))" in fn
    assert "MIN = 220" in fn


def test_both_panes_can_hold_a_long_line():
    """A long unbroken tool line in one pane would shove the other off the
    grid without min-width:0."""
    assert ".split > .pane{min-width:0;min-height:0;}" in SRC


def test_the_width_is_remembered_but_written_once_per_drag():
    """A JSON parse and a synchronous write per pixel is what made the other
    dividers feel like treacle."""
    i = SRC.index("function dragSplit(")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert "saved.wPane2" in fn
    assert fn.index('addEventListener("pointerup"') < fn.index("localStorage.setItem")
    move = fn[fn.index('addEventListener("pointermove"'):
              fn.index('addEventListener("pointerup"')]
    assert "localStorage" not in move


def test_a_collapsed_pane_gives_its_column_away():
    assert '.split:has(#termpane[data-open="0"])' in SRC
    assert '.split:has(#termpane2[data-open="0"])' in SRC


def test_the_second_pane_opens_with_the_first():
    """Side by side, a collapsed pane is an empty column, and nobody asked for
    two panes in order to look at one."""
    assert 'setPaneOpen($("#termpane2"), true)' in SRC
    assert "termpane2Open" in SRC, "no way to shut it on purpose"


# ------------------------------------------- the two panes must differ
def test_the_server_says_which_repo_is_pane_one():
    assert 'out["this_repo"] = FLEET.parent.name' in SERVER


def test_pane_two_never_defaults_to_pane_ones_repo():
    """Both panes would read the same transcript folder and print the same
    conversation -- two panes showing one thing, which is worse than one
    pane because it looks like it works. Marsita, 2026-09-17: "One tab needs
    to be different for full multitasking"."""
    i = SRC.index("function fillPicker(")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert "names.find(n => n !== thisRepo)" in fn
    assert "setWs2(names[0])" not in fn, "still defaults to the newest, which is this repo"


def test_choosing_pane_ones_repo_says_so_instead_of_mirroring():
    """Silently showing the same conversation twice is the failure that is
    hard to notice."""
    i = SRC.index("async function loadStream2()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert "w === d.this_repo" in fn
    assert "left pane" in fn
    # and it returns rather than rendering the mirrored lines
    assert fn.index("w === d.this_repo") < fn.index("body.innerHTML = lines.map")
