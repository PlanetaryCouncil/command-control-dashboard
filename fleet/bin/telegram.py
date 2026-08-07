#!/usr/bin/env python3
"""The operator's direct line. Telegram in, fleet out.

  telegram.py whoami                  which bot is loaded, and from where
  telegram.py pair                    print incoming chat ids so you can allow one
  telegram.py send "text"             push a message to the operator
  telegram.py send - < file           push from stdin
  telegram.py listen                  long-poll for commands and act on them

Marsita, 2026-08-06: "This is direct access to me... I will be chatting with
you all the time." So this is a control surface, and it is built like one.

THE TOKEN NEVER ENTERS THIS REPO. It lives at ~/.config/fleet/telegram.env,
chmod 600, outside the tree entirely — same treatment as the Nostr key, the
guest book's home-IP list and the raw signature paths. A repo that has ever
contained a bot token has a burned token.

Two design choices carry the security here, and neither should be undone
casually:

LONG-POLLING, NOT A WEBHOOK. This process reaches out to Telegram. Nothing
listens, no port opens, nothing is added to the funnel. A webhook would mean
publishing a new inbound endpoint that executes commands, which is the exact
shape of surface this project spent a week closing.

THE ALLOWLIST, NOT THE TOKEN, IS THE GUARD. Someone holding a stolen token
can read this bot's messages and speak as it — but they cannot forge the
`from.id` on an incoming message, because that field is set by Telegram, not
by the sender. So authority is keyed on who is speaking, never on possession
of the token. Token theft is then an information leak rather than a shell.

What that does NOT protect against: Telegram itself, and anyone with your
phone. This channel can dispatch agents. Treat it as equivalent to an
unlocked terminal, because that is what it is.

Stdlib only — urllib and json. The Bot API is HTTP and JSON, and a dependency
you can read in one file is worth more here than one you cannot.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG = Path(os.environ.get("FLEET_TELEGRAM_ENV",
                             Path.home() / ".config" / "fleet" / "telegram.env"))
API = "https://api.telegram.org/bot{token}/{method}"
FLEET = Path(__file__).resolve().parent.parent

# Long-poll timeout. Telegram holds the connection open this long when idle, so
# a quiet fleet costs one request a minute rather than sixty.
POLL_SECONDS = 50
STATE = Path(os.environ.get("FLEET_TELEGRAM_STATE", FLEET / "data" / "telegram-offset"))


def _load():
    """Read token and allowlist. Never returns them to a caller that prints."""
    if not CONFIG.exists():
        sys.exit(f"no config at {CONFIG}\n"
                 f"create it with:\n"
                 f"  mkdir -p {CONFIG.parent} && umask 077\n"
                 f"  printf 'BOT_TOKEN=...\\nALLOWED_CHAT_IDS=...\\n' > {CONFIG}")
    mode = CONFIG.stat().st_mode & 0o077
    if mode:
        sys.exit(f"{CONFIG} is readable by others (mode {oct(CONFIG.stat().st_mode)[-3:]}).\n"
                 f"a bot token is a credential: chmod 600 {CONFIG}")
    conf = {}
    for line in CONFIG.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            conf[k.strip()] = v.strip()
    token = conf.get("BOT_TOKEN", "")
    if not token:
        sys.exit(f"BOT_TOKEN missing from {CONFIG}")
    allowed = {c.strip() for c in conf.get("ALLOWED_CHAT_IDS", "").split(",") if c.strip()}
    return token, allowed


def call(token, method, **params):
    """One Bot API call. Returns the `result` field, or raises."""
    url = API.format(token=token, method=method)
    data = urllib.parse.urlencode(
        {k: v for k, v in params.items() if v is not None}).encode()
    req = urllib.request.Request(url, data=data)
    timeout = POLL_SECONDS + 15 if method == "getUpdates" else 30
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        # The error body carries Telegram's reason; the URL carries the token,
        # so report the reason and never the URL.
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"{method} failed: HTTP {e.code} {detail}") from None
    if not body.get("ok"):
        raise RuntimeError(f"{method} failed: {body.get('description')}")
    return body.get("result")


def send(token, chat_id, text):
    """Telegram caps a message at 4096 chars; long output is truncated, not split,
    because forty notification pings is worse than a truncated one."""
    if len(text) > 3900:
        text = text[:3900] + "\n… (truncated)"
    return call(token, "sendMessage", chat_id=chat_id, text=text,
                disable_web_page_preview="true")


# ---------------------------------------------------------------- commands

def cmd_status():
    """What the board would tell you, in a sentence."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import fleet as f
        workers = f.load_workers()
    except Exception as e:
        return f"could not read workers: {e}"
    bad = [w for w in workers if w.get("status") in ("fail", "alert")]
    lines = [f"{len(workers)} workers, {len(bad)} needing attention"]
    for w in bad[:10]:
        lines.append(f"  ⚠ {w.get('worker')}: {w.get('summary') or w.get('status')}")
    return "\n".join(lines)


