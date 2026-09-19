#!/usr/bin/env python3
"""One navigation bar, same place on every page.

It used to be built per-page: header on some, footer on others, a different
order each time. Moving between pages meant hunting for the links. Defined once
here so it cannot drift again.

Always top-right in the header. Page-specific *actions* (float on top, kill)
stay where they belong on their own page — this is navigation only.
"""

# Canonical order: overview first, then the detail views, then the controls.
# Three surfaces, because the dashboard now shows everything the other pages
# did. The retired routes still resolve — /board, /agents, /live, /procs — they
# are simply not worth a permanent slot in front of you.
# Two. The terminal is a drawer on the dashboard, not a destination — having
# both a CONSOLE button and a TERMINAL tab was the same word twice.
# The orrery (/orbit) came off the nav on 2026-08-05 — "looks amateur" — and
# was deleted on 2026-08-06. Orbital distance looked like it meant something
# and was derived from charge alone, so two projects sitting near each other
# said nothing about each other. A replacement that lays projects out by how
# they actually relate is parked in the freezer-of-ideas repo.
PAGES = [
    ("/", "fleet"),
    ("/hi", "send a message"),
    ("https://planetarycouncil.github.io/selfie-gallery/", "send a selfie"),
    ("/chat", "chat"),
]

CSS = """
/* Cross-document view transitions: the pages are still separate documents and
   still reload, but Chrome cross-fades between them instead of flashing white.
   Pure CSS — no client-side router, so nothing can double-bind a listener or
   drop a live event stream. */
@view-transition { navigation: auto; }
@media (prefers-reduced-motion: reduce) {
  @view-transition { navigation: none; }
}
::view-transition-old(root), ::view-transition-new(root) {
  animation-duration: .18s;
}

.fleetnav{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap;align-items:center;}
.fleetnav a{font-family:var(--mono);font-size:10.5px;padding:5px 10px;
  border-radius:6px;border:1px solid var(--border);background:var(--raised);
  color:var(--ink);text-decoration:none;white-space:nowrap;}
.fleetnav a:hover{border-color:var(--muted);}
.fleetnav a:focus-visible{outline:2px solid var(--ink);outline-offset:2px;}
.fleetnav a[aria-current="page"]{border-color:var(--muted);color:var(--muted);
  background:transparent;cursor:default;}

/* Scrollbars. Chrome's default is a pale slab sized for a document, and on a
   dark panel it reads as a UI element in its own right -- brighter than the
   text it sits beside. Thin, themed, transparent track: it marks position and
   stops competing. Firefox gets the same through scrollbar-color. */
*{scrollbar-width:thin;scrollbar-color:var(--border) transparent;}
::-webkit-scrollbar{width:10px;height:10px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-corner{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:6px;
  border:2px solid transparent;background-clip:content-box;}
::-webkit-scrollbar-thumb:hover{background:var(--muted);background-clip:content-box;}
"""


# Chrome loads these pages in the background and runs their scripts, so a click
# activates an already-live page instead of starting one.
#
# `moderate` fires on hover / pointer-down rather than immediately. Eager
# preloading of all five would hold four idle server-sent-event connections open
# permanently for pages you may never open; hover precedes click by a few hundred
# milliseconds, which is enough to feel instant without that waste.
SPECULATION = """<script type="speculationrules">
{"prerender":[{"where":{"href_matches":"/*"},"eagerness":"moderate"}]}
</script>"""


# Doors that answer 404 through the funnel (CONTROL_PATHS in fleet.py). A
# remote render must not advertise them: Marsita clicked /chat from the
# public URL on 2026-08-04 and met the guard — "how on earth we left a dead
# URL?" The guard is right; the signpost was wrong.
# /terminal left this list on 2026-09-17 with the button: the route still
# 301s for old bookmarks, but PAGES no longer offers it, so there is
# nothing here to hide from a remote render.
CONTROL = {"/chat"}


def board_name() -> str:
    """Which dashboard this is. Tabs need it; the h1 already had it.

    FLEET_NAME env, else data/board-name.txt (per box, not in git), else
    hostname. Uppercase so GAIA and NUC read as names, not files.
    """
    import os
    import socket
    from pathlib import Path

    def from_file():
        try:
            return (Path(__file__).resolve().parent.parent / "data"
                    / "board-name.txt").read_text().strip()
        except OSError:
            return ""

    raw = (os.environ.get("FLEET_NAME") or from_file()
           or socket.gethostname().split(".")[0] or "FLEET")
    raw = " ".join(raw.split())[:40]
    return (raw or "FLEET").upper()


def title(*suffix: str, remote: bool | None = None) -> str:
    """Escaped <title> text. Name first, so two hosts never share a tab.

    Pass `remote` and the tab also says which door it came through. Marsita
    keeps the laptop board and the public URL open side by side; both tabs
    read "GAIA" and there is no way to tell which one is which without
    clicking it (2026-09-02). The name alone separates the machines; this
    separates the doors.
    """
    import html
    # The door is in brackets: "GAIA (local)" / "GAIA (public)". On
    # 2026-09-18 "the brackets no longer in the <title>" was read as a request
    # to drop them; it was a report that they had gone missing. Marsita,
    # 2026-09-19: "lost (public) and (local) info tags in the <head> <title>".
    door = "" if remote is None else ("public" if remote else "local")
    parts = [board_name(), *(s for s in suffix if s)]
    text = " · ".join(parts) + (f" ({door})" if door else "")
    return html.escape(text, quote=True)


def html(current: str = "", remote: bool = False) -> str:
    """Nav markup. `current` is the path of the page rendering it."""
    out = []
    for href, label in PAGES:
        if remote and href in CONTROL:
            continue
        if href.startswith("http"):
            out.append(f'<a href="{href}" target="_blank" rel="noopener">{label}</a>')
        elif href == current:
            out.append(f'<a href="{href}" aria-current="page">{label}</a>')
        else:
            out.append(f'<a href="{href}">{label}</a>')
    return ('<nav class="fleetnav">' + "".join(out) + "</nav>" + SPECULATION)
