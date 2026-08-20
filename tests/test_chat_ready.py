"""Chat must not invent an agent the caller did not pick.

A stale picker used to substitute Claude (with acceptEdits) when the
requested CLI was missing. Fail closed: no ready requested agent means
no job.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fleet" / "bin"))
import chat  # noqa: E402


@pytest.fixture(autouse=True)
def no_threads(monkeypatch):
    monkeypatch.setattr(chat, "_worker", lambda *a, **k: None)


def test_missing_requested_agents_start_no_job(monkeypatch):
    monkeypatch.setattr(chat, "_agent_ready", lambda name, have=None: False)
    res = chat.start_job("hello", ["openclaw"], [])
    assert res["agents"] == []
    assert "error" in res
    assert not res.get("job")


def test_does_not_substitute_a_different_vendor(monkeypatch):
    monkeypatch.setattr(chat, "_agent_ready",
                        lambda name, have=None: name == "claude")
    res = chat.start_job("hello", ["openclaw"], [])
    assert not res.get("job")
    assert "claude" not in res.get("agents", [])


def test_keeps_only_the_requested_agents_that_are_ready(monkeypatch):
    monkeypatch.setattr(chat, "_agent_ready",
                        lambda name, have=None: name == "hermes")
    res = chat.start_job("hello", ["openclaw", "hermes"], [])
    assert res["agents"] == ["hermes"]
    assert res.get("job")


def test_agy_is_a_known_cloud_agent():
    assert "agy" in chat.AGENTS
    assert chat.ask_agy.__name__ == "ask_agy"


def test_readiness_uses_resolve_not_bare_which(monkeypatch, tmp_path):
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(chat, "resolve",
                        lambda name: str(fake) if name == "claude" else name)
    assert chat._agent_ready("claude") is True
    monkeypatch.setattr(chat, "resolve", lambda name: name)
    assert chat._agent_ready("claude") is False
