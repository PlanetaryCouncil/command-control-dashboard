#!/usr/bin/env python3
"""Multi-agent chat backend.

One question, fanned out to any subset of the agents on this machine, each
answering independently in parallel. Adapters are deliberately thin — every
agent already has a working one-shot interface, so this drives those rather
than reimplementing anyone's runtime.

Attachments arrive base64 in JSON (no multipart parsing); text files are inlined
into the prompt, images are written to disk and handed to Claude by path.

Local vision was tried and dropped: llava:7b could not describe a 64x64 image in
over two minutes on this machine's Intel m3, so images route to Claude instead.
Text still runs locally and privately on dolphin-llama3.
"""

import base64
import json
import os
import queue
import re
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
UPLOADS = FLEET / "uploads"
OLLAMA = "http://127.0.0.1:11434"
# The local model. dolphin-llama3 (8B, 4.7GB) was measured unable to take a
# council turn on this 8GB box (2026-08-03: 300s timeout, load 166).
# llama3.2:1b (1.3GB) measured 2026-08-04: 160 tokens in 17s, 10.4 tok/s.
# qwen2.5:3b answers a short question better than llama3.2:1b and costs
# about the same when the prompt is small (measured 2026-08-05: 79s vs
# 87s on a one-line question). It is markedly worse on long input — 195s
# vs 71s at 200 words — which is exactly why the local model belongs in
# the chat pane, where questions are short, and not in the council, where
# the brief is 1,500 tokens.
OLLAMA_MODEL = os.environ.get("FLEET_OLLAMA_MODEL", "qwen2.5:3b")

TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml",
            ".csv", ".tsv", ".sh", ".html", ".css", ".sql", ".xml", ".log", ".rs", ".go"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# name -> (label, needs_vision_model)
AGENTS = {
    "ollama":   ("llama3.2 1B (local, private, text only)", False),
    "claude":   ("Claude Code (handles images)", False),
    "hermes":   ("Hermes", False),
    "openclaw": ("OpenClaw", False),
    "grok":     ("Grok (xAI, cloud, has a tool loop)", False),
}

JOBS = {}          # job_id -> {queue, agents, done}
JOBS_LOCK = threading.Lock()

# Four agents at once on a four-core laptop means each gets a quarter core while
# competing with an 8B model doing CPU inference. Observed: load average 15, and
# Claude and Hermes both hitting a 300s timeout on "what is your name". Two at a
# time finishes sooner in wall-clock than four in parallel, because nothing
# thrashes. Raise on better hardware via FLEET_CHAT_CONCURRENCY.
CONCURRENCY = int(os.environ.get("FLEET_CHAT_CONCURRENCY", "2"))
_slots = threading.Semaphore(CONCURRENCY)

# But only LOCAL work contends for cores. hermes and openclaw are calls to
# somebody else's GPU: they cost this laptop a socket and some waiting, and
# making them queue behind a local model is throttling the wrong thing.
# Marsita, 2026-08-05: "I prefer to launch them all at once. Some agents
# use external API (cloud), only ollama is local here."
LOCAL_AGENTS = {"ollama", "claude"}


class _NoWait:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_free = _NoWait()


# --------------------------------------------------------------------------- utils
def safe_name(name):
    name = re.sub(r"[^A-Za-z0-9._-]", "_", (name or "file"))[-80:]
    return name or "file"


def save_upload(name, b64):
    UPLOADS.mkdir(exist_ok=True)
    p = UPLOADS / f"{int(time.time())}-{safe_name(name)}"
    try:
        p.write_bytes(base64.b64decode(b64))
        return p
    except Exception:
        return None


