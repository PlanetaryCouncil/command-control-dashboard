"""The quota pulse must say when a scheduled vendor is dry.

A binary on PATH is not a plan with credits. Claude ran out and still
looked ready. This file pins the cheaper check: login + recent
quota-shaped errors, and never put an email on the public card.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "fleet" / "bin"))
import quotas  # noqa: E402


def _ts(hours_ago=0):
    t = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_quota_shaped_errors_are_counted_and_old_ones_are_not():
    events = [
        {"ts": _ts(1), "agent": "claude", "level": "error",
         "msg": "out of credits on this plan"},
        {"ts": _ts(1), "agent": "hermes", "level": "ok",
         "msg": "council discussed the quotas card"},
        {"ts": _ts(1), "agent": "grok", "level": "ok",
         "msg": "[council] quotas alert: scheduled dry"},
        {"ts": _ts(48), "agent": "claude", "level": "error",
         "msg": "rate limit exceeded"},
    ]
    assert quotas.recent_quota_hits("claude", events=events) == 1
    assert quotas.recent_quota_hits("hermes", events=events) == 0
    assert quotas.recent_quota_hits("grok", events=events) == 0


def test_public_row_drops_email_and_paths():
    raw = {
        "agent": "claude", "vendor": "anthropic", "binary": True,
        "auth": "logged-in", "ok": True, "note": "max",
        "email": "you@example.com",
        "home": "/Users/YOU/.claude",
    }
    pub = quotas.public_row(raw)
    blob = json.dumps(pub)
    assert "example.com" not in blob
    assert "/Users/" not in blob
    assert pub["agent"] == "claude"


def test_scheduled_dry_vendor_makes_the_card_alert(monkeypatch):
    monkeypatch.setattr(quotas, "scheduled_agents",
                        lambda cfg=None: ["hermes", "grok"])

    def fake(name, ok):
        return {"agent": name, "vendor": name, "binary": True,
                "auth": "logged-in" if ok else "logged-out",
                "ok": ok, "note": "ok" if ok else "not logged in"}

    monkeypatch.setattr(quotas, "check_hermes", lambda: fake("hermes", True))
    monkeypatch.setattr(quotas, "check_grok", lambda: fake("grok", False))
    monkeypatch.setattr(quotas, "check_claude", lambda: fake("claude", True))
    monkeypatch.setattr(quotas, "check_ollama", lambda: fake("ollama", True))
    monkeypatch.setattr(quotas, "check_openclaw", lambda: fake("openclaw", False))
    # pulse looks up CHECKS, not the names above
    monkeypatch.setitem(quotas.CHECKS, "hermes", lambda: fake("hermes", True))
    monkeypatch.setitem(quotas.CHECKS, "grok", lambda: fake("grok", False))
    monkeypatch.setitem(quotas.CHECKS, "claude", lambda: fake("claude", True))
    monkeypatch.setitem(quotas.CHECKS, "ollama", lambda: fake("ollama", True))
    monkeypatch.setitem(quotas.CHECKS, "openclaw", lambda: fake("openclaw", False))
    monkeypatch.setitem(quotas.CHECKS, "agy", lambda: fake("agy", True))

    worker, down = quotas.pulse(cfg={})
    assert down == ["grok"]
    assert worker["status"] == "alert"
    assert "grok" in worker["summary"]
    # Logged out is not "dry". Dry is quota-shaped errors.
    assert "logged out" in worker["summary"]
    assert "dry" not in worker["summary"]


def test_all_scheduled_ok_is_pass(monkeypatch):
    monkeypatch.setattr(quotas, "scheduled_agents", lambda cfg=None: ["hermes"])

    def ok(name):
        return {"agent": name, "vendor": name, "binary": True,
                "auth": "logged-in", "ok": True, "note": "ok"}

    for n in quotas.CHECKS:
        monkeypatch.setitem(quotas.CHECKS, n, lambda n=n: ok(n))
    worker, down = quotas.pulse(cfg={})
    assert down == []
    assert worker["status"] == "pass"


def test_eligible_skips_dry_and_holds_rare_while_plenty_is_up():
    cfg = {"quotas": {"spend": {"grok": "plenty", "hermes": "plenty",
                                "claude": "rare"}}}
    rows = {
        "grok": {"agent": "grok", "ok": True},
        "hermes": {"agent": "hermes", "ok": True},
        "claude": {"agent": "claude", "ok": True},
    }
    assert quotas.eligible(["hermes", "grok", "claude"], cfg=cfg, rows=rows) \
        == ["hermes", "grok"]
    rows["grok"]["ok"] = False
    rows["hermes"]["ok"] = False
    assert quotas.eligible(["hermes", "grok", "claude"], cfg=cfg, rows=rows) \
        == ["claude"]


def test_eligible_without_a_pulse_still_holds_rare():
    cfg = {"quotas": {"spend": {"grok": "plenty", "claude": "rare"}}}
    assert quotas.eligible(["claude", "grok"], cfg=cfg, rows={}) == ["grok"]


def test_hermes_codex_checkmark_is_logged_in(monkeypatch):
    """'not logged in' contains the letters 'logged in'. Nous being
    out must not make Codex look in, and the checkmark is the bit
    that means in."""
    monkeypatch.setattr(quotas.chat, "_agent_ready", lambda n: True)
    monkeypatch.setattr(quotas, "recent_quota_hits", lambda *a, **k: 0)
    out = ("Nous Portal   ✗ not logged in\n"
           "OpenAI Codex  ✓ logged in\n")
    monkeypatch.setattr(quotas, "run", lambda *a, **k: (0, out))
    row = quotas.check_hermes()
    assert row["ok"] is True
    assert row["auth"] == "logged-in"
    assert row["note"] == "codex"


def test_hermes_status_timeout_is_not_dry(monkeypatch):
    """An 8s probe on a loaded box used to mark Hermes logged-out,
    then the card said 'vendor dry' and dinged needs_you."""
    monkeypatch.setattr(quotas.chat, "_agent_ready", lambda n: True)
    monkeypatch.setattr(quotas, "recent_quota_hits", lambda *a, **k: 0)
    monkeypatch.setattr(quotas, "run", lambda *a, **k: (1, "timeout"))
    row = quotas.check_hermes()
    assert row["ok"] is True
    assert row["auth"] == "unknown"
    assert "timed out" in row["note"]


def test_quota_hits_are_the_only_dry(monkeypatch):
    monkeypatch.setattr(quotas, "scheduled_agents",
                        lambda cfg=None: ["hermes", "grok"])

    def fake(name, hits=0, ok=True, auth="logged-in"):
        return {"agent": name, "vendor": name, "binary": True,
                "auth": auth, "ok": ok, "note": "x",
                "quota_errors_24h": hits}

    monkeypatch.setitem(quotas.CHECKS, "hermes",
                        lambda: fake("hermes", hits=2, ok=False))
    monkeypatch.setitem(quotas.CHECKS, "grok", lambda: fake("grok"))
    monkeypatch.setitem(quotas.CHECKS, "claude", lambda: fake("claude"))
    monkeypatch.setitem(quotas.CHECKS, "ollama", lambda: fake("ollama"))
    monkeypatch.setitem(quotas.CHECKS, "openclaw",
                        lambda: fake("openclaw", ok=False, auth="missing"))
    monkeypatch.setitem(quotas.CHECKS, "agy", lambda: fake("agy"))
    worker, down = quotas.pulse(cfg={})
    assert down == ["hermes"]
    assert worker["summary"].startswith("scheduled dry:")
    assert "hermes" in worker["summary"]
    assert "grok" not in worker["summary"]


def test_scheduled_agents_come_from_config_and_builder(monkeypatch):
    monkeypatch.delenv("FLEET_BUILDER", raising=False)
    got = quotas.scheduled_agents({
        "heartbeat": {"agents": ["hermes"]},
        "council": {"agents": ["hermes", "grok"]},
        "rota": {"agents": ["grok"]},
    })
    assert got == ["hermes", "grok"]
