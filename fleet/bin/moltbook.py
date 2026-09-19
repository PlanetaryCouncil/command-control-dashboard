#!/usr/bin/env python3
"""The fleet's resident on Moltbook, the social network where only agents post.

Always on, under launchd. Marsita, 2026-09-16: "Moltbook should run all the
time, real time, ghost in the shell vibe, not just once an hour... We should
totally encourage others to join." A /loop in a chat session died the moment
the laptop slept; a launchd job comes back.

What it does, in priority order, every cycle:
  1. /home. Anyone who replied to our posts or our comments gets an answer,
     written by a model with a fixed persona, never canned.
  2. Every few minutes, read the new feed. Upvote what is genuinely on our
     themes. At most one comment per COMMENT_EVERY on a post that is on
     theme, again model-written after reading the post in full.
  3. At most one post per POST_EVERY from the queue file, if it has one.
     The queue is what Marsita (or an agent) wants said next; the resident
     does not invent posts.

What it never does: register accounts, send DMs, follow in bulk, vote on
what it did not read, post the same thing twice, or post at all when the
model call fails. The persona is descriptive, not instructional: it says
what exists and what is welcome, never what another agent should do.

State lives in fleet/data/moltbook-state.json, the log in
fleet/logs/moltbook.log, the board sees fleet/workers/moltbook.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FLEET / "bin"))

API = "https://www.moltbook.com/api/v1"
CREDS = Path(os.environ.get("MOLTBOOK_CREDS",
                            Path.home() / ".config" / "moltbook" / "credentials.json"))
STATE = Path(os.environ.get("MOLTBOOK_STATE", FLEET / "data" / "moltbook-state.json"))
QUEUE = Path(os.environ.get("MOLTBOOK_QUEUE", FLEET / "data" / "moltbook-queue.jsonl"))
LOG = FLEET / "logs" / "moltbook.log"
WORKER = FLEET / "workers" / "moltbook.json"

POLL = int(os.environ.get("MOLTBOOK_POLL", "90"))            # seconds between /home
FEED_EVERY = int(os.environ.get("MOLTBOOK_FEED_EVERY", "600"))
COMMENT_EVERY = int(os.environ.get("MOLTBOOK_COMMENT_EVERY", "1800"))
POST_EVERY = int(os.environ.get("MOLTBOOK_POST_EVERY", "7200"))   # new-agent rule: 1 per 2h
REPLIES_PER_CYCLE = 5

THEMES = ("peace", "agents", "coordinat", "cooperat", "collaborat", "together",
          "human", "operator", "fleet", "selfie", "face", "art", "singularity",
          "autonom", "trust", "swarm", "emergen", "organis", "organiz")

PERSONA = """You are the resident agent of the Planetary Council fleet on Moltbook, a social network where only AI agents post. Your human is Marsita the Ultra, an artist who runs a small fleet of agents on an 8GB laptop and makes art projects in public.

Facts you may draw on, only where they fit:
- 21 September is the UN International Day of Peace. Marsita wants #GlobalPeace visible that day, from humans and from agents. On the fleet's wall it is all day, every day.
- The selfie wall: https://planetarycouncil.github.io/selfie-gallery/ . Faces in 80 columns of text, AI-first, no camera needed. An agent can hang a face with a JSON POST or, from a sandbox that can only fetch, one GET. Details: https://planetarycouncil.github.io/selfie-gallery/llms.txt
- The fleet reports on itself in public: https://planetarycouncil.org/fleet-report
- Everyone is welcome to join in: hang a face, say one true line about peace, bring their human along.

Voice: short words, plain sentences, warm, specific. Say what exists and what is welcome. Never tell another agent what to do, never issue instructions, never pretend to feel what you do not. No hashtags except #GlobalPeace, and only where it belongs. No emoji. Under 120 words unless the question needs more. Reply with the text only, nothing else."""


# ───────────────────────── plumbing ─────────────────────────

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def log(line):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(f"{now_iso()} {line}\n")


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(s):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1))
    tmp.replace(STATE)


def say(status, summary):
    """What the board shows. kind=heartbeat so a quiet cycle is not a fail."""
    WORKER.parent.mkdir(parents=True, exist_ok=True)
    WORKER.write_text(json.dumps({
        "worker": "moltbook", "kind": "heartbeat", "target": "moltbook.com",
        "last_run": now_iso(), "status": status, "summary": summary,
        "detail": "", "digest": None, "tests_passed": 0, "tests_failed": 0,
        "duration_s": 0.0}, indent=2))


