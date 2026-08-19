#!/usr/bin/env python3
"""Is this machine too busy for another fleet job?

Load of 6 on 4 cores was still 'ok' while the box swapped millions of
pages. Snappy means: defer when load > ncpu, or the compressor is
holding more than ~1.5 GB. Never starts a model.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
WORKER = FLEET / "workers" / "pressure.json"
PAGE = 4096
COMPRESSOR_GB_HOT = 1.5


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


def snapshot(vm_stat_text: str | None = None) -> dict:
    load = load1()
    cores = ncpu()
    gate = max_load()
    comp = compressor_gb(vm_stat_text)
    load_hot = load > gate
    ram_hot = comp >= COMPRESSOR_GB_HOT
    reasons = []
    if load_hot:
        reasons.append(f"load {load:.1f} over {gate:.0f} on {cores} cores")
    if ram_hot:
        reasons.append(f"compressor {comp:.1f}G")
    return {
        "load1": round(load, 2),
        "ncpu": cores,
        "max_load": gate,
        "compressor_gb": round(comp, 2),
        "hot": load_hot or ram_hot,
        "reason": "; ".join(reasons) or "ok",
    }


def too_hot(vm_stat_text: str | None = None) -> bool:
    return snapshot(vm_stat_text)["hot"]


def publish(snap=None):
    snap = snap or snapshot()
    worker = {
        "worker": "pressure",
        "kind": "pulse",
        "target": "load + compressor",
        "last_run": now(),
        "status": "warn" if snap["hot"] else "pass",
        "summary": snap["reason"],
        "detail": json.dumps(snap, indent=2),
        "tests_passed": 0 if snap["hot"] else 1,
        "tests_failed": 1 if snap["hot"] else 0,
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
