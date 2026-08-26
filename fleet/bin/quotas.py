#!/usr/bin/env python3
"""Vendor pulse: who is logged in, who is scheduled, who looks dry.

Never call ask_claude / ask_grok / ask_hermes. A probe that spends the
credits it is guarding is the nine days of silence again. Binary, auth
status, local ollama tags, and 24h event shapes only.

Writes workers/quotas.json so the board shows it like anything else.
No emails, home paths, or tokens in the card — /workers.json is public.
"""
from __future__ import annotations

import argparse
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
# hermes status prints every provider. 8s was enough to call it
# logged-out on a loaded box, then the card said "dry" and painted
# whoever else missed the same pulse. 20s is still cheap; a turn is not.
HERMES_STATUS_TIMEOUT = 20
HERMES_CODEX_RE = re.compile(
    r"OpenAI Codex[^\n]*✓[^\n]*logged in", re.I)
# Tight on purpose: council talking about the quotas card used to match
# the word "quotas" and mark Hermes dry. Only failure shapes, only
# error/warn/needs_you. Never a completion to find this out.
QUOTA_RE = re.compile(
    r"out of credits|credits? (exhausted|exceeded)|"
    r"insufficient[_ ]quota|quota (exceeded|reached)|"
    r"rate.?limit(ed| exceed)|HTTP[ /]?429|"
    r"billing (denied|error)|usage.?limit exceeded",
    re.I,
)
HERMES_CUSTOM_RE = re.compile(r"Provider:\s+Custom endpoint", re.I)
ERROR_LEVELS = {"error", "warn", "needs_you"}
CONFIG = FLEET / "config.json"
EVENTS = FLEET / "events.jsonl"
WORKER = FLEET / "workers" / "quotas.json"
CAPACITY = FLEET / "state" / "quota-capacity.json"
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


