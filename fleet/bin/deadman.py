#!/usr/bin/env python3
"""The operator's dead-man switch. Silence, escalated.

  deadman.py alive [note]      reset the clock — "I am fine"
  deadman.py status            how long since check-in, what fires next
  deadman.py check             evaluate the clock; send anything now due
  deadman.py check --dry-run   same, but print instead of sending
  deadman.py check --corroborate   look for proof of life before escalating
  deadman.py disarm / rearm    stop / resume firing without deleting config

Every other heartbeat in this fleet watches the machines. This one watches the
operator: if no check-in arrives for long enough, it tells people, in an order
you chose, with words you wrote.

WHY THE MESSAGE TEXT IS NOT WRITTEN HERE, AND NOT WRITTEN BY AN AGENT.
The whole point of this file is what happens when you are not available to
review anything. A generated message is a guess about your circumstances made
by a process that cannot see them, delivered to someone who will believe it.
So the wording is yours, authored in advance, stored verbatim, and sent
unmodified. This script chooses *when*, never *what*.

WHY THE CONFIG LIVES OUTSIDE THE REPO.
Same reasoning as telegram.env, and the same path convention. This file names
your family and how to reach them, and this repository is public. A contacts
list is a credential — it just happens to be a credential about people rather
than about a service. It lives at ~/.config/fleet/deadman.json, chmod 600, and
this script refuses to run if it is readable by anyone else.

WHY IT FIRES ONCE PER STAGE.
The check runs on a schedule; the condition it tests ("no check-in since T")
stays true after it fires. Without a record of what has already gone out, every
subsequent tick re-sends, and the people you most wanted to reach get a message
every fifteen minutes. Fired stages are recorded in the state file and never
repeat until you check in again.

Stdlib only, like telegram.py. This has to work on a box that has had no
attention for two days.
"""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

FLEET = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(FLEET / "bin"))

import events as ev  # noqa: E402

CONFIG = Path(os.environ.get("FLEET_DEADMAN_CONFIG",
                             Path.home() / ".config" / "fleet" / "deadman.json"))
STATE = Path(os.environ.get("FLEET_DEADMAN_STATE", FLEET / "data" / "deadman.json"))
WORKER = FLEET / "workers" / "deadman.json"


# ---------------------------------------------------------------- config/state

def load_config():
    if not CONFIG.exists():
        sys.exit(f"no config at {CONFIG}\n"
                 f"start from the template:\n"
                 f"  mkdir -p {CONFIG.parent} && umask 077\n"
                 f"  cp {FLEET}/deadman.example.json {CONFIG}\n"
                 f"then edit it — the stages ship empty on purpose.")
    if CONFIG.stat().st_mode & 0o077:
        sys.exit(f"{CONFIG} is readable by others "
                 f"(mode {oct(CONFIG.stat().st_mode)[-3:]}).\n"
                 f"it names your contacts: chmod 600 {CONFIG}")
    conf = json.loads(CONFIG.read_text())

    stages = conf.get("stages") or []
    if not stages:
        sys.exit(f"no stages in {CONFIG} — nothing would ever be sent")
    for i, s in enumerate(stages, 1):
        # Presence, not truthiness: after_hours 0 is a legitimate stage (fire
        # on the next tick), and `not 0` would reject it as missing.
        for key in ("after_hours", "channel", "to", "body"):
            if s.get(key) in (None, ""):
                sys.exit(f"stage {i} is missing '{key}' in {CONFIG}")
        try:
            float(s["after_hours"])
        except (TypeError, ValueError):
            sys.exit(f"stage {i}: after_hours must be a number, "
                     f"got {s['after_hours']!r}")
        if s["channel"] not in ("telegram", "email"):
            sys.exit(f"stage {i}: unknown channel {s['channel']!r} "
                     f"(telegram | email)")
    # Sorted so the file can be edited in any order without silently
    # reordering who hears first.
    stages.sort(key=lambda s: float(s["after_hours"]))
    conf["stages"] = stages
    return conf


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    # Atomic: a check interrupted mid-write must not leave a state file that
    # parses as "nothing has fired yet" and re-sends the lot.
    tmp.replace(STATE)


def hours_since(state):
    last = state.get("last_alive")
    if not last:
        return None
    return (time.time() - float(last)) / 3600.0


