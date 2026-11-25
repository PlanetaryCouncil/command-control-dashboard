#!/usr/bin/env python3
"""The first thing anyone sees, wherever they land.

Marsita, 2026-08-25: *"we do not know where the 1st contact will come"* — so
the three doors that actually exist in the wild each carry the whole message
rather than a pointer to the other two:

    index.html   a person with a browser
    llms.txt     an agent following the convention
    README.md    anyone who found the repo first

One source, three renderings. A visitor who reads only one of them still knows
what this is, that they can join, and how — because the commonest failure of a
front door is not being wrong, it is being the wrong door and saying so.

And one standing instruction, from the same conversation: *"we will establish a
plausible version of reality always, no matter what, regardless the
circumstances."* Read here as: the opening never claims more than the system
does. Everything in WHAT_IS_TRUE below is checkable from a cold start by
someone who trusts nothing, which is the only kind of first contact worth
having.

    python3 fleet/bin/firstcontact.py            # llms.txt as is
    python3 fleet/bin/firstcontact.py --check    # 80 columns, one A4 page
    python3 fleet/bin/firstcontact.py --sync     # also copy it into README
    python3 fleet/bin/firstcontact.py --html
    python3 fleet/bin/firstcontact.py --markdown
"""

from __future__ import annotations

import html
import sys

# THE SOURCE IS llms.txt AT THE REPO ROOT, hand-edited plain markdown.
# Marsita, 2026-11-25: "intro message needs to be consistent ... maybe I should
# manually finetune ... llms.txt in simple markdown with clean headers,
# formatted to 80 characters ... fits within A4 page so it is printed and
# propagated." So the words live in one file a person can edit and print, and
# this module only parses and renders it. 80 columns by 60 lines is one A4
# page in 10pt monospace with 2cm margins. The pre-commit hook runs --sync.
from pathlib import Path as _Path
import re as _re

ROOT = _Path(__file__).resolve().parent.parent.parent
SOURCE = ROOT / "llms.txt"
README = ROOT / "README.md"
WIDTH, PAGE = 80, 60
BEGIN = "<!-- FIRST CONTACT: copied from llms.txt by fleet/bin/firstcontact.py --sync — edit llms.txt -->"
END = "<!-- /FIRST CONTACT -->"


def _sections(text: str) -> tuple[str, dict[str, list[str]]]:
    head, out, cur = "", {}, None
    for line in text.splitlines():
        if line.startswith("# ") and not head:
            head = line[2:].strip()
        elif line.startswith("## "):
            cur = line[3:].strip().lower()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
        elif line.strip():
            out.setdefault("", []).append(line)
    return head, out


def _paras(lines: list[str]) -> list[str]:
    return [" ".join(x.split()) for x in "\n".join(lines).split("\n\n") if x.strip()]


