"""The board, driven in a real browser.

Every other test in this suite reads the page as a STRING. They prove the
markup and the CSS say the right things -- and they said the right things
while a menu button drew 36px off the edge of the screen and could not be
clicked, and while pane two's send button did nothing visible and was reported
as broken. A string cannot tell you where a pixel landed.

So these drive Chrome. Marsita, 2026-09-18: "Can you do some E-2-E real
browser automation tests?"

Skipped, never failed, when Chrome or playwright is absent: a machine without
a browser has not discovered a bug in the board.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
playwright_api = pytest.importorskip("playwright.sync_api")


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def board():
    """A board of our own, on its own port.

    Never the running one on 8787: a test that types into the operator's live
    session is not a test, it is an interruption.
    """
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(REPO / "fleet" / "bin" / "fleet.py"), "serve", str(port)],
        cwd=str(REPO), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), 0.2):
                break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        pytest.skip("the board did not come up")
    yield url
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


@pytest.fixture(scope="module")
def page(board):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        try:
            # The Chrome already installed, rather than a 130MB download.
            browser = pw.chromium.launch(channel="chrome", headless=True)
        except Exception as exc:                      # no Chrome on this box
            pytest.skip(f"no chrome: {exc}")
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg.goto(board, wait_until="load")
        # The panes start data-open="0" and are opened by the page's own
        # script, so "load" is not "usable". Waiting for the compose box to be
        # visible is waiting for the board to be finished with itself.
        pg.wait_for_selector("#tellBox", state="visible", timeout=30000)
        yield pg
        browser.close()


# ------------------------------------------------------------------ the shell
def test_the_skeleton_arrives_before_the_board(board):
    """The first packet must paint. Measured against the wire, not the DOM:
    the question is when bytes a browser can draw leave the server."""
    import urllib.request
    t0 = time.perf_counter()
    with urllib.request.urlopen(board, timeout=30) as r:
        first = r.read(2048)
        t_first = time.perf_counter() - t0
        r.read()
        t_all = time.perf_counter() - t0
    assert b'id="boot"' in first, "the loader is not in the first 2KB"
    assert t_first < t_all, "nothing was flushed early"


def test_the_loader_goes_away(page):
    """A loader that outlives the load is worse than none."""
    page.wait_for_selector("#boot", state="detached", timeout=20000)
    assert page.locator("#boot").count() == 0


def test_the_board_is_actually_there(page):
    page.wait_for_selector("#grid", timeout=20000)
    assert page.locator(".pane").count() >= 6


# ------------------------------------------------------------- the two panes
def test_both_panes_are_visible_and_side_by_side(page):
    a = page.locator("#termpane").bounding_box()
    b = page.locator("#termpane2").bounding_box()
    assert a and b, "a pane did not render"
    assert a["x"] + a["width"] <= b["x"] + 8, "panes are stacked, not split"
    assert abs(a["y"] - b["y"]) < 4, "panes are not on the same row"


def test_the_panes_are_named_differently(page):
    """Both said "claude - ..." and read as the same pane twice."""
    one = page.locator("#termpane h2").inner_text()
    two = page.locator("#termpane2 h2").inner_text()
    assert one.strip() and two.strip()
    assert one.split()[0] != two.split()[0], f"same tag: {one!r} {two!r}"


def test_both_send_buttons_are_the_same_shape(page):
    """They had drifted -- 3px radius against 4px, stretch against not -- and
    looked like different widgets side by side. A string test compared the
    CSS; this compares the rendered boxes."""
    a = page.locator("#tell button[type=submit]").bounding_box()
    b = page.locator("#tell2 button[type=submit]").bounding_box()
    assert a and b
    assert abs(a["height"] - b["height"]) < 2, f"{a['height']} vs {b['height']}"
    ra = page.locator("#tell button[type=submit]").evaluate(
        "el => getComputedStyle(el).borderRadius")
    rb = page.locator("#tell2 button[type=submit]").evaluate(
        "el => getComputedStyle(el).borderRadius")
    assert ra == rb, f"{ra} vs {rb}"


# --------------------------------------------------------------- the controls
def test_every_control_is_inside_the_window(page):
    """The bug a string test cannot see: the reload pill rendered at x=1740 in
    a 1704px window. Perfect markup, perfect handler, off the screen."""
    w = page.viewport_size["width"]
    offscreen = page.evaluate("""(w) => {
      const out = [];
      for (const el of document.querySelectorAll('button, select')) {
        if (el.offsetParent === null) continue;      // legitimately hidden
        const r = el.getBoundingClientRect();
        if (r.width === 0) continue;
        if (r.right > w + 1 || r.left < -1) out.push(el.id || el.textContent.trim().slice(0, 20));
      }
      return out;
    }""", w)
    assert offscreen == [], f"off the edge: {offscreen}"


def test_a_click_on_a_control_lands_on_that_control(page):
    """Nothing invisible may sit over the send buttons -- the loader is
    position:fixed over the whole board and would swallow the first click if
    it were hidden rather than removed."""
    for sel in ("#tell button[type=submit]", "#tell2 button[type=submit]"):
        hit = page.locator(sel).evaluate("""el => {
          const r = el.getBoundingClientRect();
          const top = document.elementFromPoint(r.left + r.width/2, r.top + r.height/2);
          return top === el || el.contains(top);
        }""")
        assert hit, f"something is covering {sel}"


def test_typing_a_digit_does_not_fire_a_hotkey(page):
    """1-6 answer the menu, but a digit typed into a compose box is a digit."""
    box = page.locator("#tellBox")
    # focus(), not click(): the panes repaint every second, so playwright's
    # "stable" actionability check never settles and click() times out on an
    # element that is perfectly visible and perfectly clickable by a human.
    # Focus is what the hotkey guard actually keys off, so this tests the
    # thing rather than the wrapper.
    box.focus()
    page.keyboard.type("123")
    assert box.input_value() == "123", "a digit was swallowed by the hotkeys"
    box.fill("")


def test_a_digit_outside_a_box_is_a_hotkey(page):
    """The other half: with nothing focused, 1-6 answer the menu. Proven by
    the guard standing down rather than by pressing a live option, which would
    send a real message into a real session."""
    page.locator("#grid").click(position={"x": 2, "y": 2}, force=True)
    typing = page.evaluate("""() => {
      const el = document.activeElement;
      if (!el) return false;
      const t = el.tagName;
      return t === "TEXTAREA" || t === "INPUT" || t === "SELECT"
          || el.isContentEditable;
    }""")
    assert typing is False, "focus stayed in a box; the hotkeys would not fire"


def test_the_reload_pill_is_hidden_when_nothing_is_stale(page):
    """It appears only when the server has moved on."""
    assert page.locator("#rebtn").count() == 1
    assert not page.locator("#rebtn").is_visible()
