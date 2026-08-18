"""The rota must tell its agents not to re-file what the board already holds.

On 2026-08-04 the already_proposed list held six entries, all outcome
"proposed", all circling the same branch-backlog topic — Marsita read six
versions of the same ask. The fix is one conditional in the rota prompt:
overlap with a recent proposal means NOTHING TO ADD, not a sixth restatement.
"""

import importlib.util
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "rota.py"
spec = importlib.util.spec_from_file_location("rota", BIN)
rota = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rota)


def test_the_prompt_tells_agents_to_check_already_proposed_first():
    prompt = rota.prompt_for("claude", {"already_proposed": []})
    assert "already_proposed" in prompt
    assert "last 4 hours" in prompt
    assert "NOTHING TO ADD" in prompt


def test_naming_a_project_comes_before_the_other_rules():
    """An agent reading rules top-down should hit the two gates that matter
    first: name a project, and do not repeat what was already proposed.

    Reordered 2026-08-07 when the questions were: the old first rule was
    "be specific", which a turn about the fleet can satisfy perfectly while
    still being a turn about the fleet."""
    prompt = rota.prompt_for("claude", {})
    rules = prompt[prompt.index("Rules:"):]
    assert rules.index("Name the project") < rules.index("already_proposed")
    assert rules.index("already_proposed") < rules.index("NOTHING TO ADD")
