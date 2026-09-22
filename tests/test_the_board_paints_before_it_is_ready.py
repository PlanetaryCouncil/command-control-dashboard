"""The first packet is a loader, not a white screen.

The board is ~215KB and was built in full before a single byte left the
server: the browser waited out the render AND the transfer with nothing on
screen. Marsita, 2026-09-18: "create a unloader and loader... I want to make
it appear smooth and sleek."

So a ~1.6KB shell is flushed first, and the expensive part is built behind it
with the loader already painted.
"""

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "fleet" / "bin"))

SRC = (REPO / "fleet" / "bin" / "oneview.py").read_text()
SERVER = (REPO / "fleet" / "bin" / "fleet.py").read_text()

import oneview


def test_the_shell_fits_in_the_first_packet():
    """It carries a whole skeleton now, so it is bigger -- but an initial
    congestion window is ~14KB and this must stay nowhere near it."""
    assert len(oneview.shell().encode()) < 4096


def test_the_shell_needs_no_second_request():
    """A <link> or <script src> in the shell would stall the instant part on
    another round trip -- exactly what this avoids."""
    sh = oneview.shell()
    assert "<link" not in sh
    assert "<script" not in sh
    assert "<style>" in sh, "no inline styling; the loader would be unstyled"


def test_the_shell_is_shaped_like_the_board():
    """A centred logo said "busy" and nothing else. Marsita, 2026-09-18: "I
    prefer partial load ----> and then different panes load inside". The first
    packet draws the layout, so the real board lands into a shape that is
    already familiar rather than replacing a splash screen."""
    sh = oneview.shell()
    assert 'id="boot"' in sh
    assert 'role="status"' in sh, "a loader that says nothing to a screenreader"
    assert sh.count('class="col"') == 3, "not the three-column board"
    assert sh.count('class="blk"') >= 6, "too few panes to read as the board"


def test_the_skeleton_does_not_lie_about_the_layout():
    """Its columns are the ones #grid actually uses; a skeleton that settles
    somewhere else is worse than none, because the board then jumps."""
    import re
    real = re.search(r"#grid\{[^}]*grid-template-columns:var\(--wL,(\d+)px\)"
                     r"[^}]*var\(--wR,(\d+)px\)", SRC)
    assert real, "could not read #grid's columns"
    sh = oneview.shell()
    assert f"grid-template-columns:{real.group(1)}px 1fr {real.group(2)}px" in sh


def test_the_panes_load_individually_behind_it():
    """"different panes load inside" -- each pane carries its own loading
    state, so once the skeleton lifts they fill in one at a time rather than
    all at once."""
    rest = oneview.page_rest("[]", "[]", "tok", remote=False, build="x")
    assert rest.count('data-state="loading"') >= 6


def test_the_shell_is_a_constant_and_is_cached():
    """It is the same string every load, and rebuilding it cost 13ms of
    config reading each time."""
    assert oneview.shell() is oneview.shell()


def test_the_rest_does_not_repeat_the_document():
    """The shell has already opened head, closed it and opened body."""
    rest = oneview.page_rest("[]", "[]", "tok", remote=False, build="x")
    assert "<!doctype" not in rest.lower()
    assert "<head>" not in rest
    assert "<body>" not in rest


def test_the_head_contents_survive_into_the_body():
    """51KB of CSS and the signature script live in the head; moving them into
    the body is what stops them delaying the first paint."""
    rest = oneview.page_rest("[]", "[]", "tok", remote=False, build="x")
    assert "#bar{" in rest, "the stylesheet was dropped"
    assert "signature.js" in rest, "a head script was dropped"


def test_charset_is_not_declared_twice():
    """The shell said it. Repeating it is not harmless."""
    rest = oneview.page_rest("[]", "[]", "tok", remote=False, build="x")
    assert "charset" not in rest


def test_shell_plus_rest_is_one_valid_document():
    whole = oneview.shell() + oneview.page_rest("[]", "[]", "tok",
                                                remote=False, build="x")
    assert whole.lower().count("<!doctype") == 1
    assert whole.count("<body>") == 1
    assert whole.count("</html>") == 1
    assert whole.count('id="boot"') == 1


def test_the_response_is_chunked():
    """A shell flushed early cannot carry a Content-Length for a body that has
    not been written yet."""
    i = SERVER.index("def _send_streamed")
    fn = SERVER[i:SERVER.index("\n        def ", i + 10)]
    assert '"Transfer-Encoding", "chunked"' in fn
    # The header, not the word: the docstring explains why there is no
    # Content-Length, and a bare substring test found its own explanation.
    assert 'send_header("Content-Length"' not in fn
    assert '"X-Accel-Buffering", "no"' in fn, "a buffering proxy undoes all of it"
    assert "self.wfile.flush()" in fn


