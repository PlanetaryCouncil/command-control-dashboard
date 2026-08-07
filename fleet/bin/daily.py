#!/usr/bin/env python3
"""One message a day. The only thing Marsita has to read.

Marsita, 2026-08-07: "I don't want to worry about infra / pr / code / issues
---> fleet of agents does it... Daily summary maybe... just write me 1
liners."

So the format is fixed and small: what landed, what is stuck, what needs a
human. One line each, no diffs, no branch names where a description will do.
A summary that grows into a report is a summary nobody reads, and then the
fleet is unsupervised rather than autonomous.

The last section is the only one that costs attention, and it is deliberately
narrow: money, public identity, irreversible actions, and genuine forks in
intent. Everything else the fleet decides.

    daily.py            print it
    daily.py --send     print it and send it to Telegram
    daily.py --json     the same figures as data, for a page to render
    daily.py --publish  write that data to the public site and push it
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
REPO = FLEET.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

WINDOW_H = 24


def _since() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=WINDOW_H)


def _ts(v) -> datetime | None:
    try:
        t = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _run(cmd, cwd=REPO):
    try:
        p = subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                           text=True, timeout=60)
        return p.stdout.strip()
    except Exception:
        return ""


def landed() -> list[str]:
    """What actually reached main, in the words of the commit subject."""
    out = _run(["git", "log", "--since", f"{WINDOW_H} hours ago",
                "--no-merges", "--pretty=%s", "main"])
    return [l for l in out.splitlines() if l.strip()][:12]


def pipeline_state() -> tuple[list[str], list[str]]:
    """Anything the pipeline could not finish, and why — one line each."""
    stuck, rejected = [], []
    p = FLEET / "rota" / "pipeline.jsonl"
    try:
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    except (OSError, json.JSONDecodeError):
        return stuck, rejected
    cut = _since()
    for r in rows:
        t = _ts(r.get("ts"))
        if t and t < cut:
            continue
        name = str(r.get("branch", "")).split("/")[-1][:44]
        if r.get("stage") == "land" and not r.get("ok"):
            stuck.append(f"{name} could not land: {str(r.get('detail'))[:60]}")
        elif r.get("stage") == "verify" and not r.get("ok"):
            rejected.append(f"{name} rejected: {str(r.get('review'))[:70]}")
    return stuck[-6:], rejected[-6:]


def workers_needing_you() -> list[str]:
    """Only genuine alerts. A worker that is merely slow is not news."""
    out = []
    for f in sorted((FLEET / "workers").glob("*.json")):
        try:
            w = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if w.get("status") in ("fail", "alert"):
            out.append(f"{w.get('worker')}: {str(w.get('summary'))[:70]}")
    return out


def proposals_open() -> int:
    p = FLEET / "rota" / "proposals.jsonl"
    try:
        rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    except (OSError, json.JSONDecodeError):
        return 0
    try:
        import pipeline
        return len([r for r in rows
                    if r.get("text") and r["ts"] not in pipeline.by_proposal()])
    except Exception:
        return len([r for r in rows if r.get("text")])


def projects() -> list[dict]:
    """The project list, with whichever ones the fleet actually watches.

    projects.yaml is the operator's own list — what exists and what state it
    is in. The watchdogs know something narrower but harder: whether the
    tests ran and passed today. Joining them by name gives a project row that
    says both "this is live" and "this was proved live an hour ago", which
    neither source can say alone.

    Parsed with a deliberately small reader rather than a YAML dependency:
    this file's project block is a flat list of scalar fields, and adding a
    third-party parser to the daily job to read it would be the tail wagging
    the dog.
    """
    p = FLEET / "data" / "projects.yaml"
    try:
        lines = p.read_text().splitlines()
    except OSError:
        return []

    out, cur, inside = [], None, False
    for raw in lines:
        if raw.startswith("projects:"):
            inside = True
            continue
        if inside and raw and not raw[0].isspace():
            break                       # next top-level key ends the block
        if not inside:
            continue
        s = raw.strip()
        if s.startswith("- name:"):
            cur = {"name": s.split(":", 1)[1].strip()}
            out.append(cur)
        elif cur is not None and ":" in s and not s.startswith("#"):
            k, v = s.split(":", 1)
            k, v = k.strip(), v.split("#")[0].strip()
            if k in ("status", "url", "tagline") and v:
                cur[k] = v.strip('"')

    # A watchdog result, where one exists, outranks the yaml's self-report.
    checks = {}
    for f in (FLEET / "workers").glob("*.json"):
        try:
            w = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        checks[str(w.get("worker", "")).lower()] = {
            "status": w.get("status"), "last_run": w.get("last_run")}
    for pr in out:
        key = pr["name"].lower().replace(" ", "-")
        if key in checks:
            pr["tests"] = checks[key]
    return out


def build_hosts() -> str:
    try:
        import buildgate
        g = buildgate.read()
        return f"{g['host']}: build {'on' if g['enabled'] else 'off'}"
    except Exception:
        return ""


def report() -> str:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    land = landed()
    stuck, rejected = pipeline_state()
    alerts = workers_needing_you()
    open_props = proposals_open()

    L = [f"fleet · {day} · last {WINDOW_H}h", ""]
    L.append(f"landed on main: {len(land)}")
    L += [f"  {s[:72]}" for s in land] or ["  nothing"]

    if rejected:
        L += ["", f"rejected by review: {len(rejected)}"]
        L += [f"  {s}" for s in rejected]
    if stuck:
        L += ["", "could not land:"]
        L += [f"  {s}" for s in stuck]

    L += ["", f"proposals waiting: {open_props}"]
    hosts = build_hosts()
    if hosts:
        L.append(hosts)

    L += ["", "needs you:"]
    # The whole point of the section is that it is usually empty. If this
    # starts filling up every day, the escalation rule is wrong, not Marsita.
    L += [f"  {s}" for s in alerts] or ["  nothing"]
    return "\n".join(L)


def send(text: str) -> bool:
    """To every allowlisted chat — which is the operator, and only them.

    Reuses telegram.py's loader rather than reading the token here: that
    module already refuses a config other users can read, and a second
    credential path is a second place to get it wrong.
    """
    try:
        import telegram
        token, allowed = telegram._load()
        for chat_id in sorted(allowed):
            telegram.send(token, chat_id, text)
        return bool(allowed)
    except Exception as e:
        print(f"send failed: {e}", file=sys.stderr)
        return False


def data() -> dict:
    """The same figures the text report reads from, as data.

    A published page should render numbers, not scrape a paragraph. Same
    source, two renderings — so the page and the Telegram message can never
    disagree about how many things landed.
    """
    stuck, rejected = pipeline_state()
    land = landed()
    try:
        import buildgate
        gate = buildgate.read()
    except Exception:
        gate = {}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_hours": WINDOW_H,
        "host": gate.get("host"),
        "building": gate.get("enabled"),
        "landed": land,
        "landed_count": len(land),
        "rejected": rejected,
        "could_not_land": stuck,
        "proposals_waiting": proposals_open(),
        "needs_you": workers_needing_you(),
        "projects": projects(),
    }


SITE = Path(os.environ.get(
    "FLEET_SITE_REPO", Path.home() / "projects" / "planetarycouncil.org"))
SITE_FILE = "fleet-report/daily.json"


def publish() -> bool:
    """Write the figures into the public site and push, if anything changed.

    The page at planetarycouncil.org/fleet-report/ reads this file, so the
    published numbers age exactly as fast as the morning message does. No
    commit when the data is unchanged — a repository full of "no news today"
    commits is noise, and the timestamp alone always differs.
    """
    repo = SITE
    target = repo / SITE_FILE
    if not (repo / ".git").exists():
        print(f"no site checkout at {repo}", file=sys.stderr)
        return False

    fresh = data()
    try:
        old = json.loads(target.read_text())
        old.pop("generated_at", None)
        cmp_new = dict(fresh)
        cmp_new.pop("generated_at", None)
        if old == cmp_new:
            print("site unchanged", file=sys.stderr)
            return True
    except (OSError, json.JSONDecodeError):
        pass

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(fresh, indent=2) + "\n")

    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    msg = (f"fleet-report: {day} — {fresh['landed_count']} landed, "
           f"{fresh['proposals_waiting']} waiting")
    for cmd in (["git", "add", SITE_FILE],
                ["git", "commit", "-m", msg],
                ["git", "pull", "--rebase", "origin", "gh-pages"],
                ["git", "push", "origin", "gh-pages"]):
        p = subprocess.run(cmd, cwd=str(repo), capture_output=True, text=True,
                           timeout=180)
        if p.returncode != 0:
            print(f"{' '.join(cmd)}: {p.stderr.strip()[:200]}", file=sys.stderr)
            return False
    print("site published", file=sys.stderr)
    return True


if __name__ == "__main__":
    # launchd takes one command, systemd takes a list — hence the combined
    # form, so both schedulers can do the whole morning in one entry.
    both = "--publish-and-send" in sys.argv
    if "--publish" in sys.argv or both:
        publish()
        if not both:
            sys.exit(0)
    if "--json" in sys.argv:
        print(json.dumps(data(), indent=2))
        sys.exit(0)
    txt = report()
    print(txt)
    if "--send" in sys.argv or both:
        print("sent" if send(txt) else "not sent", file=sys.stderr)
