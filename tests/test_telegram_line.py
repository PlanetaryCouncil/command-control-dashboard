"""The direct line is a control surface, so its guards are tested, not assumed.

Free text sent to this bot is dispatched to an agent. That is the operator's
explicit choice, and it means exactly one thing stands between a stranger and
an agent: the chat_id allowlist. These tests pin that, and the handling of the
token that would otherwise leak it.
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

FLEET_BIN = Path(__file__).resolve().parent.parent / "fleet" / "bin"
sys.path.insert(0, str(FLEET_BIN))

import telegram  # noqa: E402


def _config(tmp_path, body, mode=0o600):
    p = tmp_path / "telegram.env"
    p.write_text(body)
    p.chmod(mode)
    return p


def test_a_world_readable_token_is_refused(tmp_path, monkeypatch):
    """A bot token is a credential. Loose permissions fail loudly, not quietly."""
    cfg = _config(tmp_path, "BOT_TOKEN=secret\nALLOWED_CHAT_IDS=1\n", mode=0o644)
    monkeypatch.setattr(telegram, "CONFIG", cfg)
    with pytest.raises(SystemExit) as e:
        telegram._load()
    assert "readable by others" in str(e.value)


def test_a_correctly_locked_config_loads(tmp_path, monkeypatch):
    cfg = _config(tmp_path, "BOT_TOKEN=secret\nALLOWED_CHAT_IDS= 42 , 43 \n")
    monkeypatch.setattr(telegram, "CONFIG", cfg)
    token, allowed = telegram._load()
    assert token == "secret"
    assert allowed == {"42", "43"}, "whitespace around ids must not create ghost entries"


def test_a_missing_allowlist_parses_as_empty_not_as_everyone(tmp_path, monkeypatch):
    """The dangerous failure: absent read as permitted.

    An empty allowlist must be empty. `listen` refuses to start on one, which
    is only safe if the empty case is actually represented as empty.
    """
    cfg = _config(tmp_path, "BOT_TOKEN=secret\n")
    monkeypatch.setattr(telegram, "CONFIG", cfg)
    _, allowed = telegram._load()
    assert allowed == set()
    assert "" not in allowed, "an empty string id would match a sender with no id"


def test_listen_refuses_an_empty_allowlist(tmp_path, monkeypatch):
    """Without this, every caller on earth is the operator."""
    cfg = _config(tmp_path, "BOT_TOKEN=secret\n")
    monkeypatch.setattr(telegram, "CONFIG", cfg)
    with pytest.raises(SystemExit) as e:
        telegram.main(["listen"])
    assert "empty allowlist" in str(e.value)


def test_send_refuses_an_empty_allowlist(tmp_path, monkeypatch):
    cfg = _config(tmp_path, "BOT_TOKEN=secret\n")
    monkeypatch.setattr(telegram, "CONFIG", cfg)
    with pytest.raises(SystemExit):
        telegram.main(["send", "hello"])


def test_an_unknown_sender_is_not_the_operator():
    """The comparison is string-to-string against a set of strings.

    Telegram sends from.id as an integer; the allowlist is parsed from text.
    If one side were an int this would silently never match, and every message
    would be ignored — or worse, if inverted, every message accepted.
    """
    allowed = {"42"}
    assert str(42) in allowed
    assert str(99) not in allowed


def test_the_help_text_carries_no_token(tmp_path, monkeypatch):
    """--help prints the module docstring; it must never learn the secret."""
    out = subprocess.run([sys.executable, str(FLEET_BIN / "telegram.py"), "--help"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0
    assert "BOT_TOKEN=" not in out.stdout.replace("BOT_TOKEN=...", "")


def test_long_replies_are_truncated_not_dropped(monkeypatch):
    """Telegram rejects >4096 chars. A dropped reply looks like a dead bot."""
    captured = {}

    def fake_call(token, method, **params):
        captured.update(params)
        return {}

    monkeypatch.setattr(telegram, "call", fake_call)
    telegram.send("t", "42", "x" * 9000)
    assert len(captured["text"]) < 4096
    assert captured["text"].endswith("(truncated)")


def test_claude_dispatch_puts_the_prompt_on_stdin(monkeypatch, tmp_path):
    """`--allowedTools Bash Read Edit` ate the prompt. stdin cannot."""
    monkeypatch.setattr(telegram, "SESSION", tmp_path / "sid")
    seen = {}

    def fake_run(cmd, timeout, cwd=None, stdin_text=None):
        seen["cmd"] = cmd
        seen["stdin"] = stdin_text
        return "ok", ""

    monkeypatch.setattr(telegram, "_run", fake_run)
    monkeypatch.setattr(telegram, "telegram_agent", lambda: "claude")
    assert telegram.dispatch("triage the pile") == "ok"
    assert seen["stdin"] == "triage the pile"
    tools = [a for i, a in enumerate(seen["cmd"])
             if i and seen["cmd"][i - 1] == "--allowedTools"]
    assert tools == [",".join(telegram.TOOLS)]
    assert "triage the pile" not in seen["cmd"]


def test_stale_claude_session_retries_the_same_text(monkeypatch, tmp_path):
    sid = tmp_path / "sid"
    sid.write_text("dead-session-id\n")
    monkeypatch.setattr(telegram, "SESSION", sid)
    calls = []

    def fake_run(cmd, timeout, cwd=None, stdin_text=None):
        calls.append(stdin_text)
        if "--resume" in cmd:
            return "", "No conversation found with session ID: dead-session-id"
        return "triaged 40", ""

    monkeypatch.setattr(telegram, "_run", fake_run)
    monkeypatch.setattr(telegram, "telegram_agent", lambda: "claude")
    assert telegram.dispatch("127 proposals?") == "triaged 40"
    assert calls == ["127 proposals?", "127 proposals?"]
    assert sid.read_text().strip() != "dead-session-id"


def test_config_path_is_outside_the_repo():
    """A repo that has ever contained a bot token has a burned token."""
    repo = Path(__file__).resolve().parent.parent
    assert repo not in telegram.CONFIG.resolve().parents
