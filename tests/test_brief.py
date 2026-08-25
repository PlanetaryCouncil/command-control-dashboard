import importlib.util
from pathlib import Path

BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin" / "brief.py"
spec = importlib.util.spec_from_file_location("brief", BIN)
brief = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brief)


def test_latest_handoff_is_newest_name(monkeypatch, tmp_path):
    (tmp_path / "handoff-2026-08-21.md").write_text("old")
    newest = tmp_path / "handoff-2026-08-23.md"
    newest.write_text("new")
    monkeypatch.setattr(brief, "REPORTS", tmp_path)
    assert brief.latest_handoff() == newest


def test_brief_is_small_live_context_not_another_state_store(monkeypatch,
                                                              tmp_path):
    handoff = tmp_path / "handoff-2026-08-23.md"
    handoff.write_text("# Handoff\n\nNext: make it comfy.\n")
    monkeypatch.setattr(brief, "latest_handoff", lambda: handoff)
    monkeypatch.setattr(brief, "REPO", tmp_path)
    monkeypatch.setattr(brief, "git", lambda *a: (
        "abc123 current" if "log" in a else " M shared.py"))
    monkeypatch.setattr(brief, "quota_line", lambda: "spending hermes")
    out = brief.render()
    assert "abc123 current" in out
    assert "1 changed paths" in out
    assert "spending hermes" in out
    assert "Next: make it comfy" in out


def test_model_entry_files_point_to_one_contract():
    repo = Path(__file__).resolve().parent.parent
    entry_files = [repo / "CLAUDE.md", repo / "GEMINI.md",
                   repo / ".grok" / "rules" / "project.md"]
    for path in entry_files:
        text = path.read_text()
        assert "AGENTS.md" in text
        assert "fleet/bin/brief.py" in text


def test_agents_file_uses_the_canonical_operating_contract():
    repo = Path(__file__).resolve().parent.parent
    agents = (repo / "AGENTS.md").read_text()
    block = agents.split("<!-- AGENT CONTRACT:", 1)[1]
    block = block.split("-->", 1)[1].split("<!-- /AGENT CONTRACT -->", 1)[0]
    assert block.strip() == brief.agentcontract.as_markdown().strip()


def test_brief_carries_the_canonical_operating_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(brief, "latest_handoff", lambda: None)
    monkeypatch.setattr(brief, "REPO", tmp_path)
    monkeypatch.setattr(brief, "git", lambda *a: "")
    monkeypatch.setattr(brief, "quota_line", lambda: "unknown")
    out = brief.render()
    for rule in brief.agentcontract.RULES:
        assert rule in out
