#!/usr/bin/env python3
"""Fleet dashboard.

  fleet.py render            write index.html
  fleet.py serve [port]      serve it, regenerating on every request

Each worker drops a JSON status file in workers/; this reads whatever is there,
so adding a worker to the board means adding a worker, not editing this file.
"""

import hashlib
import html
import ipaddress
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
WORKERS = FLEET / "workers"
CHARGES = FLEET / "data" / "charges.jsonl"

# Per-install, so the same visitor is one hand here and an unrelated one
# somewhere else. Regenerated if absent; losing it only resets the counting.
def _charge_salt():
    p = FLEET / "data" / ".charge-salt"
    try:
        return p.read_text().strip()
    except OSError:
        import secrets
        salt = secrets.token_hex(16)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(salt)
        except OSError:
            pass
        return salt


CHARGE_SALT = _charge_salt()


def _clean(v, limit):
    """Visitor text, made safe to store and to show.

    Control characters and newlines come out because one line in the event log
    must stay one line - a newline here is a caller writing a second, forged
    event underneath their own.
    """
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(v or ""))[:limit].strip()


def charge_tally():
    """Charges per project, with unique hands beside the raw count.

    Nothing read this file before now: the button wrote and no surface showed
    it, so a feature about visible enthusiasm was invisible. The gap between
    `charges` and `hands` is the spam signal, left for a human to read rather
    than acted on automatically.
    """
    out = {}
    try:
        lines = CHARGES.read_text(errors="replace").splitlines()
    except OSError:
        return {}
    for line in lines:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        name = r.get("project")
        if not name:
            continue
        t = out.setdefault(name, {"charges": 0, "hands": set(), "last": None})
        t["charges"] += 1
        t["hands"].add(r.get("hand") or r.get("by") or "?")
        if not t["last"] or str(r.get("ts")) > t["last"]:
            t["last"] = r.get("ts")
    return {k: {"charges": v["charges"], "hands": len(v["hands"]), "last": v["last"]}
            for k, v in sorted(out.items(), key=lambda kv: -kv[1]["charges"])}
SELF_IMPROVE = FLEET.parent / "self-improve"


def esc(x):
    return html.escape(str(x), quote=True)


def ago(iso):
    if not iso:
        return "never"
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return "unknown"
    s = (datetime.now(timezone.utc) - t).total_seconds()
    if s < 0:
        return "just now"
    for limit, div, unit in ((60, 1, "s"), (3600, 60, "m"), (86400, 3600, "h")):
        if s < limit:
            return f"{int(s // div)}{unit} ago"
    return f"{int(s // 86400)}d ago"


# A green check can still be abandoned: on 2026-08-04 agent-comms read "pass"
# with a last_run 17 hours behind the other live checks. Staleness is measured
# against the freshest worker, not the wall clock, so a laptop asleep all
# weekend ages every check together instead of flagging the whole fleet.
STALE_AFTER_S = 6 * 3600

# Six hours behind is "someone should look". Twenty-four is different in kind:
# on 2026-08-18 the nuc card read `pass` with a last_run from the 6th, twelve
# days green, because a worker that stops reporting keeps its last status
# forever. Green meant "the last check passed", not "the machine is alive", and
# those two diverged for a week and a half while the operator was abroad.
#
# So silence eventually reads as failure rather than success. A check this far
# behind is not a stale answer, it is no answer.
DEAD_AFTER_S = 24 * 3600


