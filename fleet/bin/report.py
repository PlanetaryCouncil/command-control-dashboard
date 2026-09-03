#!/usr/bin/env python3
"""What the fleet did in the last 24 hours, in three formats.

  report.py                 human-readable text, to stdout
  report.py --json          the same facts as JSON
  report.py --markdown      the same facts as Markdown
  report.py --html          the same facts as a standalone page
  report.py --publish DIR   write all three into DIR, for GitHub Pages

Why this exists: the fleet runs all night and the only record is a stream
nobody scrolls back through. On 2026-09-03 it turned out that nothing had been
built for two days, the heartbeat had been dead for 31 hours and the watchdog
tier had never run on the NUC at all -- three failures, each of them visible in
some log, none of them visible anywhere a person actually looks. A report is
how a quiet failure becomes a loud one.

One rule throughout: **count, do not narrate.** Every number here comes from a
file the fleet wrote while working, and a section with nothing in it says so
rather than being omitted. A report that only appears when things went well is
an advert, and this project has enough of those.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
REPO = FLEET.parent

WINDOW_HOURS = 24

# The three sites, and the org that builds each one. Named here rather than in
# the template because the report is also published as JSON, and a reader
# parsing it should get the same pairing a reader looking at it does.
PARTNERSHIP = [
    ("PlanetaryCouncil.org", "https://planetarycouncil.org",
     "https://github.com/PlanetaryCouncil", "decides"),
    ("IndependentTribunal.org", "https://independenttribunal.org",
     "https://github.com/independenttribunal", "contests"),
    ("BaseX.com", "https://demo.basex.com",
     "https://github.com/basexhq", "deploys"),
]

TAGLINE = "We truly build a new civilisation."


def now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _jsonl(path: Path) -> list[dict]:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _recent(rows: list[dict], since: datetime, key="ts") -> list[dict]:
    out = []
    for r in rows:
        t = _parse(r.get(key))
        if t and t >= since:
            out.append(r)
    return out


def _git(args: list[str]) -> str:
    import subprocess
    try:
        r = subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                           text=True, timeout=20)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def collect(hours: int = WINDOW_HOURS) -> dict:
    """Every number in the report, gathered once."""
    since = now() - timedelta(hours=hours)

    # --- what was committed ---------------------------------------------
    log = _git(["log", f"--since={since.isoformat()}",
                "--pretty=%H%x1f%an%x1f%aI%x1f%s"])
    commits = []
    for line in log.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 4:
            commits.append({"sha": parts[0][:8], "author": parts[1],
                            "at": parts[2], "subject": parts[3]})

    # --- what the pipeline decided ---------------------------------------
    pipe = _recent(_jsonl(FLEET / "rota" / "pipeline.jsonl"), since)
    stages: dict[str, dict[str, int]] = {}
    for r in pipe:
        st = str(r.get("stage") or "?")
        bucket = stages.setdefault(st, {"ok": 0, "failed": 0})
        bucket["ok" if r.get("ok") else "failed"] += 1

    # --- what the fleet said ----------------------------------------------
    events = _recent(_jsonl(FLEET / "events.jsonl"), since)
    by_agent: dict[str, int] = {}
    for e in events:
        a = str(e.get("agent") or "?")
        by_agent[a] = by_agent.get(a, 0) + 1
    levels: dict[str, int] = {}
    for e in events:
        lv = str(e.get("level") or "info")
        levels[lv] = levels.get(lv, 0) + 1

    # Things that asked for a person. These are the report's headline: an
    # unanswered needs_you is the fleet saying it is stuck.
    attention = [{"at": e.get("ts"), "agent": e.get("agent"),
                  "msg": str(e.get("msg", ""))[:200]}
                 for e in events if e.get("level") == "needs_you"][-10:]

    # --- who is up ---------------------------------------------------------
    workers = []
    for f in sorted((FLEET / "workers").glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        workers.append({"worker": d.get("worker", f.stem),
                        "status": d.get("status", "?"),
                        "last_run": d.get("last_run"),
                        "summary": str(d.get("summary", ""))[:160]})

    # --- proposals still waiting -------------------------------------------
    proposals = _jsonl(FLEET / "rota" / "proposals.jsonl")

    return {
        "generated_at": now().isoformat(timespec="seconds"),
        "window_hours": hours,
        "since": since.isoformat(timespec="seconds"),
        "partnership": [{"site": s, "url": u, "github": g, "role": r}
                        for s, u, g, r in PARTNERSHIP],
        "tagline": TAGLINE,
        "commits": {"count": len(commits), "list": commits[:40]},
        "pipeline": {"records": len(pipe), "stages": stages},
        "events": {"count": len(events), "by_level": levels,
                   "by_agent": dict(sorted(by_agent.items(),
                                           key=lambda kv: -kv[1])[:12])},
        "needs_you": attention,
        "workers": workers,
        "proposals_total": len(proposals),
    }


# --------------------------------------------------------------------------
# Renderings. Same facts, three audiences: a person in a terminal, a person in
# a browser, and a program.
# --------------------------------------------------------------------------

def _headline(d: dict) -> str:
    """The one sentence that says whether the day was any good.

    Deliberately blunt about nothing happening. The first draft said "a quiet
    day"; a fleet that built nothing for two days is not quiet, it is broken,
    and a report that cannot say so is decoration.
    """
    c = d["commits"]["count"]
    n = len(d["needs_you"])
    if c == 0:
        return ("Nothing was merged in the last "
                f"{d['window_hours']} hours.")
    return (f"{c} commit{'s' if c != 1 else ''} merged in the last "
            f"{d['window_hours']} hours"
            + (f", and {n} thing{'s' if n != 1 else ''} asked for a person."
               if n else "."))


def as_text(d: dict) -> str:
    L = [f"THE FLEET — LAST {d['window_hours']} HOURS",
         d["generated_at"], "", _headline(d), ""]
    L.append(f"commits           {d['commits']['count']}")
    for c in d["commits"]["list"][:10]:
        L.append(f"  {c['sha']}  {c['subject'][:64]}")
    L.append("")
    L.append(f"pipeline records  {d['pipeline']['records']}")
    for st, b in sorted(d["pipeline"]["stages"].items()):
        L.append(f"  {st:<10} ok {b['ok']:<4} failed {b['failed']}")
    if not d["pipeline"]["stages"]:
        L.append("  nothing — the pipeline recorded no decisions")
    L.append("")
    L.append(f"events            {d['events']['count']}")
    for lv, n in sorted(d["events"]["by_level"].items()):
        L.append(f"  {lv:<10} {n}")
    L.append("")
    L.append("needs you")
    for a in d["needs_you"] or []:
        L.append(f"  {str(a['at'])[:19]}  {a['agent']}: {a['msg'][:70]}")
    if not d["needs_you"]:
        L.append("  nothing")
    L.append("")
    L.append("workers")
    for w in d["workers"]:
        L.append(f"  {w['worker']:<16} {w['status']:<6} {w['summary'][:60]}")
    L.append("")
    L.append("the partnership")
    for p in d["partnership"]:
        L.append(f"  {p['site']:<26} {p['role']:<9} {p['github']}")
    L.append("")
    L.append(d["tagline"])
    return "\n".join(L) + "\n"


def as_markdown(d: dict) -> str:
    L = [f"# The fleet — last {d['window_hours']} hours", "",
         f"*{d['generated_at']}*", "", f"**{_headline(d)}**", ""]
    L += ["## Merged", ""]
    if d["commits"]["list"]:
        L.append("| commit | subject |")
        L.append("|---|---|")
        for c in d["commits"]["list"][:20]:
            L.append(f"| `{c['sha']}` | {c['subject'][:80]} |")
    else:
        L.append("Nothing.")
    L += ["", "## Pipeline", ""]
    if d["pipeline"]["stages"]:
        L.append("| stage | ok | failed |")
        L.append("|---|---:|---:|")
        for st, b in sorted(d["pipeline"]["stages"].items()):
            L.append(f"| {st} | {b['ok']} | {b['failed']} |")
    else:
        L.append("No decisions recorded.")
    L += ["", "## Asked for a person", ""]
    if d["needs_you"]:
        for a in d["needs_you"]:
            L.append(f"- `{str(a['at'])[:19]}` **{a['agent']}** — {a['msg']}")
    else:
        L.append("Nothing.")
    L += ["", "## Workers", "", "| worker | status | summary |", "|---|---|---|"]
    for w in d["workers"]:
        L.append(f"| {w['worker']} | {w['status']} | {w['summary'][:90]} |")
    L += ["", "## The partnership", ""]
    for p in d["partnership"]:
        L.append(f"- **[{p['site']}]({p['url']})** {p['role']} — "
                 f"source: [{p['github'].split('github.com/')[-1]}]({p['github']})")
    L += ["", f"*{d['tagline']}*", ""]
    return "\n".join(L)


def as_html(d: dict) -> str:
    e = html.escape

    def rows(pairs):
        return "".join(f"<tr><td>{e(str(a))}</td><td>{e(str(b))}</td></tr>"
                       for a, b in pairs)

    commits = "".join(
        f"<tr><td><code>{e(c['sha'])}</code></td><td>{e(c['subject'][:90])}</td></tr>"
        for c in d["commits"]["list"][:20]) or \
        '<tr><td colspan="2" class="none">nothing</td></tr>'
    stages = rows((f"{st} — ok {b['ok']}, failed {b['failed']}", "")
                  for st, b in sorted(d["pipeline"]["stages"].items())) or \
        '<tr><td colspan="2" class="none">no decisions recorded</td></tr>'
    attention = "".join(
        f"<tr><td>{e(str(a['at'])[:19])}</td>"
        f"<td><b>{e(str(a['agent']))}</b> {e(a['msg'])}</td></tr>"
        for a in d["needs_you"]) or \
        '<tr><td colspan="2" class="none">nothing</td></tr>'
    workers = "".join(
        f"<tr><td>{e(w['worker'])}</td>"
        f"<td><span class='s {e(w['status'])}'>{e(w['status'])}</span> "
        f"{e(w['summary'][:100])}</td></tr>" for w in d["workers"])
    partners = "".join(
        f"<li><a href='{e(p['url'])}'>{e(p['site'])}</a> {e(p['role'])} "
        f"&mdash; <a href='{e(p['github'])}'>"
        f"{e(p['github'].split('github.com/')[-1])}</a></li>"
        for p in d["partnership"])

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The fleet &mdash; last {d['window_hours']} hours</title>
<style>
:root{{color-scheme:dark;--ink:#e6e6e6;--muted:#8a8f98;--line:#26292e;
  --bg:#0d0f12;--surface:#14171b;--good:#5ac27a;--warn:#e0a44a;--bad:#e05a5a}}
body{{margin:0;background:var(--bg);color:var(--ink);
  font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;padding:24px}}
main{{max-width:900px;margin:0 auto}}
h1{{font-size:17px;letter-spacing:.06em;margin:0 0 2px}}
h2{{font-size:11px;letter-spacing:.14em;text-transform:uppercase;
  color:var(--muted);margin:26px 0 6px;border-bottom:1px solid var(--line);
  padding-bottom:4px}}
.when{{color:var(--muted);font-size:11px}}
.head{{margin:14px 0 0;padding:10px 12px;background:var(--surface);
  border-left:2px solid var(--good);border-radius:3px}}
table{{width:100%;border-collapse:collapse}}
td{{padding:3px 8px 3px 0;vertical-align:top;border-bottom:1px solid var(--line)}}
td:first-child{{color:var(--muted);white-space:nowrap;width:1%}}
.none{{color:var(--muted);font-style:italic}}
.s{{font-weight:700}} .s.pass{{color:var(--good)}} .s.alert{{color:var(--bad)}}
.s.warn{{color:var(--warn)}} .s.fail{{color:var(--bad)}}
ul{{padding-left:18px}} a{{color:#6aa9ff}}
footer{{margin-top:30px;color:var(--muted);font-size:11px;
  border-top:1px solid var(--line);padding-top:10px}}
</style></head><body><main>
<h1>The fleet &mdash; last {d['window_hours']} hours</h1>
<div class="when">{e(d['generated_at'])}</div>
<p class="head">{e(_headline(d))}</p>

<h2>merged</h2><table>{commits}</table>
<h2>pipeline</h2><table>{stages}</table>
<h2>asked for a person</h2><table>{attention}</table>
<h2>workers</h2><table>{workers}</table>
<h2>the partnership</h2><ul>{partners}</ul>

<footer>{e(d['tagline'])} &middot;
Machine-readable: <a href="report.json">report.json</a> &middot;
<a href="report.md">report.md</a></footer>
</main></body></html>
"""


def publish(d: dict, out: Path) -> list[Path]:
    """Write all three into a directory, for GitHub Pages.

    index.html as well as report.html: a Pages directory whose only entry is
    a named file is a directory that 404s at its own address.
    """
    out.mkdir(parents=True, exist_ok=True)
    page = as_html(d)
    written = []
    for name, body in (("report.json", json.dumps(d, indent=2) + "\n"),
                       ("report.md", as_markdown(d)),
                       ("report.html", page),
                       ("index.html", page)):
        f = out / name
        f.write_text(body)
        written.append(f)
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--html", action="store_true")
    ap.add_argument("--hours", type=int, default=WINDOW_HOURS)
    ap.add_argument("--publish", metavar="DIR")
    a = ap.parse_args(argv)

    d = collect(a.hours)
    if a.publish:
        for f in publish(d, Path(a.publish)):
            print(f)
        return 0
    if a.json:
        print(json.dumps(d, indent=2))
    elif a.markdown:
        print(as_markdown(d))
    elif a.html:
        print(as_html(d))
    else:
        print(as_text(d), end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
