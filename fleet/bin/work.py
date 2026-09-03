#!/usr/bin/env python3
"""What is being worked on right now, read straight out of git.

Every other pane on this board describes the *fleet* — what ran, what is
stale, what is burning CPU. None of them answers the question you actually ask
when you sit down: what am I in the middle of? The board could show ten commits
landed today and not one pane knew it.

So this reads the repository itself. Not a status file somebody has to
remember to update — a status file is a claim, and a claim goes stale the
moment the work moves. git already knows, and git cannot lie about it.

Public and local see different things. Landed commits and the file history are
already on GitHub, so a stranger gets those. Uncommitted work is not published
yet and does not become published by being on a board, so the dirty tree is
local-only — the same split the rest of the server uses: reads are public,
the unfinished stuff stays home.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# A day's work, not an hour's. Short enough that "today" means today, long
# enough that a late night still counts as the same session.
HOT_DAYS = 7
HOT_TOP = 6
RECENT_COMMITS = 8


def _git_raw(*args: str, cwd: Path | None = None) -> str:
    """Run git and return stdout untouched, or "" if anything goes wrong.

    A dashboard pane must never take the page down because a directory is not
    a repo, or git is missing, or the index is locked by a commit happening in
    another window. Every failure here means "nothing to report", never a 500.
    """
    try:
        r = subprocess.run(("git", *args), cwd=str(cwd or REPO),
                           capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout if r.returncode == 0 else ""


def _git(*args: str, cwd: Path | None = None) -> str:
    """`_git_raw` with the surrounding whitespace trimmed.

    Convenient for everything except porcelain status, where column 1 is a
    SPACE for an unstaged change — " M path" — and stripping it shifts every
    field left by one. That bug shipped a pane reading "leet/bin/fleet.py".
    Anything parsed by column offset must use `_git_raw`.
    """
    return _git_raw(*args, cwd=cwd).strip()


def _branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD") or "?"


def _ahead_behind() -> tuple[int, int]:
    """Commits ahead of and behind the upstream, or (0, 0) with no upstream.

    "3 unpushed" is the sentence that makes someone go push. A branch with no
    upstream is not behind by infinity, it just has nowhere to be compared to.
    """
    out = _git("rev-list", "--left-right", "--count", "@{upstream}...HEAD")
    if not out:
        return 0, 0
    try:
        behind, ahead = (int(x) for x in out.split())
    except ValueError:
        return 0, 0
    return ahead, behind


def _dirty() -> list[dict]:
    """Uncommitted paths with their porcelain status code.

    -z because filenames contain spaces and one of them will eventually
    contain a newline; splitting porcelain output on "\\n" works right up until
    the day it silently drops a file.
    """
    out = _git_raw("status", "--porcelain=1", "-z")
    if not out:
        return []
    items = []
    for entry in out.split("\0"):
        if len(entry) > 3:
            items.append({"code": entry[:2].strip() or "?", "path": entry[3:]})
    return items


def _commits_since_midnight() -> list[dict]:
    """Today's landed work, newest first.

    Local midnight, not UTC: the question is "what did I do today", and today
    is the day the person asking is living in.
    """
    midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    out = _git("log", "--since", midnight.isoformat(),
               "--format=%h\x1f%s\x1f%cI", f"-{RECENT_COMMITS * 3}")
    rows = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            rows.append({"sha": parts[0], "subject": parts[1], "at": parts[2]})
    return rows


def _recent_commits() -> list[dict]:
    """The last few commits whatever their date.

    A quiet day would otherwise render an empty pane, which reads as "the
    board is broken" rather than "you have not committed yet". There is always
    a last commit; show it.
    """
    out = _git("log", f"-{RECENT_COMMITS}", "--format=%h\x1f%s\x1f%cI")
    rows = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) == 3:
            rows.append({"sha": parts[0], "subject": parts[1], "at": parts[2]})
    return rows


def _hot_files() -> list[dict]:
    """Files touched most often in the last week — where the work actually is.

    Commit subjects say what you meant to do. The file histogram says what you
    kept going back to, which is usually the more honest answer.
    """
    out = _git("log", f"--since={HOT_DAYS}.days", "--name-only",
               "--format=", "--no-merges")
    counts: dict[str, int] = {}
    for line in out.splitlines():
        p = line.strip()
        if p:
            counts[p] = counts.get(p, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"path": p, "touches": n} for p, n in ranked[:HOT_TOP]]


# --------------------------------------------------------------- the log page
# Same palette as /poems so the two read as one site. Wider than the poem page
# because a commit body is prose in paragraphs, not a couplet.
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
.wrap{max-width:46rem;margin:0 auto;padding:1.4rem 1.2rem 4rem}
header{display:flex;flex-wrap:wrap;gap:.8rem;align-items:flex-start;
  margin-bottom:1.4rem}
h1{margin:0;font-size:1.6rem;font-weight:600}
.lede{color:var(--ink-2);margin:.4rem 0 0;max-width:52ch}
a{color:var(--info)}
/* The day heading is the spine of the page. Sticky, because scrolling a
   fortnight of commits without one leaves you with no idea when you are. */
.day{position:sticky;top:0;background:var(--ground);z-index:1;
  display:flex;align-items:baseline;gap:.6rem;
  margin:2rem 0 .2rem;padding:.5rem 0 .35rem;
  border-bottom:1px solid var(--border);
  font-family:var(--mono);font-size:.82rem;font-weight:600;
  letter-spacing:.08em;color:var(--ink-2)}
.day .cnt{font-weight:400;color:var(--muted);font-size:.72rem}
.c{border-bottom:1px solid var(--border);padding:.9rem 0}
.c:last-child{border-bottom:0}
/* The subject is the headline. These commit subjects are sentences, so they
   are set as prose rather than as monospace log lines. */
.c h3{margin:0;font-size:1.02rem;font-weight:600;line-height:1.35}
.c p{margin:.5rem 0 0;color:var(--ink-2);font-size:.92rem}
.c .meta{margin:.3rem 0 0;font-family:var(--mono);font-size:.72rem;
  color:var(--muted);letter-spacing:.04em}
.sha{font-family:var(--mono)}
details{margin:.6rem 0 0}
summary{cursor:pointer;font-family:var(--mono);font-size:.72rem;
  color:var(--muted)}
details ul{margin:.4rem 0 0;padding-left:1.1rem}
details li{font-family:var(--mono);font-size:.74rem;color:var(--ink-2)}
.empty{color:var(--ink-2)}
"""



