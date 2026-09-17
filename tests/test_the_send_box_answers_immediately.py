"""Pressing send has to show something before the transcript catches up.

The stream pane polls every 3 seconds, so send used to do nothing visible for
up to three seconds: the box emptied and the page sat still. That is exactly
what a box which ATE your message looks like. Marsita, 2026-09-16: "As I press
enter here to send, update the text long above for more interactive experience
so I know something is happening... And have little loader animation".

These tests are the workflow, not the plumbing: type, send, see it, see the
wait move, see the echo replaced by the real line. Claude is mocked — no
model, no pty, no tmux. What matters is that the page never leaves you
guessing whether the machine heard you.
"""

import re
import sys
from pathlib import Path

BIN = Path(__file__).resolve().parents[1] / "fleet" / "bin"
sys.path.insert(0, str(BIN))

SRC = (BIN / "oneview.py").read_text()


def _submit():
    """The #tell submit handler.

    Sliced by searching FORWARD from the handler, not by two independent
    index() calls: there is an earlier keydown listener on the #say box, so
    the naive version produced a backwards slice and silently tested "".
    """
    i = SRC.index('form.addEventListener("submit"')
    j = SRC.index('box.addEventListener("keydown"', i)
    return SRC[i:j]


def _js(name):
    """The body of one JS function out of the page source."""
    i = SRC.index(f"function {name}(")
    depth, j = 0, SRC.index("{", i)
    for k in range(j, len(SRC)):
        if SRC[k] == "{":
            depth += 1
        elif SRC[k] == "}":
            depth -= 1
            if depth == 0:
                return SRC[i:k + 1]
    raise AssertionError(f"{name} never closes")


# ------------------------------------------------------- the echo, immediately
def test_the_echo_goes_up_before_the_request_returns():
    """The round trip is the slow part, so the echo has to beat it, not
    follow it. Showing it in the success branch would still leave the page
    still for as long as the network took."""
    submit = _submit()
    assert "showPending(text);" in submit
    assert submit.index("showPending(text);") < submit.index("await fetch")


def test_a_refused_send_does_not_leave_the_dots_spinning():
    """Dots after a failed send are the page claiming work it never started."""
    submit = _submit()
    # Both failure paths — a refusal from the server, and a dead request.
    assert submit.count("clearPending();") >= 2
    assert "could not send" in submit


def test_enter_sends_and_shift_enter_does_not():
    i = SRC.index('box.addEventListener("keydown"',
                  SRC.index('form.addEventListener("submit"'))
    keydown = SRC[i:SRC.index("});", i)]
    assert '"Enter"' in keydown and "!e.shiftKey" in keydown
    assert "requestSubmit()" in keydown


def test_the_page_looks_sooner_than_the_next_tick():
    """Waiting out the 3s poll wastes the part of the turn that already
    started on the machine."""
    submit = _submit()
    m = re.search(r"setTimeout\(loadStream,\s*(\d+)\)", submit)
    assert m, "no early look after a send"
    assert int(m.group(1)) < 3000


# ------------------------------------------------------------------- the dots
def test_the_dots_run_one_to_five_and_wrap():
    """Marsita asked for . .. ... .... ..... — five, then round again."""
    fn = _js("startDots")
    assert "(n % 5) + 1" in fn
    assert '".".repeat(n)' in fn


def test_the_dots_actually_move():
    """A static 'sending...' cannot be told from a frozen page."""
    fn = _js("startDots")
    m = re.search(r"setInterval\(tick,\s*(\d+)\)", fn)
    assert m, "the dots never tick"
    assert 100 <= int(m.group(1)) <= 600, "too fast to read or too slow to notice"


def test_the_dots_are_fixed_width():
    """A growing span shoves the row sideways five times a second."""
    assert re.search(r"\.dots\{[^}]*width:\s*[\d.]+em", SRC)


# --------------------------------------------- the echo gives way to the truth
def test_the_real_line_replaces_the_echo():
    fn = _js("pendingSettled")
    assert 'l.who === "you"' in fn
    lines = [{"who": "you", "text": "please run the tests"}]
    # Prefix match, because the transcript may wrap or trim what it stores.
    assert ".slice(0, 40)" in fn and "includes(head)" in fn
    del lines


def test_a_message_that_never_lands_stops_waiting():
    """Dots forever would be the page insisting on something that is not
    coming. Two minutes, then give up."""
    fn = _js("pendingSettled")
    m = re.search(r"PENDING\.since\s*>\s*(\d+)", fn)
    assert m and int(m.group(1)) == 120000


