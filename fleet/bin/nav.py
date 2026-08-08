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
# The orrery (/orbit) is off the nav from 2026-08-05 — "looks amateur".
# The route still resolves; it is a sketch, not a room, until the drawing
# is worth the idea.
PAGES = [
    ("/", "fleet"),
    ("/intro", "intro"),
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
CONTROL = {"/chat", "/terminal"}


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
