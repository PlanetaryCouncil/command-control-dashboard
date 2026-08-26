#!/usr/bin/env python3
"""Clickable approval queue. 80 columns, boxes, yes and no.

Terminals have reported mouse events since the 1980s and almost nothing uses it.
The program asks by writing an escape sequence and the terminal starts sending
clicks and motion back on stdin as more escape sequences:

    \\033[?1003h   report ALL motion, not just clicks — this is what makes hover
                   possible; 1000 gives clicks only and 1002 adds drag
    \\033[?1006h   SGR extended coordinates. The original protocol encoded x and
                   y as single bytes offset by 32, so it broke past column 223.
                   SGR sends them as decimal text: \\033[<0;34;12M

So a box drawn at known coordinates can be hit-tested: the click arrives as a row
and a column, and the program asks which box contains it. That is the whole
trick, and it is why htop and vim have felt clickable for decades.

Keyboard works too, always — y/n/arrows/q. A mouse-only interface in a terminal
is a worse terminal, and this has to stay usable over ssh with mouse reporting
off.

  python3 fleet/bin/approve.py            # the live queue
  python3 fleet/bin/approve.py --demo     # no server needed
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import sys
import termios
import tty
import urllib.request

COCKPIT = os.environ.get("COCKPIT", "http://127.0.0.1:8770")
W = 78                      # inside an 80-column terminal, with a column each side

# --- ANSI ---------------------------------------------------------------------
ESC = "\033"
ALT_ON, ALT_OFF = f"{ESC}[?1049h", f"{ESC}[?1049l"
HIDE, SHOW = f"{ESC}[?25l", f"{ESC}[?25h"
MOUSE_ON = f"{ESC}[?1003h{ESC}[?1006h"
MOUSE_OFF = f"{ESC}[?1006l{ESC}[?1003l"
CLEAR, HOME = f"{ESC}[2J", f"{ESC}[H"

DIM, BOLD, RESET = f"{ESC}[2m", f"{ESC}[1m", f"{ESC}[0m"
GREEN, RED, CYAN, GREY = f"{ESC}[32m", f"{ESC}[31m", f"{ESC}[36m", f"{ESC}[90m"
INV = f"{ESC}[7m"

# \033[<BUTTON;COL;ROW M|m  — M is press, m is release. Motion sets bit 5 (32).
MOUSE_RE = re.compile(rf"{re.escape(ESC)}\[<(\d+);(\d+);(\d+)([Mm])")


def fetch(demo: bool) -> list[dict]:
    if demo:
        return [{"id": "apr-002", "action": "Publish this dashboard to a public URL",
                 "project": "command-control-dashboard", "risk": "medium",
                 "target": "public host", "requested_by": "marsita",
                 "proposed": "Deploy read-only. Write endpoints stay on localhost.",
                 "rollback": "Take the host down", "status": "pending"}]
    try:
        with urllib.request.urlopen(f"{COCKPIT}/api/approvals", timeout=5) as r:
            rows = json.load(r).get("approvals", [])
    except Exception:
        return []
    return [a for a in rows if a.get("status") == "pending"]


class Screen:
    """Draws, and remembers where it drew so a click can be resolved."""

    def __init__(self) -> None:
        self.rows: list[str] = []
        self.zones: dict[str, tuple[int, int, int]] = {}   # name -> (row, c0, c1)

    def line(self, s: str = "") -> None:
        self.rows.append(s)

    def box(self, label: str, name: str, col: int, active: bool, colour: str) -> str:
        """Register a clickable region and return its rendered text.

        Width is computed from the label rather than assumed — the hit test reads
        the same numbers the renderer used, so a box can never be clickable
        somewhere it is not drawn.
        """
        text = f"  {label}  "
        self.zones[name] = (len(self.rows), col, col + len(text) - 1)
        style = f"{colour}{INV}{BOLD}" if active else colour
        return f"{style}{text}{RESET}"

    def hit(self, row: int, col: int) -> str | None:
        for name, (r, c0, c1) in self.zones.items():
            if row == r and c0 <= col <= c1:
                return name
        return None


def render(items: list[dict], idx: int, hover: str | None, msg: str) -> Screen:
    s = Screen()
    s.line(f"{BOLD}{'█' * W}{RESET}")
    s.line(f"{BOLD}  APPROVAL QUEUE{RESET}{GREY}   ·   {len(items)} pending   ·   "
           f"click or press y / n / ↑ ↓ / q{RESET}")
    s.line(f"{GREY}{'─' * W}{RESET}")
    s.line()

    if not items:
        s.line(f"{GREEN}  Nothing waiting on you.{RESET}")
        s.line()
        s.line(f"{GREY}  A grant here is standing — it lasts until revoked, so the")
        s.line(f"  scope is the only thing bounding it.{RESET}")
        return s

    a = items[idx]
    risk = {"low": GREEN, "medium": CYAN, "high": RED}.get(a.get("risk", ""), GREY)
    s.line(f"  {GREY}{idx + 1} of {len(items)}{RESET}   "
           f"{risk}{a.get('risk', '?').upper()}{RESET}   {GREY}{a.get('id')}{RESET}")
    s.line()
    s.line(f"  {BOLD}{a.get('action', '')[:W - 4]}{RESET}")
    s.line()
    for k in ("project", "target", "requested_by"):
        if a.get(k):
            s.line(f"  {GREY}{k + ':':14}{RESET}{a[k][:W - 20]}")
    s.line()
    if a.get("proposed"):
        s.line(f"  {GREY}proposed{RESET}      {a['proposed'][:W - 20]}")
    if a.get("rollback"):
        s.line(f"  {GREY}rollback{RESET}      {a['rollback'][:W - 20]}")
    s.line()
    s.line(f"{GREY}{'─' * W}{RESET}")
    s.line()

    yes = s.box("✓  APPROVE", "yes", 2, hover == "yes", GREEN)
    no = s.box("✗  DECLINE", "no", 22, hover == "no", RED)
    # Both boxes share a row, so both zones must be registered against it. box()
    # records the row it is called on — hence assembling the line after.
    s.zones["no"] = (s.zones["yes"][0], 22, 22 + len("  ✗  DECLINE  ") - 1)
    s.line(f"  {yes}    {no}")
    s.line()
    s.line(f"{GREY}  Approving asks for a scope. Nothing is granted without one —{RESET}")
    s.line(f"{GREY}  an unscoped standing grant is a blank cheque.{RESET}")
    if msg:
        s.line()
        s.line(f"  {msg}")
    return s


def read_event(buf: str) -> tuple[str | None, tuple[int, int, str] | None, str]:
    """Pull one key or mouse event off the buffer. Returns (key, mouse, rest)."""
    m = MOUSE_RE.match(buf)
    if m:
        btn, col, row, kind = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
        rest = buf[m.end():]
        # Bit 5 marks motion. Anything else with M is a press.
        return None, (row - 1, col - 1, "move" if btn & 32 else
                      ("press" if kind == "M" else "release")), rest
    if buf.startswith(f"{ESC}[") and len(buf) >= 3:
        return {"A": "up", "B": "down"}.get(buf[2]), None, buf[3:]
    if buf.startswith(ESC) and len(buf) == 1:
        return "esc", None, ""
    return buf[0], None, buf[1:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="one fake item, no server")
    args = ap.parse_args()

    if not sys.stdin.isatty():
        print("approve.py needs a terminal"); return 1
    if shutil.get_terminal_size().columns < 80:
        print("needs at least 80 columns"); return 1

    items = fetch(args.demo)
    idx, hover, msg = 0, None, ""
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)

    def restore(*_):
        # A terminal left in raw mode with mouse reporting on is unusable, and
        # the user cannot fix it without knowing to type `reset`. Restore on
        # every path out, including signals.
        sys.stdout.write(MOUSE_OFF + SHOW + ALT_OFF)
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)

    signal.signal(signal.SIGINT, lambda *_: (restore(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (restore(), sys.exit(0)))

    try:
        tty.setraw(fd)
        sys.stdout.write(ALT_ON + HIDE + MOUSE_ON)
        buf = ""
        while True:
            screen = render(items, idx, hover, msg)
            sys.stdout.write(CLEAR + HOME + "\r\n".join(screen.rows) + "\r\n")
            sys.stdout.flush()

            buf += os.read(fd, 1024).decode("utf-8", "ignore")
            while buf:
                key, mouse, buf = read_event(buf)

                if mouse:
                    row, col, kind = mouse
                    zone = screen.hit(row, col)
                    if kind == "move":
                        hover = zone            # this is the hover effect
                    elif kind == "press" and zone:
                        key = "y" if zone == "yes" else "n"

                if key in ("q", "esc", "\x03"):
                    restore(); return 0
                if key == "up":
                    idx = max(0, idx - 1); msg = ""
                elif key == "down":
                    idx = min(len(items) - 1, idx + 1) if items else 0; msg = ""
                elif key in ("y", "n") and items:
                    verb = "approve" if key == "y" else "decline"
                    msg = (f"{GREEN if key == 'y' else RED}{verb}d "
                           f"{items[idx]['id']}{RESET}  "
                           f"{GREY}(demo — nothing sent){RESET}" if args.demo else
                           f"{GREY}scope required — not wired to the API yet{RESET}")
    finally:
        restore()


if __name__ == "__main__":
    raise SystemExit(main())
