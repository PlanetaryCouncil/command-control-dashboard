"""The rota must ask about the projects, not about itself.

Marsita, 2026-08-07: "I want each agent to do rota... analyse the board and
suggest or just do 1 action for the advancement of my projects. My projects
are fundamental, everything else is coordination and tooling and
infrastructure."

Before this, question one was "what would most improve this machine", and a
fleet asked about itself answers about itself: 72 proposals filed in a single
day, almost none of them touching a project. The ordering IS the fix, so it
is what these tests pin.
"""

import sys
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(BIN))

import rota  # noqa: E402


def test_the_first_question_is_about_a_project():
    assert "project" in rota.QUESTIONS[0].lower()
    assert "ONE project" in rota.QUESTIONS[0]


def test_the_machine_question_is_last_and_conditional():
    """It has to earn its slot by naming what it unblocks."""
    machine = rota.QUESTIONS[-1]
    assert machine.startswith("Only if")
    assert "BLOCKING" in machine
    assert "NOTHING TO ADD" in machine


def test_the_prompt_carries_the_actual_project_list():
    """Not a summary of it, not the board's idea of it — the operator's file."""
    prompt = rota.prompt_for("claude", {})
    assert "projects.yaml" in rota.projects_text() or "Planetary Council" in prompt
    assert "THE PROJECTS ARE THE POINT" in prompt


def test_the_prompt_no_longer_says_a_human_decides():
    """The fleet merges its own work now. Telling agents a human reads and
    decides invites advice instead of implementable proposals."""
    prompt = rota.prompt_for("claude", {})
    assert "A human reads this and decides" not in prompt
    assert "The fleet builds what you propose" in prompt


def test_narrating_the_prompt_back_is_called_out():
    """Six of ten turns on 2026-08-07 opened by restating the questions."""
    prompt = rota.prompt_for("claude", {})
    assert "Do not restate these questions back" in prompt


def test_projects_text_survives_a_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(rota, "FLEET", tmp_path)
    assert "NOTHING TO ADD" in rota.projects_text()