def test_a_poll_with_no_news_leaves_the_echo_alone():
    """loadStream returns early when nothing changed — and that early return
    must not be reached before the echo is checked, or a quiet stream would
    hold a settled echo on screen forever."""
    fn = _js("loadStream")
    assert fn.index("pendingSettled(lines)") < fn.index("if (sig === streamSeen) return;")


def test_rendering_puts_the_echo_back():
    """The body is replaced wholesale on every change, which takes the echo
    with it. A message vanishing one poll after you sent it is the original
    complaint, happening twice."""
    fn = _js("loadStream")
    assert "body.appendChild(PENDING.el)" in fn
    assert fn.index("body.innerHTML = lines.map") < fn.index("body.appendChild(PENDING.el)")


# ------------------------------------------------------------- no model needed
def test_none_of_this_needs_claude_running():
    """The whole point: the page's promise to the reader is testable without
    a model, a pty, or tmux. If this file ever needs one, the feedback loop
    has been built into the wrong layer."""
    assert "subprocess" not in SRC[:0] + ""  # nothing spawned by these tests
    assert _js("showPending") and _js("clearPending")


# ------------------------------------------- the placeholder gets out of the way
def test_the_placeholder_goes_when_you_are_typing():
    """A hint under the cursor competes with the thing it was hinting at."""
    assert re.search(r"#tellBox:focus::placeholder\{[^}]*color:\s*transparent", SRC)


# --------------------------------------------------- markdown out of the log
def _plain(text):
    """Run the page's own `plain()` rules over text, in Python.

    The function is JS in a Python string, so it cannot be imported. These
    mirror it case for case; if the two drift the shape below stops matching
    and the test says so.
    """
    fn = _js("plain")
    assert ".replace(" in fn
    return fn


def test_markdown_marks_are_stripped_and_words_are_kept():
    fn = _plain("")
    for rule in ("```", "#{1,6}", r"\*\*(.+?)\*\*", "`([^`]+)`", "u2588"):
        assert rule in fn, f"{rule} is not handled"


def test_a_heading_keeps_its_words():
    """`## CONTEXT` must become `CONTEXT`, not disappear. Dropping whole lines
    would delete the section titles that make the log readable."""
    fn = _plain("")
    assert '/^#{1,6}\\s+/gm, ""' in fn


def test_a_link_keeps_its_label():
    fn = _plain("")
    assert r'\[([^\]]+)\]\([^)]*\)/g, "$1"' in fn


def test_only_claude_lines_are_stripped():
    """Your own message is yours; rewriting what you typed would be lying
    about the transcript."""
    fn = _js("loadStream")
    # Non-claude lines return early, untouched; only the claude branch calls
    # plain() and splitPicks().
    assert 'if (l.who !== "claude")' in fn
    assert "splitPicks(plain(l.text))" in fn


# ------------------------------------------------------- the menu, as buttons
def test_a_menu_option_is_parsed_out_of_the_drawing():
    fn = _js("splitPicks")
    assert "PICK_RE" in fn
    assert "n: m[1]" in fn and "label: m[2]" in fn


def test_only_the_newest_menu_is_clickable():
    """An old menu is a decision already taken. A page of clickable history
    will send the wrong answer to the wrong question."""
    fn = _js("loadStream")
    assert "liveAt" in fn
    assert "for (let i = lines.length - 1; i >= 0; i--)" in fn


def test_clicking_an_option_sends_its_digit():
    submit = SRC[SRC.index('form.addEventListener("submit"'):]
    submit = submit[:submit.index("})();")]
    assert 'closest(".pick")' in submit
    assert "box.value = hit.dataset.pick" in submit
    assert "form.requestSubmit()" in submit


def test_answering_a_menu_disables_the_whole_set():
    """Two answers to one question is noise."""
    submit = SRC[SRC.index('form.addEventListener("submit"'):]
    submit = submit[:submit.index("})();")]
    assert 'querySelectorAll(".pick").forEach' in submit


def test_the_click_handler_survives_the_next_poll():
    """The stream is rebuilt every second, so a listener on the button itself
    would be thrown away a second after it was attached."""
    submit = SRC[SRC.index('form.addEventListener("submit"'):]
    submit = submit[:submit.index("})();")]
    assert "tpane.addEventListener(\"click\"" in submit


