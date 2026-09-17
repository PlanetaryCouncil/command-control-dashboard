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


def test_a_remote_visitor_does_not_get_it():
    """A deliberate trade, not an oversight.

    The pill sits in the compose row because that is where Marsita looks, and
    the compose row is local-only -- nothing on a public page may put a
    keystroke into this machine. A remote visitor therefore has no reload
    button and must use their own browser's.

    Reloading is a browser control rather than a control over the machine, so
    a remote pill would be harmless; it would just need somewhere to live that
    is not the compose row. Worth doing if a stale public board ever matters.
    """
    assert 'id="rebtn"' not in oneview.page("[]", "[]", "", remote=True, build="abc")
    assert 'id="tellBox"' not in oneview.page("[]", "[]", "", remote=True, build="abc")


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


def test_the_pill_is_reachable_on_a_laptop_screen():
    """It began in the right-hand group -- nowrap, already holding convene,
    the nav, a clock, a goal and an alarm -- and rendered at x=1740 in a
    1704px window. Off the edge, unclickable by anyone. The handler was fine;
    the button was not on the screen.

    It now sits in the compose row, which is sized by the pane rather than by
    whatever else the bar is carrying.
    """
    page = oneview.page("[]", "[]", "tok", remote=False, build="abc")
    i = page.index('id="rebtn"')
    assert page.rindex('class="tellbar"', 0, i) > page.rindex('id="bar"', 0, i)
    assert ".tellbar #rebtn{flex:none;}" in SRC, "the row could squeeze it away"


def test_the_pill_wins_the_cascade():
    """A bare `#rebtn` at (1,0,0) lost to `#bar button` at (1,0,1) and
    rendered with the bar's 5px radius. Every rule carries a second selector
    so it cannot lose that fight again, wherever the pill is moved to."""
    assert ".tellbar #rebtn{display:inline-flex" in SRC
    assert "border-radius:999px" in SRC
    import re
    loose = [m.start() for m in re.finditer(r"(?<!\.tellbar )#rebtn[{\[:]", SRC)]
    assert not loose, "an unprefixed #rebtn rule will lose to a tag selector"


def test_a_click_anywhere_on_the_pill_counts():
    """The glyph and the label are decoration inside the button; a click
    landing on either must still be a click on the button."""
    assert ".tellbar #rebtn > *{pointer-events:none;}" in SRC


def test_no_comment_carries_the_html_terminator():
    """Marsita writes arrows as four dashes and a bracket, which contains the
    comment terminator. Quoting her verbatim inside an HTML comment ended the
    comment early and printed the rest of it in the top bar.

    Three or more dashes is the tell, not two: prose uses `--` as an em dash
    all over this file and is harmless, while `---->` contains the terminator
    and truncates the comment at the arrow.
    """
    import re
    for m in re.finditer(r"<!--((?:(?!-->).)*)-->", SRC, re.S):
        body = m.group(1)
        assert "---" not in body, (
            "an arrow inside an HTML comment: " + body.strip()[:70])

    # And the direct check: nothing after a comment opener may reach the page
    # before its terminator does. A stray `>` alone is fine; a `-->` is not.
    page = oneview.page("[]", "[]", "tok", remote=False, build="abc")
    for m in re.finditer(r"<!--", page):
        rest = page[m.end():]
        assert "-->" in rest, "an HTML comment that never closes"


def test_the_pill_sits_above_the_box_not_beside_it():
    """Left of the textarea it was reachable and still not where Marsita
    looks: "pill should be directly here, above the text area, this is where
    I'm looking" (2026-09-18)."""
    page = oneview.page("[]", "[]", "tok", remote=False, build="abc")
    assert 'class="tellbar"' in page
    assert page.index('class="tellbar"') < page.index('id="tellBox"')
    assert '.tellbar{' in SRC and "padding:4px 7px 0" in SRC


def test_the_pill_is_not_a_submit_button():
    """Inside a <form>, a bare <button> submits it. A reload control that
    also sent your half-written message would be a trap."""
    page = oneview.page("[]", "[]", "tok", remote=False, build="abc")
    i = page.index('id="rebtn"')
    assert 'type="button"' in page[max(0, i - 120):i]