PAGE_N = 120

# github.com/x/y from any of the forms git stores a remote in. Used only to
# build a link; a repo with no GitHub remote renders the same page with the
# shas as plain text rather than dropping the page.
_GH = re.compile(r"github\.com[:/]+([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")


def origin_web() -> str:
    """The https GitHub URL for this checkout, or "" if there is none.

    Not just `origin`: this repo's remote is called `GitHub_priv`, and a
    function that only knows the conventional name silently renders every sha
    as dead plain text. Try origin first, then any remote that looks like
    GitHub.
    """
    for name in ["origin"] + _git("remote").split():
        m = _GH.search(_git("remote", "get-url", name))
        if m:
            return f"https://github.com/{m.group(1)}/{m.group(2)}"
    return ""


def log(n: int = PAGE_N) -> list[dict]:
    """The last `n` commits with subject, body and the files each touched.

    The body matters here in a way it does not in most repos: these commits
    explain *why*, and a subject line alone throws that away. The page is for
    reading, not for `git log --oneline` in a browser.
    """
    sep, fsep = "\x1e", "\x1f"
    out = _git("log", f"-{n}", "--no-merges",
               f"--format={sep}%h{fsep}%cI{fsep}%an{fsep}%s{fsep}%b{fsep}",
               "--name-only")
    rows = []
    for chunk in out.split(sep):
        if not chunk.strip():
            continue
        # Exactly five separators were emitted, so the file list is whatever
        # follows the fifth. Splitting with a cap keeps a body that somehow
        # contains the separator from stealing the file list.
        parts = chunk.split(fsep, 4)
        if len(parts) < 5:
            continue
        sha, at, author, subject = parts[0], parts[1], parts[2], parts[3]
        tail = parts[4].split(fsep, 1)
        body_text = tail[0]
        files = [f.strip() for f in tail[1].split("\n") if f.strip()] if len(tail) > 1 else []
        rows.append({"sha": sha, "at": at, "author": author,
                     "subject": subject, "body": _paragraphs(body_text),
                     "files": files})
    return rows


# Trailers are addressing and provenance, not reasoning. They belong in the
# commit and not on a page someone is reading to find out what changed.
#
# Two conditions, because one is not enough. The key must be capitalised
# (Co-Authored-By, Claude-Session) AND the line must be in the final block of
# the message, where trailers live by convention. Matching on the colon alone
# deleted "knows: branch, unpushed count, ..." from the middle of a sentence
# and the page rendered "git already files you kept going back to this week" —
# a sentence that was never written, presented as if it had been.
_TRAILER = re.compile(r"^[A-Z][A-Za-z]*(?:-[A-Za-z]+)*:\s")


