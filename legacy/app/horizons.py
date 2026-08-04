"""The horizon chain: 10y → 1y → quarter → month → week → day → hour → now.

The point of the ladder is not eight lists. It is one thread. If `now` cannot be
traced up to `10y`, the ladder is decorative — so the only real logic here is
finding the breaks.
"""

from __future__ import annotations

from datetime import datetime, timezone

# Ordered widest → narrowest. Order is the parent relationship.
SCALES = ["10y", "1y", "quarter", "month", "week", "day", "hour", "now"]

LABELS = {
    "10y": "10 years",
    "1y": "1 year",
    "quarter": "quarter",
    "month": "month",
    "week": "week",
    "day": "today",
    "hour": "this hour",
    "now": "right now",
}


def elapsed_minutes(started_at: str | None, now: datetime | None = None) -> int | None:
    if not started_at:
        return None
    now = now or datetime.now(timezone.utc)
    try:
        then = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return max(0, int((now - then).total_seconds() // 60))


def chain(levels: list[dict], now: datetime | None = None) -> list[dict]:
    """Return every scale in order, marking the ones that are empty.

    Missing scales are included rather than skipped: a blank `week` between a
    filled `month` and a filled `day` is the finding, not something to hide.
    """
    by_scale = {level.get("scale"): level for level in levels}
    out = []
    for i, scale in enumerate(SCALES):
        level = dict(by_scale.get(scale) or {})
        goal = (level.get("goal") or "").strip()
        level.update(
            scale=scale,
            label=LABELS[scale],
            depth=i,
            goal=goal,
            gap=not goal,
        )
        if scale == "now":
            level["elapsed_min"] = elapsed_minutes(level.get("started_at"), now)
        out.append(level)
    return out


def integrity(levels: list[dict]) -> dict:
    """Is the thread unbroken from now up to 10y?"""
    links = chain(levels)
    gaps = [level["scale"] for level in links if level["gap"]]
    return {
        "intact": not gaps,
        "gaps": gaps,
        "filled": len(links) - len(gaps),
        "total": len(links),
    }


def focus_line(levels: list[dict]) -> str:
    """One sentence tracing the thread, for /boot and for agents."""
    links = {level["scale"]: level for level in chain(levels)}
    now = links["now"]["goal"] or "(nothing set)"
    day = links["day"]["goal"] or "(no day goal)"
    year = links["1y"]["goal"] or "(no year goal)"
    return f"now: {now} — serving today: {day} — serving the year: {year}"
