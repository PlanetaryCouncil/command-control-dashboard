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


def test_the_button_is_in_the_page_but_hidden_until_it_matters():
    """Marsita, 2026-09-18: "reload should appear only if something new
    deployed... only when something needs reloading".

    A control that is always there is furniture. One that appears exactly when
    it is the right thing to press is information -- and with nothing to say,
    the row above the box is a gap that never explains itself.
    """
    page = oneview.page("[]", "[]", "tok", remote=False, build="abc")
    assert 'id="rebtn"' in page, "it must exist to be revealed later"
    assert ".tellhead #rebtn{display:none;}" in SRC
    assert '.tellhead #rebtn[data-stale="1"]{display:inline-flex;}' in SRC


def test_the_keys_work_whether_it_is_showing_or_not():
    """The button is the notice, not the only way in."""
    i = SRC.index("function wireReload()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    # the keydown handler is bound unconditionally, before the BUILD guard
    assert fn.index('addEventListener("keydown"') < fn.index("if (!BUILD) return;")


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
    # The glow lives in the stale rule that also sets the colour, not in
    # whichever `[data-stale]` selector happens to come first in the file --
    # one of those is a :has() that only controls layout.
    rule = re.search(
        r'\.tellhead #rebtn\[data-stale="1"\]\{color:[^}]*\}', SRC)
    assert rule and "box-shadow" in rule.group(0)


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
    # Inside the compose row, which is sized by the pane -- not in the top
    # bar, which is sized by whatever else it happens to be carrying.
    assert 'class="tellhead"' in page[:i]
    assert page.rindex('class="tellhead"', 0, i) > page.index('id="grid"')
    assert ".tellhead #rebtn{flex:none;}" in SRC


def test_the_pill_wins_the_cascade():
    """A bare `#rebtn` at (1,0,0) lost to `#bar button` at (1,0,1) and
    rendered with the bar's 5px radius. Every rule carries a second selector
    so it cannot lose that fight again, wherever the pill is moved to."""
    assert ".tellhead #rebtn{display:inline-flex" in SRC
    assert "border-radius:999px" in SRC
    import re
    # `:has(#rebtn[...])` is a match on a descendant, not a rule whose
    # specificity competes -- exclude it rather than pretend it is a bug.
    loose = [m.start() for m in re.finditer(r"(?<![.\w] )(?<!\()#rebtn[{\[:]", SRC)]
    assert not loose, "an unprefixed #rebtn rule will lose to a tag selector"


def test_a_click_anywhere_on_the_pill_counts():
    """The glyph and the label are decoration inside the button; a click
    landing on either must still be a click on the button."""
    assert ".tellhead #rebtn > *{pointer-events:none;}" in SRC


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
    assert 'class="tellhead"' in page
    assert page.index('class="tellhead"') < page.index('id="tellBox"')


def test_the_pill_is_not_a_submit_button():
    """Inside a <form>, a bare <button> submits it. A reload control that
    also sent your half-written message would be a trap."""
    page = oneview.page("[]", "[]", "tok", remote=False, build="abc")
    i = page.index('id="rebtn"')
    assert 'type="button"' in page[max(0, i - 120):i]


def test_the_stale_pill_is_filled_not_outlined():
    """Marsita, 2026-09-18: "Make it yellow / orange / bright." An amber
    outline on a dark board is still a dark button, and the one thing this has
    to beat is being skimmed past."""
    import re
    rule = re.search(r'\.tellhead #rebtn\[data-stale="1"\]\{color:[^}]*\}', SRC)
    assert rule, "no stale rule"
    css = rule.group(0)
    assert "background:var(--warning)" in css, "outline only; not bright"
    # dark text on the fill: amber on amber is a smudge
    assert re.search(r"color:#[0-9a-f]{6}", css), "no explicit text colour"
    assert "box-shadow" in css


def test_the_pulse_is_not_carrying_the_message():
    """Reduced motion must kill the animation and leave a button that still
    reads as urgent on its own."""
    import re
    m = re.search(r"@media \(prefers-reduced-motion:reduce\)\{([^@]*)\}", SRC)
    assert m and m.group(1).count("animation:none") >= 2, \
        "the pill or its ring keeps animating under reduced motion"


def test_the_label_says_what_it_does():
    """Marsita, 2026-09-18: "Reload the page. Not simply reload ready." A
    control that only exists when it is needed does not also have to announce
    that it is needed."""
    page = oneview.page("[]", "[]", "tok", remote=False, build="abc")
    assert ">Reload the page<" in page
    assert 'content:" ready"' not in SRC


def test_send_stays_beside_the_box_on_the_right():
    """Marsita, 2026-09-18: "you did something funny with send image size...
    I prefer it is on the right." Moving send up into the control row changed
    its shape; it belongs against the thing you just typed."""
    page = oneview.page("[]", "[]", "tok", remote=False, build="abc")
    i = page.index('id="tellBox"')
    after = page[i:page.index("</form>", i)]
    assert 'type="submit"' in after, "send is no longer beside the box"
    assert "#tell{flex:none;display:flex;gap:6px;align-items:flex-end" in SRC


def test_the_reload_row_is_above_the_form_and_holds_only_the_pill():
    page = oneview.page("[]", "[]", "tok", remote=False, build="abc")
    i = page.index('class="tellhead"')
    row = page[i:page.index("</div>", i)]
    assert 'id="rebtn"' in row
    assert "submit" not in row, "send crept back into the control row"
    assert page.index('class="tellhead"') < page.index('<form id="tell">')


def test_the_pill_lines_up_with_the_text_you_are_writing():
    """"have an indentation like you code" -- the row takes the same 7px the
    box does, so the pill's left edge sits under the first character."""
    import re
    row = re.search(r"\.tellhead\{[^}]*\}", SRC).group(0)
    assert "padding:5px 7px 0" in row
    box = re.search(r"#tell\{[^}]*\}", SRC).group(0)
    assert "padding:5px 7px" in box


def test_the_empty_reload_row_collapses():
    """Otherwise a blank strip sits above the box whenever nothing is stale."""
    import re
    row = re.search(r"\.tellhead\{[^}]*\}", SRC).group(0)
    assert "display:none" in row
    assert '.tellhead:has(#rebtn[data-stale="1"]){display:flex;}' in SRC