def test_nothing_expensive_happens_before_the_flush():
    """Reading 200 events and building the agent table took ~1.5s. Doing it
    before the flush meant the loader arrived after the wait it was meant to
    cover."""
    i = SERVER.index('if path in ("/", "/fleet", "/one", "/index.html"):')
    route = SERVER[i:SERVER.index('if path == "/board"', i)]
    before = route[:route.index("def rest():")]
    for expensive in ("ev.tail(", "av.AGENTS", "json.dumps("):
        assert expensive not in before, f"{expensive} runs before the shell"


def test_a_render_that_throws_still_says_so():
    """The shell is already on the wire and cannot be replaced by an error
    page, so the failure has to be written into the stream."""
    i = SERVER.index("def _send_streamed")
    fn = SERVER[i:SERVER.index("\n        def ", i + 10)]
    assert "__boardFailed" in fn


def test_the_loader_is_dismissed_last():
    """On DOMContentLoaded the panes are parsed but not wired, and the first
    thing you would see is a half-built board."""
    assert SRC.rstrip().endswith("unload();\n\"\"\"") or "unload();" in SRC
    i = SRC.index("JS = r\"\"\"")
    js = SRC[i:SRC.index('"""', i + 9)]
    assert js.rstrip().endswith("unload();"), "unload() is not the last line"


def test_a_board_that_never_boots_keeps_the_loader_up():
    """An empty screen is not a loaded one. Nothing removes the loader except
    the page's own last line."""
    assert SRC.count("boot.remove()") == 1
    assert SRC.count('boot.dataset.done = "1"') == 1


def test_the_loader_is_removed_not_just_hidden():
    """It is position:fixed over the whole board; an invisible sheet still
    swallows the first click."""
    i = SRC.index("function unload()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert "boot.remove()" in fn


def test_the_fade_waits_for_a_paint():
    """Without a frame in hand the fade and the first real paint happen
    together, which reads as a flicker."""
    i = SRC.index("function unload()")
    fn = SRC[i:SRC.index("\n}\n", i)]
    assert fn.count("requestAnimationFrame") == 2


def test_reduced_motion_gets_a_still_loader():
    m = re.search(r"@media \(prefers-reduced-motion:reduce\)\{\{([^@]*)\}\}",
                  SRC)
    assert m and "animation:none" in m.group(1)


# ── the five seconds, once, then the panes ────────────────────────────────
# Marsita, 2026-09-22: "5 second generic intro, then per-pane intro as they
# continue? After 1 minute a timeout... Best of all worlds".

def test_the_intro_is_not_in_the_everyday_shell():
    """A reload goes straight to the panes; the intro is a first-visit thing.
    So the default shell stays exactly the small script-free skeleton."""
    sh = oneview.shell()
    assert 'id="intro"' not in sh
    assert len(sh.encode()) < 4096


def test_the_intro_shell_lifts_itself_at_five_seconds_without_script():
    """It has to start on the first paint and end on its own, whatever the
    rest of the page is doing -- so it is CSS, and it stays in one packet."""
    sh = oneview.shell(intro=True)
    assert 'id="intro"' in sh
    assert "<script" not in sh
    assert re.search(r"#intro\{[^}]*animation:ilift 1s ease-in 5s forwards", sh)
    assert len(sh.encode()) < 8192, "still well inside one congestion window"
    assert "prefers-reduced-motion" in sh


def test_the_server_plays_the_intro_once_per_browser_session():
    """A session cookie, set on the first shell and read on the next: no
    Max-Age, so it dies with the browser and the next day gets its five
    seconds again."""
    assert 'seen = "pc_intro=1" in (self.headers.get("Cookie")' in SERVER
    assert "intro=not seen" in SERVER
    assert 'cookie="" if seen else "pc_intro=1; Path=/; SameSite=Lax"' in SERVER
    assert "Max-Age" not in SERVER.split("pc_intro=1; Path=/")[1][:60]


def test_the_panes_light_the_room_and_stall_after_a_minute():
    """The page watches its own panes' data-state: the fraction landed sets
    --lit, and a pane still loading after 60 s says "not answering"."""
    rest = oneview.page_rest("{}", "[]", "tok", remote=False)
    assert "MutationObserver" in rest and "attributeFilter:['data-state']" in rest
    assert "STALL_MS=60000" in rest
    assert "p.dataset.state='stalled'" in rest
    assert '.pane[data-state="stalled"] .load .msg::after{content:"not answering";}' in rest
    assert 'id="lit"' in rest and "opacity:var(--lit,0)" in rest
    assert '.load .msg::after{content:"activating…";}' in rest
