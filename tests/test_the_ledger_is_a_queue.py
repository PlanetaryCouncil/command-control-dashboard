"""The ledger holds work, not a transcript of everything anyone said.

4,886 rows, of which twelve were waiting. The rest was settled history and
noise that rota.py had already classified as junk and written anyway:

    547 rows  "[unknown agent codex]"     -- a roster name with no adapter
    263 rows  HTTP 402 Payment Required   -- a vendor out of credit
    ~170 rows "Here are my answers to the three questions: **1. Pick ONE
              project from the list..."  -- an agent reading this file's own
              prompt heading back instead of the board

Fable 5.1 found it triaging its own backlog on 2026-09-04: "events already
carry the warn; the ledger does not need the corpse. autotriage then has
nothing to drop."
"""

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import rota  # noqa: E402

SRC = (BIN / "rota.py").read_text()


def test_a_failed_turn_is_not_filed_as_work():
    body = SRC[SRC.index("LEDGER.parent.mkdir"):]
    guard = SRC[:SRC.index("LEDGER.parent.mkdir")]
    assert guard.rstrip().endswith("if not failed and not unusable:"), \
        "the ledger write is not guarded"


def test_the_failure_is_still_visible_on_the_board():
    """Not filing it must not mean hiding it. The warn stays."""
    assert 'ev.emit(agent, "warn", f"[rota] turn failed' in SRC
    assert "unusable turn after" in SRC


def test_the_prompt_heading_counts_as_narration():
    """The rota asks three numbered questions. An answer that opens by
    restating them is answering the brief, not reading the board."""
    for echo in ("here are my answers", "pick one project from the list"):
        assert echo in rota.NARRATION, echo


def test_a_roster_name_with_no_adapter_never_takes_a_turn():
    """It would burn the whole slot producing "[unknown agent codex]"."""
    assert rota.dispatchable(["grok", "codex", "agy"]) == ["grok", "agy"]
    assert rota.dispatchable(["codex"]) == []


def test_every_known_name_actually_dispatches():
    """KNOWN is a claim that ask() will reach it. Check the claim."""
    body = SRC[SRC.index("def ask("):SRC.index("def dispatchable(")]
    for name in rota.KNOWN:
        assert f'agent == "{name}"' in body, name


def test_the_filter_runs_before_the_quota_check():
    """After it, a name with no adapter has already cost a turn."""
    order = SRC.index("agents = dispatchable(agents)")
    assert order < SRC.index("agents = quotas.eligible(agents)")
