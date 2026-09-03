"""A probe that did not answer is not an account that logged out.

Marsita, 2026-09-03, reading their own board while talking to Claude through
it: "why claude says logged out if I'm talking with you here?"

`claude auth status` returns in well under a second on an idle box. Gaia runs
at a load of 4-7 on four cores, and PROBE_TIMEOUT is 8 seconds. When it
overran, `run()` returned "timeout", `json.loads` raised, and the handler fell
through to logged-out -- reporting a live, paid session as signed out.

Hermes already had this fix (`test_hermes_status_timeout_is_not_dry`). claude
did not, which is why the same bug read as a different one.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "fleet" / "bin"))
import quotas                                              # noqa: E402


def test_a_timeout_is_unknown_not_logged_out(monkeypatch):
    monkeypatch.setattr(quotas.chat, "_agent_ready", lambda n: True)
    monkeypatch.setattr(quotas.chat, "resolve", lambda n: "/bin/true")
    monkeypatch.setattr(quotas, "recent_quota_hits", lambda *a, **k: 0)
    monkeypatch.setattr(quotas, "run", lambda *a, **k: (1, "timeout"))
    monkeypatch.setattr(quotas, "_log_probe_failure", lambda *a: None)
    row = quotas.check_claude()
    assert row["auth"] == "unknown"
    assert row["ok"] is True, "unproven is not down"
    assert "timed out" in row["note"]


def test_an_actual_no_is_still_a_no(monkeypatch):
    monkeypatch.setattr(quotas.chat, "_agent_ready", lambda n: True)
    monkeypatch.setattr(quotas.chat, "resolve", lambda n: "/bin/true")
    monkeypatch.setattr(quotas, "recent_quota_hits", lambda *a, **k: 0)
    monkeypatch.setattr(quotas, "run",
                        lambda *a, **k: (0, '{"loggedIn": false}'))
    row = quotas.check_claude()
    assert row["auth"] == "logged-out"
    assert row["ok"] is False


def test_a_healthy_answer_carries_the_plan(monkeypatch):
    monkeypatch.setattr(quotas.chat, "_agent_ready", lambda n: True)
    monkeypatch.setattr(quotas.chat, "resolve", lambda n: "/bin/true")
    monkeypatch.setattr(quotas, "recent_quota_hits", lambda *a, **k: 0)
    monkeypatch.setattr(quotas, "run", lambda *a, **k: (
        0, '{"loggedIn": true, "subscriptionType": "max"}'))
    row = quotas.check_claude()
    assert row["auth"] == "logged-in" and row["ok"] is True
    assert row["plan"] == "max"


def test_the_raw_output_is_kept_so_it_can_be_reported(monkeypatch):
    """"then report exact report in GH issue so then we can debug"."""
    monkeypatch.setattr(quotas.chat, "_agent_ready", lambda n: True)
    monkeypatch.setattr(quotas.chat, "resolve", lambda n: "/bin/true")
    monkeypatch.setattr(quotas, "recent_quota_hits", lambda *a, **k: 0)
    monkeypatch.setattr(quotas, "run", lambda *a, **k: (7, "boom\n  wide"))
    monkeypatch.setattr(quotas, "_log_probe_failure", lambda *a: None)
    row = quotas.check_claude()
    assert row["probe_exit"] == 7
    assert row["probe_raw"] == "boom wide"


def test_the_raw_output_never_reaches_the_public_card():
    """`claude auth status` prints an email address."""
    pub = quotas.public_row({"agent": "claude", "probe_raw": "email@example.com",
                             "probe_exit": 1, "ok": True})
    assert "probe_raw" not in pub and "probe_exit" not in pub