def build_context(attachments):
    """Split attachments into inlined text and base64 images."""
    text_parts, images, saved = [], [], []
    for a in attachments or []:
        name = a.get("name", "file")
        b64 = (a.get("data") or "").split(",")[-1]   # tolerate data: URLs
        if not b64:
            continue
        p = save_upload(name, b64)
        if p:
            saved.append(p)
        ext = Path(name).suffix.lower()
        if ext in IMAGE_EXT:
            images.append(b64)
        elif ext in TEXT_EXT or not ext:
            try:
                body = base64.b64decode(b64).decode("utf-8", errors="replace")
                text_parts.append(f"--- file: {name} ---\n{body[:20000]}")
            except Exception:
                pass
    return "\n\n".join(text_parts), images, saved


def resolve(name):
    """Absolute path to an agent binary.

    launchd gives the server a minimal PATH that misses ~/.local/bin and the
    node prefix, so bare names fail with ENOENT even though they work in a
    shell. Resolve against a known-good search path instead of inheriting one.
    """
    import shutil
    extra = [
        str(Path.home() / ".local/bin"),
        "/usr/local/bin", "/opt/homebrew/bin",
        "/usr/local/opt/node@22/bin", "/usr/bin", "/bin",
    ]
    found = shutil.which(name, path=":".join(extra + [os.environ.get("PATH", "")]))
    return found or name


def run_cmd(cmd, timeout, stdin_text=None):
    cmd = [resolve(cmd[0])] + list(cmd[1:])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           input=stdin_text, cwd=str(FLEET))
        out = (r.stdout or "").strip()
        err = (r.stderr or "").strip()
        if not out and err:
            return f"[stderr] {err[:1500]}"
        return out or "(no output)"
    except subprocess.TimeoutExpired as e:
        # "Did not answer" and "answered too slowly" are different faults —
        # hermes hit the 300s ceiling three times on 2026-08-02 and the board
        # could not say whether it was alive. The killed process's partial
        # stdout is the tell: present means slow, absent means silent.
        part = e.stdout if e.stdout is not None else e.output
        if isinstance(part, bytes):
            part = part.decode(errors="replace")
        part = " ".join((part or "").split())
        if part:
            return f"[timed out after {timeout}s; partial: {part[:200]}]"
        return f"[timed out after {timeout}s; no output]"
    except Exception as e:
        return f"[error] {e}"


