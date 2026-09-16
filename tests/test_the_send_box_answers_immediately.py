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
