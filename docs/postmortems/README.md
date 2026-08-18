# Post-mortems

What broke, what we learned, and which numbers are still guesses.

One file per incident, named `YYYY-MM-DD-short-name.md`, dated by when the
thing broke rather than when we noticed — the gap between those two is usually
the real finding.

These are written for the person who hits the same wall in a year, which may
well be one of us. So: quote the raw log rather than paraphrasing it, say
plainly what was ruled out so nobody re-investigates it, and never dress a
guess up as a root cause. A post-mortem that claims more than it proved is
worse than none, because the next person believes it.

| Date | Incident | Lesson in one line |
|---|---|---|
| 2026-08-08 | [The NUC froze for nine days](2026-08-08-nuc-freeze.md) | A frozen machine still draws power, so restore-on-AC-loss cannot save it. |