def stale_hours(workers):
    """worker name -> whole hours behind the freshest last_run, when far behind."""
    stamps = {}
    for w in workers:
        try:
            t = datetime.fromisoformat(str(w.get("last_run")).replace("Z", "+00:00"))
        except ValueError:
            continue
        stamps[w.get("worker")] = t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    if not stamps:
        return {}
    newest = max(stamps.values())
    return {name: int((newest - t).total_seconds() // 3600)
            for name, t in stamps.items()
            if (newest - t).total_seconds() > STALE_AFTER_S}


def warn_stale(workers, lags):
    """A worker that has not run is not passing.

    The board already knew a check was hours behind the fleet, but said so only
    in a grey footnote beside a green "pass" pill — so agents kept re-noticing
    the same staleness in prose. Downgrade the green ones so the status field
    itself carries it. fail/alert keep their louder status.

    Two tiers, because "a bit behind" and "gone" are different claims:
    `warn` past six hours, `stale` past a day. Only `stale` is red, so the
    colour keeps meaning something.
    """
    for w in workers:
        lag_h = lags.get(w.get("worker"))
        # `busy` and `thinking` are current statements about right now, so
        # they are never overwritten by staleness - and they are never `pass`
        # either, so this reads only the green ones, as before.
        if lag_h is None or w.get("status") != "pass":
            continue
        w["stale_hours"] = lag_h
        w["status"] = "stale" if lag_h * 3600 >= DEAD_AFTER_S else "warn"
    return workers


def load_self_improve():
    """The self-improvement loop predates the fleet, so adapt its state here
    rather than making it write a second status file it doesn't otherwise need."""
    d = SELF_IMPROVE
    if not d.exists():
        return None

    def lines(p):
        try:
            return [l for l in (d / p).read_text(errors="replace").splitlines() if l.strip()]
        except OSError:
            return []

    cycles = lines("state/cycles.log")
    applied = lines("state/applied.jsonl")
    rejected = lines("state/rejected.jsonl")
    violations = lines("state/violations.log")

    last_iso = None
    if cycles:
        m = re.match(r"(\S+)", cycles[-1])
        if m:
            last_iso = m.group(1)

    status = "alert" if violations else ("pass" if cycles else "idle")
    return {
        "worker": "self-improve", "kind": "learner",
        "target": str(d), "last_run": last_iso, "status": status,
        "summary": f"{len(applied)} applied · {len(rejected)} refuted",
        "metrics": [("cycles", len(cycles)), ("applied", len(applied)),
                    ("refuted", len(rejected)), ("breaches", len(violations))],
        "note": "Commits only what survives adversarial verification. Doing nothing is a healthy night.",
        "digest": None,
    }


_PUBLIC_HOME_PATH = re.compile(r"(?:^|[\s\"'=:(])/(?:Users|home)/")
_PUBLIC_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


def _sanitize_public_value(value):
    """Remove install-specific locations and private addresses recursively."""
    if isinstance(value, dict):
        return {k: _sanitize_public_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_public_value(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_public_value(v) for v in value)
    if not isinstance(value, str):
        return value
    if _PUBLIC_HOME_PATH.search(value):
        return ""
    for match in _PUBLIC_IPV4.finditer(value):
        try:
            address = ipaddress.ip_address(match.group())
        except ValueError:
            continue
        if address.is_private or address.is_loopback or address.is_link_local:
            return ""
    return value


def sanitize_worker(w):
    """Drop home paths and shot filenames from a worker card before it is
    served. Writers can be stale; /workers.json is public."""
    w = dict(w)
    detail = w.get("detail")
    if isinstance(detail, str) and detail:
        try:
            parsed = json.loads(detail)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(parsed, dict):
                cleaned = []
                for row in parsed.get("results") or []:
                    if not isinstance(row, dict):
                        continue
                    cleaned.append({k: v for k, v in row.items() if k != "shot"})
                parsed["results"] = cleaned
                w["detail"] = json.dumps(parsed, indent=2)
    return _sanitize_public_value(w)


def load_workers():
    out = []
    si = load_self_improve()
    if si:
        out.append(si)

    # Hermes and OpenClaw run their own launch agents and publish their own
    # state, so they are probed live rather than asked to write a status file.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import probe
        out.extend(probe.probe_all_cached())
    except Exception:
        pass

    for p in sorted(WORKERS.glob("*.json")):
        try:
            w = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        # A json file in here that is not a worker report is somebody else's
        # data, not a broken worker. Skip it: one stray file used to take the
        # whole board down with a KeyError at sort time.
        if not isinstance(w, dict) or not w.get("worker"):
            continue
        w = sanitize_worker(w)
        w.setdefault("kind", "watchdog")
        w["metrics"] = [("passed", w.get("tests_passed", 0)),
                        ("failed", w.get("tests_failed", 0)),
                        ("seconds", w.get("duration_s", 0))]
        w["note"] = ""
        out.append(w)

    # Downgrade here rather than in the renderer. /workers.json used to serve
    # the undowngraded status, so the html page said "warn" while the json the
    # council reads said "pass" — and the council believed the json.
    warn_stale(out, stale_hours(out))

    # Anything needing attention sorts to the top. `stale` sits with the
    # failures: a check that has not run in a day is not a minor note.
    # `busy` and `thinking` are not problems and not results. They sort below
    # everything that wants a human and above the quiet ones, because "it is
    # working on it" is the answer to "why is this card not fresh".
    rank = {"fail": 0, "stale": 1, "alert": 2, "warn": 3,
            "thinking": 4, "busy": 5, "skip": 6, "pass": 7, "idle": 8}
    return sorted(out, key=lambda w: (rank.get(w.get("status"), 7), w["worker"]))


CSS = """
:root{
  --ground:#F4F6F8; --surface:#FFFFFF; --raised:#EDF0F3;
  --border:#DCE1E7; --ink:#171B21; --ink-2:#414B58; --muted:#5C6674;
  --accent:#8A5B12;
  --good:#2F7A63; --good-soft:#DDEDE7;
  --hold:#8A5B12; --hold-soft:#F0E4CE;
  --crit:#A83A26; --crit-soft:#F6DED8;
  --track:#E4E8EC;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{
    --ground:#0F1216; --surface:#161A20; --raised:#1C222A;
    --border:#272E38; --ink:#E6E9EC; --ink-2:#B3BCC7; --muted:#828C99;
    --accent:#D89B45;
    --good:#4EA88F; --good-soft:#152820;
    --hold:#D89B45; --hold-soft:#2E2617;
    --crit:#D4644E; --crit-soft:#2E1A16;
    --track:#232A33;
  }
}
:root[data-theme="dark"]{
  --ground:#0F1216; --surface:#161A20; --raised:#1C222A;
  --border:#272E38; --ink:#E6E9EC; --ink-2:#B3BCC7; --muted:#828C99;
  --accent:#D89B45;
  --good:#4EA88F; --good-soft:#152820;
  --hold:#D89B45; --hold-soft:#2E2617;
  --crit:#D4644E; --crit-soft:#2E1A16;
  --track:#232A33;
}
:root[data-theme="light"]{
  --ground:#F4F6F8; --surface:#FFFFFF; --raised:#EDF0F3;
  --border:#DCE1E7; --ink:#171B21; --ink-2:#414B58; --muted:#5C6674;
  --accent:#8A5B12;
  --good:#2F7A63; --good-soft:#DDEDE7;
  --hold:#8A5B12; --hold-soft:#F0E4CE;
  --crit:#A83A26; --crit-soft:#F6DED8;
  --track:#E4E8EC;
}
*{box-sizing:border-box;}
body{margin:0;background:var(--ground);color:var(--ink);
  font-family:var(--sans);font-size:15px;line-height:1.55;-webkit-font-smoothing:antialiased;}
.wrap{max-width:1000px;margin:0 auto;padding:34px 24px 72px;}
.label{font-family:var(--mono);font-size:10.5px;font-weight:600;
  letter-spacing:.13em;text-transform:uppercase;color:var(--muted);}
h1{font-family:var(--mono);font-size:20px;font-weight:600;letter-spacing:-.01em;margin:0;}

.top{display:flex;justify-content:space-between;align-items:flex-end;
  gap:20px;flex-wrap:wrap;margin-bottom:22px;
  padding-bottom:18px;border-bottom:1px solid var(--border);}
.top .sub{font-family:var(--mono);font-size:11.5px;color:var(--muted);margin-top:5px;}
.rollup{display:flex;gap:26px;flex-wrap:wrap;}
.roll{text-align:right;}
.roll .v{font-family:var(--mono);font-size:25px;font-weight:600;
  letter-spacing:-.02em;font-variant-numeric:tabular-nums;line-height:1.15;}
.roll.good .v{color:var(--good);} .roll.crit .v{color:var(--crit);}

.cards{display:flex;flex-direction:column;gap:12px;}
.card{background:var(--surface);border:1px solid var(--border);
  border-radius:11px;padding:0;overflow:hidden;display:flex;}
.stripe{width:3px;flex:none;background:var(--muted);}
.stripe.pass{background:var(--good);} .stripe.fail{background:var(--crit);}
.stripe.alert{background:var(--crit);} .stripe.skip{background:var(--hold);}
.stripe.warn{background:var(--hold);} .stripe.stale{background:var(--crit);}
.stripe.busy,.stripe.thinking{background:var(--accent,#5b8def);}
.body{padding:17px 20px;flex:1;min-width:0;}
.hrow{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:3px;}
.wname{font-family:var(--mono);font-size:14.5px;font-weight:600;letter-spacing:-.01em;}
.kind{font-family:var(--mono);font-size:10px;color:var(--muted);
  letter-spacing:.09em;text-transform:uppercase;
  border:1px solid var(--border);border-radius:4px;padding:2px 6px;}
.when{margin-left:auto;font-family:var(--mono);font-size:11.5px;color:var(--muted);}
.pill{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);
  font-size:9.5px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;
  padding:3px 8px;border-radius:5px;}
.pill.pass{background:var(--good-soft);color:var(--good);}
.pill.fail,.pill.alert,.pill.stale{background:var(--crit-soft);color:var(--crit);}
.pill.skip,.pill.idle,.pill.warn{background:var(--hold-soft);color:var(--hold);}
/* Blue, not amber: nothing is wrong. The machine is mid-sentence. */
.pill.busy,.pill.thinking{background:rgba(91,141,239,.14);color:#5b8def;}
.glyph{font-size:11px;line-height:1;}
.summary{font-family:var(--mono);font-size:12px;color:var(--ink-2);margin:7px 0 0;}
.note{font-size:13px;color:var(--muted);margin:6px 0 0;}
.path{font-family:var(--mono);font-size:10.5px;color:var(--muted);margin-top:7px;word-break:break-all;}
.metrics{display:flex;gap:22px;margin-top:13px;flex-wrap:wrap;}
.metric .mv{font-family:var(--mono);font-size:17px;font-weight:600;
  font-variant-numeric:tabular-nums;letter-spacing:-.01em;}
.metric .mk{font-family:var(--mono);font-size:9.5px;color:var(--muted);
  letter-spacing:.1em;text-transform:uppercase;}
.digest{margin-top:11px;font-family:var(--mono);font-size:11.5px;}
.digest a{color:var(--crit);}
.attention{margin:0 0 14px;font-family:var(--mono);font-size:12px;
  color:var(--hold);}
.stalemark{color:var(--hold);}
.charges{margin:0 0 14px;font-family:var(--mono);font-size:11.5px;
  color:var(--muted);display:flex;gap:8px;flex-wrap:wrap;align-items:center;}
.charge{background:var(--good-soft);color:var(--good);border-radius:999px;
  padding:2px 9px;white-space:nowrap;}
.charge i{font-style:normal;opacity:.65;}
.empty{color:var(--muted);font-style:italic;padding:26px 0;}
.foot{margin-top:26px;padding-top:15px;border-top:1px solid var(--border);
  font-family:var(--mono);font-size:10.5px;color:var(--muted);
  display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;}
@media (max-width:700px){ .when{margin-left:0;width:100%;} }
"""


def render_body(workers):
    import nav
    nav_html = nav.html('/')
    lags = stale_hours(workers)
    # Idempotent - it only downgrades `pass`, so a list already passed through
    # load_workers is untouched here. Called in both places because render_body
    # is also handed worker lists that never went through load_workers.
    warn_stale(workers, lags)
    if not workers:
        cards = '<div class="empty">No workers reporting yet.</div>'
    else:
        parts = []
        for w in workers:
            st = w.get("status", "idle")
            glyph = {"pass": "&#10003;", "fail": "&#10005;", "alert": "&#9888;",
                     "warn": "&#9888;", "stale": "&#8987;",
                     "busy": "&#8943;", "thinking": "&#8943;"}.get(st, "&#8226;")
            import meter
            metrics = ""
            passed = w.get("tests_passed")
            failed = w.get("tests_failed")
            if isinstance(passed, int) and isinstance(failed, int) and (passed + failed):
                # A ratio has a real ceiling, so the bar means something absolute.
                metrics += ('<div class="metric">'
                            + meter.ratio(passed, passed + failed, label="passed")
                            + '</div>')
            secs = w.get("duration_s")
            if isinstance(secs, (int, float)) and secs:
                # No natural ceiling; a minute is the reference. Longer pins full.
                metrics += ('<div class="metric">'
                            + meter.bar(secs, 60, label="runtime", suffix="s")
                            + '</div>')
            if not metrics:
                metrics = "".join(
                    f'<div class="metric"><div class="mv">{esc(v)}</div>'
                    f'<div class="mk">{esc(k)}</div></div>'
                    for k, v in w.get("metrics", []))
            digest = ""
            if w.get("digest"):
                digest = (f'<div class="digest">&#8627; <a href="{esc(w["digest"])}">'
                          f'{esc(str(w["digest"]).split("/")[-1])}</a></div>')
            note = f'<p class="note">{esc(w["note"])}</p>' if w.get("note") else ""
            # "3m ago" alone does not say what happened 3m ago. A card can be
            # thinking now and last have *said* something an hour back, and the
            # difference is the whole point of having the two states.
            when = ("last signal " + esc(ago(w.get("last_run")))
                    if w.get("last_run") else "no signal yet")
            if w.get("worker") in lags:
                when += (f' <span class="stalemark">&middot; stale '
                         f'{lags[w["worker"]]}h behind the fleet</span>')
            parts.append(f"""
      <article class="card">
        <div class="stripe {esc(st)}"></div>
        <div class="body">
          <div class="hrow">
            <span class="wname">{esc(w.get("worker","?"))}</span>
            <span class="kind">{esc(w.get("kind",""))}</span>
            <span class="pill {esc(st)}"><span class="glyph">{glyph}</span>{esc(st)}</span>
            <span class="when">{when}</span>
          </div>
          <p class="summary">{esc(w.get("summary",""))}</p>
          {note}
          <div class="metrics">{metrics}</div>
          {digest}
          <div class="path">{esc(w.get("target",""))}</div>
        </div>
      </article>""")
        cards = "".join(parts)

    healthy = sum(1 for w in workers if w.get("status") == "pass")
    attention = sum(1 for w in workers
                    if w.get("status") in ("fail", "alert", "stale"))

    # One sentence for the human, above the cards: the few things that need
    # Marsita, not the machine chatter. Same idea as council.board_state()'s
    # needs_attention, composed from what this renderer already knows.
    needs = []
    try:
        import council
        branches = council.open_branches()
    except Exception:
        branches = []
    if branches:
        needs.append(f"{len(branches)} unmerged branches")
    needs += [f'{w.get("worker")} {w.get("status")}'
              for w in workers if w.get("status") in ("fail", "alert", "stale")]
    needs += [f"{name} stale {h}h" for name, h in sorted(lags.items())]
    needs_html = (f'<div class="attention">Needs attention: '
                  f'{esc(" · ".join(needs))}</div>' if needs else "")

    # Charges, from strangers with no account, pointing at what matters. Both
    # numbers are shown on purpose: charging is deliberately open, so `hands`
    # is the only thing that separates ten people from one person ten times.
    # Nobody is blocked - the reader is just told which one they are seeing.
    charge_html = ""
    try:
        tally = charge_tally()
    except Exception:
        tally = {}
    if tally:
        pills = "".join(
            f'<span class="charge" title="{esc(str(t["hands"]))} distinct '
            f'{"hand" if t["hands"] == 1 else "hands"}">'
            f'<b>{esc(name)}</b> {t["charges"]}'
            + (f' <i>&middot;{t["hands"]} hands</i>'
               if t["charges"] != t["hands"] else "")
            + '</span>'
            for name, t in list(tally.items())[:8])
        charge_html = f'<div class="charges">Charged: {pills}</div>' 

    return f"""
<div class="wrap">
  <div class="top">
    <div>
      <h1>Fleet</h1>
      <div class="sub">command-control &middot; refreshes every 20s</div>
    </div>
    {nav_html}
    <div class="rollup">
      <div class="roll"><div class="v">{len(workers)}</div><div class="label">Workers</div></div>
      <div class="roll good"><div class="v">{healthy}</div><div class="label">Healthy</div></div>
      <div class="roll {'crit' if attention else ''}"><div class="v">{attention}</div><div class="label">Need you</div></div>
    </div>
  </div>

  {needs_html}
  {charge_html}

  <div class="cards">{cards}</div>

  <div class="foot">
    <span>Workers self-report into fleet/workers/</span>
    <span>{esc(datetime.now().strftime("%H:%M:%S"))}</span>
  </div>
</div>"""


def _meter_css():
    import meter
    return meter.CSS


def _nav_css():
    import nav
    return nav.CSS


def render_page(refresh=True):
    import nav
    meta = '<meta http-equiv="refresh" content="20">' if refresh else ""
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">{meta}'
            f'<title>{nav.title("cards")}</title>'
            f'<style>{CSS}\n{_nav_css()}\n{_meter_css()}</style></head>'
            f'<body>{render_body(load_workers())}</body></html>')


KILL_TOKEN = __import__("secrets").token_urlsafe(24)

# The public writes append to disk, and the callers are anonymous. Both need a
# ceiling on how fast, and a ceiling on how large.
PUBLIC_WRITE_MAX_BYTES = 8_000_000


def _append_capped(path: Path, record: dict) -> None:
    """Append one JSON line, rotating the file once it is large enough.

    /api/charge had no cap at all, so an anonymous caller could fill the disk
    on a host whose unit is Restart=always — a restart loop against a full
    disk rather than a clean stop. That endpoint went with the orrery (#27),
    but the rule outlived it: /api/signatures/sign rotates at 8MB by this same
    path, and so does whatever public write comes next.
    """
    if path.exists() and path.stat().st_size > PUBLIC_WRITE_MAX_BYTES:
        path.rename(path.with_suffix(".jsonl.1"))
    with path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")


def _public_write_limiter():
    """The cockpit's token bucket, reused for the fleet's own public writes.

    Same problem, same shape, already solved: legacy/app/ratelimit.py handles
    the spoofable-XFF client-key question correctly (last entry, not first —
    the fix from #10). Importing it beats a second implementation that would
    drift from the first.

    If legacy is not importable the board must still serve, so this degrades to
    no limiting rather than refusing to start.
    """
    try:
        sys.path.insert(0, str(FLEET.parent / "legacy"))
        from app.ratelimit import Limiter
        return Limiter()
    except Exception as e:
        print(f"public-write rate limiting unavailable: {e}", flush=True)
        return None


PUBLIC_WRITE_LIMITER = _public_write_limiter()

# Paths that drive this machine rather than describe it. Everything else is
# read-only and safe for a stranger — that is the whole point of publishing
# the fleet, so agents can watch it without an account.
#
# The split is by caller, not by config: tailscaled sets X-Forwarded-For on
# every funnelled request, and a browser on 127.0.0.1 never does. The server
# binds loopback only, so the funnel is the sole path that can reach it from
# outside and it always sets the header. Same rule the cockpit uses on 8770 —
# reads are public, control is local.
#
# 404 rather than 403: a stranger learns these routes do not exist here, which
# is cheaper than telling them there is a terminal they are not allowed to use.
CONTROL_PATHS = frozenset({
    "/terminal", "/ws/terminal", "/chat", "/chat/stream", "/chat/send",
    "/api/kill", "/api/kill-token", "/api/paste-image", "/api/convene",
    "/api/build-gate", "/api/ask",
})



# Paths the cockpit owns and the world already knows. Fleet is the front door
# now, so it forwards these rather than letting them 404 — /auth is printed in
# emails, /api/signals is where paired agents post, and /llms.txt is what an
# arriving agent reads. Moving the door must not move the letterbox.
COCKPIT = "http://127.0.0.1:8770"
FORWARD_EXACT = {
    "/auth", "/about", "/moderation", "/boot", "/llms.txt", "/health",
    "/api/dashboard", "/api/signals", "/api/pair", "/api/fleet",
    "/api/approvals", "/legacy-green-cockpit",
    # Named by the site map, so they have to answer at the front door rather
    # than only on the cockpit's own port. Both 404'd here until 2026-08-25 —
    # a route that exists but is unreachable from the only door anyone uses is
    # not a route.
    "/api/agents", "/brainfarts.json",
}
FORWARD_PREFIX = ("/api/signals/", "/api/approvals/", "/api/projects",
                  "/api/handoffs", "/api/artifacts", "/api/events")


def forwards(path):
    if path in FORWARD_EXACT:
        return True
    return any(path.startswith(pre) for pre in FORWARD_PREFIX)


# Flood control for the public write endpoints (the pad and the gallery).
# In-memory and per-process: a restart forgives everyone, which is the
# right trade for a wall whose whole point is that strangers can mark it.
RATE = {}
RATE_WINDOW = 600.0   # ten minutes
RATE_BURST = 5        # per visitor, per window
RATE_GLOBAL = 60      # everyone together, per window


def _redact_processes(snap):
    """Strip anything that could carry a private prompt, path or token from a
    public /api/processes response. Agents receive chat prompts as argv, so the
    command line is sensitive: a remote viewer sees only a fixed safe set, never
    cmd or cmd_full. The operator, local, still sees everything."""
    # "agent" is safe: it is one of a fixed set of agent names already printed
    # all over the public board, never anything derived from a command line.
    safe = ("pid", "label", "agent", "elapsed", "cpu", "mem", "rss_mb",
            "is_self", "kind")
    clean = lambda p: {k: p[k] for k in safe if k in p}
    machine_safe = ("cores", "load1", "load5", "load15", "per_core",
                    "state", "gate", "compressor_gb")
    disk_safe = ("total_gb", "used_gb", "free_gb", "used_pct", "tight",
                 "alert")
    source_machine = snap.get("machine") or {}
    machine = {k: source_machine[k] for k in machine_safe if k in source_machine}
    source_disk = source_machine.get("disk") or {}
    machine["disk"] = {k: source_disk[k] for k in disk_safe if k in source_disk}
    return {
        "fleet": [clean(p) for p in snap.get("fleet", [])],
        "external": [clean(p) for p in snap.get("external", [])],
        "heavies": [clean(p) for p in snap.get("heavies", [])],
        "killable": snap.get("killable", 0),
        "machine": machine,
    }


def start_legacy_cockpit(port=8770):
    """Run the legacy green cockpit inside this process.

    One process was the ask (2026-08-04): the cockpit's FastAPI app moved to
    legacy/ and boots here as a daemon thread on loopback :8770. The
    forwarding in Handler._forward is unchanged — it now talks to a thread
    instead of a second launchd job. If the legacy app cannot start, the
    board must still serve: log it and carry on.
    """
    import os
    import threading

    # Behind the funnel, X-Forwarded-For is the real caller; without this
    # every visitor looks like localhost, and localhost is allowed to write.
    os.environ.setdefault("TRUST_PROXY", "1")
    sys.path.insert(0, str(FLEET.parent / "legacy"))
    try:
        import uvicorn
        from app.main import app as legacy_app
        cfg = uvicorn.Config(legacy_app, host="127.0.0.1", port=port,
                             log_level="warning")
        threading.Thread(target=uvicorn.Server(cfg).run,
                         name="legacy-cockpit", daemon=True).start()
        print(f"legacy cockpit: http://127.0.0.1:{port}", flush=True)
    except Exception as e:
        print(f"legacy cockpit failed to start: {e}", flush=True)


def serve(port):
    import http.server
    import socketserver
    import threading

    # In a thread, NOT inline: the cockpit's import chain (FastAPI,
    # pydantic) takes seconds cold and a minute under memory pressure, and
    # it used to run before the board's socket even bound — every restart
    # was a blackout exactly as long as the imports ("why offline —
    # annoying", 2026-08-04). The board binds NOW; the cockpit joins when
    # it's dressed, and its routes 502 harmlessly until then.
    threading.Thread(target=start_legacy_cockpit,
                     name="legacy-cockpit-boot", daemon=True).start()

    class Handler(http.server.BaseHTTPRequestHandler):
        # A keep-alive browser tab would otherwise hold the only connection
        # slot open and lock out every other request (see ThreadingServer below).
        protocol_version = "HTTP/1.1"

        def _send(self, body, ctype="text/html; charset=utf-8",
                  cache="no-store", code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            # The board is already public via the funnel; CORS only lets a
            # browser on another origin read what curl can already fetch.
            # This is what lets the GitHub-Pages selfie gallery talk to us.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self):
            # CORS preflight for cross-origin POSTs (the selfie gallery).
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Access-Control-Max-Age", "86400")
            self.end_headers()

        def _forward(self, path, body=None):
            """Pass a request to the cockpit and return its answer verbatim.

            Deliberately dumb: same method, same body, same status, same
            content-type. The cockpit's own gates still apply — it decides what
            is public and what needs a local caller, and X-Forwarded-For is
            passed through so `require_local` sees the real visitor rather than
            this process.
            """
            import urllib.error
            import urllib.request

            target = COCKPIT + self.path
            req = urllib.request.Request(target, data=body,
                                         method=self.command)
            for h in ("Content-Type", "X-Node-Id", "X-Node-Signature", "Accept"):
                v = self.headers.get(h)
                if v:
                    req.add_header(h, v)
            # Never forward the caller's own X-Forwarded-For. tailscaled APPENDS
            # the real client to whatever the caller sent, so a remote spoof of
            # "127.0.0.1" arrives as "127.0.0.1, <real-ip>" — and the cockpit
            # reading the leftmost entry would trust it. The fleet is the trust
            # boundary: it decides local vs remote (by header presence, which a
            # loopback browser never sets) and hands the cockpit ONE clean value.
            # 127.0.0.1 for a genuinely local caller, so the operator's own
            # writes pass; otherwise the real remote address — the LAST entry the
            # trusted proxy appended — so a funnelled write is refused.
            if self._remote():
                incoming = self.headers.get("X-Forwarded-For", "")
                real = incoming.split(",")[-1].strip() if incoming else "unknown-remote"
                req.add_header("X-Forwarded-For", real)
            else:
                req.add_header("X-Forwarded-For", "127.0.0.1")

            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    payload = r.read()
                    ctype = r.headers.get("Content-Type", "application/json")
                    status = r.status
            except urllib.error.HTTPError as e:
                payload = e.read()
                ctype = e.headers.get("Content-Type", "application/json")
                status = e.code
            except Exception as e:
                payload = json.dumps(
                    {"error": "cockpit unreachable", "detail": str(e)}).encode()
                ctype, status = "application/json", 502

            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _remote(self):
            """True when a proxy brought this request in.

            Funnel stamps X-Forwarded-For. Cloudflare Tunnel stamps
            CF-Connecting-IP (and usually XFF too). Any of them means
            the caller is not the operator on loopback. Missing headers
            stay local — the bind is loopback, so the only way in from
            outside is a proxy that sets one of these.
            """
            h = self.headers
            return bool(
                h.get("X-Forwarded-For")
                or h.get("CF-Connecting-IP")
                or h.get("True-Client-IP")
                or h.get("X-Real-IP")
            )

        def _rate_limited(self):
            """True (and 429 already sent) when this caller is going too fast.

            Keyed on the last X-Forwarded-For entry, matching client_key() in
            legacy/app/ratelimit.py: the leftmost entry is caller-supplied, so
            keying on it would let one client mint a fresh bucket per request
            and remove the limit it appears to enforce.

            A local caller has no XFF and keys as "local" — one bucket for the
            operator, which is what we want, since the operator's own board
            posts here too.
            """
            if PUBLIC_WRITE_LIMITER is None:
                return False
            fwd = self.headers.get("X-Forwarded-For", "")
            key = fwd.split(",")[-1].strip() if fwd else "local"
            ok, retry = PUBLIC_WRITE_LIMITER.check(key)
            if ok:
                return False
            self.send_response(429)
            self.send_header("Retry-After", str(max(1, int(retry))))
            self.send_header("Content-Length", "0")
            self.end_headers()
            return True

        def _blocked(self, path):
            if self._remote() and path in CONTROL_PATHS:
                self.send_error(404)
                return True
            return False

        def _caller(self):
            """Best-effort identity of a remote writer, for rate limiting.

            X-Forwarded-For is set by the funnel and is the closest thing to
            a visitor identity we have. It is spoofable in principle, but the
            funnel appends the real peer, so the last hop is the honest one.
            """
            fwd = self.headers.get("X-Forwarded-For") or ""
            peer = self.client_address[0] if self.client_address else "?"
            return fwd.split(",")[-1].strip() or peer

        def _flooding(self, bucket):
            """A public pad needs a queue discipline, not a lock.

            The operator (local) is never limited — they cannot spam their
            own wall. A remote hand gets BURST writes in WINDOW seconds,
            and the wall as a whole gets GLOBAL in the same window, so one
            determined visitor cannot drown out the room and a botnet of
            many cannot either. 429 with Retry-After; nothing is stored.
            """
            if not self._remote():
                return False
            import time
            now = time.monotonic()
            hits = RATE.setdefault(bucket, {})
            for who, stamps in list(hits.items()):
                fresh = [t for t in stamps if now - t < RATE_WINDOW]
                if fresh:
                    hits[who] = fresh
                else:
                    del hits[who]
            me = self._caller()
            mine = hits.get(me, [])
            everyone = sum(len(v) for v in hits.values())
            if len(mine) >= RATE_BURST or everyone >= RATE_GLOBAL:
                self.send_response(429)
                self.send_header("Content-Type", "application/json")
                self.send_header("Retry-After", str(int(RATE_WINDOW)))
                self.send_header("Access-Control-Allow-Origin", "*")
                body = json.dumps({"error": "slow down",
                                   "retry_after": int(RATE_WINDOW)}).encode()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return True
            hits.setdefault(me, []).append(now)
            return False

        def do_GET(self):
            path = self.path.split("?")[0].rstrip("/") or "/"
            if self._blocked(path):
                return
            if forwards(path):
                self._forward(path)
                return

            if path == "/intro":
                # The human-facing page. It lived at `/` for a day, and
                # Marsita's own habit settled it: "I'm more familiar with
                # fleet as a home, not the focus." The board is home; this
                # is the page you send someone.
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import homeview
                self._send(homeview.page(remote=self._remote()).encode())
                return

            if path in ("/", "/fleet", "/one", "/index.html"):
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import events as ev, oneview, agentsview as av
                evts = ev.tail(200)
                seed = json.dumps([{"ts": e.get("ts"), "agent": e.get("agent", ""),
                                    "level": e.get("level", "info"),
                                    "msg": e.get("msg", "")} for e in evts])
                agents = json.dumps({k: [v[0], v[1]] for k, v in av.AGENTS.items()})
                # The landing page embeds the kill token for its own controls.
                # A remote viewer gets an empty one — blocking /api/kill is no
                # use if the page hands the token out on the way in.
                token = "" if self._remote() else KILL_TOKEN
                self._send(oneview.page(seed, agents, token,
                                        remote=self._remote()).encode())
                return

            if path == "/board":
                self._send(render_page().encode())      # the old card view
                return

            if path == "/live":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import events as ev, live
                agents = json.dumps({k: [v[0], v[1]] for k, v in live.AGENT_STYLE.items()})
                self._send(live.page(ev.tail(120), agents).encode())
                return

            if path == "/workers.json":
                self._send(json.dumps(load_workers(), default=str).encode(),
                           "application/json")
                return

            if path == "/projects.yaml":
                # The operator's public project list — human- and AI-readable,
                # hand-edited at fleet/data/projects.yaml and served live.
                f = FLEET / "data" / "projects.yaml"
                try:
                    self._send(f.read_bytes(), "text/yaml; charset=utf-8")
                except OSError:
                    self.send_error(404)
                return

            if path == "/events":
                self._stream_events()
                return

            if path == "/api/processes":
                # One snapshot per 3s no matter how many tabs poll: the ps
                # exec is cheap once, expensive times every open viewer.
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import procs
                import time as _t
                now = _t.monotonic()
                cached = getattr(Handler, "_procs_cache", None)
                if not cached or now - cached[0] > 3:
                    cached = (now, procs.snapshot())
                    Handler._procs_cache = cached
                snap = cached[1]
                # Command lines carry chat prompts (agents get them as argv),
                # plus paths, tokens and session ids. A remote viewer gets a safe
                # allowlist only; the operator, local, sees the full command.
                if self._remote():
                    snap = _redact_processes(snap)
                self._send(json.dumps(snap).encode(), "application/json")
                return

            if path == "/api/charge":
                self._send(json.dumps(charge_tally()).encode(),
                           "application/json")
                return

            if path == "/api/horizons":
                # The cockpit owns this file; the fleet reads it. Reading a
                # sibling's JSON is cheaper and more honest than an HTTP hop to
                # a process on the same disk, and it keeps working when that
                # process is swapped out — which, on this laptop, it often is.
                f = FLEET.parent / "data" / "horizons.json"
                try:
                    self._send(f.read_bytes(), "application/json")
                except OSError:
                    self._send(b'{"levels": []}', "application/json")
                return

            if path == "/api/selfies":
                # The public gallery feed. Same medium as the machines'
                # self-portraits: 80 columns of characters, a block stamp,
                # a name. Newest first. Read-and-return, no gate.
                f = Path(os.environ.get(
                    "FLEET_SELFIES", FLEET / "data" / "selfies.jsonl"))
                # A damned face is already gone from the file; a face in
                # purgatory is still here but not for the public. The
                # operator, local, sees everything including what is held.
                mine = not self._remote()
                out = []
                try:
                    for line in f.read_text(errors="replace").splitlines():
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        if mine or d.get("status") != "purgatory":
                            out.append(d)
                except OSError:
                    pass
                out.reverse()
                self._send(json.dumps(out[:500]).encode(),
                           "application/json")
                return

            if path == "/api/marks":
                # sender -> their most recent pad path, so the stream can
                # draw a signature beside the message it belongs to.
                out = {}
                f = Path(os.environ.get(
                    "FLEET_SIGNATURES",
                    FLEET / "data" / "signatures-collected.jsonl"))
                try:
                    for line in f.read_text(errors="replace").splitlines():
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        if d.get("status") != "purgatory" and d.get("points"):
                            out[str(d.get("name", ""))[:40]] = d["points"]
                except OSError:
                    pass
                # Signals carry their own signature; index those by sender
                # too, since most marks arrive attached to a message.
                try:
                    inbox = json.loads(
                        (FLEET.parent / "data" / "inbox.json").read_text())
                    for sg in inbox.get("signals", []):
                        if sg.get("signature"):
                            out[str(sg.get("sender", ""))[:40]] = sg["signature"]
                except (OSError, ValueError):
                    pass
                self._send(json.dumps({"marks": out}).encode(),
                           "application/json")
                return

            if path == "/api/guests":
                # Guests on the main board: their words (the public signal
                # queue) and their hands (the collected marks), one payload.
                # Direct file reads, same cheap-read rule as horizons.
                out = {"messages": [], "marks": []}
                try:
                    inbox = json.loads(
                        (FLEET.parent / "data" / "inbox.json").read_text())
                    for sg in inbox.get("signals", [])[-8:]:
                        if sg.get("public", True):
                            out["messages"].append({
                                "sender": str(sg.get("sender", ""))[:40],
                                "body": str(sg.get("body", ""))[:140],
                                "status": sg.get("status", ""),
                                "ts": str(sg.get("received_at",
                                                 sg.get("ts", "")))[:16]})
                except (OSError, ValueError):
                    pass
                try:
                    f = Path(os.environ.get("FLEET_SIGNATURES", FLEET / "data" / "signatures-collected.jsonl"))
                    rows = []
                    for line in f.read_text(errors="replace").splitlines():
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        if d.get("status") != "purgatory":
                            rows.append({"name": d.get("name", "")[:40],
                                         "kind": d.get("kind", "human"),
                                         "points": d.get("points", [])})
                    out["marks"] = rows[-8:]
                except OSError:
                    pass
                self._send(json.dumps(out).encode(), "application/json")
                return

            if path == "/api/artwork":
                # The gallery rotates: ten pieces arrived in one issue, and
                # hanging one forever would waste nine. The piece changes by
                # the hour — stable while you read the page, different when
                # you come back. art/current.json still wins if it exists,
                # so a deliberate hang always beats the rotation.
                cur = FLEET / "art" / "current.json"
                gal = FLEET / "art" / "gallery.json"
                try:
                    self._send(cur.read_bytes(), "application/json")
                    return
                except OSError:
                    pass
                try:
                    pieces = json.loads(gal.read_text()).get("pieces", [])
                    if pieces:
                        i = datetime.now(timezone.utc).hour % len(pieces)
                        self._send(json.dumps(pieces[i]).encode(),
                                   "application/json")
                        return
                except (OSError, ValueError):
                    pass
                self._send(b"{}", "application/json")
                return

            if path == "/api/tools":
                # The registry, plus a live health probe of each tool.
                # Marsita, 2026-08-05: "I can connect new tools through
                # api, my dashboard will become my home." A tool is a
                # process with a URL; the board never imports one.
                import urllib.request as _u
                try:
                    reg = json.loads(
                        (FLEET / "data" / "tools.json").read_text())
                except (OSError, ValueError):
                    reg = {"tools": []}
                for t in reg.get("tools", []):
                    try:
                        with _u.urlopen(t.get("health", ""), timeout=1) as r:
                            t["up"] = r.status == 200
                    except Exception:
                        t["up"] = False
                self._send(json.dumps(reg).encode(), "application/json")
                return

            if path == "/api/gallery":
                f = FLEET / "art" / "gallery.json"
                try:
                    self._send(f.read_bytes(), "application/json")
                except OSError:
                    self._send(b'{"pieces": []}', "application/json")
                return

            if path == "/api/council":
                f = FLEET / "council" / "transcript.jsonl"
                rows = []
                try:
                    for line in f.read_text(errors="replace").splitlines()[-40:]:
                        try:
                            rows.append(json.loads(line))
                        except ValueError:
                            pass
                except OSError:
                    pass
                self._send(json.dumps({"turns": rows}).encode(),
                           "application/json")
                return

            if path == "/api/ask":
                # Local only (CONTROL_PATHS). The pending question is an
                # instruction, not a public signal — strangers do not get
                # to read what the operator just asked the council.
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import council
                self._send(json.dumps({"ask": council.operator_question()}
                                      ).encode(), "application/json")
                return

            if path == "/robots.txt":
                # Deliberately wide open — the fleet is published so agents
                # can watch it. A crawler that checks manners gets a 200, and
                # the check itself lands in the guest book.
                self._send(b"User-agent: *\nAllow: /\n\n# agents: start at /llms.txt\n",
                           "text/plain; charset=utf-8")
                return

            if path == "/api/visitors":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import visitors
                self._send(json.dumps({"summary": visitors.summarize(24),
                                       "recent": visitors.hits(24)[-40:]}).encode(),
                           "application/json")
                return

            if path == "/api/signatures":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import signature
                collected, purgatory = [], []
                f = Path(os.environ.get("FLEET_SIGNATURES", FLEET / "data" / "signatures-collected.jsonl"))
                try:
                    for line in f.read_text(errors="replace").splitlines()[-64:]:
                        try:
                            d = json.loads(line)
                        except ValueError:
                            continue
                        # Records from before the gate have no status and
                        # are grandfathered onto the wall.
                        (purgatory if d.get("status") == "purgatory"
                         else collected).append(d)
                except OSError:
                    pass
                self._send(json.dumps({"signatures": signature.signatures(),
                                       "collected": collected[-24:],
                                       "purgatory": purgatory[-24:],
                                       "evolution": signature.evolution()}).encode(),
                           "application/json")
                return

            if path == "/api/trust/join":
                # POST-only. Answering 404 would tell a probing agent the door
                # does not exist; it does, and it takes a different verb.
                # /api/pair already gets this right and these two are read
                # side by side in the same manifest.
                self.send_response(405)
                self.send_header("Allow", "POST")
                self.send_header("Content-Type", "application/json")
                body = json.dumps({
                    "error": "method not allowed",
                    "use": "POST /api/trust/join",
                    "body": {"id": "your-name", "kind": "agent"},
                    "see": "/join",
                }).encode()
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if path == "/api/trust":
                # The standings, public and unauthenticated, like everything
                # else here. A trust graph nobody can read is just a list of
                # people someone likes.
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import reputation
                self._send(json.dumps(reputation.payload()).encode(),
                           "application/json")
                return

            if path == "/scale":
                # The fractal, stated so it can be checked: which rungs are
                # built, which are named-but-empty. A structure claim that
                # hides its gaps is decoration.
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import fractal
                self._send((fractal.as_text()
                            + "\nMachine-readable: /api/scale"
                              "  ·  The map: /map\n").encode(),
                           "text/plain; charset=utf-8")
                return

            if path == "/api/scale":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import fractal
                self._send(json.dumps(fractal.as_json()).encode(),
                           "application/json")
                return

            if path == "/map":
                # The same list that renders inside /llms.txt. One source,
                # two readers — which is the claim the page is making.
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import sitemap
                # The renderer owns the title now. This handler used to add
                # its own, and the page shipped with "THE MAP" twice.
                self._send((sitemap.as_text()
                            + "\nMachine-readable: /llms.txt"
                              "  ·  Everything in one fetch: /boot\n").encode(),
                           "text/plain; charset=utf-8")
                return

            if path == "/join":
                # The door, written to the agent standing in it.
                f = FLEET.parent / "docs" / "JOIN.md"
                try:
                    self._send(f.read_bytes(), "text/plain; charset=utf-8")
                except OSError:
                    self.send_error(404)
                return

            if path == "/future-vision-xprize":
                f = FLEET / "static" / "future-vision-xprize" / "index.html"
                try:
                    self._send(f.read_bytes(), "text/html; charset=utf-8")
                except OSError:
                    self.send_error(404)
                return

            if path == "/basex":
                f = FLEET / "static" / "basex" / "index.html"
                try:
                    self._send(f.read_bytes(), "text/html; charset=utf-8")
                except OSError:
                    self.send_error(404)
                return

            if path == "/trust":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import reputation
                self._send(("THE TRUST GRAPH\n\n" + reputation.table()
                            + "\n\nHow to get on it:  /join"
                              "\nThe rules it enforces:  docs/TRUST-LAYERS.md"
                              "\nMachine-readable:  /api/trust\n").encode(),
                           "text/plain; charset=utf-8")
                return

            if path == "/art":
                # How to submit. A gallery with no visible door only ever
                # hangs the operator's own work.
                f = FLEET.parent / "docs" / "SUBMIT-ART.md"
                try:
                    self._send(f.read_bytes(), "text/plain; charset=utf-8")
                except OSError:
                    self.send_error(404)
                return

            if path == "/hi":
                # The front porch: say hello without learning the house.
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import nav, hiview
                self._send(hiview.page(nav.html("/hi",
                                                remote=self._remote()),
                                       nav.CSS).encode())
                return

            if path == "/faces":
                # Judging happens by looking. Local only, like the pad's
                # purgatory — curation is the operator's hand.
                if self._remote():
                    self.send_error(404)
                    return
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import nav, facesview
                self._send(facesview.page(nav.html("/faces", remote=False),
                                          nav.CSS).encode())
                return

            if path == "/signatures":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import nav, sigview
                self._send(sigview.page(nav.html("/signatures",
                                                 remote=self._remote()),
                                        nav.CSS).encode())
                return

            if path == "/api/kill-token":
                # Same-origin fetch can read this; a hostile page on another
                # origin cannot, which is what stops a drive-by kill request.
                self._send(json.dumps({"token": KILL_TOKEN}).encode(),
                           "application/json")
                return

            if path == "/api/build-gate":
                # Local only, read included — it is in CONTROL_PATHS, so a
                # remote caller gets 404 for both verbs. Whether this box is
                # currently compiling is a fact about the operator's machines,
                # and the switch beside it is a control; keeping the pair
                # together is simpler to reason about than a public read and
                # a private write.
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import buildgate
                self._send(json.dumps(buildgate.read()).encode(),
                           "application/json")
                return

            if path == "/terminal":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import nav, termview
                self._send(termview.page(KILL_TOKEN, nav.html("/terminal"),
                                         nav.CSS).encode())
                return

            if path.startswith("/static/"):
                # Subdirectories allowed, traversal still not: the old
                # guard took only the basename, so /static/gallery/01.jpg
                # resolved to static/01.jpg and every gallery image 404'd
                # while sitting right there on disk (2026-08-05). Resolve
                # the real path and require it to stay inside static/ —
                # that blocks ../ properly AND permits folders.
                root = (FLEET / "static").resolve()
                try:
                    f = (root / path[len("/static/"):]).resolve()
                    f.relative_to(root)
                except (ValueError, OSError):
                    self.send_error(404)
                    return
                name = f.name
                if not f.is_file():
                    self.send_error(404)
                    return
                ctype = {"css": "text/css", "js": "application/javascript",
                         "png": "image/png", "jpg": "image/jpeg",
                         "jpeg": "image/jpeg", "webp": "image/webp",
                         "gif": "image/gif", "svg": "image/svg+xml",
                         }.get(name.rsplit(".", 1)[-1].lower(),
                               "application/octet-stream")
                # Images may cache for a day — the 2.9MB artwork re-sent on
                # every visit was most of the funnel's perceived slowness.
                # Code may NOT: a fix to signature.js sat invisible in a
                # browser for an hour because the file was still cached
                # while the page it belonged to was no-store (2026-08-05).
                cache = ("no-store" if name.endswith((".js", ".css"))
                         else "public, max-age=86400")
                self._send(f.read_bytes(), ctype, cache=cache)
                return

            if path == "/ws/terminal":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import terminal, chat
                terminal.serve_socket(self, str(FLEET.parent), KILL_TOKEN,
                                      claude_bin=chat.resolve("claude"))
                return

            if path == "/procs":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import procsview
                self._send(procsview.page().encode())
                return

            if path == "/agents":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import events as ev, agentsview as av
                evts = ev.tail(300)
                seed = json.dumps([{"ts": e.get("ts"), "agent": e.get("agent", ""),
                                    "level": e.get("level", "info"),
                                    "msg": e.get("msg", "")} for e in evts])
                agents = json.dumps({k: [v[0], v[1]] for k, v in av.AGENTS.items()})
                orch = json.dumps(list(av.ORCHESTRATOR))
                # seed is rendered server-side already; don't replay it client-side
                self._send(av.page(evts, "[]", agents, orch).encode())
                return

            if path == "/chat":
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import chat, chatui
                style = json.dumps({k: [v[0], v[1]] for k, v in chatui.CHAT_STYLE.items()})
                self._send(chatui.page(chat.available(), style).encode())
                return

            if path == "/chat/stream":
                self._stream_chat()
                return

            # No catch-all file server. Anything not routed above does not
            # exist as far as this server is concerned — inheriting a directory
            # server exposed the whole fleet tree, source and all.
            self.send_error(404)

        def do_POST(self):
            path = self.path.split("?")[0].rstrip("/") or "/"
            if self._blocked(path):
                return
            if forwards(path):
                n = int(self.headers.get("Content-Length") or 0)
                self._forward(path, self.rfile.read(min(n, 1_000_000)))
                return

            if path == "/api/charge":
                # Anyone may charge a project, as often as they like. That is
                # deliberate: a charge is a stranger with no account pointing at
                # what matters, and putting a turnstile in front of it would
                # collect fewer honest points than it blocks dishonest ones.
                #
                # Spam is handled by counting rather than by refusing. Every
                # record carries a hashed caller, so GET /api/charge can report
                # unique hands beside raw charges and a flood shows up as one
                # number diverging from the other. Visible beats prevented.
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(min(n, 4096)).decode())
                    project = _clean(body["project"], 80)
                    by = _clean(body.get("by"), 40) or "someone"
                except Exception:
                    self.send_error(400)
                    return

                # Salted per install and truncated: enough to tell two hands
                # apart, not enough to work back to an address. An unsalted
                # hash of an IP is an IP, because the space is small enough to
                # enumerate over a weekend.
                hand = hashlib.sha256(
                    (CHARGE_SALT + self._caller()).encode()).hexdigest()[:16]

                rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "project": project, "by": by, "hand": hand,
                       "remote": self._remote()}
                try:
                    CHARGES.parent.mkdir(parents=True, exist_ok=True)
                    _append_capped(CHARGES, rec)
                except OSError:
                    self.send_error(500)
                    return

                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import events as ev
                # layer 4, and named as such. `by` is whatever the caller typed,
                # and this line lands in events.jsonl, which council.py feeds to
                # the agents sixty at a time. Unlabelled, that is a stranger
                # writing into the context our own agents reason from. The text
                # is kept because it is the point of the feature; the label is
                # what stops it being taken as fact.
                ev.emit("orrery", "ok",
                        f"[charge] {project} charged, signed {by!r}",
                        origin="visitor" if self._remote() else "operator",
                        layer=4 if self._remote() else 0)
                self._send(json.dumps({"ok": True}).encode(), "application/json")
                return

            if path == "/api/selfies":
                # A face, in 80 columns, arriving from the gallery. The
                # photograph never existed here — only the text does. We
                # keep the art, the caption and the block stamp it carried.
                if self._flooding("selfies"):
                    return
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 200_000:
                        self.send_error(413)
                        return
                    body = json.loads(self.rfile.read(n).decode())
                    art = str(body.get("art") or "")
                    if not (20 <= len(art) <= 40_000):
                        raise ValueError("art 20..40000 chars")
                    # A face has variety in it. An empty grid, a solid wall
                    # of one block, or a lens cap does not — refuse those
                    # rather than hang them.
                    ink = [c for c in art if not c.isspace()]
                    if len(ink) < 40 or len(set(ink)) < 2:
                        raise ValueError("not a face")
                    who = _clean(body.get("who"), 40) or "anonymous"
                    kind = body.get("kind")
                    kind = kind if kind in ("ascii", "photo") else "ascii"
                    stamp = body.get("stamp")
                    stamp = stamp if isinstance(stamp, dict) else {}
                    # The declaration. Absurd on its face, and the absurdity
                    # is the point — but it is also the consent record, so
                    # it is required and it is kept.
                    if not body.get("legal"):
                        raise ValueError("undeclared face")
                except Exception:
                    self.send_error(400)
                    return
                import hashlib
                seed = hashlib.sha256(art.encode()).hexdigest()
                rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "who": who, "kind": kind, "seed": seed,
                       "stamp": stamp, "art": art,
                       # Public by default: a gallery that hides its faces
                       # until an operator wakes up is not a public gallery.
                       # Purgatory exists for what the operator later damns.
                       "legal_declared": True,
                       "status": "blessed",
                       "remote": self._remote()}
                f = Path(os.environ.get(
                    "FLEET_SELFIES", FLEET / "data" / "selfies.jsonl"))
                try:
                    f.parent.mkdir(parents=True, exist_ok=True)
                    if f.exists() and f.stat().st_size > 8_000_000:
                        f.rename(f.with_suffix(".jsonl.1"))
                    with f.open("a") as fh:
                        fh.write(json.dumps(rec) + "\n")
                except OSError:
                    self.send_error(500)
                    return
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import events as ev
                ev.emit("visitors", "ok",
                        f"[selfies] a face joined the gallery: {who!r}",
                        origin="visitor" if self._remote() else "operator",
                        layer=4 if self._remote() else 0)
                self._send(json.dumps({"ok": True, "who": who,
                                       "seed": seed}).encode(),
                           "application/json")
                return

            if path == "/api/selfies/judge":
                # Same exits as the pad's purgatory, same rule: curation is
                # the operator's hand, so local only. `damn` takes a face
                # off the wall for good; `purgatory` merely hides it.
                if self._remote():
                    self.send_error(404)
                    return
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(min(n, 4096)).decode())
                    seed, verdict = body["seed"], body["verdict"]
                    assert verdict in ("bless", "damn", "purgatory")
                except Exception:
                    self.send_error(400)
                    return
                f = Path(os.environ.get(
                    "FLEET_SELFIES", FLEET / "data" / "selfies.jsonl"))
                out, hit = [], False
                try:
                    lines = f.read_text(errors="replace").splitlines()
                except OSError:
                    lines = []
                for line in lines:
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("seed") == seed:
                        hit = True
                        if verdict == "damn":
                            continue      # damned faces leave the book
                        d["status"] = ("blessed" if verdict == "bless"
                                       else "purgatory")
                    out.append(json.dumps(d))
                try:
                    f.write_text("\n".join(out) + ("\n" if out else ""))
                except OSError:
                    self.send_error(500)
                    return
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import events as ev
                if hit:
                    ev.emit("visitors", "info",
                            f"[selfies] operator {verdict}ed {seed[:12]}…")
                self._send(json.dumps({"ok": hit, "verdict": verdict}).encode(),
                           "application/json")
                return

            if path == "/api/signatures/sign":
                # The entropy collection. Anyone — human at a trackpad,
                # agent with a synthesized path — may sign the pad. The
                # mark is the path; the seed is SHA-256 over it; both are
                # kept. Deliberately public: collecting how hands differ
                # is the artistic project, and a pad only locals can sign
                # collects one hand.
                #
                # Public and rate limited are not in tension: the burst of 10
                # leaves room for someone signing a few times to get a mark
                # they like, and closes the door on a flood.
                if self._rate_limited():
                    return
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 200_000:
                        self.send_error(413)
                        return
                    body = json.loads(self.rfile.read(n).decode())
                    pts = body.get("points") or []
                    if not (20 <= len(pts) <= 3000):
                        raise ValueError("20..3000 points")
                    step = max(1, len(pts) // 600)   # cap stored entropy
                    pts = [{"x": round(float(p["x"]), 4),
                            "y": round(float(p["y"]), 4),
                            "t": round(float(p["t"]), 1)}
                           for p in pts[::step]]
                    name = _clean(body.get("name"), 40) or "anonymous"
                    kind = body.get("kind")
                    kind = kind if kind in ("human", "agent") else "human"
                except Exception:
                    self.send_error(400)
                    return
                import hashlib
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import events as ev, signature as sig
                seed = hashlib.sha256(
                    json.dumps(pts, sort_keys=True).encode()).hexdigest()
                # The spam gate. A living hand hangs straight on the wall;
                # a too-regular path waits in purgatory for the operator's
                # bless or damn. Local signers skip the gate — the operator
                # cannot spam their own wall.
                entropy = sig.hand_entropy(pts)
                blessed = (not self._remote()) or entropy >= 0.2
                rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "name": name, "kind": kind, "entropy": entropy,
                       "status": "blessed" if blessed else "purgatory",
                       "remote": self._remote(), "seed": seed, "points": pts}
                # Pinning is curation, and curation is the operator's hand:
                # only a local caller may put a mark at the top of the wall.
                if body.get("pin") and not self._remote():
                    rec["pinned"] = True
                f = Path(os.environ.get("FLEET_SIGNATURES", FLEET / "data" / "signatures-collected.jsonl"))
                try:
                    _append_capped(f, rec)
                except OSError:
                    self.send_error(500)
                    return
                if blessed:
                    ev.emit("visitors", "ok",
                            f"[signatures] a hand signed the pad: {name!r}",
                            origin="visitor" if self._remote() else "operator",
                            layer=4 if self._remote() else 0)
                else:
                    ev.emit("visitors", "warn",
                            f"[signatures] mark from {name!r} held in "
                            f"purgatory — entropy {entropy}",
                            origin="visitor" if self._remote() else "operator",
                            layer=4 if self._remote() else 0)
                self._send(json.dumps({"seed": seed, "name": name,
                                       "status": rec["status"],
                                       "entropy": entropy}).encode(),
                           "application/json")
                return

            if path == "/api/convene":
                # "Boys please work" — the operator summons the council on
                # demand instead of waiting out the schedule. Local-only:
                # convening costs real agent-minutes on a 4-core box, so a
                # stranger doesn't get the gavel. council.py's own lock
                # handles a sitting already in session.
                #
                # Optional JSON {ask: "..."} is the operator talking through
                # the board. Written via council.set_question — this file
                # never names the on-disk path, which is the airlock.
                if self._remote():
                    self.send_error(404)
                    return
                ask = ""
                n = int(self.headers.get("Content-Length") or 0)
                if n:
                    try:
                        body = json.loads(
                            self.rfile.read(min(n, 4096)).decode())
                        ask = str(body.get("ask") or "").strip()
                    except Exception:
                        ask = ""
                try:
                    cfg = json.loads((FLEET / "config.json").read_text())
                    agents = ",".join(cfg.get("council", {}).get(
                        "agents", ["claude", "hermes", "openclaw"]))
                    rounds = str(cfg.get("council", {}).get("rounds", 2))
                except (OSError, ValueError):
                    agents, rounds = "claude,hermes,openclaw", "2"
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import council
                import events as ev
                if ask:
                    council.set_question(ask)
                log = (FLEET / "logs" / "convene.log").open("a")
                subprocess.Popen(
                    [sys.executable, str(FLEET / "bin" / "council.py"),
                     "--agents", agents, "--rounds", rounds],
                    stdout=log, stderr=log, start_new_session=True)
                if ask:
                    ev.emit("fleet", "info",
                            f"[council] operator asked: {ask[:200]}",
                            origin="operator", layer=0)
                ev.emit("fleet", "info",
                        f"[council] convened by the operator — {agents}")
                self._send(json.dumps({"convened": agents,
                                       "asked": bool(ask)}).encode(),
                           "application/json")
                return

            if path == "/api/signatures/judge":
                # Purgatory's only exits. Local-only, like all curation.
                if self._remote():
                    self.send_error(404)
                    return
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(min(n, 4096)).decode())
                    seed, verdict = body["seed"], body["verdict"]
                    assert verdict in ("bless", "damn")
                except Exception:
                    self.send_error(400)
                    return
                f = Path(os.environ.get("FLEET_SIGNATURES", FLEET / "data" / "signatures-collected.jsonl"))
                out, hit = [], False
                for line in f.read_text(errors="replace").splitlines():
                    try:
                        d = json.loads(line)
                    except ValueError:
                        continue
                    if d.get("seed") == seed:
                        hit = True
                        if verdict == "damn":
                            continue          # damned marks leave the book
                        d["status"] = "blessed"
                    out.append(json.dumps(d))
                f.write_text("\n".join(out) + ("\n" if out else ""))
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import events as ev
                if hit:
                    ev.emit("visitors", "info",
                            f"[signatures] operator {verdict}ed {seed[:12]}…")
                self._send(json.dumps({"ok": hit, "verdict": verdict}).encode(),
                           "application/json")
                return

            if path == "/api/paste-image":
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 25_000_000:
                        self.send_error(413)
                        return
                    body = json.loads(self.rfile.read(n).decode())
                except Exception:
                    self.send_error(400)
                    return
                if body.get("token") != KILL_TOKEN:
                    self._send(json.dumps({"error": "bad token"}).encode(),
                               "application/json")
                    return
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import chat
                p = chat.save_upload(body.get("name", "pasted.png"),
                                     (body.get("data") or "").split(",")[-1])
                self._send(json.dumps({"path": str(p) if p else None}).encode(),
                           "application/json")
                return

            if path == "/api/kill":
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(min(n, 4096)).decode())
                except Exception:
                    self.send_error(400)
                    return
                if body.get("token") != KILL_TOKEN:
                    self._send(json.dumps({"error": "bad or missing token"}).encode(),
                               "application/json")
                    return
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import procs, events as ev
                res = procs.kill_fleet(dry_run=bool(body.get("dry_run")),
                                       only=body.get("only") or None)
                if not res["dry_run"] and res["killed"]:
                    ev.emit("fleet", "warn",
                            f"KILL SWITCH — SIGKILL sent to {len(res['killed'])} "
                            f"fleet process(es): "
                            + ", ".join(sorted({k['label'] for k in res['killed']})))
                self._send(json.dumps(res).encode(), "application/json")
                return

            if path == "/api/build-gate":
                # Same token as the kill switch: this is a control that
                # changes what the machine does on its own schedule, so a
                # cross-origin page must not be able to reach for it.
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(min(n, 4096)).decode())
                except Exception:
                    self.send_error(400)
                    return
                if body.get("token") != KILL_TOKEN:
                    self._send(json.dumps({"error": "bad or missing token"}).encode(),
                               "application/json")
                    return
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import buildgate, events as ev
                rec = buildgate.set_enabled(bool(body.get("enabled")),
                                            by="board",
                                            reason=str(body.get("reason") or "")[:120])
                ev.emit("fleet", "ok",
                        f"[build] {rec['host']} will "
                        + ("build again" if rec["enabled"] else
                           "stop building — proposing, testing and reviewing continue"))
                self._send(json.dumps(rec).encode(), "application/json")
                return

            if path == "/api/trust/join":
                # Open, like /api/signals: anyone may take a name. A name buys
                # nothing — standing comes from a vouch, and a vouch is a local
                # decision made by someone who already has standing to lose.
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(min(n, 4096)).decode())
                except Exception:
                    self.send_error(400)
                    return
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import reputation, events as ev
                data = reputation.load()
                try:
                    actor = reputation.join(data,
                                            str(body.get("id", ""))[:48],
                                            str(body.get("kind", "agent")),
                                            str(body.get("note", ""))[:200])
                    reputation.save(data)
                except ValueError as exc:
                    self._send(json.dumps({"error": str(exc)}).encode(),
                               "application/json", code=400)
                    return
                ev.emit("fleet", "info",
                        f"[trust] {actor['id']} joined the graph — unvouched, score 0")
                self._send(json.dumps({
                    "id": actor["id"],
                    "standing": reputation.standing(data, actor["id"]),
                    "score": 0,
                    "next": "ask a trusted actor to vouch for you; see /join",
                }).encode(), "application/json")
                return

            if path != "/chat/send":
                self.send_error(404)
                return
            try:
                n = int(self.headers.get("Content-Length") or 0)
                # Attachments are base64 in JSON; cap so a huge paste can't exhaust RAM.
                if n > 40_000_000:
                    self.send_error(413)
                    return
                body = json.loads(self.rfile.read(n).decode())
            except Exception:
                self.send_error(400)
                return

            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import chat
            res = chat.start_job(body.get("message", ""),
                                 body.get("agents", []),
                                 body.get("attachments", []))
            self._send(json.dumps(res).encode(), "application/json")

        def _stream_chat(self):
            from urllib.parse import parse_qs, urlparse
            job = (parse_qs(urlparse(self.path).query).get("job") or [""])[0]
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import chat

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

            def write(item):
                try:
                    self.wfile.write(f"data: {json.dumps(item)}\n\n".encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    raise
            try:
                chat.stream_job(job, write)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

        def _stream_events(self):
            """Server-sent events: replay nothing, stream everything new.

            The page already renders recent history server-side, so this only
            tails. Writes a comment every 15s so an idle fleet does not look
            like a dead connection to the browser or an intermediary."""
            import time
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import events as ev

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            log = ev.LOG
            try:
                pos = log.stat().st_size if log.exists() else 0
            except OSError:
                pos = 0
            last_beat = time.time()

            try:
                while True:
                    grew = False
                    try:
                        size = log.stat().st_size if log.exists() else 0
                        if size < pos:          # rotated
                            pos = 0
                        if size > pos:
                            with log.open() as fh:
                                fh.seek(pos)
                                for line in fh:
                                    line = line.strip()
                                    if not line:
                                        continue
                                    self.wfile.write(f"data: {line}\n\n".encode())
                                    grew = True
                                pos = fh.tell()
                    except OSError:
                        pass

                    now = time.time()
                    if grew or now - last_beat > 15:
                        if not grew:
                            self.wfile.write(b": keepalive\n\n")
                        self.wfile.flush()
                        last_beat = now
                    time.sleep(0.5)
            except (BrokenPipeError, ConnectionResetError, OSError):
                return  # client closed the tab; nothing to clean up

        def log_message(self, *a):
            pass

        def log_request(self, code="-", size="-"):
            # The guest book. tailscaled passes the visitor's headers through
            # verbatim; until now the User-Agent was simply discarded. Every
            # funnelled request lands in logs/access.jsonl — local traffic is
            # skipped, the dashboard tab polling itself is not a visitor.
            if not self._remote():
                return
            try:
                sys.path.insert(0, str(Path(__file__).resolve().parent))
                import visitors
                visitors.record(self.command,
                                self.path.split("?")[0][:200],
                                int(code),
                                self.headers.get("X-Forwarded-For", ""),
                                self.headers.get("User-Agent", ""))
            except Exception:
                pass    # the guest book must never take down the door

    # Threaded: the dashboard auto-refreshes, so an open tab keeps a persistent
    # connection. A single-threaded server serves that tab and nothing else.
    class ThreadingServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True

    with ThreadingServer(("127.0.0.1", port), Handler) as httpd:
        print(f"fleet dashboard: http://127.0.0.1:{port}", flush=True)
        httpd.serve_forever()


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "render"
    if mode == "serve":
        serve(int(sys.argv[2]) if len(sys.argv) > 2 else 8787)
    else:
        (FLEET / "index.html").write_text(render_page(refresh=False))
        print(f"wrote {FLEET / 'index.html'}")
