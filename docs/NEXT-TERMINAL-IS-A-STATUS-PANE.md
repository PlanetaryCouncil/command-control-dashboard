# Next: the board terminal stops pretending to be a terminal

**Decided 2026-09-03 by Marsita. Not yet built.**

> "This terminal in the browser is shite. I don't like it. It's really
> non-functional. [...] It won't be very interactive. It will just give me
> when something is finished, because that's actually the most important
> thing. [...] I don't need to know what's going on. Just show me the
> progress. [...] I have a terminal on my computer, so it's maybe just
> perfect. Best of both worlds."

## The mistake being corrected

Weeks went into making a real xterm in the browser work: pty, websocket,
resize, image paste, scrollback replay, transcript resume, and finally tmux so
it survives a restart. Every one of those was a real fix for a real bug, and
the whole thing was still the wrong product.

Typing into a browser terminal is worse than typing into a real one and always
will be — the latency, the key handling, the output racing your cursor. The
laptop already has a terminal that does this perfectly. The browser was
competing with it and losing.

What the browser is genuinely better at is being **glanceable from across the
room**. So it should do that instead.

## What to build

A **non-interactive status pane**. It answers one question — *is it done yet?*

1. **State**: working / finished / waiting for you. Large, readable at a
   glance, no scrollback.
2. **Elapsed timer**, counting up while a turn is running.
3. **Effort estimate** shown when a turn starts, from history of comparable
   turns. It is a guess and should be labelled as one.
4. **Overrun notice** when a turn passes ~2× its estimate — a second, distinct
   message rather than a silently growing number. That is the moment worth
   interrupting for.
5. **A large compose box**, send-only. Write at leisure, press send, the text
   goes to the session. No echo, no cursor race — the composer already built
   for this is the right shape; it just becomes the whole interface.

## What to remove

- xterm.js and the live output stream in the board pane
- image paste (the real terminal handles files better anyway) — **check with
  Marsita first**, this was explicitly asked for on 2026-09-02 and may still
  be wanted on the send path
- scrollback replay

## What to keep

- **tmux ownership** (`terminal.py:session_argv`). It is what makes
  `tmux attach -t board` on the laptop and the browser pane the *same*
  session. That is the "best of both worlds" — the pane watches, the real
  terminal drives.
- Local-only gating. `/ws/terminal` stays in `CONTROL_PATHS`.
- `--continue`, so a fresh session resumes the conversation.

## Where the numbers come from

`tmux` can be polled without attaching, which is how a status pane stays
cheap:

```
tmux display -p -t board '#{pane_current_command} #{?pane_dead,dead,live}'
tmux capture-pane -p -t board | tail -3
```

The distinction between *working* and *waiting for you* is the hard part and
should be got right rather than guessed: Claude Code's prompt line is
recognisable in the captured pane, and that is more reliable than watching for
output to stop.

## Why this is written down rather than done

Marsita asked for it at the end of a long session, about to compact context. A
design decided in one sentence and built from a summary is how the last three
UI reversals happened.
