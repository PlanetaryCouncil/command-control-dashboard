#!/usr/bin/env python3
"""Drive the operator's real, logged-in browser — and hand back the wheel
at every human check.

  browser.py check                    is a drivable Chrome listening?
  browser.py open URL                 open a tab, report the title
  browser.py shot URL [out.png]       screenshot a page
  browser.py text URL                 the visible text of a page
  browser.py tabs                     what is open right now

Marsita, 2026-08-05: "full control of the browser and sending me captchas
so I can solve as human... I want to be fully autonomous able to run from
human browser."

Two halves, and the second is the point:

  AUTONOMOUS   a scheduled job can navigate, read, click and screenshot in
               a Chrome that already holds the operator's sessions. No
               logging in, no credentials in this repo, no scraping around
               an auth wall — it is their browser.

  ESCALATION   a CAPTCHA exists to tell a human from a program. When one
               appears, this refuses to guess: it screenshots the page,
               raises needs_you on the board with the tab id, and stops.
               The operator solves it in the same window — the tab is
               already open in front of them — and the task resumes.
               Solving it automatically would be lying to the site AND
               risking the operator's own logged-in accounts, which are in
               the blast radius of any ban.

HOW IT CONNECTS. Chrome must be started with a debugging port. The stock
Chrome on this machine uses `--remote-debugging-pipe` (the extension's
private channel), which nothing else can attach to, so `browser.py check`
will report that and tell you how to restart. That restart is the
operator's decision, and it is a real one: a debugging port lets ANY
process on this machine drive the logged-in browser. Loopback only, but
still a widening of what localhost means here. Stated plainly rather than
buried, because it is the kind of thing that should be chosen once and
knowingly.
"""

import base64
import json
import subprocess
import sys
import time
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
PORT = 9222
SHOTS = FLEET / "browser" / "shots"
TASKS = FLEET / "browser" / "tasks.jsonl"

# Text and DOM markers that mean "a human is required". Deliberately broad:
# a false positive costs one notification, a false negative means a bot
# quietly failing at a wall it cannot see.
HUMAN_CHECK = [
    "recaptcha", "hcaptcha", "cf-turnstile", "turnstile",
    "are you a robot", "i'm not a robot", "verify you are human",
    "unusual traffic", "complete the security check",
    "press and hold", "solve the puzzle", "captcha",
]

LAUNCH_HINT = f"""Chrome is not listening on :{PORT}.

To let the fleet drive your real browser, quit Chrome and start it once
with a debugging port — same profile, same logins:

  ! open -a "Google Chrome" --args --remote-debugging-port={PORT}

Read this before you do: any process on this machine can then drive that
browser, with your sessions. It is bound to loopback, so nothing outside
can reach it, but it does widen what "localhost" means here. Your call,
and worth making once rather than by accident."""


def _http(path):
    import urllib.request
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}",
                                timeout=5) as r:
        return json.loads(r.read())


def check() -> int:
    try:
        v = _http("/json/version")
    except Exception:
        print(LAUNCH_HINT)
        return 1
    print(f"connected: {v.get('Browser')}")
    print(f"tabs open: {len(tabs(quiet=True))}")
    return 0


def tabs(quiet=False):
    try:
        pages = [t for t in _http("/json/list") if t.get("type") == "page"]
    except Exception:
        if not quiet:
            print(LAUNCH_HINT)
        return []
    if not quiet:
        for t in pages:
            print(f"  {t['id'][:8]}  {t.get('title','')[:44]:<46} {t.get('url','')[:60]}")
    return pages


class Tab:
    """One CDP session. Small on purpose — navigate, read, shoot, click."""

    def __init__(self, url=None):
        import websocket
        target = _http(f"/json/new?{url}") if url else (tabs(quiet=True) or [None])[0]
        if not target:
            raise SystemExit("no tab to drive")
        self.id = target["id"]
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"],
                                              timeout=30)
        self._n = 0

    def cmd(self, method, **params):
        self._n += 1
        self.ws.send(json.dumps({"id": self._n, "method": method,
                                 "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self._n:
                return msg.get("result", {})

    def goto(self, url, settle=2.5):
        self.cmd("Page.enable")
        self.cmd("Page.navigate", url=url)
        time.sleep(settle)

    def text(self):
        r = self.cmd("Runtime.evaluate",
                     expression="document.body ? document.body.innerText : ''",
                     returnByValue=True)
        return (r.get("result") or {}).get("value", "")

    def html_head(self, n=4000):
        r = self.cmd("Runtime.evaluate",
                     expression="document.documentElement.outerHTML",
                     returnByValue=True)
        return ((r.get("result") or {}).get("value") or "")[:n]

    def shot(self, out: Path):
        r = self.cmd("Page.captureScreenshot", format="png")
        data = r.get("data")
        if not data:
            return None
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(data))
        return out

    def needs_human(self):
        """The page is asking for a human. Returns the marker, or None."""
        blob = (self.text()[:6000] + self.html_head()).lower()
        for m in HUMAN_CHECK:
            if m in blob:
                return m
        return None

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def escalate(tab, marker, url):
    """Hand the wheel back. Screenshot, ring the board, notify, stop."""
    shot = tab.shot(SHOTS / f"human-check-{int(time.time())}.png")
    sys.path.insert(0, str(FLEET / "bin"))
    import events as ev
    ev.emit("browser", "needs_you",
            f"[browser] human check ('{marker}') at {url[:60]} — "
            f"the tab is open in your Chrome; solve it and re-run the task")
    # Best effort, never fatal: a notification is a courtesy, the board
    # entry is the record.
    try:
        subprocess.run(["osascript", "-e",
                        f'display notification "Solve the check in Chrome, '
                        f'then re-run" with title "🦩 fleet needs you"'],
                       capture_output=True, timeout=5)
    except Exception:
        pass
    print(f"HUMAN CHECK: {marker}")
    print(f"  page      {url}")
    if shot:
        print(f"  screenshot {shot}")
    print("  the tab is open in your Chrome — solve it there, then re-run")
    return 2


def run(url, want="text", out=None) -> int:
    tab = Tab()
    try:
        tab.goto(url)
        marker = tab.needs_human()
        if marker:
            return escalate(tab, marker, url)
        if want == "shot":
            p = tab.shot(Path(out) if out else
                         SHOTS / f"shot-{int(time.time())}.png")
            print(p)
        elif want == "text":
            print(tab.text()[:4000])
        else:
            r = tab.cmd("Runtime.evaluate", expression="document.title",
                        returnByValue=True)
            print((r.get("result") or {}).get("value", ""))
        return 0
    finally:
        tab.close()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    arg = sys.argv[2] if len(sys.argv) > 2 else None
    if cmd == "check":
        sys.exit(check())
    if cmd == "tabs":
        tabs()
        sys.exit(0)
    if cmd in ("open", "text", "shot") and arg:
        sys.exit(run(arg, {"open": "title", "text": "text", "shot": "shot"}[cmd],
                     sys.argv[3] if len(sys.argv) > 3 else None))
    print(__doc__.strip())
