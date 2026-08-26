#!/usr/bin/env python3
"""Hoverable, clickable option boxes in an 80-column terminal.

The mouse half is the same trick approve.py uses — `\\033[?1003h` asks the
terminal to report all motion rather than only clicks, `\\033[?1006h` switches
coordinates to decimal text so nothing breaks past column 223 — but the hit
regions here are rectangles rather than single rows, because an option is a box
you can point anywhere inside.

Three states, and each is carried by *shape* as well as colour:

    idle      ┌────┐   thin, dim
    hovered   ╔════╗   double rule, bright, with a ▸ in the margin
    pressed   ▛▀▀▀▀▜   heavy, filled, for ~90ms

Shape matters because colour alone fails on a monochrome terminal, over a bad
ssh session, and for anyone who cannot distinguish the two colours. The border
changing weight is legible with no colour at all.

Every box is drawn from a computed width, never hand-padded — a lesson this
project has logged twice, both times as a frame wrong by exactly one column.
render() asserts every row is equal before it returns.

  python3 fleet/bin/pick.py --demo
"""

from __future__ import annotations

import os
import re
import shutil
import signal
import sys
import termios
import time
import tty

ESC = "\033"
ALT_ON, ALT_OFF = f"{ESC}[?1049h", f"{ESC}[?1049l"
HIDE, SHOW = f"{ESC}[?25l", f"{ESC}[?25h"
MOUSE_ON = f"{ESC}[?1003h{ESC}[?1006h"
MOUSE_OFF = f"{ESC}[?1006l{ESC}[?1003l"
CLEAR, HOME = f"{ESC}[2J", f"{ESC}[H"

RESET, BOLD, DIM = f"{ESC}[0m", f"{ESC}[1m", f"{ESC}[2m"
GREY, CYAN, GREEN, AMBER = f"{ESC}[90m", f"{ESC}[96m", f"{ESC}[92m", f"{ESC}[93m"
INV = f"{ESC}[7m"

MOUSE_RE = re.compile(rf"{re.escape(ESC)}\[<(\d+);(\d+);(\d+)([Mm])")
W = 76                      # inside 80, with a margin either side

# idle, hovered, pressed — corners, horizontal, vertical
FRAMES = {
    "idle":    ("┌", "┐", "└", "┘", "─", "│", GREY),
    "hover":   ("╔", "╗", "╚", "╝", "═", "║", CYAN),
    "press":   ("▛", "▜", "▙", "▟", "▀", "▌", GREEN),
}


def wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            out.append(line); line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


class Box:
    """One option. Knows its own rectangle, so the hit test cannot disagree
    with the renderer about where it is."""

    def __init__(self, key: str, title: str, body: str = "") -> None:
        self.key, self.title, self.body = key, title, body
        self.top = self.bottom = 0

    def height(self) -> int:
        return 2 + 1 + (len(wrap(self.body, W - 6)) if self.body else 0)

    def draw(self, row: int, state: str) -> list[str]:
        tl, tr, bl, br, h, v, colour = FRAMES[state]
        inner = W - 2
        self.top, self.bottom = row, row + self.height() - 1
        marker = f"{colour}▸{RESET}" if state != "idle" else " "
        weight = BOLD if state != "idle" else ""

        rows = [f"{marker} {colour}{tl}{h * inner}{tr}{RESET}"]
        rows.append(f"  {colour}{v}{RESET}{weight} {self.title.ljust(inner - 1)}{RESET}"
                    f"{colour}{v}{RESET}")
        for ln in (wrap(self.body, inner - 4) if self.body else []):
            rows.append(f"  {colour}{v}{RESET}{GREY}   {ln.ljust(inner - 4)}{RESET} "
                        f"{colour}{v}{RESET}")
        rows.append(f"  {colour}{bl}{h * inner}{br}{RESET}")
        return rows

    def contains(self, row: int, col: int) -> bool:
        return self.top <= row <= self.bottom and 2 <= col <= W + 1


def visible_len(s: str) -> int:
    return len(re.sub(rf"{re.escape(ESC)}\[[0-9;?]*[a-zA-Z]", "", s))


