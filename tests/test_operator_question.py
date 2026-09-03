"""A question from the operator must outrank the board.

2026-08-07: the operator put a decision on the board — merge a deny-list fix
before the self-improve loop ran unattended at 03:00 — convened the council,
and none of the three agents mentioned it. Nothing malfunctioned. The prompt
said "pick ONE line from the state above", his question was one log line among
sixty, and three models picked three other lines.

The council had no concept of being asked anything. These tests pin the one it
has now: the question is rendered, it is given standing over the board, and it
does not outlive the council that received it.
"""

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import council  # noqa: E402

STATE = {
    "workers": [{"worker": "pipeline", "status": "alert", "summary": "x"}],
    "recent_events": ["[fleet] something unrelated happened"],
    "event_levels": {}, "event_kinds": {}, "guest_signals": [],
}
QUESTION = "Merge PR #34 before the 03:00 self-improve run, or is a pattern deny list theatre?"


def _ask(tmp_path, monkeypatch, text=QUESTION):
    f = tmp_path / "council-question.md"
    f.write_text(text)
    monkeypatch.setattr(council, "ASK_FILE", f)
    return f


def test_no_question_is_the_empty_string_not_a_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(council, "ASK_FILE", tmp_path / "absent.md")
    assert council.operator_question() == ""


def test_the_question_reaches_the_full_prompt(tmp_path, monkeypatch):
    _ask(tmp_path, monkeypatch)
    p = council.build_prompt("claude", STATE, [])
    assert QUESTION in p, "the operator's question is not in the prompt at all"


def test_the_question_reaches_the_small_model_prompt(tmp_path, monkeypatch):
    """The 1B is the one that ignored it. It must see the question FIRST —
    a completion model answers what it read last and remembers what it read
    first, so the question is placed at both ends."""
    _ask(tmp_path, monkeypatch)
    p = council.build_prompt("ollama", STATE, [])
    assert "operator asked" in p.lower()
    head = p[:300].lower()
    assert "operator asked" in head, "the question must lead, not trail the board"


def test_the_question_outranks_the_board_in_the_instructions(tmp_path, monkeypatch):
    """Rendering it is not enough — it was rendered last time, as a log line.

    The instruction block must make answering it the job, otherwise the model
    is still free to pick any other line and be following orders.
    """
    _ask(tmp_path, monkeypatch)
    p = council.build_prompt("claude", STATE, [])
    low = p.lower()
    assert "first sentence" in low or "answer it directly" in low
    assert "outranks" in low or "before any other observation" in low


def test_without_a_question_the_old_instruction_is_unchanged(tmp_path, monkeypatch):
    """Councils that were not asked anything must behave exactly as before."""
    monkeypatch.setattr(council, "ASK_FILE", tmp_path / "absent.md")
    for agent in ("claude", "ollama"):
        p = council.build_prompt(agent, STATE, [])
        assert "operator asked" not in p.lower()
        assert "ground it in something visible" in p.lower() or "pick one line" in p.lower()


def test_an_over_long_question_is_truncated_not_dropped(tmp_path, monkeypatch):
    """Too long to fit is still the most important thing on the page."""
    _ask(tmp_path, monkeypatch, "Q" * (council.ASK_MAX * 3))
    q = council.operator_question()
    assert 0 < len(q) <= council.ASK_MAX


def test_clearing_removes_it(tmp_path, monkeypatch):
    """A stale question would make every later council answer a decision the
    operator has moved past — and agreement-by-echo reads like agreement."""
    _ask(tmp_path, monkeypatch)
    council.clear_question()
    assert council.operator_question() == ""


def test_clearing_a_missing_question_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(council, "ASK_FILE", tmp_path / "absent.md")
    council.clear_question()


def test_the_question_file_is_not_publicly_writable_by_design():
    """The airlock is unchanged: this channel carries an INSTRUCTION, which is
    exactly why nothing reachable from the funnel may write it. If a public
    route ever writes this path, a stranger is steering the council."""
    fleet_py = (BIN / "fleet.py").read_text()
    assert "council-question" not in fleet_py, \
        "the web server writes the operator question file — that is the airlock, breached"


def test_set_question_is_what_the_council_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(council, "ASK_FILE", tmp_path / "q.md")
    assert council.set_question("  merge it now  ") == "merge it now"
    assert council.operator_question() == "merge it now"


def test_the_local_board_has_an_ask_button_and_the_public_one_does_not():
    """Dogfood: the operator talks through the board. Strangers still post
    airlocked signals. The ask button is the split."""
    import oneview
    local = oneview.page("[]", "{}", "tok", remote=False)
    remote = oneview.page("[]", "{}", "", remote=True)
    assert "<title>" in local and "Fleet</title>" not in local
    assert 'id="askbtn"' in local
    assert 'id="askbtn"' not in remote
    assert "talk to the board" in local
    assert "leave a public signal" in remote
    # api/ask is no longer fetched by the board. It used to fill a separate
    # "YOU ASKED" strip above the composer -- a second surface for something
    # the stream already carried. The endpoint stays for callers that want
    # to read the pending question; the board just does not need it
    # (2026-09-03).
    assert "api/convene" in local
