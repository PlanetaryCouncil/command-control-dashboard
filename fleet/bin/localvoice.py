#!/usr/bin/env python3
"""The local model, kept alive as a backup rather than a participant.

  localvoice.py            one ping — asks it something small, records it

This laptop is too old and slow to run a local model as a working agent.
Measured 2026-08-05: llama3.2:1b took a median 169s per council turn and
produced one usable thought in twenty; qwen2.5:3b took 564s on the same
brief. Prefill on four cores with no GPU runs around 5 tokens/second, so
any prompt with real context costs minutes before a word comes back.

Marsita: "maybe we can agree this laptop is too old / slow for local
models... maybe keep one LLM as ultimate backup — but with no overheads
of maintaining — one daily ping so it is not lonely."

So: it stays installed, stays out of the council, and gets one short
question a day. The ping is not sentiment — it is a health check with a
memory. If the wifi dies and every cloud agent goes silent, this is what
is left, and you want to know it still answers BEFORE that day, not
during it.

Cost: one question, ~60 tokens out, about 80 seconds, once every 24 hours.
"""

import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FLEET / "bin"))

import chat          # noqa: E402
import events as ev  # noqa: E402

LEDGER = FLEET / "data" / "localvoice.jsonl"

# A health check that hangs is not a health check. 2026-08-06 it answered in
# 25.3s; 2026-08-07 it blocked for 607.1s, holding two of four cores and its
# share of 8GB against the rest of the fleet. Past ~90s the answer has stopped
# being useful and only the RAM matters, so we give up and mark alert.
# A cold model on this laptop is mostly disk, not compute: llama3.2:1b needs
# ~75s to answer its first question of the day because ollama loads the weights
# with --no-mmap and the box is already 1.5GB into swap. 90s left almost no
# margin, so the check was reporting a slow load as a dead model — which is the
# specific lie a health check must not tell.
PING_TIMEOUT = 240

# Default to the small model. qwen2.5:3b was the original choice and it can no
# longer load here at all: the runner sat at 67MB resident and 12% cpu with a
# load average of 3.6, which is thrash, not work. The NUC keeps the bigger
# models; this box only has to prove a self-hosted voice still answers.
DEFAULT_MODEL = "llama3.2:1b"

# Short, answerable, and different each day — so a stuck cache or a dead
# model shows up as a wrong or missing answer rather than a repeat.
QUESTIONS = [
    "In one sentence: what is a watchdog process?",
    "In one sentence: why would a system prefer append-only logs?",
    "In one sentence: what does a load average measure?",
    "In one sentence: what is a race condition?",
    "In one sentence: why do backups need to be tested?",
    "In one sentence: what is idempotence?",
    "In one sentence: why is a queue that fills faster than it drains a problem?",
]


def ping():
    import pressure
    if pressure.too_hot():
        snap = pressure.snapshot()
        print(f"deferred — {snap['reason']}")
        return 0
    q = random.choice(QUESTIONS)
    noop = lambda *a, **k: None
    t0 = time.time()
    model = os.environ.get("FLEET_OLLAMA_MODEL") or DEFAULT_MODEL
    answer = chat.ask_ollama(model, q, [], noop, num_predict=80,
                             timeout=PING_TIMEOUT)
    secs = round(time.time() - t0, 1)
    ok = bool(answer) and not answer.startswith("[") and len(answer) > 20

    rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "model": model, "question": q,
           "seconds": secs, "ok": ok,
           "answer": " ".join(str(answer).split())[:300]}
    LEDGER.parent.mkdir(exist_ok=True)
    with LEDGER.open("a") as fh:
        fh.write(json.dumps(rec) + "\n")

    # The worker file, so the board carries it like anything else. Never
    # "fail": a slow local model is not a broken fleet, and this must not
    # be the thing that turns the board red.
    (FLEET / "workers").mkdir(exist_ok=True)
    (FLEET / "workers" / "localvoice.json").write_text(json.dumps({
        "worker": "localvoice", "kind": "backup",
        "status": "pass" if ok else "alert",
        "last_run": rec["ts"],
        "summary": (f"{model} answered in {secs}s — the offline "
                    f"fallback is alive" if ok
                    else f"{model} did not answer ({secs}s)"),
        "duration_s": secs,
    }, indent=2) + "\n")

    ev.emit("localvoice", "ok" if ok else "warn",
            f"[local] {model} {'answered' if ok else 'failed'} "
            f"in {secs}s — the offline fallback is "
            f"{'alive' if ok else 'NOT responding'}")
    print(f"{secs}s ok={ok}: {rec['answer'][:120]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(ping())
