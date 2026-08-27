#!/usr/bin/env python3
"""Append-only archive of the couplet that closes an agent turn.

Every turn in this fleet used to end with one or two lines, then throw them
away. append(text, author, task) keeps them: one JSON object per line in
data/poems.jsonl. The board serves the feed at /poems.json and the newest
50 at /poems.

  poems.py append --author grok --task rota "the door is open now\\nthe couplet stays"

Fields: ts, author (the agent), task (worker or proposal slug), lines (the
couplet). A turn with no extractable couplet is a no-op, not an error.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# Box-drawing used to frame a closer. Stripped so the verse is what is kept.
BOX_RE = re.compile(r"[╭╮╯╰┌┐└┘├┤┬┴┼─│━┃┏┓┗┛┳┻┣┫╋═║╔╗╚╝╦╩╠╣╬]")

PAGE_N = 50


def log_path() -> Path:
    return Path(os.environ.get("POEMS_JSONL", ROOT / "data" / "poems.jsonl"))


def _clean(v, limit):
    return re.sub(r"[\x00-\x1f\x7f]", " ", str(v or "")).strip()[:limit]


def _plain(line: str) -> str:
    return " ".join(BOX_RE.sub(" ", line).split())


def _unpoetic(val: str) -> bool:
    s = val.strip()
    u = s.upper()
    if u == "NOTHING TO ADD" or u.startswith("SKIP:"):
        return True
    return s.startswith(("[timed out", "[error", "[unknown", "[stderr]"))


def couplet(text) -> list[str]:
    """Last one or two short lines of a turn, if they look like a closer.

    A whole output of one or two short lines is itself the couplet. A longer
    body keeps a closer only when a blank line or a box frame sets it off —
    otherwise the last two sentences of a proposal would fill the archive.
    """
    if isinstance(text, (list, tuple)):
        raw_lines = [str(x) for x in text]
    else:
        raw_lines = str(text or "").splitlines()

    entries: list[tuple[str, str]] = []
    for line in raw_lines:
        plain = _plain(line)
        if plain:
            entries.append(("line", plain))
        elif not line.strip() or BOX_RE.search(line):
            if not entries or entries[-1][0] != "break":
                entries.append(("break", ""))

    while entries and entries[-1][0] == "break":
        entries.pop()

    taken: list[str] = []
    i = len(entries) - 1
    while i >= 0 and len(taken) < 2:
        kind, val = entries[i]
        if kind == "break":
            break
        if len(val) > 80 or _unpoetic(val):
            return []
        taken.append(val)
        i -= 1
    taken.reverse()
    if not taken:
        return []
    if i < 0:
        return taken
    if entries[i][0] == "break":
        return taken
    return []


def append(text, author, task):
    """Write one poem. Returns the record, or None if there was no couplet.

    Never raises: a turn that cannot be logged still closed, and the caller
    must not die for the archive.
    """
    try:
        lines = couplet(text)
        if not lines:
            return None
        rec = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "author": (_clean(author, 40).lower() or "unknown"),
            "task": (_clean(task, 80) or "unknown"),
            "lines": lines,
        }
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return rec
    except Exception:
        return None


def load() -> list[dict]:
    """Oldest first, skipping truncated tails."""
    path = log_path()
    try:
        raw = path.read_text(errors="replace")
    except OSError:
        return []
    out = []
    for line in raw.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if not isinstance(rec, dict):
            continue
        lines = rec.get("lines")
        if not isinstance(lines, list) or not lines:
            continue
        out.append(rec)
    return out


def recent(n: int = PAGE_N) -> list[dict]:
    recs = load()
    recs.reverse()
    return recs[: max(0, n)]


def as_json() -> str:
    recs = load()
    recs.reverse()
    return json.dumps(recs, ensure_ascii=False)


CSS = """
:root{
  --ground:#0d0f12; --surface:#15181d; --raised:#1c2027; --border:#262b33;
  --ink:#eef1f4; --ink-2:#b6bec9; --muted:#7c8794; --info:#5b93d6;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  font-size:15px;line-height:1.55}
.wrap{max-width:40rem;margin:0 auto;padding:1.4rem 1.2rem 4rem}
header{display:flex;flex-wrap:wrap;gap:.8rem;align-items:flex-start;
  margin-bottom:1.4rem}
h1{margin:0;font-size:1.6rem;font-weight:600}
.lede{color:var(--ink-2);margin:.4rem 0 0;max-width:42ch}
a{color:var(--info)}
.poem{border-top:1px solid var(--border);padding:1rem 0}
blockquote{margin:0;font-size:1.05rem;line-height:1.45}
blockquote p{margin:.15rem 0}
.meta{margin:.55rem 0 0;font-family:var(--mono);font-size:.72rem;
  color:var(--muted);letter-spacing:.04em}
.empty{color:var(--ink-2)}
"""


def page(nav_html: str = "", nav_css: str = "") -> str:
    import nav
    poems = recent(PAGE_N)
    if poems:
        body = []
        for rec in poems:
            verses = "".join(
                f"<p>{html.escape(str(line))}</p>" for line in rec.get("lines") or []
            )
            meta = " · ".join(
                html.escape(str(x))
                for x in (rec.get("author") or "?", rec.get("task") or "?",
                          rec.get("ts") or "")
                if x
            )
            body.append(
                f'<article class="poem"><blockquote>{verses}</blockquote>'
                f'<p class="meta">{meta}</p></article>'
            )
        inner = "\n".join(body)
    else:
        inner = '<p class="empty">No poems yet. They appear when an agent turn closes.</p>'
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nav.title("poems")}</title>
<!-- agents: /llms.txt -->
<link rel="alternate" type="application/json" href="/poems.json" title="poems.json">
<style>{nav_css}{CSS}</style>
</head><body>
<div class="wrap">
  <header>
    {nav_html}
    <div>
      <h1>poems</h1>
      <p class="lede">The couplet that closes each agent turn, newest first.
        Machine feed: <a href="/poems.json">/poems.json</a></p>
    </div>
  </header>
  {inner}
</div>
</body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    a = sub.add_parser("append")
    a.add_argument("--author", required=True)
    a.add_argument("--task", required=True)
    a.add_argument("text")
    sub.add_parser("recent")
    args = ap.parse_args(argv)
    if args.cmd == "append":
        rec = append(args.text.replace("\\n", "\n"), args.author, args.task)
        if rec is None:
            print("no couplet", file=sys.stderr)
            return 1
        print(json.dumps(rec, ensure_ascii=False))
        return 0
    print(json.dumps(recent(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