def _paragraphs(body: str) -> list[str]:
    """Blank-line-separated paragraphs, rewrapped, trailers dropped.

    git hard-wraps a commit body at 72 columns. Rendering those as separate
    lines in a browser gives a ragged column harder to read than the terminal
    it came from, so each paragraph is rejoined and the browser wraps it.
    """
    blocks, cur = [], []
    for line in body.split("\n"):
        t = line.strip()
        if t:
            cur.append(t)
        elif cur:
            blocks.append(cur)
            cur = []
    if cur:
        blocks.append(cur)
    if not blocks:
        return []

    # Only the last block may be trailers, only if every line in it is one,
    # and never if it is the only block. A body that is a single paragraph
    # opening "Note: ..." is the whole reasoning of the commit, and deleting
    # it leaves the page silent about a change that was explained. Rendering
    # a stray trailer is a much cheaper mistake than that.
    if len(blocks) > 1 and all(_TRAILER.match(x) for x in blocks[-1]):
        blocks = blocks[:-1]
    return [" ".join(b) for b in blocks]


def _day(iso: str) -> str:
    return iso[:10] if iso else ""


def page(nav_html: str = "", nav_css: str = "") -> str:
    """The commits page.

    Marsita: "I'm not watching commits though... maybe if they are here I'll
    see them more." So this is not `git log` in a browser — it is a changelog.
    Grouped by day with a count, subject as the headline, the reasoning
    underneath, and the files folded away behind a disclosure so the prose is
    what you see first.
    """
    import html as _h
    import nav

    rows = log()
    base = origin_web()
    if rows:
        out, day = [], None
        for c in rows:
            d = _day(c["at"])
            if d != day:
                day = d
                same = sum(1 for x in rows if _day(x["at"]) == d)
                out.append(f'<h2 class="day">{_h.escape(d)}'
                           f'<span class="cnt">{same} commit'
                           f'{"" if same == 1 else "s"}</span></h2>')
            sha = _h.escape(c["sha"])
            link = (f'<a class="sha" href="{base}/commit/{sha}">{sha}</a>'
                    if base else f'<span class="sha">{sha}</span>')
            body = "".join(f"<p>{_h.escape(b)}</p>" for b in c["body"])
            files = ""
            if c["files"]:
                items = "".join(f"<li>{_h.escape(f)}</li>" for f in c["files"])
                files = (f'<details><summary>{len(c["files"])} file'
                         f'{"" if len(c["files"]) == 1 else "s"}</summary>'
                         f'<ul>{items}</ul></details>')
            out.append(
                f'<article class="c">'
                f'<h3>{_h.escape(c["subject"])}</h3>'
                f'<p class="meta">{link} · {_h.escape(c["at"][11:16])}'
                f' · {_h.escape(c["author"])}</p>'
                f'{body}{files}</article>')
        inner = "\n".join(out)
    else:
        inner = '<p class="empty">No commits found. This is not a git checkout.</p>'

    repo_link = (f' Source: <a href="{base}">{_h.escape(base)}</a>.'
                 if base else "")
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nav.title("commits")}</title>
<!-- agents: /llms.txt -->
<link rel="alternate" type="application/json" href="/api/work" title="work.json">
<style>{nav_css}{CSS}</style>
</head><body>
<div class="wrap">
  <header>
    {nav_html}
    <div>
      <h1>commits</h1>
      <p class="lede">What actually changed, newest first &mdash; the reasoning
        as written, not just the subject line.{repo_link}
        Live state: <a href="/api/work">/api/work</a></p>
    </div>
  </header>
  {inner}
</div>
</body></html>"""


def snapshot(local: bool = False) -> dict:
    """The whole picture. `local` adds the uncommitted tree.

    Ordered the way it gets read: what is unfinished, then what landed, then
    where the work has been sitting.
    """
    today = _commits_since_midnight()
    ahead, behind = _ahead_behind()
    out = {
        "at": datetime.now(timezone.utc).isoformat(),
        "branch": _branch(),
        "ahead": ahead,
        "behind": behind,
        "today": today,
        "today_count": len(today),
        "recent": _recent_commits(),
        "hot": _hot_files(),
        "local": local,
    }
    if local:
        dirty = _dirty()
        out["dirty"] = dirty
        out["dirty_count"] = len(dirty)
    else:
        # Absent, not zero. A public viewer being told "0 uncommitted files"
        # would be a claim about a tree they were not shown.
        out["dirty"] = None
        out["dirty_count"] = None
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(snapshot(local=True), indent=2))
