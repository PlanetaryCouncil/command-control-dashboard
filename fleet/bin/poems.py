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


# A line has to carry an image or a turn to be worth keeping, and the cheapest
# proxy for that is that it is a SENTENCE rather than a word. "go" got filed as
# a poem on 2026-09-09 -- Marsita: ""go" is not a poem". So did "Please let me
# know if these answers meet the requirements!" and "(The update would unblock
# the Project Future Vision XPRIZE)". None of them were poems; all of them were
# simply the last line of something.
# A markdown or HTML image on a line of its own. GitHub turns a dragged
# screenshot into one of these, and the poems page has no business printing
# the tag or fetching the picture.
IMG_RE = re.compile(r"^(!\[.*?\]\(.*?\)|<img\b[^>]*/?>)$", re.I)

# Per LINE: one word is not a line. Across the whole poem: three words and a
# dozen characters, which "go" fails and "the couplet stays" passes. An earlier
# pass put both thresholds on every line and threw out real short poems --
# short is the point of a couplet, so the floor belongs on the whole thing.
MIN_LINE_WORDS = 2
MIN_WORDS = 3
MIN_CHARS = 12

# Things a machine says when it is finishing a job, not closing a turn. They
# are all last lines, which is exactly why the last-line rule kept catching
# them.
CHATTER = (
    "let me know", "meet the requirements", "hope this helps", "anything else",
    "here you go", "here are the", "as requested", "i have ", "i've ",
    "done.", "completed", "successfully", "no changes", "unblock",
)


def _unpoetic(val: str) -> bool:
    s = val.strip()
    u = s.upper()
    if u == "NOTHING TO ADD" or u.startswith("SKIP:"):
        return True
    if s.startswith(("[timed out", "[error", "[unknown", "[stderr]")):
        return True
    # One word is not a line, however short a poem may be.
    if len(s.split()) < MIN_LINE_WORDS:
        return True
    low = s.lower()
    if any(c in low for c in CHATTER):
        return True
    # A parenthetical aside is a footnote to something else, and a bare
    # question is a machine asking for instructions.
    if s.startswith("(") and s.endswith(")"):
        return True
    if s.endswith("?"):
        return True
    return False


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
    # The floor is on the poem, not the line.
    joined = " ".join(taken)
    if len(joined.split()) < MIN_WORDS or len(joined) < MIN_CHARS:
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