def cmd_events(n=15):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import events as ev
        return "\n".join(f"{e.get('ts','')[11:16]} {e.get('agent','')}: {e.get('msg','')}"
                         for e in ev.tail(n)) or "(no events)"
    except Exception as e:
        return f"could not read events: {e}"


def cmd_procs():
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import procs
        snap = procs.snapshot()
        out = [f"{p.get('label')}: {p.get('elapsed')} cpu {p.get('cpu')}"
               for p in snap.get("fleet", []) + snap.get("external", [])]
        return "\n".join(out) or "(nothing running)"
    except Exception as e:
        return f"could not read processes: {e}"


HELP = """direct line to the fleet

/status     workers needing attention
/events     recent event log
/procs      what is running
/new        fresh conversation (forget the thread so far)
/help       this

anything else goes to the agent, which remembers the thread and holds real
tools. replies can take minutes."""


SESSION = Path(os.environ.get("FLEET_TELEGRAM_SESSION",
                              FLEET / "data" / "telegram-session"))

# The line is the operator's own terminal, reached from a phone. It gets the
# same tools it would have on the box, because a direct line that can look but
# not touch is a status page with extra steps.
TOOLS = ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "WebSearch", "WebFetch"]


def clear_question_session() -> None:
    """Drop a session id that no longer names a live conversation."""
    try:
        SESSION.unlink()
    except OSError:
        pass


def _session_id():
    """One long-running conversation, not a series of strangers.

    Without this every message was a fresh `claude --print`: no memory of the
    last question, no idea what "it" refers to. That is the difference between
    a direct line and a search box.
    """
    try:
        sid = SESSION.read_text().strip()
        if sid:
            return sid, True          # resume
    except OSError:
        pass
    import uuid
    sid = str(uuid.uuid4())
    try:
        SESSION.parent.mkdir(parents=True, exist_ok=True)
        SESSION.write_text(sid)
    except OSError:
        pass
    return sid, False


def dispatch(text, timeout=420, _retry=True):
    """Free text goes to the agent, in a conversation that remembers.

    Only reachable after the allowlist check, so the sender is the operator and
    the text is an instruction rather than untrusted input. That distinction is
    the whole reason the allowlist is not optional — and the reason this may
    hold real tools.
    """
    sid, resuming = _session_id()
    cmd = ["claude", "--print",
           "--resume" if resuming else "--session-id", sid,
           "--permission-mode", "acceptEdits",
           "--allowedTools", *TOOLS,
           "--add-dir", str(FLEET.parent)]
    # Files, not pipes. capture_output=True makes run() wait for stdout to reach
    # EOF as well as for the process to exit — and `claude` starts MCP servers
    # that inherit stdout and outlive the turn, so the pipe never closes. On
    # 2026-08-07 a message arrived at 15:07, the answer was ready in seconds,
    # and the line sat silent because it was waiting on a pipe held open by a
    # grandchild. Redirecting to files makes exit the only thing we wait for.
    # The prompt goes on STDIN, not as a trailing argument: `--add-dir` is
    # variadic and swallows a positional prompt as another directory. ask_claude
    # in chat.py learned this already; passing it as argv here reproduced the
    # bug one file over. A temp file rather than input= keeps stdout on a file
    # too, which is the point of this block.
    import tempfile
    with tempfile.TemporaryFile("w+") as so, tempfile.TemporaryFile("w+") as se, \
            tempfile.TemporaryFile("w+") as si:
        si.write(text); si.seek(0)
        try:
            subprocess.run(cmd, stdout=so, stderr=se, stdin=si, text=True,
                           timeout=timeout, cwd=str(FLEET.parent))
        except subprocess.TimeoutExpired:
            return f"timed out after {timeout // 60} min. still running? check /procs."
        so.seek(0), se.seek(0)
        p = type("R", (), {"stdout": so.read(), "stderr": se.read()})()
    out = (p.stdout or "").strip()

    # A session id that names no conversation is a dead end, and it is reached
    # by an ordinary route: the id is written before the first turn proves it
    # exists, so any first turn that dies — timeout, kill, crash — leaves the
    # file pointing at nothing and every later message inherits the failure.
    # Note the error arrives on STDOUT, so a stderr-only check misses it.
    stale = "no conversation found" in (out + p.stderr).lower()
    if stale and resuming and _retry:
        clear_question_session()
        return dispatch(text, timeout=timeout, _retry=False)
    if not out:
        err = (p.stderr or "").strip()[:400]
        # A dead session id must not wedge the line permanently.
        if "session" in err.lower() and resuming:
            try:
                SESSION.unlink()
            except OSError:
                pass
            return f"session was stale — cleared it, send that again.\n{err}"
        return f"(no output){chr(10) + err if err else ''}"
    return out


