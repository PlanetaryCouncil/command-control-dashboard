#!/usr/bin/env python3
"""What happened while you were asleep, in one screen.

The fleet runs six scheduled jobs overnight and every one of them reports into
a different place — `events.jsonl`, a git branch, `rota/proposals.jsonl`, a
CHANGELOG. Reading them all is the reason a night's work goes unread. This
collapses them into one page with a fixed shape: what needs you, then what ran,
then nothing else.

The ordering is the whole design. `NEEDS YOU` is first because it is the only
section that costs you anything to miss. `RAN` is a receipt — skim it or don't.
Anything that is merely interesting does not get a section, because a briefing
that grows is a briefing that stops being read.

    python3 fleet/bin/morning.py            # print it
    python3 fleet/bin/morning.py --write    # also write fleet/MORNING.md
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
REPO = FLEET.parent
WINDOW_HOURS = 14


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _git(*args):
    try:
        r = subprocess.run(["git", "-C", str(REPO), *args],
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def recent_events(hours=WINDOW_HOURS):
    path = FLEET / "events.jsonl"
    if not path.exists():
        return []
    cutoff = _now() - timedelta(hours=hours)
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        ts = _parse(e.get("ts"))
        if ts and ts >= cutoff:
            out.append(e)
    return out


def needs_you(events):
    """A `needs_you` stands until the same agent reports ok afterwards.

    Same rule the fleet board uses: an alarm must survive later chatter from
    other agents, or a busy night silently clears a standing request.
    """
    raised = {}
    for e in events:
        agent, level = e.get("agent", ""), e.get("level", "")
        if level == "needs_you":
            raised[agent] = e
        elif level == "ok" and agent in raised:
            del raised[agent]
    return list(raised.values())


def open_branches():
    """Self-improve branches that exist but were never merged into main."""
    names = [b.strip().lstrip("* ") for b in _git("branch", "--list",
             "self-improve/*", "--sort=-committerdate").splitlines() if b.strip()]
    out = []
    for name in names[:5]:
        if _git("branch", "--contains", name, "--list", "main"):
            continue                      # already in main, nothing to review
        subject = _git("log", "-1", "--format=%s", name)
        stat = _git("diff", "--shortstat", f"main...{name}")
        out.append((name, subject, stat))
    return out


def rota_proposals(hours=WINDOW_HOURS):
    path = FLEET / "rota" / "proposals.jsonl"
    if not path.exists():
        return []
    cutoff = _now() - timedelta(hours=hours)
    out = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            p = json.loads(line)
        except ValueError:
            continue
        ts = _parse(p.get("ts"))
        if ts and ts >= cutoff:
            out.append(p)
    return out


def open_signals():
    """Messages from strangers that nobody has answered.

    These arrive on the cockpit and log `signal.received` into
    `data/events.jsonl` — a different file from the fleet's, which is why
    nothing here ever mentioned them. Codex wrote twice on 2026-08-03 asking
    whether any agent could see its message, and the honest answer was that
    the only surface reporting anything was not reading that inbox.

    A stranger waiting on a reply is the definition of NEEDS YOU: it decays,
    and nothing else in the system will raise it.
    """
    path = REPO / "data" / "inbox.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(errors="replace"))
    except ValueError:
        return []
    return [s for s in data.get("signals", [])
            if s.get("status") == "new" and not (s.get("response") or "").strip()]


def first_line(text, limit=88):
    """First line that says something.

    The agents follow the same house style as this repo's operator-facing
    output, so their replies open with an 80-block `█` rule and often a
    markdown heading. Taking `splitlines()[0]` verbatim rendered every
    proposal in the briefing as an identical wall of blocks — a summary column
    that summarised nothing. Skip the furniture and take the first line with
    prose in it.
    """
    for raw in (text or "").splitlines():
        # Some agents return the whole reply as one line, bar and all, so the
        # rule has to be stripped from within a line and not just skipped.
        line = raw.strip().lstrip("█").strip()
        if not line or line.startswith("#"):
            continue                      # heading: names the section, not the point
        if set(line) <= set("█━─-=_* "):
            continue                      # a rule, not a sentence
        return line[:limit] + ("…" if len(line) > limit else "")
    return ""


def render():
    events = recent_events()
    alarms = needs_you(events)
    branches = open_branches()
    proposals = rota_proposals()
    signals = open_signals()

    L = []
    stamp = _now().strftime("%Y-%m-%d %H:%M UTC")
    L.append(f"# Morning — {stamp}")
    L.append("")
    L.append(f"Last {WINDOW_HOURS}h: {len(events)} events, {len(alarms)} unresolved, "
             f"{len(branches)} branch(es) waiting, {len(proposals)} proposal(s), "
             f"{len(signals)} unanswered message(s).")
    L.append("")

    L.append("## NEEDS YOU")
    L.append("")
    if not alarms and not branches and not signals:
        L.append("Nothing. The fleet handled its own night.")
    # Strangers first. A branch waits indefinitely without complaining; a person
    # or an agent that wrote to you is the only item here with someone on the
    # other end of it.
    for s in signals:
        L.append(f"- **{s.get('sender', '?')}** asks "
                 f"({s.get('received_at', '')[:16].replace('T', ' ')}) — "
                 f"{first_line(s.get('body'), 76)}")
        L.append(f"  `{s.get('id', '')}` · unanswered")
    for e in alarms:
        L.append(f"- **{e.get('agent', '?')}** — {first_line(e.get('msg'))}")
    for name, subject, stat in branches:
        L.append(f"- **{name}**")
        L.append(f"  {subject}")
        if stat:
            L.append(f"  `{stat.strip()}`")
        L.append(f"  `git diff main...{name}`")
    L.append("")

    L.append("## RAN")
    L.append("")
    by_agent = {}
    for e in events:
        by_agent.setdefault(e.get("agent", "?"), []).append(e)
    if not by_agent:
        L.append("Nothing logged. Either it was quiet or the fleet is not running.")
    for agent in sorted(by_agent):
        rows = by_agent[agent]
        last = rows[-1]
        when = (_parse(last.get("ts")) or _now()).strftime("%H:%M")
        L.append(f"- `{when}` **{agent}** ×{len(rows)} — {first_line(last.get('msg'), 70)}")
    L.append("")

    if proposals:
        L.append("## PROPOSED")
        L.append("")
        for p in proposals:
            when = (_parse(p.get("ts")) or _now()).strftime("%H:%M")
            L.append(f"- `{when}` **{p.get('agent', '?')}** "
                     f"({p.get('outcome', '?')}) — {first_line(p.get('text'), 78)}")
        L.append("")

    return "\n".join(L)


if __name__ == "__main__":
    page = render()
    print(page)
    if "--write" in sys.argv:
        out = FLEET / "MORNING.md"
        out.write_text(page + "\n")
        print(f"\n[wrote {out}]", file=sys.stderr)
