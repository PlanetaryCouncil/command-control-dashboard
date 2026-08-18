#!/usr/bin/env python3
"""Pull the NUC's browser-monitor result onto the fleet board.

The NUC writes ~/monitor/last.json. This host fetches it over SSH
(key-only) and republishes a public-safe worker card. Set FLEET_NUC
(user@host); the script exits if that is unset.
"""
import json
import os
import pathlib
import subprocess
import sys

FLEET = pathlib.Path(__file__).resolve().parent.parent


def nuc_target():
    return os.environ.get("FLEET_NUC", "").strip()


def _public_results(results):
    out = []
    for x in results or []:
        if not isinstance(x, dict):
            continue
        out.append({
            "profile": x.get("profile", "?"),
            "status": x.get("status"),
            "load_s": x.get("load_s"),
            "ok": x.get("ok"),
        })
    return out


def public_report(ok, url="marsrobertson.com", results=None, unreachable=None,
                  ts=None):
    rep = {"ok": bool(ok), "url": url, "results": _public_results(results)}
    if unreachable:
        rep["unreachable"] = unreachable
    if ts:
        rep["ts"] = ts
    return rep


def worker_record(rep):
    res = rep.get("results") or []
    if res:
        summary = " · ".join(
            f"{x.get('profile', '?')} {x.get('status')} {x.get('load_s')}s"
            for x in res)
    else:
        summary = rep.get("unreachable") or "no data"
    ts = (rep.get("ts") or "").replace("+00:00", "Z")
    return {
        "worker": "nuc",
        "kind": "browser",
        "target": rep.get("url", "marsrobertson.com"),
        "last_run": ts,
        "status": "pass" if rep.get("ok") else "fail",
        "summary": f"human browser (desktop+mobile) · {summary}",
        "detail": json.dumps(rep, indent=2),
        "tests_passed": sum(1 for x in res if x.get("ok")),
        "tests_failed": (sum(1 for x in res if not x.get("ok"))
                         or (0 if rep.get("ok") else 1)),
        "duration_s": round(sum((x.get("load_s") or 0) for x in res), 1),
    }


def pull_shots(target, dest_dir):
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in ("desktop", "mobile"):
        dest = dest_dir / f"{name}.png"
        r = subprocess.run(
            ["scp", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
             f"{target}:~/monitor/shots/{name}.png", str(dest)],
            capture_output=True)
        if r.returncode != 0 and dest.exists():
            dest.unlink()


def fetch_report(target):
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
         target, "cat ~/monitor/last.json"],
        capture_output=True, text=True)
    if r.returncode != 0:
        return public_report(False, unreachable="ssh failed")
    try:
        raw = json.loads(r.stdout)
    except ValueError:
        return public_report(False, unreachable="unparseable")
    if not isinstance(raw, dict):
        return public_report(False, unreachable="unparseable")
    return public_report(
        raw.get("ok"),
        url=raw.get("url") or "marsrobertson.com",
        results=raw.get("results"),
        ts=raw.get("ts"),
    )


def publish(rep, fleet=FLEET):
    workers = fleet / "workers"
    workers.mkdir(parents=True, exist_ok=True)
    worker = worker_record(rep)
    (workers / "nuc.json").write_text(json.dumps(worker, indent=2) + "\n")
    return worker


def main(argv=None):
    target = nuc_target()
    if not target:
        print("FLEET_NUC is unset (expected user@host)", file=sys.stderr)
        return 2
    rep = fetch_report(target)
    pull_shots(target, FLEET / "static" / "nuc")
    worker = publish(rep)
    print(f"published nuc: {worker['status']} — {worker['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