def render(heading: str, boxes: list[Box], hover: int | None,
           pressed: int | None) -> list[str]:
    out = [f"{BOLD}{'█' * W}{RESET}", f"{BOLD}  {heading}{RESET}", ""]
    for i, b in enumerate(boxes):
        state = "press" if i == pressed else ("hover" if i == hover else "idle")
        out += b.draw(len(out), state)
        out.append("")
    out.append(f"{GREY}  point at a box · click to choose · 1-{len(boxes)} · q to quit{RESET}")

    # Never trust a hand-built layout. Two logged failures in this project were a
    # frame wrong by exactly one column, both from padding by eye.
    widths = {visible_len(r) for r in out if r.strip() and "█" not in r}
    assert all(w <= 80 for w in widths), f"a row exceeded 80 columns: {sorted(widths)[-3:]}"
    return out


def read_event(buf: str):
    m = MOUSE_RE.match(buf)
    if m:
        btn, col, row, kind = (int(m.group(1)), int(m.group(2)),
                               int(m.group(3)), m.group(4))
        return None, (row - 1, col - 1,
                      "move" if btn & 32 else ("press" if kind == "M" else "up")), buf[m.end():]
    if buf.startswith(f"{ESC}[") and len(buf) >= 3:
        return {"A": "up", "B": "down"}.get(buf[2]), None, buf[3:]
    if buf.startswith(ESC) and len(buf) == 1:
        return "q", None, ""
    return buf[0], None, buf[1:]


def choose(heading: str, options: list[tuple[str, str, str]]) -> str | None:
    """Show the boxes, return the chosen key — or None if they quit."""
    if not sys.stdin.isatty():
        print("pick.py needs a terminal"); return None
    if shutil.get_terminal_size().columns < 80:
        print("needs at least 80 columns"); return None

    boxes = [Box(*o) for o in options]
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)

    def restore(*_):
        sys.stdout.write(MOUSE_OFF + SHOW + ALT_OFF); sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)

    signal.signal(signal.SIGINT, lambda *_: (restore(), sys.exit(0)))
    signal.signal(signal.SIGTERM, lambda *_: (restore(), sys.exit(0)))

    def paint(hover, pressed=None):
        sys.stdout.write(CLEAR + HOME + "\r\n".join(render(heading, boxes, hover, pressed)))
        sys.stdout.flush()

    def flash(i: int) -> None:
        """A press with no feedback feels broken on a terminal that repaints
        slowly. 90ms is long enough to register and short enough not to lag."""
        paint(i, pressed=i); time.sleep(0.09); paint(i)

    try:
        tty.setraw(fd)
        sys.stdout.write(ALT_ON + HIDE + MOUSE_ON)
        hover, buf = None, ""
        paint(hover)
        while True:
            buf += os.read(fd, 1024).decode("utf-8", "ignore")
            while buf:
                key, mouse, buf = read_event(buf)
                if mouse:
                    row, col, kind = mouse
                    over = next((i for i, b in enumerate(boxes) if b.contains(row, col)), None)
                    if kind == "move" and over != hover:
                        hover = over; paint(hover)
                    elif kind == "press" and over is not None:
                        flash(over); restore(); return boxes[over].key
                elif key == "up":
                    hover = 0 if hover is None else max(0, hover - 1); paint(hover)
                elif key == "down":
                    hover = 0 if hover is None else min(len(boxes) - 1, hover + 1); paint(hover)
                elif key in ("\r", "\n") and hover is not None:
                    flash(hover); restore(); return boxes[hover].key
                elif key and key.isdigit() and 1 <= int(key) <= len(boxes):
                    i = int(key) - 1; flash(i); restore(); return boxes[i].key
                elif key in ("q", "\x03"):
                    restore(); return None
    finally:
        restore()


if __name__ == "__main__":
    demo = [
        ("read", "Read the two proposals",
         "claude and hermes each answered the three questions. Print them, then act or decline."),
        ("ledger", "Build the findings ledger",
         "Every proposal gets accepted or declined. Stops silence being the default answer."),
        ("watchdog", "Skip pytest when HEAD is unchanged",
         "309s of pegged four-core CPU, hourly, over a tree that has not changed a byte."),
        ("stop", "Stop for tonight",
         "The rota runs hourly without you. There will be more in the morning."),
    ]
    picked = choose("WHAT NEXT", demo)
    print(f"chose: {picked}" if picked else "cancelled")
