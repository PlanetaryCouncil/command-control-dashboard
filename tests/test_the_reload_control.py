"""The board never reloads itself, but it stops pretending to be current.

"live reload is like asking for trouble, easier to simply reload"
(2026-09-16), and then "CTRL +R should be some funky futuristic icon ---->
so I know how to reload" (2026-09-17). Both at once: a visible button, so the
gesture is discoverable instead of remembered, and a glow when this tab is
behind the server -- but never an automatic refresh.

The board restarts every time it is improved, and an already-open tab keeps
showing the old page. Marsita has judged new work by a stale screen more than
once.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "fleet" / "bin"))

SRC = (REPO / "fleet" / "bin" / "oneview.py").read_text()
SERVER = (REPO / "fleet" / "bin" / "fleet.py").read_text()

import fleet as fleetmod
import oneview


def test_the_button_is_always_there():
    """A keystroke you have to be reminded of is not a control."""
    page = oneview.page("[]", "[]", "tok", remote=False, build="abc")
    assert 'id="rebtn"' in page


def test_a_remote_visitor_gets_it_too():
    """Reloading is not a control over the machine; it is a control over your
    own browser, and a stale public board is just as wrong."""
    assert 'id="rebtn"' in oneview.page("[]", "[]", "", remote=True, build="abc")


def test_the_stamp_reaches_the_page():
    page = oneview.page("[]", "[]", "tok", remote=False, build="deadbeef")
    assert 'const BUILD  = "deadbeef"' in page


def test_the_stamp_moves_when_the_page_code_moves(tmp_path, monkeypatch):
    """Otherwise the glow never fires and the whole thing is decoration."""
    fleetdir = tmp_path / "fleet" / "bin"
    fleetdir.mkdir(parents=True)
    for n in ("oneview.py", "nav.py", "fleet.py"):
        (fleetdir / n).write_text("x")
    monkeypatch.setattr(fleetmod, "FLEET", tmp_path / "fleet")
    first = fleetmod.build_stamp()
    (fleetdir / "nav.py").write_text("y")          # a real edit
    assert fleetmod.build_stamp() != first


def test_the_stamp_is_stable_when_nothing_changed():
    """A stamp that moved on its own would cry wolf every five seconds."""
    assert fleetmod.build_stamp() == fleetmod.build_stamp()


def test_the_endpoint_answers_without_rendering():
    """Polled by every open tab: three stat() calls, no render, no git."""
    i = SERVER.index('if path == "/api/build"')
    route = SERVER[i:SERVER.index("return", i)]
    assert "build_stamp()" in route
    assert "oneview.page" not in route


def test_the_badge_is_never_cleared():
    """Once the server has moved on, this tab cannot become current again by
    any means except reloading. A badge that flickered off would say
    otherwise."""
    i = SRC.index("function wireReload()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert 'b.dataset.stale = "1"' in fn
    assert "delete b.dataset.stale" not in fn
    assert 'dataset.stale = "0"' not in fn


def test_it_never_reloads_by_itself():
    """The whole bargain. location.reload() may only follow a click or a key."""
    i = SRC.index("function wireReload()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    for call in re.finditer(r"location\.reload\(\)", fn):
        before = fn[:call.start()]
        assert 'addEventListener("click"' in before or 'e.key !== "r"' in before, \
            "a reload that no gesture asked for"
    assert "setInterval(check" in fn      # the poll only checks
    poll = fn[fn.index("const check ="):fn.index("check();")]
    assert "location.reload" not in poll


def test_r_reloads_but_not_while_typing():
    i = SRC.index("function wireReload()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert 'e.key !== "r"' in fn
    assert "typingNow()" in fn
    assert fn.index("typingNow()") < fn.index('e.key !== "r"') or "||" in fn


def test_a_board_mid_restart_is_not_an_error():
    """The poll runs straight through a restart, which is exactly when the
    fetch fails."""
    i = SRC.index("function wireReload()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert "catch (e) {}" in fn


def test_the_glow_survives_reduced_motion():
    """The spin is a nicety; the warning is not."""
    m = re.search(r"@media \(prefers-reduced-motion:reduce\)\{([^@]*)\}", SRC)
    assert m and "animation:none" in m.group(1)
    assert 'box-shadow' in SRC[SRC.index('#rebtn[data-stale="1"]'):][:300]
