#!/usr/bin/env python3
"""Is this machine too busy for another fleet job?

CPU, RAM, SSD. Load of 6 on 4 cores was still 'ok' while the box
swapped millions of pages. Snappy means: defer when load > ncpu, or
the compressor is holding more than ~1.5 GB. Disk is watched the same
way — df, never a walk of the tree. Never starts a model.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
WORKER = FLEET / "workers" / "pressure.json"
PAGE = 4096
COMPRESSOR_GB_HOT = 1.5
DISK_FREE_WARN_GB = 5.0
DISK_FREE_ALERT_GB = 2.0
DISK_USED_WARN = 90
DISK_USED_ALERT = 95


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ncpu() -> int:
    return os.cpu_count() or 4


def load1() -> float:
    return os.getloadavg()[0]


def max_load() -> float:
    env = os.environ.get("MAX_LOAD")
    if env:
        try:
            return float(env)
        except ValueError:
            pass
    return float(ncpu())


def compressor_gb(vm_stat_text: str | None = None) -> float:
    text = vm_stat_text
    if text is None:
        try:
            r = subprocess.run(["vm_stat"], capture_output=True, text=True,
                               timeout=2)
            text = r.stdout or ""
        except Exception:
            return 0.0
    for line in text.splitlines():
        if "occupied by compressor" in line.lower():
            raw = line.split(":")[-1].strip().rstrip(".")
            try:
                return int(raw) * PAGE / (1024 ** 3)
            except ValueError:
                return 0.0
    return 0.0


def disk(path: str | None = None) -> dict:
    """Usage of the volume that holds the fleet. One statvfs. No walk."""
    target = path or str(FLEET)
    try:
        u = shutil.disk_usage(target)
    except OSError:
        return {"path": target, "total_gb": 0, "used_gb": 0, "free_gb": 0,
                "used_pct": 0, "tight": False, "alert": False}
    total = u.total / (1024 ** 3)
    used = u.used / (1024 ** 3)
    free = u.free / (1024 ** 3)
    pct = (100.0 * u.used / u.total) if u.total else 0
    alert = free < DISK_FREE_ALERT_GB or pct >= DISK_USED_ALERT
    tight = alert or free < DISK_FREE_WARN_GB or pct >= DISK_USED_WARN
    return {
        "path": target,
        "total_gb": round(total, 1),
        "used_gb": round(used, 1),
        "free_gb": round(free, 1),
        "used_pct": round(pct, 1),
        "tight": tight,
        "alert": alert,
    }


def snapshot(vm_stat_text: str | None = None, disk_path: str | None = None) -> dict:
    load = load1()
    cores = ncpu()
    gate = max_load()
    comp = compressor_gb(vm_stat_text)
    dsk = disk(disk_path)
    load_hot = load > gate
    ram_hot = comp >= COMPRESSOR_GB_HOT
    reasons = []
    if load_hot:
        reasons.append(f"load {load:.1f} over {gate:.0f} on {cores} cores")
    if ram_hot:
        reasons.append(f"compressor {comp:.1f}G")
    if dsk["alert"]:
        reasons.append(f"disk {dsk['used_pct']:.0f}% {dsk['free_gb']:.1f}G free")
    elif dsk["tight"]:
        reasons.append(f"disk {dsk['used_pct']:.0f}% {dsk['free_gb']:.1f}G free")
    return {
        "load1": round(load, 2),
        "ncpu": cores,
        "max_load": gate,
        "compressor_gb": round(comp, 2),
        "disk": dsk,
        "hot": load_hot or ram_hot,
        "disk_tight": dsk["tight"],
        "reason": "; ".join(reasons) or (
            f"ok · disk {dsk['used_pct']:.0f}% {dsk['free_gb']:.0f}G free"),
    }


def too_hot(vm_stat_text: str | None = None) -> bool:
    return snapshot(vm_stat_text)["hot"]


def disk_alert(path: str | None = None) -> bool:
    return bool(disk(path).get("alert"))


def publish(snap=None):
    snap = snap or snapshot()
    worker = {
        "worker": "pressure",
        "kind": "pulse",
        "target": "cpu + ram + ssd",
        "last_run": now(),
        "status": ("alert" if (snap.get("disk") or {}).get("alert")
                   else "warn" if snap["hot"] or snap.get("disk_tight")
                   else "pass"),
        "summary": snap["reason"],
        "detail": json.dumps(snap, indent=2),
        "tests_passed": 0 if snap["hot"] or snap.get("disk_tight") else 1,
        "tests_failed": 1 if snap["hot"] or snap.get("disk_tight") else 0,
        "duration_s": 0,
    }
    WORKER.parent.mkdir(parents=True, exist_ok=True)
    WORKER.write_text(json.dumps(worker, indent=2) + "\n")
    return worker


def main():
    snap = snapshot()
    w = publish(snap)
    print(w["summary"])
    return 1 if snap["hot"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