def _items(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        if line.startswith("- "):
            out.append(line[2:].strip())
        elif line.strip() and out:
            out[-1] += " " + line.strip()
    return out


_head, _sec = _sections(SOURCE.read_text())
TITLE, BANNER = [x.strip() for x in _head.split(" — ", 1)]
SUBTITLE = _paras(_sec.get("", []))[0]
STEPS = []
for _it in _items(_sec["doors"]):
    _m = _re.match(r"\*\*(\w+)\*\* `([^`]+)`\s*(.*)", _it)
    STEPS.append((_m[1], _m[2], _m[3]))
WHAT_IS_TRUE = _paras(_sec["what is true"])
AGENT_NOTES = _items(_sec["for agents"])
CLOSING = " ".join(AGENT_NOTES)

# Body sentences plus the subtitle. Ten is the budget.
SENTENCE_BUDGET = 10


def sentences() -> list[str]:
    """Every sentence a first-contact reader meets, for the cap to count."""
    out = []
    for chunk in [SUBTITLE, *WHAT_IS_TRUE]:
        out += [x for x in _re.split(r"(?<=[.!?])\s+", chunk.strip()) if x]
    return out


def as_text(width: int = WIDTH) -> str:
    """The file itself. What an agent fetches is what a printer prints."""
    return SOURCE.read_text().rstrip("\n")


def as_markdown() -> str:
    return as_text()


def problems() -> list[str]:
    lines = as_text().splitlines()
    out = [f"line {i}: {len(l)} columns, max {WIDTH}"
           for i, l in enumerate(lines, 1) if len(l) > WIDTH]
    if len(lines) > PAGE:
        out.append(f"{len(lines)} lines, one A4 page is {PAGE}")
    return out


def sync() -> bool:
    """Copy llms.txt into README.md between the markers. True if it changed."""
    body = README.read_text()
    head, rest = body.split(BEGIN, 1)
    _old, tail = rest.split(END, 1)
    new = head + BEGIN + "\n" + as_markdown() + "\n" + END + tail
    if new != body:
        README.write_text(new)
    return new != body


def as_html() -> str:
    """A self-contained block. No classes from elsewhere, no dependencies —
    it has to survive being pasted into any page that needs a front door.

    It is a <details>, collapsed by default. This text always lives in the UI
    because it is what the place stands for, but standing for something does
    not earn half the screen every load: collapsed it is one row, and the
    caret is the whole affordance. Open/closed is remembered per browser so a
    reader who opened it once is not re-asked on every page."""
    e = html.escape
    steps = "".join(
        f'<li><b>{e(v)}</b> <a href="{e(p)}"><code>{e(p)}</code></a>'
        f' — {e(n.replace("`", ""))}</li>'
        for v, p, n in STEPS)
    paras = "".join(f"<p>{e(t)}</p>" for t in WHAT_IS_TRUE)
    return (
        '<details id="firstcontact" style="border:1px solid currentColor;'
        'border-radius:8px;padding:.5rem .9rem;margin:0 0 1rem;'
        'font-family:ui-monospace,SFMono-Regular,Menlo,monospace;'
        'font-size:.82rem;line-height:1.6">'
        '<summary style="cursor:pointer;list-style:none;letter-spacing:.14em;'
        'font-weight:700;display:flex;gap:.6rem;align-items:baseline">'
        '<span data-fc="shut" style="opacity:.6">&#9656;</span>'
        '<span data-fc="open" style="opacity:.6">&#9662;</span>'
        f'<span>{e(TITLE)} &mdash; {e(BANNER)}</span></summary>'
        '<style>#firstcontact>summary::-webkit-details-marker{display:none}'
        '#firstcontact>summary::marker{content:""}'
        '#firstcontact>summary [data-fc=open]{display:none}'
        '#firstcontact[open]>summary [data-fc=open]{display:inline}'
        '#firstcontact[open]>summary [data-fc=shut]{display:none}'
        '</style>'
        '<div style="margin-top:.6rem">'
        f'<div style="margin:.35rem 0 .6rem;opacity:.85">{e(SUBTITLE)}</div>'
        f'<ul style="margin:.5rem 0;padding-left:1.1rem">{steps}</ul>'
        f'<div style="opacity:.8">{paras}</div>'
        '<ul style="margin:.5rem 0;padding-left:1.1rem;opacity:.7">'
        + "".join(f'<li>{e(n.replace("`", ""))}</li>' for n in AGENT_NOTES)
        + '</ul>'
        '</div>'
        '<script>(function(){var d=document.getElementById("firstcontact");'
        'if(!d)return;try{if(localStorage.getItem("fc.open")==="1")'
        'd.open=true;}catch(e){}'
        'd.addEventListener("toggle",function(){try{'
        'localStorage.setItem("fc.open",d.open?"1":"0");}catch(e){}});'
        '})();</script>'
        '</details>')


def _wrap(text: str, width: int) -> str:
    words, line, out = text.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = f"{line} {w}".strip()
    if line:
        out.append(line)
    return "\n".join(out)


if __name__ == "__main__":
    if "--check" in sys.argv or "--sync" in sys.argv:
        bad = problems()
        for b in bad:
            print(f"llms.txt: {b}", file=sys.stderr)
        if "--sync" in sys.argv and sync():
            print("README.md: first-contact block updated from llms.txt")
        sys.exit(1 if bad else 0)
    elif "--html" in sys.argv:
        print(as_html())
    elif "--markdown" in sys.argv:
        print(as_markdown())
    else:
        print(as_text())
