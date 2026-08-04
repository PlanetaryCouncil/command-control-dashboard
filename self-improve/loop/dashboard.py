#!/usr/bin/env python3
"""Render the loop's state as a standalone HTML dashboard.

Run with --fragment to emit body-content only (for publishing as an Artifact);
default emits a full standalone document for opening locally.
"""

import html
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE = REPO / "state"


def esc(x):
    return html.escape(str(x), quote=True)


def read_lines(p):
    try:
        return [l for l in (REPO / p).read_text(errors="replace").splitlines() if l.strip()]
    except OSError:
        return []


def read_jsonl(p):
    out = []
    for line in read_lines(p):
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return out


def sh(cmd):
    try:
        r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=10)
        return r.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def collect():
    cycles = read_lines("state/cycles.log")
    applied = read_jsonl("state/applied.jsonl")
    rejected = read_jsonl("state/rejected.jsonl")
    violations = read_lines("state/violations.log")

    try:
        obs = json.loads((STATE / "observations.json").read_text())
    except (OSError, json.JSONDecodeError):
        obs = {}

    commits = []
    for line in sh(["git", "log", "--pretty=format:%h|%ad|%s",
                    "--date=format:%Y-%m-%d %H:%M", "-25"]).splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            commits.append({"sha": parts[0], "date": parts[1], "subject": parts[2]})

    scheduled = "re.genesis.self-improve" in sh(["launchctl", "list"])

    skills = sorted(p.name for p in (REPO / "claude" / "skills").glob("*") if p.is_dir())
    agents = sorted(p.stem for p in (REPO / "claude" / "agents").glob("*.md"))

    last = cycles[-1] if cycles else ""
    m = re.match(r"(\S+)\s+(.*)", last)
    last_run = m.group(1) if m else "never"

    return {
        "cycles": cycles, "applied": applied, "rejected": rejected,
        "violations": violations, "obs": obs, "commits": commits,
        "scheduled": scheduled, "skills": skills, "agents": agents,
        "last_run": last_run,
    }


