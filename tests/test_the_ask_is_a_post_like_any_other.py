"""An ask lands on the board under the name that wrote it.

Marsita, 2026-09-03, looking at their own question on the board:

  "[council] operator asked: ... " ----> it was ny dude, not operator...
  I used "ask".

Three things were wrong at once. The line called them "the operator" instead
of the name they had typed. The ask was ALSO echoed into a separate "YOU
ASKED" strip above the composer -- a second surface showing what the stream
already carried. And the signature pad kept its drawing afterwards, so the
next message went out wearing the previous one's hand.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))
import oneview                                             # noqa: E402

LOCAL = oneview.page("[]", "{}", "tok", remote=False)
VIEW = (ROOT / "fleet" / "bin" / "oneview.py").read_text()
SRV = (ROOT / "fleet" / "bin" / "fleet.py").read_text()


def test_the_ask_carries_the_name_that_was_typed():
    assert 'who: ($("#sayWho").value || "").trim()' in VIEW
    assert 'asker = str(body.get("who") or "").strip()' in SRV


def test_nothing_is_filed_under_a_role_the_person_did_not_choose():
    code = "\n".join(l for l in SRV.splitlines()
                     if not l.lstrip().startswith("#"))
    assert "[council] operator asked" not in code


def test_the_ask_lands_in_the_shape_that_draws_a_hand():
    """`[signals] <sender>: <text>` is what the stream reads a sender out of,
    so an ask gets its signature beside it like any other post."""
    assert 'f"[signals] {who}: {ask[:200]}"' in SRV


def test_a_name_with_a_colon_cannot_break_the_lookup():
    assert 'if ":" in who:' in SRV


def test_there_is_no_second_place_showing_the_ask():
    assert "pendingAsk" not in LOCAL
    assert "loadAsk" not in VIEW


def test_asking_clears_the_pad_the_way_posting_does():
    handler = VIEW.split('askBtn.addEventListener("click"')[1].split("askBtn.disabled = false;")[0]
    assert "window.__sayReset" in handler


def test_the_buttons_say_what_they_do():
    """"post" is the regular one; the privileged one says so."""
    assert ">as admin<" in LOCAL
    assert ">post<" in LOCAL or "type=\"submit\">post" in LOCAL