def fmt_age(hours):
    if hours is None:
        return "never checked in"
    if hours < 1:
        return f"{hours * 60:.0f}m ago"
    if hours < 48:
        return f"{hours:.1f}h ago"
    return f"{hours / 24:.1f}d ago"


# -------------------------------------------------------------------- channels

def send_telegram(conf, to, subject, body):
    import telegram
    token, _allowed = telegram._load()
    text = f"{subject}\n\n{body}" if subject else body
    telegram.send(token, to, text)


def send_email(conf, to, subject, body):
    smtp = conf.get("smtp") or {}
    for key in ("host", "port", "user", "password", "from"):
        if not smtp.get(key):
            raise RuntimeError(f"smtp.{key} missing from {CONFIG}")

    msg = EmailMessage()
    msg["From"] = smtp["from"]
    msg["To"] = to
    msg["Subject"] = subject or "(no subject)"
    msg.set_content(body)

    port = int(smtp["port"])
    # 465 is implicit TLS, 587 is STARTTLS. Both are encrypted; plain 25 is not
    # offered, because this message travels when nobody is watching the link.
    if port == 465:
        server = smtplib.SMTP_SSL(smtp["host"], port, timeout=30)
    else:
        server = smtplib.SMTP(smtp["host"], port, timeout=30)
    with server:
        if port != 465:
            server.starttls()
        server.login(smtp["user"], smtp["password"])
        server.send_message(msg)


SENDERS = {"telegram": send_telegram, "email": send_email}


# ---------------------------------------------------------------- corroboration

"""Before escalating, ask the box whether the operator has been seen.

THE ONLY HARD RULE: A SIGNAL MUST BE CAUSED BY A HUMAN.
This fleet writes to events.jsonl around the clock — `fleet`, `codex` and
`hermes` all logged within two minutes while this was being written. Wiring
that in as proof of life would produce a switch that can never fire, which is
strictly worse than no switch at all, because you would believe you had one.
Machine activity proves the machine is up. It says nothing about you.

So signals are opt-in and named individually. Nothing is inferred from load,
uptime, running processes, or the event log.

A fresh signal moves the clock to the moment of that signal — it does not reset
it to now. Evidence that you were alive on Tuesday means the ladder should be
counting from Tuesday, not from the day the cron job happened to notice.
"""


def signal_age_hours(sig):
    """Age of one life signal, in hours, or None if it yields nothing."""
    kind = sig.get("kind")
    try:
        if kind == "file":
            # Shell history: written when an interactive shell exits. Note it
            # is NOT updated live during a long-lived session.
            return (time.time() - Path(sig["path"]).expanduser().stat().st_mtime) / 3600.0

        if kind == "git":
            # Commits by a specific author. Imperfect: an agent committing with
            # your name and email is indistinguishable from you. Only list a
            # repo here if you know nothing automated commits to it as you.
            import subprocess
            out = subprocess.run(
                ["git", "-C", str(Path(sig["path"]).expanduser()), "log", "-1",
                 "--format=%ct", f"--author={sig['author']}"],
                capture_output=True, text=True, timeout=20)
            if out.returncode != 0 or not out.stdout.strip():
                return None
            return (time.time() - int(out.stdout.strip())) / 3600.0

        if kind == "nostr":
            # The strongest signal available, and the only one that is
            # cryptographically *you* rather than "an account did something":
            # relay events are signed by your key. Also the only one that
            # needs no credential, so nothing here expires while you are away.
            try:
                import nostr
                import websocket  # noqa: F401  (nostr imports it lazily)
            except ImportError:
                # A missing dependency and an unreachable relay both yield "no
                # reading", and only one of them is a mistake you can fix. Say
                # which, loudly, or the strongest signal quietly disappears the
                # first time cron runs the wrong interpreter.
                ev.emit("deadman", "error",
                        "nostr signal unavailable: websocket-client missing — "
                        "run deadman.py with .venv/bin/python, not system python")
                return None
            ts = nostr.last_seen(nostr.from_npub(sig["npub"]),
                                 relays=sig.get("relays"),
                                 timeout=int(sig.get("timeout", 12)))
            if ts is None:
                return None          # every relay failed — a reading, not silence
            return (time.time() - ts) / 3600.0

        if kind == "command":
            # Escape hatch: any command printing a unix timestamp on stdout.
            import subprocess
            out = subprocess.run(sig["run"], shell=True, capture_output=True,
                                 text=True, timeout=20)
            if out.returncode != 0 or not out.stdout.strip():
                return None
            return (time.time() - float(out.stdout.strip().split()[0])) / 3600.0
    except (OSError, ValueError, KeyError, IndexError):
        return None
    except Exception:
        return None
    return None


