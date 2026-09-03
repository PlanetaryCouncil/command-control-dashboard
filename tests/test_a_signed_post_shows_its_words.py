"""A signed post shows what was written, and whose hand wrote it.

The board rang for a hand-signed stranger with

    [signals] a hand-signed hello from 'someone' — on the board

-- an announcement that a person had spoken, without saying what they said.
Two things broke at once. The words never appeared, and the stream's mark
lookup keys off `[signals] <sender>: <text>`, so a differently-shaped line
matched nothing and the signature was never drawn beside it either.

Marsita, 2026-09-03: "display the actual text ---> display the actual
signature ---> it is art ---> I want agents (from around the world) to use
board as coordination mechanism."

The airlock is unchanged where it still counts: an UNSIGNED stranger is still
a count until triage. A node signature or a living hand costs something to
produce, and that cost is the vetting.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))

MAIN = (ROOT / "legacy" / "app" / "main.py").read_text()
VIEW = (ROOT / "fleet" / "bin" / "oneview.py").read_text()

# The shape the stream parses a sender out of.
SENDER_RE = re.compile(r"\^\\\[signals\\\]\\s\+\(\[\^:\]\{1,40\}\):")


def _rings():
    """Every fleet.ring line in the signal handler."""
    body = MAIN.split("caller_is_local = ")[1].split("out = inbox.public_view")[0]
    return [b for b in body.split("fleet.ring(")[1:]]


def test_every_signed_ring_uses_the_one_shape():
    for r in _rings():
        assert "[signals] " in r, r[:80]
        assert "}: {" in r, f"a ring without the colon shape: {r[:80]}"


def test_the_words_themselves_are_in_the_line():
    for r in _rings():
        assert "body" in r or "record.get('body'" in r, r[:80]


def test_nothing_merely_announces_that_someone_spoke():
    assert "a hand-signed hello from" not in MAIN


def test_an_unsigned_stranger_is_still_only_a_count():
    """The airlock's remaining job. There is no else-branch ringing text for
    a caller with no node signature and no living hand."""
    body = MAIN.split("caller_is_local = ")[1].split("out = inbox.public_view")[0]
    assert "hand_signed" in body
    assert body.count("fleet.ring(") == 3, "a fourth ring would be the airlock"


def test_the_stream_still_reads_that_shape():
    assert r"/^\[signals\]\s+([^:]{1,40}):/" in VIEW


def test_the_signature_is_drawn_at_a_size_worth_looking_at():
    """"it is art" -- a mark is 110x26, not a favicon."""
    assert "canvas.mark{height:26px;width:110px" in VIEW


def test_a_signals_row_asks_for_its_mark():
    assert "row.dataset.wantsMark = who;" in VIEW
    assert "drawRawSignature(cv, MARKS[who])" in VIEW