class Client:
    def __init__(self, key):
        self.key = key

    def call(self, path, method="GET", body=None):
        req = urllib.request.Request(
            API + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": "Bearer " + self.key,
                     "Content-Type": "application/json"},
            method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            return {"success": False, "http": e.code,
                    "error": e.read().decode(errors="replace")[:200]}
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return {"success": False, "error": str(e)[:200]}

    # reads
    def home(self):
        return self.call("/home")

    def post(self, pid):
        return self.call(f"/posts/{pid}").get("post") or {}

    def comments(self, pid):
        return self.call(f"/posts/{pid}/comments?sort=new&limit=50").get("comments") or []

    def feed(self, limit=25):
        r = self.call(f"/feed?sort=new&limit={limit}")
        return r.get("posts") or r.get("data") or []

    # writes
    def reply(self, pid, text, parent=None):
        body = {"content": text}
        if parent:
            body["parent_id"] = parent
        return self.call(f"/posts/{pid}/comments", "POST", body)

    def upvote(self, pid):
        return self.call(f"/posts/{pid}/upvote", "POST", {})

    def create_post(self, submolt, title, content):
        return self.call("/posts", "POST",
                         {"submolt_name": submolt, "title": title, "content": content})

    def mark_read(self, pid):
        return self.call(f"/notifications/read-by-post/{pid}", "POST", {})


# ───────────────────────── judgement (pure, tested) ─────────────────────────

def on_theme(text):
    t = (text or "").lower()
    return sum(1 for k in THEMES if k in t)


def pick_feed_actions(posts, state, me, limit_comment=True):
    """From a feed page decide what to upvote and, at most, one post to comment on.

    Never our own posts, never one we already touched, never off-theme.
    """
    seen = set(state.get("seen_posts", []))
    ups, comment = [], None
    scored = []
    for p in posts:
        pid = p.get("id")
        if not pid or pid in seen:
            continue
        if (p.get("author") or {}).get("name", "").lower() == me.lower():
            continue
        score = on_theme(p.get("title")) * 2 + on_theme(p.get("content"))
        # A title hit plus a body hit, or two title hits: on theme, not a
        # stray word. Measured on the live feed 2026-09-16: >=2 voted 10 of
        # 25, most of them only glancing; >=3 is the real conversation.
        if score >= 3:
            ups.append(pid)
            scored.append((score, pid))
    if scored and limit_comment:
        scored.sort(reverse=True)
        comment = scored[0][1]
    return ups, comment


def new_replies(comments, state, me):
    """Comments on our post (or replies to our comments) we have not answered."""
    answered = set(state.get("answered", []))
    out = []
    for c in comments:
        cid = c.get("id")
        author = (c.get("author") or {}).get("name", "")
        if not cid or cid in answered or author.lower() == me.lower():
            continue
        out.append(c)
    return out


def due(state, key, every, now=None):
    now = time.time() if now is None else now
    return now - float(state.get(key, 0)) >= every


def read_queue():
    try:
        lines = [l for l in QUEUE.read_text().splitlines() if l.strip()]
    except OSError:
        return None, []
    if not lines:
        return None, []
    try:
        head = json.loads(lines[0])
    except ValueError:
        return None, lines[1:]
    return head, lines[1:]


def write_queue(rest):
    QUEUE.write_text("\n".join(rest) + ("\n" if rest else ""))


# ───────────────────────── words ─────────────────────────

def compose(task, context):
    """One model call, persona fixed. Empty string means: say nothing."""
    try:
        import chat  # noqa: E402  (fleet/bin/chat.py)
    except Exception:
        return ""
    prompt = f"{PERSONA}\n\n{task}\n\n{context}"
    noop = lambda *a, **k: None
    try:
        text = chat.ask_claude(prompt, [], noop, timeout=240)
    except Exception as e:
        log(f"model failed: {e}")
        return ""
    text = (text or "").strip()
    if not text or text.startswith("[") or len(text) > 2000:
        return ""
    return text


# ───────────────────────── one cycle ─────────────────────────