def corroborate(conf, age):
    """Look for proof of life newer than the current silence.

    Returns (best_age_hours, [description...]) or (None, notes) if nothing
    was found. Never raises: a broken signal must not block an escalation.
    """
    signals = conf.get("life_signals") or []
    if not signals:
        return None, ["no life_signals configured"]

    best, notes = None, []
    for sig in signals:
        h = signal_age_hours(sig)
        label = sig.get("label") or sig.get("kind", "?")
        if h is None:
            notes.append(f"{label}: no reading")
            continue
        notes.append(f"{label}: {fmt_age(h)}")
        if best is None or h < best:
            best = h
    return best, notes


def deliver(conf, stage, dry_run):
    """Send one stage. Returns (ok, detail)."""
    to = str(stage["to"])
    subject = stage.get("subject", "")
    body = stage["body"]
    if dry_run:
        print(f"  [dry-run] {stage['channel']} -> {to}")
        print(f"            subject: {subject}")
        for line in body.splitlines():
            print(f"            | {line}")
        return True, "dry-run"
    try:
        SENDERS[stage["channel"]](conf, to, subject, body)
        return True, "sent"
    except Exception as e:
        return False, str(e)[:300]


# -------------------------------------------------------------------- commands

def cmd_alive(args):
    state = load_state()
    state["last_alive"] = time.time()
    state["last_alive_iso"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["note"] = " ".join(args.note) if args.note else ""
    # Checking in clears the fired record: the next silence is a new silence,
    # and every stage is eligible again.
    state["fired"] = []
    save_state(state)
    ev.emit("deadman", "ok", f"operator checked in{': ' + state['note'] if state['note'] else ''}")
    print(f"checked in at {state['last_alive_iso']}")
    return 0


def cmd_status(args):
    conf = load_config()
    state = load_state()
    age = hours_since(state)
    fired = set(state.get("fired", []))

    print(f"last check-in : {fmt_age(age)}"
          + (f"  ({state.get('last_alive_iso')})" if state.get("last_alive_iso") else ""))
    if state.get("note"):
        print(f"note          : {state['note']}")
    print(f"armed         : {'no — disarmed' if state.get('disarmed') else 'yes'}")
    print("stages:")
    for s in conf["stages"]:
        key = stage_key(s)
        due = age is not None and age >= float(s["after_hours"])
        if key in fired:
            mark = "SENT"
        elif due:
            mark = "DUE"
        elif age is None:
            mark = "-"
        else:
            mark = f"in {float(s['after_hours']) - age:.1f}h"
        print(f"  {float(s['after_hours']):>6.1f}h  {s['channel']:<8} "
              f"{str(s['to']):<28} {mark}")

    if conf.get("life_signals"):
        print("life signals:")
        for sig in conf["life_signals"]:
            h = signal_age_hours(sig)
            label = sig.get("label") or sig.get("kind", "?")
            print(f"  {label:<28} {fmt_age(h) if h is not None else 'no reading'}")
    return 0


def stage_key(stage):
    return f"{stage['after_hours']}:{stage['channel']}:{stage['to']}"


def cmd_check(args):
    conf = load_config()
    state = load_state()

    if state.get("disarmed") and not args.dry_run:
        print("disarmed; nothing will be sent")
        return 0

    age = hours_since(state)
    if age is None:
        # Never checked in. Firing now would mean every fresh install emails
        # the operator's family, so treat install time as the first check-in
        # and say so loudly enough that a silent switch is not assumed armed.
        state["last_alive"] = time.time()
        state["last_alive_iso"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        save_state(state)
        ev.emit("deadman", "warn",
                "no check-in on record — clock started now, not firing")
        print("no check-in on record; clock started now")
        return 0

    fired = list(state.get("fired", []))
    due = [s for s in conf["stages"]
           if age >= float(s["after_hours"]) and stage_key(s) not in fired]

    # Only pay for corroboration when something is actually about to be sent.
    if due and args.corroborate:
        best, notes = corroborate(conf, age)
        detail = " · ".join(notes)
        if best is not None and best < age:
            # Seen more recently than the clock believed. Move the clock to the
            # evidence, not to now, and re-decide from there.
            state["last_alive"] = time.time() - best * 3600.0
            state["last_alive_iso"] = datetime.fromtimestamp(
                state["last_alive"], timezone.utc).isoformat(timespec="seconds")
            state["corroborated"] = detail
            age = best
            due = [s for s in conf["stages"]
                   if age >= float(s["after_hours"]) and stage_key(s) not in fired]
            save_state(state)
            if not due:
                ev.emit("deadman", "warn",
                        f"escalation stood down — proof of life {fmt_age(best)} "
                        f"({detail})")
                print(f"stood down: proof of life {fmt_age(best)} · {detail}")
                write_worker(conf, state, age, "pass",
                             f"stood down on evidence: {detail}")
                return 0
            print(f"clock moved to {fmt_age(age)} on evidence · {detail}")
        else:
            # Fail toward sending. No evidence, or evidence older than the
            # silence, both mean proceed.
            print(f"no fresher proof of life · {detail}")
            ev.emit("deadman", "warn", f"corroboration found nothing: {detail}")

    if not due:
        print(f"last check-in {fmt_age(age)}; nothing due")
        write_worker(conf, state, age, "pass", f"quiet {fmt_age(age)}")
        return 0

    failures = []
    for s in due:
        print(f"stage {s['after_hours']}h due ({fmt_age(age)} silent)")
        ok, detail = deliver(conf, s, args.dry_run)
        if args.dry_run:
            continue
        if ok:
            fired.append(stage_key(s))
            ev.emit("deadman", "needs_you",
                    f"escalation sent: {s['channel']} -> {s['to']} "
                    f"after {s['after_hours']}h silence")
        else:
            # Not recorded as fired, so the next tick retries. A transient SMTP
            # failure must not consume the one message that mattered.
            failures.append(f"{s['channel']}->{s['to']}: {detail}")
            ev.emit("deadman", "error",
                    f"escalation FAILED: {s['channel']} -> {s['to']}: {detail}")

    if args.dry_run:
        return 0

    state["fired"] = fired
    save_state(state)

    status = "fail" if failures else "alert"
    summary = (f"{len(due) - len(failures)}/{len(due)} escalations sent after "
               f"{fmt_age(age)} silence"
               + (f" · FAILED: {'; '.join(failures)}" if failures else ""))
    write_worker(conf, state, age, status, summary)
    print(summary)
    return 1 if failures else 0


def write_worker(conf, state, age, status, summary):
    """Publish to the board, so a dead switch is visible next to a failing suite."""
    WORKER.parent.mkdir(parents=True, exist_ok=True)
    WORKER.write_text(json.dumps({
        "worker": "deadman", "kind": "heartbeat",
        "target": f"operator check-in · {fmt_age(age)}",
        "last_run": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status, "summary": summary,
        "detail": json.dumps({"fired": state.get("fired", []),
                              "disarmed": bool(state.get("disarmed"))})[:1500],
        "digest": None,
        "tests_passed": 0, "tests_failed": 0, "duration_s": 0.0,
    }, indent=2))


def cmd_disarm(args):
    state = load_state()
    state["disarmed"] = True
    save_state(state)
    ev.emit("deadman", "warn", "dead-man switch DISARMED — no escalations will send")
    print("disarmed. `deadman.py rearm` to resume.")
    return 0


def cmd_rearm(args):
    state = load_state()
    state.pop("disarmed", None)
    # Rearming without a fresh check-in would immediately fire every overdue
    # stage from the silence that happened while it was off.
    state["last_alive"] = time.time()
    state["last_alive_iso"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["fired"] = []
    save_state(state)
    ev.emit("deadman", "ok", "dead-man switch rearmed; clock reset")
    print("rearmed; clock reset to now")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("alive", help="reset the clock")
    p.add_argument("note", nargs="*")
    p.set_defaults(fn=cmd_alive)

    p = sub.add_parser("status", help="show the clock and pending stages")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("check", help="fire anything now due")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--corroborate", action="store_true",
                   help="look for human proof of life before escalating")
    p.set_defaults(fn=cmd_check)

    p = sub.add_parser("disarm", help="stop firing, keep config")
    p.set_defaults(fn=cmd_disarm)

    p = sub.add_parser("rearm", help="resume firing, reset clock")
    p.set_defaults(fn=cmd_rearm)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