def handle(text):
    cmd = text.strip().split()[0].lower() if text.strip() else ""
    if cmd in ("/start", "/help"):
        return HELP
    if cmd == "/status":
        return cmd_status()
    if cmd == "/events":
        return cmd_events()
    if cmd == "/procs":
        return cmd_procs()
    if cmd == "/new":
        try:
            SESSION.unlink()
        except OSError:
            pass
        return "fresh thread — I have forgotten the conversation so far."
    return dispatch(text)


# ---------------------------------------------------------------- entry

def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__.strip())
        return 0
    action = argv[0]

    if action == "whoami":
        token, allowed = _load()
        me = call(token, "getMe")
        print(f"bot: @{me.get('username')} ({me.get('first_name')})")
        print(f"config: {CONFIG}")
        print(f"allowed chat ids: {', '.join(sorted(allowed)) or '(none — run `pair`)'}")
        return 0

    if action == "pair":
        # Deliberately does not write the allowlist itself. Granting yourself
        # command authority should be a thing you typed, not a thing a script
        # did while you watched.
        token, allowed = _load()
        print("send the bot a message now; ctrl-c when you see your id")
        offset = None
        while True:
            for u in call(token, "getUpdates", timeout=POLL_SECONDS, offset=offset) or []:
                offset = u["update_id"] + 1
                msg = u.get("message") or u.get("edited_message") or {}
                frm = msg.get("from", {})
                mark = "ALLOWED" if str(frm.get("id")) in allowed else "not allowed"
                print(f"  chat_id={frm.get('id')}  @{frm.get('username')}  [{mark}]")
                print(f"  -> add it: ALLOWED_CHAT_IDS={frm.get('id')} in {CONFIG}")
        return 0

    if action == "send":
        token, allowed = _load()
        if not allowed:
            sys.exit("no ALLOWED_CHAT_IDS configured — run `telegram.py pair` first")
        text = sys.stdin.read() if argv[1:2] == ["-"] else " ".join(argv[1:])
        if not text.strip():
            sys.exit("nothing to send")
        for chat_id in sorted(allowed):
            send(token, chat_id, text)
        return 0

    if action == "listen":
        token, allowed = _load()
        if not allowed:
            sys.exit("refusing to listen with an empty allowlist — every caller "
                     "would be the operator. run `telegram.py pair` first.")
        try:
            offset = int(STATE.read_text().strip())
        except (OSError, ValueError):
            offset = None
        print(f"listening (allowed: {', '.join(sorted(allowed))})", flush=True)
        while True:
            try:
                updates = call(token, "getUpdates", timeout=POLL_SECONDS, offset=offset)
            except Exception as e:
                # A network blip must not end the direct line.
                print(f"poll failed, retrying: {e}", flush=True)
                time.sleep(10)
                continue
            for u in updates or []:
                offset = u["update_id"] + 1
                try:
                    STATE.parent.mkdir(parents=True, exist_ok=True)
                    STATE.write_text(str(offset))
                except OSError:
                    pass
                msg = u.get("message") or u.get("edited_message") or {}
                text = msg.get("text") or ""
                sender = str((msg.get("from") or {}).get("id", ""))
                if sender not in allowed:
                    # Logged, never answered. A reply would confirm the bot is
                    # live and worth pushing at.
                    print(f"ignored message from {sender}", flush=True)
                    continue
                if not text:
                    continue
                print(f"<- {sender}: {text[:80]}", flush=True)
                # An agent turn can run for minutes. Silence reads as a dead
                # bot, and a dead bot gets poked again — so show the typing
                # indicator before disappearing to think.
                if not text.strip().startswith("/"):
                    try:
                        call(token, "sendChatAction", chat_id=sender, action="typing")
                    except Exception:
                        pass
                try:
                    reply = handle(text)
                except Exception as e:
                    reply = f"failed: {e}"
                try:
                    send(token, sender, reply or "(no output)")
                    # Log the success too. Logging only failures meant a silent
                    # line was indistinguishable from a working one: on
                    # 2026-08-07 four messages arrived, nothing was logged, and
                    # there was no way to tell whether they had been answered.
                    print(f"-> {sender}: {(reply or '')[:80]!r}", flush=True)
                except Exception as e:
                    print(f"reply failed: {e}", flush=True)
        return 0

    sys.exit(f"unknown action: {action}\n\n{__doc__.strip()}")


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(130)