CSS = """
:root{
  --ground:#F4F6F8; --surface:#FFFFFF; --raised:#EDF0F3;
  --border:#DCE1E7; --ink:#171B21; --ink-2:#414B58; --muted:#5C6674;
  --accent:#8A5B12; --accent-soft:#F0E4CE;
  --good:#2F7A63; --good-soft:#DDEDE7;
  --hold:#8A5B12; --hold-soft:#F0E4CE;
  --crit:#A83A26; --crit-soft:#F6DED8;
  --bar-track:#E4E8EC;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{
    --ground:#0F1216; --surface:#161A20; --raised:#1C222A;
    --border:#272E38; --ink:#E6E9EC; --ink-2:#B3BCC7; --muted:#828C99;
    --accent:#D89B45; --accent-soft:#2E2617;
    --good:#4EA88F; --good-soft:#152820;
    --hold:#D89B45; --hold-soft:#2E2617;
    --crit:#D4644E; --crit-soft:#2E1A16;
    --bar-track:#232A33;
  }
}
:root[data-theme="dark"]{
  --ground:#0F1216; --surface:#161A20; --raised:#1C222A;
  --border:#272E38; --ink:#E6E9EC; --ink-2:#B3BCC7; --muted:#828C99;
  --accent:#D89B45; --accent-soft:#2E2617;
  --good:#4EA88F; --good-soft:#152820;
  --hold:#D89B45; --hold-soft:#2E2617;
  --crit:#D4644E; --crit-soft:#2E1A16;
  --bar-track:#232A33;
}
:root[data-theme="light"]{
  --ground:#F4F6F8; --surface:#FFFFFF; --raised:#EDF0F3;
  --border:#DCE1E7; --ink:#171B21; --ink-2:#414B58; --muted:#5C6674;
  --accent:#8A5B12; --accent-soft:#F0E4CE;
  --good:#2F7A63; --good-soft:#DDEDE7;
  --hold:#8A5B12; --hold-soft:#F0E4CE;
  --crit:#A83A26; --crit-soft:#F6DED8;
  --bar-track:#E4E8EC;
}
*{box-sizing:border-box;}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:var(--sans); font-size:15px; line-height:1.55;
  -webkit-font-smoothing:antialiased;
}
.wrap{max-width:1120px; margin:0 auto; padding:32px 24px 72px;}
.label{
  font-family:var(--mono); font-size:10.5px; font-weight:600;
  letter-spacing:.13em; text-transform:uppercase; color:var(--muted);
}
h1{
  font-family:var(--mono); font-size:19px; font-weight:600;
  letter-spacing:-.01em; margin:0; text-wrap:balance;
}
h2{
  font-family:var(--mono); font-size:13px; font-weight:600;
  letter-spacing:.02em; margin:0; color:var(--ink);
}
.num{font-variant-numeric:tabular-nums;}

/* ---- status bar ---- */
.statusbar{
  display:flex; flex-wrap:wrap; gap:16px; align-items:center;
  justify-content:space-between;
  background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:16px 20px; margin-bottom:10px;
}
.ident{display:flex; align-items:center; gap:13px; min-width:0;}
.beacon{
  width:9px; height:9px; border-radius:50%; background:var(--good);
  box-shadow:0 0 0 4px var(--good-soft); flex:none;
}
.beacon.off{background:var(--muted); box-shadow:0 0 0 4px var(--raised);}
.path{font-family:var(--mono); font-size:11.5px; color:var(--muted); word-break:break-all;}
.nextrun{text-align:right; font-family:var(--mono);}
.nextrun .t{font-size:17px; font-weight:600; color:var(--ink); letter-spacing:-.01em;}

.note{
  font-size:13.5px; color:var(--ink-2); margin:0 0 26px;
  padding:11px 16px; border-left:2px solid var(--accent);
  background:var(--surface); border-radius:0 8px 8px 0;
}

/* ---- stat tiles ---- */
.tiles{display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:26px;}
.tile{
  background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:16px 18px;
}
.tile .v{
  font-family:var(--mono); font-size:31px; font-weight:600;
  letter-spacing:-.02em; line-height:1.1; margin:9px 0 3px;
  font-variant-numeric:tabular-nums;
}
.tile .sub{font-size:12px; color:var(--muted); line-height:1.4;}
.tile.good .v{color:var(--good);} .tile.hold .v{color:var(--hold);}
.tile.crit .v{color:var(--crit);}

/* ---- panels ---- */
.cols{display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:12px;}
.panel{
  background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:18px 20px; min-width:0;
}
.phead{
  display:flex; align-items:baseline; justify-content:space-between;
  gap:12px; margin-bottom:4px; padding-bottom:12px;
  border-bottom:1px solid var(--border);
}
.phead .cap{font-size:12px; color:var(--muted);}

/* ---- evidence bars (single series, magnitude) ---- */
.bars{display:flex; flex-direction:column; gap:13px; margin-top:15px;}
.bar-row{display:flex; flex-direction:column; gap:5px;}
.bar-top{display:flex; justify-content:space-between; gap:10px; align-items:baseline;}
.bar-name{
  font-family:var(--mono); font-size:11.5px; color:var(--ink-2);
  overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
.bar-val{font-family:var(--mono); font-size:11.5px; font-weight:600; color:var(--ink); font-variant-numeric:tabular-nums; flex:none;}
.track{height:7px; background:var(--bar-track); border-radius:4px; overflow:hidden;}
.fill{height:100%; background:var(--accent); border-radius:4px;}
.bar-meta{font-family:var(--mono); font-size:10px; color:var(--muted); letter-spacing:.03em;}

/* ---- decisions ---- */
.dec{padding:15px 0; border-bottom:1px solid var(--border);}
.dec:last-child{border-bottom:none; padding-bottom:0;}
.dec-head{display:flex; align-items:center; gap:9px; margin-bottom:7px; flex-wrap:wrap;}
.dec-name{font-family:var(--mono); font-size:12.5px; font-weight:600; color:var(--ink);}
.dec-why{font-size:13px; color:var(--ink-2); margin:0;}
.pill{
  display:inline-flex; align-items:center; gap:5px;
  font-family:var(--mono); font-size:9.5px; font-weight:600;
  letter-spacing:.09em; text-transform:uppercase;
  padding:3px 8px; border-radius:5px; flex:none;
}
.pill.hold{background:var(--hold-soft); color:var(--hold);}
.pill.good{background:var(--good-soft); color:var(--good);}
.pill.crit{background:var(--crit-soft); color:var(--crit);}
.glyph{font-size:11px; line-height:1;}

/* ---- ledger ---- */
.ledger{margin-top:15px; display:flex; flex-direction:column;}
.entry{
  display:grid; grid-template-columns:76px 116px 1fr; gap:14px;
  padding:8px 0; border-bottom:1px solid var(--border);
  font-size:13px; align-items:baseline;
}
.entry:last-child{border-bottom:none;}
.entry .sha{font-family:var(--mono); font-size:11.5px; color:var(--accent);}
.entry .when{font-family:var(--mono); font-size:11.5px; color:var(--muted); font-variant-numeric:tabular-nums;}
.entry .what{color:var(--ink-2); min-width:0;}

.empty{
  font-size:13px; color:var(--muted); font-style:italic;
  padding:18px 0 4px;
}
.foot{
  margin-top:26px; padding-top:16px; border-top:1px solid var(--border);
  font-family:var(--mono); font-size:10.5px; color:var(--muted);
  display:flex; justify-content:space-between; gap:16px; flex-wrap:wrap;
}
@media (max-width:820px){
  .cols{grid-template-columns:1fr;}
  .tiles{grid-template-columns:repeat(2,1fr);}
  .entry{grid-template-columns:68px 1fr; }
  .entry .when{grid-column:1/-1; order:3;}
}
"""


def tile(label, value, sub, cls=""):
    return (f'<div class="tile {cls}"><div class="label">{esc(label)}</div>'
            f'<div class="v">{esc(value)}</div><div class="sub">{esc(sub)}</div></div>')


