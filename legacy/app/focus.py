"""Focus scoring and staleness.

Pure functions over plain dicts so they stay testable without the web layer.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Weights from PROJECT_DASHBOARD_SPEC.md, formula v0.
WEIGHTS = {
    "strategic_priority": 3,
    "deadline_urgency": 2,
    "opportunity_value": 2,
    "blocker_severity": 2,
    "momentum": 1,
    "attention_signal": 1,
    "agent_readiness": 1,
    "energy_fit": 1,
}

# blocker_severity counts *positively*: a badly blocked project needs a human
# more urgently than a smoothly running one. The radar ranks "what needs you",
# not "what is going well".

STATUS_PENALTY = {
    "active": 0,
    "warming": 0,
    "blocked": 0,
    "paused": 10,
    "archived": 999,
}

STALE_DAYS_WARN = 14


def score(project: dict) -> int:
    raw = sum(w * int(project.get(k, 0)) for k, w in WEIGHTS.items())
    return raw - STATUS_PENALTY.get(project.get("status", "active"), 0)


def stale_days(project: dict, now: datetime | None = None) -> int | None:
    """Whole days since last_touched. None when the project has never been touched."""
    touched = project.get("last_touched")
    if not touched:
        return None
    now = now or datetime.now(timezone.utc)
    try:
        then = datetime.fromisoformat(touched.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0, (now - then).days)


def enrich(project: dict, now: datetime | None = None) -> dict:
    """Return a copy with derived fields filled in."""
    out = dict(project)
    out["focus_score"] = score(project)
    days = stale_days(project, now)
    out["stale_days"] = days
    out["is_stale"] = days is not None and days >= STALE_DAYS_WARN
    return out


def radar(projects: list[dict], now: datetime | None = None) -> list[dict]:
    """Enriched projects, highest focus first, archived dropped."""
    live = [p for p in projects if p.get("status") != "archived"]
    return sorted(
        (enrich(p, now) for p in live),
        key=lambda p: p["focus_score"],
        reverse=True,
    )