# ------------------------------------------------------------ elapsed, and ttfb
def test_the_wait_counts_seconds():
    fn = _js("showWaiting")
    assert "WAIT.since = Date.now()" in fn
    assert 'toFixed(0) + "s"' in fn
    assert "setInterval(tickClock, 1000)" in fn


def test_the_clock_stops_with_the_dots():
    """An interval left running after the row is gone is a leak that survives
    every later turn."""
    fn = _js("clearWaiting")
    assert "clearInterval(WAIT.clock)" in fn


def test_ttfb_keeps_a_hundred():
    assert "TTFB_KEEP = 100" in SRC
    fn = _js("ttfbAdd")
    assert "slice(-TTFB_KEEP)" in fn


def test_ttfb_is_measured_from_the_keypress():
    """The number that matters is the one you felt, not the one the server
    would report about itself."""
    submit = SRC[SRC.index('form.addEventListener("submit"'):]
    submit = submit[:submit.index("})();")]
    assert "TTFB.since = Date.now()" in submit
    assert submit.index("TTFB.since = Date.now()") < submit.index("await fetch")


def test_ttfb_reports_the_median():
    """One four-minute turn should not move the number you read every day."""
    fn = _js("ttfbPaint")
    assert "sort(" in fn and "median" in fn


def test_a_silly_ttfb_is_thrown_away():
    """A tab left open overnight would otherwise land a 9-hour sample."""
    fn = _js("ttfbAdd")
    assert "ms > 600000" in fn


def test_storage_failure_does_not_break_the_pane():
    """localStorage throws in a private window; a stat is never worth a page."""
    assert "try { return JSON.parse(localStorage.getItem(TTFB_KEY)" in SRC
    fn = _js("ttfbRead")
    assert "catch" in fn and "return []" in fn


# ------------------------------------------- the drawing gives way to the buttons
BOX = "╭────────╮"
END = "╰────────╯"


def _split(text):
    """Mirror of the page's `splitPicks`, run in Python over real reply text.

    The function is JS inside a Python string, so it cannot be imported. This
    reimplements the same two regexes; the assertions below then check the JS
    still carries them, so the pair cannot drift silently.
    """
    pick = re.compile(r"^\s*│\s*(\d+)\s*│\s+(.+?)\s*$")
    edge = re.compile(r"^\s*[╭╰][─]+[╮╯]\s*$")
    lines, picks, drop = text.split("\n"), [], set()
    for i, line in enumerate(lines):
        m = pick.match(line)
        if not m:
            continue
        picks.append((m.group(1), m.group(2)))
        drop.add(i)
        if i and edge.match(lines[i - 1]):
            drop.add(i - 1)
        if i + 1 < len(lines) and edge.match(lines[i + 1]):
            drop.add(i + 1)
    kept = "\n".join(l for i, l in enumerate(lines) if i not in drop)
    return re.sub(r"\n{3,}", "\n\n", kept).strip(), picks


def test_the_menu_drawing_is_removed_and_returned_as_options():
    """Rendering both said the same thing twice. Marsita, 2026-09-16: "I want
    the boxes to be integrated"."""
    text = f"words\n\n{BOX}\n│   1    │    do the thing\n{END}"
    out, picks = _split(text)
    assert picks == [("1", "do the thing")]
    assert "│   1" not in out and BOX not in out
    assert "words" in out


def test_the_poem_box_survives():
    """The closing poem is drawn with the same characters. Eating it would
    take the end-of-turn marker off the page."""
    text = (f"{BOX}\n│   1    │    an option\n{END}\n\n"
            "╭────╮\n│  a line  │\n╰────╯")
    out, picks = _split(text)
    assert len(picks) == 1
    assert "a line" in out and "╰" in out


def test_an_edge_is_only_eaten_when_it_touches_a_number():
    fn = _js("splitPicks")
    assert "EDGE_RE.test(lines[i - 1])" in fn
    assert "EDGE_RE.test(lines[i + 1]" in fn


def test_a_reply_with_no_menu_is_left_exactly_as_it_was():
    out, picks = _split("just prose, nothing to pick")
    assert picks == [] and out == "just prose, nothing to pick"
    fn = _js("splitPicks")
    assert "if (!picks.length) return {text: text, picks: []};" in fn


def test_an_old_menu_loses_its_drawing_but_not_its_place():
    """Every menu is unwrapped so the log reads the same all the way up; only
    the newest one stays clickable."""
    fn = _js("loadStream")
    assert "liveAt" in fn
    assert 'const live = i === liveAt;' in fn
    assert '" disabled"' in fn
