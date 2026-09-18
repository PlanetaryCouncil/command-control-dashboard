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
    """Above ~1.5KB it stops being one round trip, which is the whole point."""
    assert len(oneview.shell().encode()) < 2048


def test_the_shell_needs_no_second_request():
    """A <link> or <script src> in the shell would stall the instant part on
    another round trip -- exactly what this avoids."""
    sh = oneview.shell()
    assert "<link" not in sh
    assert "<script" not in sh
    assert "<style>" in sh, "no inline styling; the loader would be unstyled"


def test_the_shell_carries_a_loader():
    sh = oneview.shell()
    assert 'id="boot"' in sh
    assert 'role="status"' in sh, "a loader that says nothing to a screenreader"


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