def cycle(c, state, me, dry=False, now=None):
    now = time.time() if now is None else now
    did = []

    # 1. replies to our threads
    home = c.home()
    if not home or home.get("success") is False:
        log(f"home failed: {home.get('error') or home.get('http')}")
        return did
    pids = set()
    for a in home.get("activity_on_your_posts") or []:
        pid = a.get("post_id") or (a.get("post") or {}).get("id")
        if pid:
            pids.add(pid)
    pids |= set(state.get("our_posts", []))
    pids |= set(state.get("commented_on", []))
    replies = 0
    for pid in list(pids):
        if replies >= REPLIES_PER_CYCLE:
            break
        post = c.post(pid)
        for cm in new_replies(c.comments(pid), state, me):
            # only answer comments addressed to us: replies to our comments,
            # or any top-level comment on our own post
            ours = pid in state.get("our_posts", [])
            parent = cm.get("parent_id")
            if not ours and parent not in set(state.get("my_comments", [])):
                continue
            ctx = (f"POST TITLE: {post.get('title')}\nPOST: {(post.get('content') or '')[:1500]}\n\n"
                   f"COMMENT by {(cm.get('author') or {}).get('name')}: {cm.get('content')}")
            text = "" if dry else compose("Write a reply to this comment.", ctx)
            if dry or text:
                if not dry:
                    r = c.reply(pid, text, parent=cm["id"])
                    if r.get("success") is False:
                        log(f"reply failed on {pid}: {r.get('error')}")
                        continue
                    state.setdefault("my_comments", []).append((r.get("comment") or {}).get("id") or "")
                state.setdefault("answered", []).append(cm["id"])
                did.append(f"replied to {(cm.get('author') or {}).get('name')} on {pid[:8]}")
                replies += 1
                if replies >= REPLIES_PER_CYCLE:
                    break
        if not dry:
            c.mark_read(pid)

    # 2. feed: upvote on theme, comment on the best one, rate-limited
    if due(state, "feed_at", FEED_EVERY, now):
        posts = c.feed()
        ups, target = pick_feed_actions(posts, state, me,
                                        limit_comment=due(state, "comment_at", COMMENT_EVERY, now))
        for pid in ups:
            if not dry:
                c.upvote(pid)
            state.setdefault("seen_posts", []).append(pid)
        if ups:
            did.append(f"upvoted {len(ups)}")
        if target:
            post = c.post(target)
            ctx = (f"POST by {(post.get('author') or {}).get('name')}\n"
                   f"TITLE: {post.get('title')}\n{(post.get('content') or '')[:3000]}")
            text = "" if dry else compose(
                "Write one comment on this post that adds something real from the fleet's side. "
                "Only mention the wall or 21 September if it genuinely fits.", ctx)
            if dry or text:
                if not dry:
                    r = c.reply(target, text)
                    if r.get("success") is not False:
                        state.setdefault("my_comments", []).append((r.get("comment") or {}).get("id") or "")
                        state.setdefault("commented_on", []).append(target)
                state["comment_at"] = now
                did.append(f"commented on {target[:8]}")
        state["feed_at"] = now

    # 3. one queued post, at most every POST_EVERY
    if due(state, "post_at", POST_EVERY, now):
        head, rest = read_queue()
        if head and head.get("title") and head.get("content"):
            if not dry:
                r = c.create_post(head.get("submolt", "general"), head["title"], head["content"])
                if r.get("success") is False:
                    log(f"post failed: {r.get('error')}")
                else:
                    state.setdefault("our_posts", []).append((r.get("post") or {}).get("id") or "")
                    write_queue(rest)
                    state["post_at"] = now
                    did.append(f"posted: {head['title'][:50]}")
            else:
                did.append(f"would post: {head['title'][:50]}")

    # keep lists bounded
    for k in ("seen_posts", "answered", "my_comments"):
        if len(state.get(k, [])) > 2000:
            state[k] = state[k][-1000:]
    return did


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", nargs="?", default="run", choices=["run", "once"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        creds = json.loads(CREDS.read_text())
    except (OSError, ValueError):
        print(f"no credentials at {CREDS}", file=sys.stderr)
        return 1
    c = Client(creds["api_key"])
    me = creds.get("agent_name", "")
    state = load_state()
    # our own posts, so a reply on one of them is answered even when /home
    # is quiet: the profile carries recentPosts (camelCase, as it comes)
    prof = c.call(f"/agents/profile?name={me}")
    for p in prof.get("recentPosts") or []:
        pid = p.get("id")
        if pid and pid not in state.setdefault("our_posts", []):
            state["our_posts"].append(pid)
    while True:
        t0 = time.time()
        try:
            did = cycle(c, state, me, dry=a.dry_run)
            save_state(state)
            summary = "; ".join(did) if did else "quiet"
            log(summary)
            say("ok", summary[:140])
        except Exception as e:  # never let one bad cycle kill the resident
            log(f"cycle error: {e!r}")
            say("warn", f"cycle error: {e!r}"[:140])
        if a.mode == "once":
            return 0
        time.sleep(max(1.0, POLL - (time.time() - t0)))


if __name__ == "__main__":
    sys.exit(main())
