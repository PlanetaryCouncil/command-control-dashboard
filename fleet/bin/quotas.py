#!/usr/bin/env python3
"""Vendor pulse: who is logged in, who is scheduled, who looks dry.

Never call ask_claude / ask_grok / ask_hermes. A probe that spends the
credits it is guarding is the nine days of silence again. Binary, auth
status, local ollama tags, and 24h event shapes only.

Writes workers/quotas.json so the board shows it like anything else.
No emails, home paths, or tokens in the card — /workers.json is public.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
REPO = FLEET.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

import chat          # noqa: E402
import events as ev  # noqa: E402
import vendors       # noqa: E402

WINDOW_HOURS = 24
PROBE_TIMEOUT = 8
# Tight on purpose: council talking about the quotas card used to match
# the word "quotas" and mark Hermes dry. Only failure shapes, only
# error/warn/needs_you. Never a completion to find this out.
QUOTA_RE = re.compile(
    r"out of credits|credits? (exhausted|exceeded)|"
    r"insufficient[_ ]quota|quota exceeded|"
    r"rate.?limit(ed| exceed)|HTTP[ /]?429|"
    r"billing (denied|error)|usage.?limit exceeded",
    re.I,
)
ERROR_LEVELS = {"error", "warn", "needs_you"}
CONFIG = FLEET / "config.json"
EVENTS = FLEET / "events.jsonl"
WORKER = FLEET / "workers" / "quotas.json"
GROK_AUTH = Path.home() / ".grok" / "auth.json"
OLLAMA = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")


def now():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def scheduled_agents(cfg=None):
    cfg = cfg if cfg is not None else load_config()
    names = []
    for key in ("heartbeat", "council", "rota"):
        for a in (cfg.get(key) or {}).get("agents") or []:
            if a not in names:
                names.append(a)
    builder = os.environ.get("FLEET_BUILDER", "grok").strip() or "grok"
    if builder not in names:
        names.append(builder)
    return names


def load_config():
    try:
        return json.loads(CONFIG.read_text())
    except (OSError, ValueError):
        return {}


def run(cmd, timeout=PROBE_TIMEOUT):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return 1, str(e)


def recent_quota_hits(agent, events=None, hours=WINDOW_HOURS):
    cutoff = now() - timedelta(hours=hours)
    hits = 0
    src = events
    if src is None:
        if not EVENTS.exists():
            return 0
        src = []
        for line in EVENTS.read_text(errors="replace").splitlines():
            try:
                src.append(json.loads(line))
            except ValueError:
                continue
    for e in src:
        if e.get("agent") != agent:
            continue
        if e.get("level") not in ERROR_LEVELS:
            continue
        ts = e.get("ts") or ""
        try:
            when = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if when < cutoff:
            continue
        blob = " ".join(str(e.get(k, "")) for k in ("msg", "level", "detail"))
        if QUOTA_RE.search(blob):
            hits += 1
    return hits


def check_ollama():
    row = {"agent": "ollama", "vendor": vendors.vendor("ollama"),
           "binary": chat._agent_ready("ollama"), "auth": "local"}
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
            names = [m.get("name", "") for m in json.loads(r.read()).get("models", [])]
        row["ok"] = bool(names)
        row["note"] = f"{len(names)} models" if names else "no models"
    except Exception:
        row["ok"] = False
        row["note"] = "daemon down"
    return row


def check_claude():
    row = {"agent": "claude", "vendor": vendors.vendor("claude"),
           "binary": chat._agent_ready("claude")}
    if not row["binary"]:
        row["ok"] = False
        row["auth"] = "missing"
        row["note"] = "CLI not on PATH"
        return row
    code, out = run([chat.resolve("claude"), "auth", "status"])
    logged_in = False
    plan = "unknown"
    try:
        data = json.loads(out)
        logged_in = bool(data.get("loggedIn"))
        plan = str(data.get("subscriptionType") or "unknown")[:24]
    except ValueError:
        logged_in = "loggedIn" in out and "true" in out.lower()
    row["auth"] = "logged-in" if logged_in else "logged-out"
    row["plan"] = plan
    hits = recent_quota_hits("claude")
    row["quota_errors_24h"] = hits
    if hits:
        row["ok"] = False
        row["note"] = f"quota-shaped errors in last {WINDOW_HOURS}h"
    elif not logged_in:
        row["ok"] = False
        row["note"] = "not logged in"
    else:
        row["ok"] = True
        row["note"] = plan
    return row


def check_hermes():
    row = {"agent": "hermes", "vendor": vendors.vendor("hermes"),
           "binary": chat._agent_ready("hermes")}
    if not row["binary"]:
        row["ok"] = False
        row["auth"] = "missing"
        row["note"] = "CLI not on PATH"
        return row
    code, out = run([chat.resolve("hermes"), "status"])
    logged_in = "OpenAI Codex" in out and "logged in" in out
    row["auth"] = "logged-in" if logged_in else "logged-out"
    hits = recent_quota_hits("hermes")
    row["quota_errors_24h"] = hits
    if hits:
        row["ok"] = False
        row["note"] = f"quota-shaped errors in last {WINDOW_HOURS}h"
    elif not logged_in:
        row["ok"] = False
        row["note"] = "not logged in"
    else:
        row["ok"] = True
        row["note"] = "codex"
    return row


def check_grok():
    row = {"agent": "grok", "vendor": vendors.vendor("grok"),
           "binary": chat._agent_ready("grok")}
    if not row["binary"]:
        row["ok"] = False
        row["auth"] = "missing"
        row["note"] = "CLI not on PATH"
        return row
    logged_in = False
    stale = False
    try:
        data = json.loads(GROK_AUTH.read_text())
        for v in data.values():
            if not isinstance(v, dict):
                continue
            if v.get("auth_mode") == "oidc" and v.get("refresh_token"):
                logged_in = True
            exp = v.get("expires_at")
            if exp:
                try:
                    when = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                    if when < now():
                        stale = True
                except ValueError:
                    pass
    except (OSError, ValueError):
        pass
    row["auth"] = "logged-in" if logged_in else "logged-out"
    hits = recent_quota_hits("grok")
    row["quota_errors_24h"] = hits
    if hits:
        row["ok"] = False
        row["note"] = f"quota-shaped errors in last {WINDOW_HOURS}h"
    elif not logged_in:
        row["ok"] = False
        row["note"] = "not logged in"
    elif stale:
        row["ok"] = True
        row["note"] = "session expired; refresh on next turn"
    else:
        row["ok"] = True
        row["note"] = "oidc"
    return row


def check_openclaw():
    row = {"agent": "openclaw", "vendor": vendors.vendor("openclaw"),
           "binary": chat._agent_ready("openclaw")}
    row["ok"] = bool(row["binary"])
    row["auth"] = "present" if row["binary"] else "missing"
    row["note"] = "on PATH" if row["binary"] else "not on PATH"
    return row


CHECKS = {
    "ollama": check_ollama,
    "claude": check_claude,
    "hermes": check_hermes,
    "grok": check_grok,
    "openclaw": check_openclaw,
}


def public_row(row):
    """Fields safe for /workers.json. No emails, paths, tokens."""
    keep = ("agent", "vendor", "binary", "auth", "ok", "note",
            "plan", "quota_errors_24h", "spend")
    return {k: row[k] for k in keep if k in row}


def spend_of(agent, cfg=None):
    """plenty spends scheduled turns. rare is held unless nobody else is up."""
    cfg = load_config() if cfg is None else cfg
    return ((cfg.get("quotas") or {}).get("spend") or {}).get(agent, "plenty")


def last_pulse_rows():
    try:
        w = json.loads(WORKER.read_text())
        detail = json.loads(w.get("detail") or "{}")
        return {r["agent"]: r for r in detail.get("vendors") or []
                if isinstance(r, dict) and r.get("agent")}
    except (OSError, ValueError, TypeError):
        return {}


def eligible(requested, cfg=None, rows=None):
    """Who may spend a turn. Dry vendors are skipped. Rare vendors
    (Claude, while that plan is tight) only run if no plentiful one is up.
    Never calls a model — reads the last pulse and the spend table.
    """
    cfg = load_config() if cfg is None else cfg
    if rows is None:
        rows = last_pulse_rows()
    live = []
    for a in requested:
        row = rows.get(a)
        if row is not None and not row.get("ok"):
            continue
        live.append(a)
    plenty = [a for a in live if spend_of(a, cfg) != "rare"]
    return plenty or live


def pulse(cfg=None):
    cfg = cfg if cfg is not None else load_config()
    scheduled = scheduled_agents(cfg)
    rows = []
    for name in ("hermes", "grok", "claude", "ollama", "openclaw"):
        raw = CHECKS[name]()
        raw["spend"] = spend_of(name, cfg)
        rows.append(public_row(raw))
    by_name = {r["agent"]: r for r in rows}

    down_scheduled = [a for a in scheduled if not by_name.get(a, {}).get("ok")]
    dry = [r["agent"] for r in rows if r.get("quota_errors_24h")]
    held = [r["agent"] for r in rows if r.get("spend") == "rare"]
    spending = eligible(scheduled, cfg=cfg, rows=by_name)
    if down_scheduled:
        status = "alert"
        summary = "scheduled dry: " + ", ".join(down_scheduled)
    elif dry:
        status = "warn"
        summary = "quota-shaped errors: " + ", ".join(dry)
    else:
        status = "pass"
        bits = [f"{a} {by_name[a].get('note') or 'ok'}" for a in spending
                if a in by_name]
        hold = f" · holding {', '.join(held)}" if held else ""
        summary = ("spending " + " · ".join(bits) + hold) if bits else "no vendors"

    worker = {
        "worker": "quotas",
        "kind": "pulse",
        "target": "vendor login + 24h quota-shaped errors",
        "last_run": iso(),
        "status": status,
        "summary": summary,
        "detail": json.dumps({"scheduled": scheduled, "spending": spending,
                              "vendors": rows}, indent=2),
        "tests_passed": sum(1 for r in rows if r.get("ok")),
        "tests_failed": sum(1 for r in rows if not r.get("ok")),
        "duration_s": 0,
    }
    return worker, down_scheduled


def publish(worker):
    WORKER.parent.mkdir(parents=True, exist_ok=True)
    WORKER.write_text(json.dumps(worker, indent=2) + "\n")
    return worker


def main():
    worker, down = pulse()
    publish(worker)
    if down:
        ev.emit("quotas", "needs_you",
                f"[quotas] scheduled vendor dry: {', '.join(down)} — "
                f"top up or take them off the roster")
    else:
        ev.emit("quotas", "ok", f"[quotas] {worker['summary']}"[:400])
    print(worker["summary"])
    return 0 if worker["status"] != "alert" else 1


if __name__ == "__main__":
    raise SystemExit(main())
