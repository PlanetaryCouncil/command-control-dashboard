#!/usr/bin/env python3
"""100-pixel meters — read a value by its length, not by its digits.

Every parameter in the interface renders as a fixed 100px track with a
proportional fill. Fixed width is the whole point: bars of the same length are
directly comparable down a column, which is what makes a page scannable at a
glance instead of readable digit by digit.

The number is not thrown away — it stays in the `title` and in screen-reader
text. Hover when you need the exact value; the rest of the time, don't.

Scales:
  percent   0-100, natural
  ratio     part/whole, e.g. 3 hops of 3
  relative  no natural ceiling (durations, counts) — scaled against a reference,
            because a bar with an invented maximum lies about magnitude
"""

WIDTH = 100

CSS = """
.meter{display:inline-flex;align-items:center;gap:7px;vertical-align:middle;}
.meter .track{width:100px;height:8px;border-radius:4px;background:var(--track,
  color-mix(in srgb,var(--muted) 24%,transparent));overflow:hidden;flex:none;}
.meter .fill{height:100%;border-radius:4px;background:var(--meter,var(--muted));
  transition:width .3s ease;
  /* A non-zero value must never render as nothing: 0.4% of 100px is half a
     pixel, indistinguishable from missing data. */
  min-width:3px;}
.meter .fill[data-zero="1"]{min-width:0;}
.meter .cap{font-family:var(--mono);font-size:9.5px;color:var(--muted);
  letter-spacing:.06em;white-space:nowrap;}
.meter.good{--meter:var(--good);} .meter.warning{--meter:var(--warning);}
.meter.critical{--meter:var(--critical);}
/* `accent` inherits an agent's colour where one is in scope; `info` is the
   neutral for pages with no agent context. Falling back to --muted made the
   fill the same colour as the track — an invisible bar. */
.meter.accent{--meter:var(--agent,var(--info-meter,#3987e5));}
.meter.info{--meter:var(--info-meter,#3987e5);}
/* Over-range: the value exceeded its reference, so the bar is pinned full and
   marked rather than silently clipped. */
.meter.over .fill{background:repeating-linear-gradient(135deg,
  var(--critical) 0 4px, transparent 4px 8px);}
.meter .sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);}
"""


def _tone(pct, invert=False):
    """Status colour by magnitude. Inverted where high is good (tests passing)."""
    if invert:
        return "good" if pct >= 99 else "warning" if pct >= 60 else "critical"
    return "critical" if pct >= 90 else "warning" if pct >= 60 else "good"


def bar(value, maximum, *, label="", tone=None, invert=False, suffix=""):
    """One meter. `label` is the caption shown beside it (keep it short)."""
    try:
        v = float(value)
        m = float(maximum) or 1.0
    except (TypeError, ValueError):
        v, m = 0.0, 1.0
    pct = max(0.0, v / m * 100.0)
    over = pct > 100.0
    width = min(100.0, pct)

    cls = tone if tone else _tone(pct, invert)
    if over:
        cls += " over"

    exact = f"{value}{suffix}" + (f" of {maximum}{suffix}" if maximum not in (100, "100") else "")
    cap = f'<span class="cap">{label}</span>' if label else ""
    zero = ' data-zero="1"' if v == 0 else ""
    return (f'<span class="meter {cls}" title="{exact}">'
            f'<span class="track"><span class="fill"{zero} style="width:{width:.1f}%"></span></span>'
            f'{cap}<span class="sr">{exact}</span></span>')


def ratio(part, whole, *, label="", invert=True):
    """Part of a whole — 3 hops of 3, 91 tests of 91."""
    return bar(part, whole or 1, label=label or f"{part}/{whole}", invert=invert)


def percent(value, *, label="", invert=False):
    return bar(value, 100, label=label, invert=invert, suffix="%")