def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def load_capacity():
    """Human/tool observations, kept per machine and never inferred from login."""
    try:
        data = json.loads(CAPACITY.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_observation(agent, remaining_pct, reset_at=None, source="manual"):
    """Record what a provider UI/command actually said without spending a turn."""
    data = load_capacity()
    data[agent] = {
        "remaining_pct": max(0.0, min(100.0, float(remaining_pct))),
        "observed_at": iso(),
        "reset_at": iso(reset_at) if reset_at else None,
        "source": str(source)[:40],
    }
    CAPACITY.parent.mkdir(parents=True, exist_ok=True)
    tmp = CAPACITY.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(CAPACITY)
    return data[agent]


def capacity_policy(cfg=None):
    q = (cfg or {}).get("quotas") or {}
    return {
        "max_age_hours": float(q.get("observation_max_age_hours", 48)),
        "reserve_below_pct": float(q.get("reserve_below_pct", 10)),
        "harvest_within_hours": float(q.get("harvest_within_hours", 24)),
    }


def capacity_fields(agent, observations=None, cfg=None):
    """Turn an observation into a flow state; stale data never steers routing."""
    observations = load_capacity() if observations is None else observations
    obs = observations.get(agent)
    if not isinstance(obs, dict):
        return {"flow": "unknown"}
    try:
        remaining = max(0.0, min(100.0, float(obs["remaining_pct"])))
    except (KeyError, TypeError, ValueError):
        return {"flow": "unknown"}
    observed = parse_time(obs.get("observed_at"))
    policy = capacity_policy(cfg)
    age_h = ((now() - observed).total_seconds() / 3600) if observed else None
    if age_h is None or age_h > policy["max_age_hours"]:
        return {"flow": "stale", "remaining_pct": remaining,
                "observed_at": obs.get("observed_at")}
    reset = parse_time(obs.get("reset_at"))
    reset_h = (reset - now()).total_seconds() / 3600 if reset else None
    # The old percentage describes the window that just ended. Once reset has
    # passed, the new balance is unknown until observed; never keep harvesting
    # a historical allowance.
    if reset_h is not None and reset_h <= 0:
        return {"flow": "stale", "remaining_pct": remaining,
                "observed_at": obs.get("observed_at"),
                "reset_at": iso(reset), "reset_hours": 0.0}
    if remaining <= 0:
        flow = "exhausted"
    elif reset_h is not None and reset_h <= policy["harvest_within_hours"]:
        flow = "harvest"
    elif remaining <= policy["reserve_below_pct"]:
        flow = "reserve"
    else:
        flow = "spend"
    out = {"flow": flow, "remaining_pct": round(remaining, 1),
           "observed_at": obs.get("observed_at")}
    if reset:
        out["reset_at"] = iso(reset)
        out["reset_hours"] = round(reset_h, 1)
        out["required_burn_pct_per_hour"] = round(remaining / max(reset_h, .25), 2)
    return out


def run(cmd, timeout=PROBE_TIMEOUT):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 1, "timeout"
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
    code, out = run([chat.resolve("hermes"), "status"],
                    timeout=HERMES_STATUS_TIMEOUT)
    hits = recent_quota_hits("hermes")
    row["quota_errors_24h"] = hits
    if hits:
        row["auth"] = "logged-in"
        row["ok"] = False
        row["note"] = f"quota-shaped errors in last {WINDOW_HOURS}h"
        return row
    # "not logged in" contains the substring "logged in". Nous being
    # logged-out used to make Codex look logged-in; a timeout used to
    # make Codex look logged-out. Both became "vendor dry".
    if out.strip() == "timeout" or "timed out" in out.lower():
        row["auth"] = "unknown"
        row["ok"] = True
        row["note"] = "status timed out"
        return row
    if HERMES_CODEX_RE.search(out):
        row["auth"] = "logged-in"
        row["ok"] = True
        row["note"] = "codex"
        return row
    # NUC runs hermes against a local/custom endpoint. Codex not
    # logged in used to mark that box "scheduled logged out" and
    # skip a working agent (pong in 2026-08-21).
    if HERMES_CUSTOM_RE.search(out):
        row["auth"] = "logged-in"
        row["ok"] = True
        row["note"] = "custom endpoint"
        return row
    row["auth"] = "logged-out"
    row["ok"] = False
    row["note"] = "not logged in"
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


def check_agy():
    """Binary + credentials dir. Never call ask_agy."""
    row = {"agent": "agy", "vendor": vendors.vendor("agy"),
           "binary": chat._agent_ready("agy")}
    if not row["binary"]:
        row["ok"] = False
        row["auth"] = "missing"
        row["note"] = "CLI not on PATH"
        return row
    creds = Path.home() / ".gemini" / "antigravity-cli"
    logged_in = creds.is_dir()
    row["auth"] = "logged-in" if logged_in else "logged-out"
    hits = recent_quota_hits("agy")
    row["quota_errors_24h"] = hits
    if hits:
        row["ok"] = False
        row["note"] = f"quota-shaped errors in last {WINDOW_HOURS}h"
    elif not logged_in:
        row["ok"] = False
        row["note"] = "not logged in"
    else:
        row["ok"] = True
        row["note"] = "google"
    return row


CHECKS = {
    "ollama": check_ollama,
    "claude": check_claude,
    "hermes": check_hermes,
    "grok": check_grok,
    "openclaw": check_openclaw,
    "agy": check_agy,
}


def public_row(row):
    """Fields safe for /workers.json. No emails, paths, tokens."""
    keep = ("agent", "vendor", "binary", "auth", "ok", "note",
            "plan", "quota_errors_24h", "spend", "flow", "remaining_pct",
            "observed_at", "reset_at", "reset_hours",
            "required_burn_pct_per_hour")
    return {k: row[k] for k in keep if k in row}


def spend_of(agent, cfg=None):
    """plenty spends scheduled turns. rare is held unless nobody else is up."""
    cfg = load_config() if cfg is None else cfg
    return ((cfg.get("quotas") or {}).get("spend") or {}).get(agent, "plenty")


def effective_spend(agent, row, cfg=None):
    """Fresh capacity can override the static fallback; unknown data cannot."""
    flow = (row or {}).get("flow")
    if flow in ("exhausted", "reserve"):
        return "rare"
    if flow in ("harvest", "spend"):
        return "plenty"
    return spend_of(agent, cfg)


def last_pulse_rows():
    try:
        w = json.loads(WORKER.read_text())
        detail = json.loads(w.get("detail") or "{}")
        return {r["agent"]: r for r in detail.get("vendors") or []
                if isinstance(r, dict) and r.get("agent")}
    except (OSError, ValueError, TypeError):
        return {}


def eligible(requested, cfg=None, rows=None, quorum=False):
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
        if row is not None and (not row.get("ok")
                                or row.get("flow") == "exhausted"):
            continue
        live.append(a)
    plentiful = [a for a in live if effective_spend(a, rows.get(a), cfg) != "rare"]
    chosen = plentiful or live

    # quorum=True: spend a rare turn rather than lose the second company.
    #
    # Only the callers that CANNOT work single-vendor ask for this, because
    # overriding thrift by default would quietly spend the tight plans that
    # `rare` exists to protect. The council refuses to sit with one
    # participant; the pipeline's reviewer must work for a different company
    # than the builder. On 2026-08-26 hermes was the only agent marked
    # plenty, so both failed silently, hourly, for three weeks -- while
    # every agent reported healthy, which is why nothing caught it.
    #
    # One rare agent per missing vendor: the cheapest quorum there is.
    have = {vendors.vendor(a) for a in chosen}
    if quorum and len(have) < 2:
        for a in live:
            if a in chosen:
                continue
            v = vendors.vendor(a)
            if v not in have:
                chosen = chosen + [a]
                have.add(v)
                if len(have) >= 2:
                    break
    # Fruit nearest ripeness first: quota about to reset has the highest
    # required burn rate. Stable sorting preserves configured order otherwise.
    return sorted(chosen, key=lambda a: (
        (rows.get(a) or {}).get("flow") == "harvest",
        (rows.get(a) or {}).get("required_burn_pct_per_hour", 0),
    ), reverse=True)


def pulse(cfg=None):
    cfg = cfg if cfg is not None else load_config()
    scheduled = scheduled_agents(cfg)
    rows = []
    observations = load_capacity()
    for name, fn in CHECKS.items():
        raw = fn()
        raw["spend"] = spend_of(name, cfg)
        raw.update(capacity_fields(name, observations=observations, cfg=cfg))
        rows.append(public_row(raw))
    by_name = {r["agent"]: r for r in rows}

    down_scheduled = [a for a in scheduled
                      if (not by_name.get(a, {}).get("ok")
                          or by_name.get(a, {}).get("flow") == "exhausted")]
    dry = [a for a in down_scheduled
           if (by_name.get(a, {}).get("quota_errors_24h")
               or by_name.get(a, {}).get("flow") == "exhausted")]
    logged_out = [a for a in down_scheduled if a not in dry]
    held = [r["agent"] for r in rows if r.get("spend") == "rare"]
    spending = eligible(scheduled, cfg=cfg, rows=by_name)

    # Quorum. Every integrity claim this fleet makes rests on more than one
    # company being in the room: the council refuses to sit with fewer than
    # two participants, and the pipeline's whole promise is that the agent
    # who reviews a diff works for a different vendor than the one who wrote
    # it. One vendor is not a fleet, it is a model with a cron job.
    #
    # Nothing watched for this until 2026-08-26, and the cost was three
    # weeks: on the NUC, grok reported ok=True with the note "session
    # expired" and agy reported ok=True as "google" -- neither was DOWN, so
    # neither tripped the logged-out alert. They were merely `rare`, and
    # eligible() prefers a plentiful vendor whenever one exists, so hermes
    # took 40 rota turns out of 40 while the council logged "needs at least
    # two participants, got 1" every three hours and nobody was told.
    #
    # Held is not down, which is why this counts VENDORS AMONG THE ELIGIBLE
    # rather than agents among the healthy. hermes and openclaw are both
    # OpenAI: two agents, one company, no quorum.
    # Only a roster that INTENDS several companies can lose quorum. An
    # operator who deliberately schedules one agent has made a choice, and a
    # monitor that nags about a choice gets muted, taking the real alarms
    # with it.
    rostered_vendors = {vendors.vendor(a) for a in scheduled}

    # Ask what the fleet can REACH, not what it is currently spending.
    #
    # `spending` is the thrift view: who takes a turn when a cheap vendor can
    # cover it. The council does not live in that view -- it asks for quorum
    # and gets a rare agent admitted. Alerting on the thrift view therefore
    # said "council cannot sit" while the council was sitting fine, which is
    # a monitor arguing with the mechanism it monitors. Whoever reads that
    # twice stops reading the board.
    #
    # Adapt first, alert only when adaptation is exhausted: this fires when
    # even quorum mode cannot find a second company -- everyone else logged
    # out, dry, or off the roster. That is the state a human must fix, and
    # it is the only one worth waking up for.
    reachable = eligible(scheduled, cfg=cfg, rows=by_name, quorum=True)
    quorum_vendors = sorted({vendors.vendor(a) for a in reachable})
    no_quorum = len(rostered_vendors) >= 2 and len(quorum_vendors) < 2

    if dry:
        status = "alert"
        summary = "scheduled dry: " + ", ".join(dry)
    elif logged_out:
        status = "alert"
        summary = "scheduled logged out: " + ", ".join(logged_out)
    elif [r["agent"] for r in rows if r.get("quota_errors_24h")]:
        status = "warn"
        summary = "quota-shaped errors: " + ", ".join(
            r["agent"] for r in rows if r.get("quota_errors_24h"))
    elif no_quorum:
        # Last, on purpose. "grok is out of credit" tells you what to do;
        # "no quorum" is the consequence of that, and a consequence that
        # hides its cause is a worse alert than no alert. This branch is for
        # the case with no named cause at all -- everyone healthy, everyone
        # held -- which is precisely the state nothing was watching for.
        status = "alert"
        only = quorum_vendors[0] if quorum_vendors else "nobody"
        summary = (f"no vendor quorum — {len(rostered_vendors)} companies "
                   f"rostered, only {only} can spend a turn "
                   f"({', '.join(spending) or 'no agents eligible'}); "
                   f"council cannot sit and the pipeline cannot review "
                   f"across vendors")
    else:
        status = "pass"
        bits = [f"{a} {by_name[a].get('flow', 'unknown')}" for a in spending
                if a in by_name]
        hold = f" · holding {', '.join(held)}" if held else ""
        # Name the reserve. "holding grok, agy" reads as absence; what it
        # actually means is that a second company is one call away whenever
        # the council needs one. A held agent that quorum can reach is
        # capacity, not a gap, and the board should say which it is.
        reserve = [a for a in reachable if a not in spending]
        ready = f" · quorum ready via {', '.join(reserve)}" if reserve else ""
        summary = (("spending " + " · ".join(bits) + hold + ready)
                   if bits else "no vendors")

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
    # What main() escalates on. A lost quorum has to be in here or the alert
    # is a colour on a card nobody is looking at -- which is exactly how the
    # fleet ran single-vendor for three weeks.
    needs_you = list(down_scheduled)
    if no_quorum:
        needs_you = needs_you or ["quorum"]
    return worker, needs_you


def publish(worker):
    WORKER.parent.mkdir(parents=True, exist_ok=True)
    WORKER.write_text(json.dumps(worker, indent=2) + "\n")
    return worker


def _previous_card():
    try:
        old = json.loads(WORKER.read_text())
        return old.get("status"), old.get("summary")
    except (OSError, ValueError):
        return None, None


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command")
    observe = sub.add_parser("observe", help="record a quota reading")
    observe.add_argument("agent")
    observe.add_argument("remaining_pct", type=float)
    reset = observe.add_mutually_exclusive_group()
    reset.add_argument("--resets-at")
    reset.add_argument("--resets-in-hours", type=float)
    observe.add_argument("--source", default="manual")
    args = ap.parse_args(argv)
    if args.command == "observe":
        reset_at = parse_time(args.resets_at)
        if args.resets_at and reset_at is None:
            ap.error("--resets-at must be ISO-8601")
        if args.resets_in_hours is not None:
            reset_at = now() + timedelta(hours=args.resets_in_hours)
        print(json.dumps(save_observation(args.agent, args.remaining_pct,
                                          reset_at, args.source), indent=2))
        return 0
    prev_status, prev_summary = _previous_card()
    worker, down = pulse()
    publish(worker)
    # Same card every five minutes is not a new emergency. The medic
    # used to ding needs_you on a loop and the stream drowned in it.
    same = (worker["status"] == prev_status
            and worker["summary"] == prev_summary)
    if not same:
        if down:
            why = worker["summary"]
            ev.emit("quotas", "needs_you",
                    f"[quotas] {why} — top up, log in, or take them "
                    f"off the roster")
        else:
            ev.emit("quotas", "ok", f"[quotas] {worker['summary']}"[:400])
    print(worker["summary"])
    return 0 if worker["status"] != "alert" else 1


if __name__ == "__main__":
    raise SystemExit(main())
