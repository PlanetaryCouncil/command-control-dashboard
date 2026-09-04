#!/usr/bin/env python3
"""What Claude is doing, in plain lines. One way only.

Marsita, 2026-09-05: "terminal in the browser is unworkable... scroll does not
work... 1 command only. And then nothing works... Just stream me stuff 1 way
only... No extra noise... Only the stuff I need to see."

The browser pane spent weeks becoming a real terminal -- pty, websocket,
resize, scrollback, tmux -- and every one of those was a correct fix for a
real bug in the wrong product. A terminal is a thing you TYPE into, and there
is already a perfect one on the laptop. What the browser is good at is being
read from across the room.

So this does not render a terminal at all. It reads Claude Code's own
transcript, which is structured, and emits the three things worth seeing:

    you      what was asked
    claude   what was answered
    ·        one grey line per tool, so the gaps are explained

Everything else is dropped on purpose -- thinking blocks, tool results,
attachments, system notices, the spinner, the tmux status bar, every escape
sequence. That is the "no extra noise" part, and it is the whole feature.
"""

from __future__ import annotations

import json
import os
import pathlib
import re

HOME = pathlib.Path.home()
# One line of a tool call is a signpost; a paragraph of it is the noise this
# exists to remove.
TOOL_ARG = ("command", "file_path", "pattern", "path", "url", "prompt",
            "description", "query")
CLIP = 110


def transcript_dir(cwd: str) -> pathlib.Path:
    """Claude Code's transcript folder for a working directory."""
    slug = re.sub(r"[^A-Za-z0-9-]", "-", os.path.abspath(cwd))
    return HOME / ".claude" / "projects" / slug


def newest(cwd: str) -> pathlib.Path | None:
    """The session being worked in right now, which is the one to watch."""
    try:
        files = sorted(transcript_dir(cwd).glob("*.jsonl"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    return files[0] if files else None


def _text(content) -> str:
    """The words out of a content block list, thinking left behind."""
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    out = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "text":
            out.append(str(b.get("text", "")))
    return "\n".join(out).strip()


def _tool_line(block: dict) -> str:
    """`Bash · git push` -- the name, and the one argument that identifies it."""
    name = str(block.get("name") or "tool")
    args = block.get("input") or {}
    for key in TOOL_ARG:
        val = args.get(key)
        if isinstance(val, str) and val.strip():
            one = " ".join(val.split())
            return f"{name} · {one[:CLIP]}" + ("…" if len(one) > CLIP else "")
    return name


def _is_noise(text: str) -> bool:
    """Machinery the operator never asked to see.

    A tool result fed back as a user turn is not something anyone said, and a
    command's stdout replayed here would be exactly the wall of terminal this
    page exists to replace.
    """
    if not text:
        return True
    head = text.lstrip()[:40].lower()
    return head.startswith(("<system-reminder", "<command-name",
                            "<local-command", "caveat:", "[request inter"))


def parse(line: str) -> dict | None:
    """One transcript row -> one displayable line, or None to drop it."""
    try:
        row = json.loads(line)
    except ValueError:
        return None
    kind = row.get("type")
    if kind not in ("user", "assistant"):
        return None                     # system, attachment, summary: not said
    msg = row.get("message") or {}
    content = msg.get("content")
    at = str(row.get("timestamp") or "")[11:19]

    if kind == "user":
        # A tool_result is the machine answering itself, not the operator.
        if isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content):
            return None
        body = _text(content)
        return None if _is_noise(body) else {"at": at, "who": "you", "text": body}

    tools = [b for b in (content or [])
             if isinstance(b, dict) and b.get("type") == "tool_use"]
    body = _text(content)
    if body:
        return {"at": at, "who": "claude", "text": body}
    if tools:
        return {"at": at, "who": "tool", "text": _tool_line(tools[0])}
    return None                          # a thinking block on its own


def tail(cwd: str = ".", limit: int = 120) -> dict:
    """The last `limit` displayable lines of the live session.

    The whole file is read and then cut, rather than seeking to the end: a
    transcript row is one JSON object per line but the lines are long, and the
    last N BYTES is not the last N rows. Reading it is a few megabytes at
    worst and this is polled every few seconds, not every frame.
    """
    path = newest(cwd)
    if path is None:
        return {"lines": [], "session": "", "at": 0.0}
    try:
        raw = path.read_text(errors="replace").splitlines()
        stamp = path.stat().st_mtime
    except OSError:
        return {"lines": [], "session": "", "at": 0.0}
    lines = [d for d in (parse(l) for l in raw) if d]
    return {"lines": lines[-limit:], "session": path.stem[:8], "at": stamp}


if __name__ == "__main__":
    for row in tail(".", 40)["lines"]:
        print(f'{row["at"]} {row["who"]:>6}  {row["text"][:100]}')