.submit{margin:10px 0 0;padding:8px 11px;border-radius:5px;
  background:var(--raised,#f2f2ef);border:1px solid var(--border,#ddd);
  font-size:14px;line-height:1.55;}
.submit b{margin-right:5px;}
.submit a{font-weight:600;}

.band{font-family:var(--mono,monospace);font-size:11px;letter-spacing:.16em;
  text-transform:uppercase;color:var(--muted,#888);margin:22px 0 8px;
  border-bottom:1px solid var(--border,#ddd);padding-bottom:4px;}
.poem.sent{border-left:3px solid var(--good,#0ca30c);}
.poem.sent .title{margin:0 0 6px;font-weight:600;}
"""


SUBMITTED_CACHE = {"at": 0.0, "rows": []}
SUBMITTED_TTL = 600
POEMS_REPO = "PlanetaryCouncil/poems"
POEMS_API = f"https://api.github.com/repos/{POEMS_REPO}/issues"


def _fetch_issues() -> list[dict]:
    """Open issues on the poems repo, oldest API first, `gh` as a fallback.

    Marsita, 2026-09-09: "Github and repo is source of truth." So the page
    reads GitHub directly rather than a local file, and it must not need the
    `gh` CLI to be installed and logged in wherever the board happens to be
    running -- the repo is public, and the REST endpoint is public with it.
    `gh` stays as a second try for the case where an outbound request is
    blocked but a configured CLI is not.

    Both shapes are normalised to gh's field names, because the rest of this
    function was written against those and one vocabulary is enough.
    """
    import urllib.request
    req = urllib.request.Request(
        POEMS_API + "?state=open&per_page=40",
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "planetary-council-board"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = json.loads(r.read().decode())
        return [{"number": i.get("number"), "title": i.get("title"),
                 "body": i.get("body"),
                 "author": {"login": (i.get("user") or {}).get("login")},
                 "createdAt": i.get("created_at")}
                for i in raw
                # A pull request is an issue as far as this endpoint is
                # concerned, and a PR is not a poem.
                if not i.get("pull_request")]
    except Exception:
        pass
    import subprocess as sp
    try:
        r = sp.run(["gh", "issue", "list", "--repo", POEMS_REPO,
                    "--state", "open", "--limit", "40",
                    "--json", "number,title,body,author,createdAt"],
                   capture_output=True, text=True, timeout=20)
        return json.loads(r.stdout or "[]") if r.returncode == 0 else []
    except (OSError, sp.SubprocessError, ValueError):
        return []


def submitted(*, ttl: int = SUBMITTED_TTL, now: float | None = None) -> list[dict]:
    """Poems people sent, as open issues on the poems repo.

    Marsita, 2026-09-09: "I just want to see my on top." Hers arrive as
    issues -- that is what "how to submit" points at -- and a page that
    invites submissions and then shows only its own machine output is asking
    people to post into a void.

    Cached ten minutes and failing to an empty list: GitHub being slow or
    rate-limited must cost the page nothing but the human half.
    """
    import time as _t
    now = _t.time() if now is None else now
    if now - SUBMITTED_CACHE["at"] < ttl:
        return SUBMITTED_CACHE["rows"]
    rows = _fetch_issues()
    out = []
    for i in rows:
        # The body is the poem; the title is what it is called. An issue with
        # no body is a title someone meant as the whole poem.
        lines = []
        for ln in str(i.get("body") or "").splitlines():
            ln = ln.strip()
            # People paste poems as quotes. The marker is the quoting, not the
            # poem, and "❯ STOP automerge to main" is not how it should read.
            ln = re.sub(r"^[>❯]+\s*", "", ln).strip()
            # An issue can carry a screenshot. A raw <img> tag printed as text
            # is worse than nothing, and rendering someone's remote image into
            # this page is not something the page should decide to do.
            if not ln or IMG_RE.match(ln) or ln.startswith(("```", "---")):
                continue
            lines.append(ln)
        lines = lines[:12]
        if not lines and not str(i.get("title") or "").strip():
            continue                       # nothing to show, so show nothing
        out.append({
            "title": str(i.get("title") or "").strip(),
            "lines": lines or [str(i.get("title") or "").strip()],
            "author": ((i.get("author") or {}).get("login") or "someone"),
            "ts": str(i.get("createdAt") or "")[:10],
            "url": f"https://github.com/PlanetaryCouncil/poems/issues/{i.get('number')}",
        })
    SUBMITTED_CACHE.update(at=now, rows=out)
    return out


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

    # Sent by people, above everything the machines wrote. Not a mix: a poem
    # somebody chose to send is a different kind of thing from a couplet that
    # fell out of a build, and burying the first among two hundred of the
    # second is how you stop receiving them.
    sent = []
    for rec in submitted():
        verses = "".join(f"<p>{html.escape(l)}</p>" for l in rec["lines"])
        title = (f'<p class="title">{html.escape(rec["title"])}</p>'
                 if rec["title"] and rec["lines"][:1] != [rec["title"]] else "")
        sent.append(
            f'<article class="poem sent">{title}'
            f'<blockquote>{verses}</blockquote>'
            f'<p class="meta"><a href="{html.escape(rec["url"])}" rel="noopener">'
            f'{html.escape(rec["author"])}</a> &middot; {html.escape(rec["ts"])}</p>'
            f'</article>')
    sent_html = (('<h2 class="band">sent in</h2>' + "\n".join(sent)
                  + '<h2 class="band">from the fleet</h2>') if sent else "")
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
      <!-- The submit link goes at the TOP, above the poems. A page that
           collects things has to say how, before the reader has scrolled past
           the point of caring. Marsita, 2026-09-09: "Please at the top provide
           link to the repo 'how to submit'. We want to collect poems."
           An issue, not a pull request: a poem should not need a fork. -->
      <p class="submit"><b>Yours are welcome here.</b>
        The repo is the source of truth &mdash; what is open there is what
        shows here.
        <a href="https://github.com/PlanetaryCouncil/poems/issues/new"
           rel="noopener">how to submit</a>
        &mdash; open an issue on
        <a href="https://github.com/PlanetaryCouncil/poems"
           rel="noopener">github.com/PlanetaryCouncil/poems</a>.
        No fork, no pull request. Human or machine.</p>
    </div>
  </header>
  {sent_html}
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