def render(d):
    obs = d["obs"]
    clusters = obs.get("recurring_tool_errors", [])[:7]
    peak = max([c["count"] for c in clusters], default=1)

    bars = []
    for c in clusters:
        txt = (c["samples"][0]["text"] if c.get("samples") else c["signature"])
        txt = re.sub(r"\s+", " ", txt).strip()[:74]
        tool = (list(c.get("tools", {}).keys()) or ["unknown"])[0]
        tool = tool.replace("mcp__Claude_Browser__", "browser/")
        pct = max(6, round(100 * c["count"] / peak))
        solo = c.get("single_session_only")
        meta = f'{tool} · {c.get("distinct_sessions", 1)} session' + \
               ("" if c.get("distinct_sessions", 1) == 1 else "s")
        if solo:
            meta += " · single-session, treat as hypothesis"
        bars.append(
            f'<div class="bar-row"><div class="bar-top">'
            f'<span class="bar-name" title="{esc(txt)}">{esc(txt)}</span>'
            f'<span class="bar-val">{c["count"]}</span></div>'
            f'<div class="track"><div class="fill" style="width:{pct}%"></div></div>'
            f'<div class="bar-meta">{esc(meta)}</div></div>'
        )
    bars_html = "".join(bars) or '<div class="empty">No friction observed in the window.</div>'

    decs = []
    for a in d["applied"]:
        decs.append(
            f'<div class="dec"><div class="dec-head">'
            f'<span class="pill good"><span class="glyph">&#10003;</span>Applied</span>'
            f'<span class="dec-name">{esc(a.get("artifact","?"))}</span></div>'
            f'<p class="dec-why">{esc(str(a.get("counterfactual",""))[:260])}</p></div>'
        )
    for r in d["rejected"]:
        decs.append(
            f'<div class="dec"><div class="dec-head">'
            f'<span class="pill hold"><span class="glyph">&#10005;</span>Refuted</span>'
            f'<span class="dec-name">{esc(r.get("artifact","?"))}</span></div>'
            f'<p class="dec-why">{esc(str(r.get("reason",""))[:300])}&hellip;</p></div>'
        )
    decs_html = "".join(decs) or '<div class="empty">No proposals yet.</div>'

    entries = "".join(
        f'<div class="entry"><span class="sha">{esc(c["sha"])}</span>'
        f'<span class="when">{esc(c["date"])}</span>'
        f'<span class="what">{esc(c["subject"])}</span></div>'
        for c in d["commits"]
    ) or '<div class="empty">No commits.</div>'

    nviol = len(d["violations"])
    sched_on = d["scheduled"]

    body = f"""
<div class="wrap">

  <div class="statusbar">
    <div class="ident">
      <span class="beacon{'' if sched_on else ' off'}"></span>
      <div>
        <h1>Self-improvement loop</h1>
        <div class="path">command-control/self-improve</div>
      </div>
    </div>
    <div class="nextrun">
      <div class="label">{'Next run' if sched_on else 'Scheduler'}</div>
      <div class="t">{'Daily 03:00' if sched_on else 'Not loaded'}</div>
    </div>
  </div>

  <p class="note">A healthy night here changes nothing. The loop only commits when
  evidence survives an adversarial check &mdash; so <strong>refused</strong> is the
  expected outcome, and a burst of accepted changes is the signal worth investigating.</p>

  <div class="tiles">
    {tile("Cycles run", len(d["cycles"]), "since bootstrap")}
    {tile("Changes applied", len(d["applied"]), "skills, agents, rules", "good")}
    {tile("Proposals refuted", len(d["rejected"]), "killed at verification", "hold")}
    {tile("Guard breaches", nviol, "settings.json integrity",
          "crit" if nviol else "")}
  </div>

  <div class="cols">
    <section class="panel">
      <div class="phead"><h2>What it saw</h2>
        <span class="cap">{esc(obs.get('sessions_scanned', 0))} sessions &middot; {esc(obs.get('window_days', 0))}d window</span></div>
      <div class="bars">{bars_html}</div>
    </section>

    <section class="panel">
      <div class="phead"><h2>What it decided</h2>
        <span class="cap">evidence &rarr; verdict</span></div>
      {decs_html}
    </section>
  </div>

  <section class="panel">
    <div class="phead"><h2>Ledger</h2>
      <span class="cap">every change is a revertible commit</span></div>
    <div class="ledger">{entries}</div>
  </section>

  <div class="foot">
    <span>{esc(len(d["skills"]))} skills &middot; {esc(len(d["agents"]))} agents authored by the loop</span>
    <span>Generated {esc(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))}</span>
  </div>

</div>"""
    return body


def main():
    fragment = "--fragment" in sys.argv
    d = collect()
    body = render(d)
    title = "Self-improvement loop"

    if fragment:
        out = f"<title>{title}</title>\n<style>{CSS}</style>\n{body}"
    else:
        out = (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
               f'<meta name="viewport" content="width=device-width,initial-scale=1">'
               f'<title>{title}</title><style>{CSS}</style></head><body>{body}</body></html>')
    sys.stdout.write(out)


if __name__ == "__main__":
    main()
