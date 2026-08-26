"""The vendor table is a claim about the world, so it has to be re-checked.

Every independence guarantee in this fleet is one lookup deep: the reviewer is
trusted because vendors.py says it works for a different company. On
2026-08-26 that lookup was wrong twice on one machine -- the NUC's `hermes`
was a llama3.2:3b on loopback while the board called it OpenAI, and `openclaw`
runs anthropic/claude-sonnet-5 while the table said openai. Weeks of council
transcripts recorded companies that were not in the room.

The old docstring said the table was "verified... not assumed". That was the
defect in one sentence: verified once, on one machine, then frozen.
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "vendors", ROOT / "fleet" / "bin" / "vendors.py")
vendors = importlib.util.module_from_spec(_spec)
sys.modules["vendors"] = vendors
_spec.loader.exec_module(vendors)


def test_a_loopback_backend_is_local_whatever_the_table_says(tmp_path, monkeypatch):
    """The NUC's exact configuration. A base_url on loopback is what the
    process calls, no matter which OAuth tokens are sitting on disk."""
    home = tmp_path
    (home / ".hermes").mkdir()
    (home / ".hermes" / "config.yaml").write_text(
        "model:\n  provider: custom\n"
        "  base_url: http://127.0.0.1:11434/v1\n  model: llama3.2:3b\n")
    # Tokens present and irrelevant -- this is the trap the old check fell into.
    (home / ".hermes" / "auth.json").write_text(
        json.dumps({"active_provider": "openai-codex"}))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))

    assert vendors.vendor("hermes") == "local"
    assert vendors.model("hermes") == "llama3.2:3b"


def test_oauth_provider_is_used_when_there_is_no_custom_endpoint(tmp_path, monkeypatch):
    home = tmp_path
    (home / ".hermes").mkdir()
    (home / ".hermes" / "auth.json").write_text(
        json.dumps({"active_provider": "openai-codex"}))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    assert vendors.vendor("hermes") == "openai"


def test_an_agent_that_became_local_stops_counting_as_a_second_company(tmp_path,
                                                                      monkeypatch):
    """The consequence that matters. independent_of() must not offer a
    reviewer whose independence has quietly evaporated."""
    home = tmp_path
    (home / ".hermes").mkdir()
    (home / ".hermes" / "config.yaml").write_text(
        "model:\n  provider: custom\n  base_url: http://localhost:11434/v1\n")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    assert vendors.vendor("hermes") != vendors.vendor("claude")
    assert vendors.vendor("hermes") == "local"


def test_an_unreadable_config_falls_back_instead_of_accusing(tmp_path, monkeypatch):
    """Silence must mean "cannot observe", never "verified" -- and a broken
    config must never take down a board or invent a mismatch."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    assert vendors.vendor("hermes") == vendors.VENDORS["hermes"]
    assert vendors.observed("hermes") is None
    assert vendors.mismatches() == []


def test_agents_with_a_fixed_cli_are_not_probed(tmp_path, monkeypatch):
    """claude, grok and agy ship talking to exactly one company. Probing them
    would only add ways to be wrong."""
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    for agent in ("claude", "grok", "agy", "ollama"):
        assert vendors.observed(agent) is None
        assert vendors.vendor(agent) == vendors.VENDORS[agent]


def test_openclaw_is_read_from_its_model_key_not_from_mentions(tmp_path,
                                                               monkeypatch):
    """The file names several vendors. Counting mentions gets the right answer
    by luck and the wrong one later."""
    home = tmp_path
    (home / ".openclaw").mkdir()
    (home / ".openclaw" / "openclaw.json").write_text(json.dumps({
        "agents": {"defaults": {"model": {
            "primary": "anthropic/claude-sonnet-5",
            "fallbacks": ["openai/gpt-5.3-codex"]}}},
        "notes": "openai openai openai openai",
    }))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    assert vendors.vendor("openclaw") == "anthropic"
    assert vendors.model("openclaw") == "claude-sonnet-5"