# --------------------------------------------------------------------------- adapters
def ask_ollama(model, prompt, images, emit, num_predict=None, timeout=600):
    """Local model. Cap the answer length, or it will not finish.

    An 8B model on this CPU generates a few tokens a second, and slower while
    the box is swapping. On 2026-08-03 its first council turn hit the 300s
    timeout — not because the prompt was too big (912 tokens, well inside its
    4096 window) but because nobody bounded the reply. A cloud model writes six
    paragraphs in twenty seconds; this one would still be writing at five
    minutes.

    So callers that need it to finish pass num_predict. A short answer from a
    genuinely independent model beats a long one that never arrives.

    timeout is wall-clock, not per-read. urlopen's timeout only bounds each
    socket read, so a model dribbling one token a minute never trips it: on
    2026-08-07 the localvoice ping hung for 607s under a nominal 600s cap.
    The streaming loop checks the deadline itself and gives up mid-answer.
    """
    deadline = time.time() + timeout
    body = {"model": model, "stream": True,
            "messages": [{"role": "user", "content": prompt}]}
    if num_predict:
        body["options"] = {"num_predict": num_predict}
    if images:
        body["messages"][0]["images"] = images
    req = urllib.request.Request(
        f"{OLLAMA}/api/chat", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    acc = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            for line in r:
                if time.time() > deadline:
                    part = "".join(acc).strip()
                    return (f"[timed out after {timeout}s; partial: {part}]"
                            if part else f"[timed out after {timeout}s; no output]")
                line = line.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tok = (d.get("message") or {}).get("content", "")
                if tok:
                    acc.append(tok)
                    emit("token", tok)          # only local models stream
                if d.get("done"):
                    break
    except Exception as e:
        return f"[error] {e}"
    return "".join(acc).strip() or "(no output)"


def ask_claude(prompt, files, emit, timeout=600):
    if files:
        prompt += ("\n\nAttached files (read them from these paths):\n"
                   + "\n".join(str(f) for f in files))
    # The prompt goes on stdin, not as an argument: `--add-dir` is variadic and
    # would swallow a trailing positional prompt as another directory.
    # Uploads live under FLEET, so --add-dir is what makes them readable.
    # WebSearch/WebFetch: asked for on 2026-08-04 ("ability to browse the
    # web") — claude is the only fleet agent with a tool loop, so it is the
    # only one that can. hermes/openclaw/ollama are single-shot chat calls.
    return run_cmd(["claude", "--print", "--permission-mode", "acceptEdits",
                    "--allowedTools", "WebSearch", "WebFetch",
                    "--add-dir", str(FLEET)], timeout=timeout, stdin_text=prompt)


def ask_grok(prompt, files, emit, timeout=600):
    """One Grok turn, headless.

    `-p` is the single-turn mode, the same shape as `claude --print`, and the
    prompt goes as an argument because grok has no variadic option to swallow
    it. `--output-format plain` is the default but is stated anyway: the other
    formats are NDJSON, and a silent change of default would arrive here as an
    agent that suddenly answers in JSON.

    No permission mode is passed, so it stays on `default` - grok reads and
    reasons for the fleet, and nothing here needs it to edit anything. An agent
    joins the fleet able to speak before it joins able to act.
    """
    if files:
        prompt += ("\n\nAttached files (read them from these paths):\n"
                   + "\n".join(str(f) for f in files))
    return run_cmd(["grok", "-p", prompt, "--output-format", "plain"],
                   timeout=timeout)


def ask_hermes(prompt, emit, timeout=300):
    return run_cmd(["hermes", "-z", prompt], timeout=timeout)


def ask_openclaw(prompt, emit, session=None, timeout=420):
    """One OpenClaw turn.

    `session` scopes the gateway's conversation memory. A fixed key makes the
    agent remember every previous turn, which is right for chat and WRONG for
    any experiment that needs turns to be independent — it silently reintroduces
    a channel you believe you have severed. Callers that need isolation pass a
    fresh key.
    """
    key = f"agent:main:{session or 'fleetchat'}"
    # Slower than the rest: a full gateway turn. Long timeout beats a false failure.
    out = run_cmd(["openclaw", "agent", "--agent", "main",
                   "--session-key", key,
                   "-m", prompt, "--json"], timeout=timeout)
    try:
        d = json.loads(out)
    except Exception:
        return out

    # The gateway wraps the reply: {"result": {"payloads": [{"text": ...}]}}.
    # Without unwrapping, other agents receive a JSON envelope instead of prose.
    res = d.get("result")
    if isinstance(res, dict):
        parts = [p.get("text", "") for p in (res.get("payloads") or [])
                 if isinstance(p, dict) and isinstance(p.get("text"), str)]
        joined = "\n".join(x for x in parts if x.strip()).strip()
        if joined:
            return joined

    for k in ("reply", "text", "message", "content", "output"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return json.dumps(d)[:2000]


# --------------------------------------------------------------------------- fan-out
def _worker(job_id, agent, prompt, images, files):
    q = JOBS[job_id]["queue"]

    def emit(kind, data):
        q.put({"agent": agent, "kind": kind, "data": data})

    gate = _slots if agent in LOCAL_AGENTS else _free
    if agent in LOCAL_AGENTS:
        emit("queued", "")
    with gate:                         # only local inference waits
        emit("start", "")
        t0 = time.time()
        _run(agent, prompt, images, files, emit, q, job_id, t0)


def _run(agent, prompt, images, files, emit, q, job_id, t0):
    try:
        if agent == "ollama":
            text = ask_ollama(OLLAMA_MODEL, prompt, [], emit)
        elif agent == "claude":
            text = ask_claude(prompt, files, emit)
        elif agent == "hermes":
            text = ask_hermes(prompt, emit)
        elif agent == "openclaw":
            text = ask_openclaw(prompt, emit)
        elif agent == "grok":
            text = ask_grok(prompt, files, emit)
        else:
            text = f"[unknown agent {agent}]"
    except Exception as e:
        text = f"[error] {e}"

    # The style leak, caught at the door: ~/.claude/CLAUDE.md loads into
    # every Claude Code process here, and agents read each other's output,
    # so block-bar furniture spreads. It carries no information in a chat
    # card — strip runs of it rather than asking four agents to remember.
    text = re.sub(r"[█▉▊▋▌▍▎▏▐▓▒░]{3,}", "", str(text)).strip()
    emit("done", {"text": text, "seconds": round(time.time() - t0, 1)})
    with JOBS_LOCK:
        JOBS[job_id]["remaining"] -= 1
        if JOBS[job_id]["remaining"] <= 0:
            q.put({"kind": "all_done"})


# Without this, an agent has no idea what it is or where. Asked about
# "hermes and openclaw" on 2026-08-05, ollama answered about characters
# from Super Mario World — correctly, for a model with no context. The
# preamble is deliberately short: a 1B model has a small window, and the
# cost of context is paid by every agent on every question.
PREAMBLE = """You are one of several AI agents running on Marsita the Ultra's
laptop, answering in a chat pane on their fleet dashboard. The others are:
claude (Claude Code, local process, can edit files), hermes and openclaw
(cloud APIs), ollama (a small local model). The machine runs a public board
at [redacted-host] with a council, a rota of proposals, a build
pipeline and a signature wall. Answer plainly and briefly. No status bars,
no block characters, no headings unless asked.

QUESTION: """


def start_job(message, agents, attachments):
    text_ctx, images, saved = build_context(attachments)
    prompt = PREAMBLE + message
    if text_ctx:
        prompt = f"{prompt}\n\n{text_ctx}"

    # Images need a model that can see. Local vision was too slow on this
    # machine, so Claude is the vision path; adding it beats dropping the image.
    requested = [a for a in (agents or []) if a in AGENTS]
    if images and "claude" not in requested:
        requested = list(requested) + ["claude"]

    agents = [a for a in requested if _agent_ready(a)]
    if not agents:
        return {"error": "none of the requested agents are ready", "agents": []}
    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {"queue": queue.Queue(), "remaining": len(agents),
                        "agents": agents, "created": time.time()}
        # bound memory: drop jobs older than an hour
        for k in [k for k, v in JOBS.items() if time.time() - v["created"] > 3600]:
            JOBS.pop(k, None)

    for a in agents:
        threading.Thread(target=_worker,
                         args=(job_id, a, prompt, images, saved),
                         daemon=True).start()
    return {"job": job_id, "agents": agents}


def stream_job(job_id, write):
    """Drain a job's queue to an SSE writer until every agent has finished."""
    job = JOBS.get(job_id)
    if not job:
        write({"kind": "error", "data": "unknown job"})
        return
    q = job["queue"]
    while True:
        try:
            item = q.get(timeout=15)
        except queue.Empty:
            write({"kind": "ping"})
            continue
        write(item)
        if item.get("kind") == "all_done":
            return


def available():
    """Which agents can actually be used right now."""
    out = []
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
            have = {m["name"] for m in json.loads(r.read())["models"]}
    except Exception:
        have = set()
    for name, (label, _vision) in AGENTS.items():
        ok = _agent_ready(name, have)
        out.append({"name": name, "label": label, "ready": ok})
    return out


def _agent_ready(name, have=None):
    """True when the agent binary (or ollama model) is on this machine."""
    if name == "ollama":
        if have is None:
            try:
                with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=2) as r:
                    have = {m["name"] for m in json.loads(r.read())["models"]}
            except Exception:
                have = set()
        return any(m.startswith(OLLAMA_MODEL.split(":")[0]) for m in have)
    if name in ("claude", "hermes", "openclaw", "grok"):
        return Path(resolve(name)).is_file()
    return False
