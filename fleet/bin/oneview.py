#!/usr/bin/env python3
"""One screen: agents, stream, processes, and an optional terminal.

Built for a 27-inch 1920x1080 panel at about 82 pixels per inch — low density,
big pixels, no retina. So type does not shrink below ~10px (below that a glyph
stroke is one pixel and antialiasing muddies it); density comes from meters
instead, which carry a value in zero characters.

One document, one event-stream connection, one polling timer. The five separate
pages opened five of each. Switching panels here is a CSS class change, which is
why it is instant in a way navigation never is.

The terminal is deliberately closed on load and its socket is not opened until
you ask for it. Marsita works from the real command line — a JavaScript terminal
repaints slower than a native one on this hardware — so this is the option, not
the default.
"""

CSS = """
:root{
  --ground:#0d0d0d; --surface:#161615; --raised:#1f1f1e;
  --border:#2b2b29; --ink:#f0f2f4; --ink-2:#b9bec5; --muted:#7d838b;
  --good:#0ca30c; --warning:#fab219; --critical:#d03b3b;
  --info:#3987e5;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
  --gap:4px;
}
:root[data-theme="light"]{
  --ground:#F1F3F5; --surface:#FFFFFF; --raised:#E9ECEF;
  --border:#D6DAE0; --ink:#14171B; --ink-2:#414B58; --muted:#5C6674;
}
*{box-sizing:border-box;}
html,body{height:100%;}
body{margin:0;background:var(--ground);color:var(--ink);
  font-family:var(--sans);font-size:11.5px;line-height:1.45;
  -webkit-font-smoothing:antialiased;overflow:hidden;
  display:flex;flex-direction:column;}

/* ---------- top bar ---------- */
#bar{flex:none;display:flex;align-items:center;gap:11px;height:26px;
  padding:0 8px;background:var(--surface);border-bottom:1px solid var(--border);}
#bar h1{font-family:var(--mono);font-size:11.5px;font-weight:600;margin:0;
  letter-spacing:.04em;}
#bar .grp{display:flex;align-items:center;gap:6px;font-family:var(--mono);
  font-size:9.5px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase;}
#bar .sp{margin-left:auto;display:flex;align-items:center;gap:8px;flex:none;}
#bar button,#bar a{font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;
  text-transform:uppercase;padding:4px 9px;border-radius:5px;cursor:pointer;
  border:1px solid var(--border);background:var(--raised);color:var(--ink-2);
  text-decoration:none;}
#bar button:hover,#bar a:hover{border-color:var(--muted);color:var(--ink);}
#bar button[aria-pressed="true"]{border-color:var(--info);color:var(--info);}
#clock{font-family:var(--mono);font-size:10px;color:var(--muted);
  font-variant-numeric:tabular-nums;
  /* Fixed width and zero-padded 24h: a right-anchored group shifts every time
     a child changes width, and a ticking clock changes width constantly. */
  width:58px;text-align:right;flex:none;}
#pulse{width:6px;height:6px;border-radius:50%;background:var(--good);}
#pulse.stale{background:var(--warning);}

/* ---------- alarm ---------- */
#alarm{display:none;flex:none;align-items:center;gap:9px;padding:7px 12px;
  background:var(--critical);color:#fff;font-size:11.5px;}
#alarm.on{display:flex;}
#alarm b{font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;
  text-transform:uppercase;}
@media (prefers-reduced-motion:no-preference){
  #alarm.on{animation:puls 2s ease-in-out infinite;}
  @keyframes puls{0%,100%{opacity:1}50%{opacity:.85}}
}

/* ---------- the grid ---------- */
/* Draggable dividers. Widths live in a custom property so a drag is one style
   write, and they persist — a layout you have to redo on every reload is not a
   layout. Sized for a 1920 panel; the middle column absorbs the remainder so
   adding a fourth pane later needs no arithmetic here. */
#grid{flex:1;min-height:0;display:grid;gap:0;padding:var(--gap);
  grid-template-columns:var(--wL,290px) 6px 1fr 6px var(--wR,520px);
  grid-template-rows:1fr;}
/* Invisible until reached for. The panes already have borders, so drawing a bar
   between them made a double line for a control that is only touched
   occasionally. The hit area stays full width; only the paint is conditional. */
.grip{cursor:col-resize;position:relative;}
.grip::after{content:"";position:absolute;inset:0 1px;border-radius:2px;
  background:transparent;transition:background .12s;}
.grip:hover::after,.grip[data-drag="1"]::after{background:var(--info);}
/* Same control rotated. Two pixels of layout, ten pixels of target: the
   ::before spills above and below the element and is hit-tested as part of it,
   so the divider is easy to grab without spending a row of the column on it.
   Vertical space is the scarce one here — a 6px divider cost more than the
   line of text it displaced. */
.griph{cursor:row-resize;position:relative;flex:none;height:2px;}
.griph::before{content:"";position:absolute;left:0;right:0;top:-4px;bottom:-4px;}
.griph::after{content:"";position:absolute;inset:0;border-radius:1px;
  background:transparent;transition:background .12s;}
.griph:hover::after,.griph[data-drag="1"]::after{background:var(--info);}
.col{padding:0;}
.col{display:flex;flex-direction:column;gap:var(--gap);min-height:0;min-width:0;}
.pane{background:var(--surface);border:1px solid var(--border);border-radius:4px;
  display:flex;flex-direction:column;min-height:0;overflow:hidden;position:relative;}

/* Loading state. The stream arrives seeded into the page, but agents and
   processes are both empty until poll() returns — on reload that gap reads as
   "nothing to report" when it means "not asked yet". Same ambiguity the council
   found in the workers: a silent one looked identical to a healthy one. The
   error state is deliberately distinct for the same reason — a fetch that threw
   must never resolve to a clean empty pane. */
.load{position:absolute;inset:0;z-index:2;background:var(--surface);
  display:none;align-items:center;justify-content:center;gap:7px;
  font-family:var(--mono);font-size:10px;color:var(--muted);}
.pane[data-state="loading"] .load,.pane[data-state="error"] .load{display:flex;}
.load i{width:13px;height:13px;border-radius:50%;flex:none;
  border:1.5px solid var(--border);border-top-color:var(--info);
  animation:spin .7s linear infinite;}
.load .msg::after{content:"loading";}

/* Is the machine working hard or chilling? Nothing showed this until load
   reached 20 on four cores and every surface blamed the agents instead. */
#machine{font-variant-numeric:tabular-nums;}
#machine[data-state="idle"]{color:var(--muted);}
#machine[data-state="working"]{color:var(--good);}
#machine[data-state="busy"]{color:var(--warning);}
#machine[data-state="saturated"]{color:var(--critical);font-weight:600;}
.pane[data-state="error"] .load i{animation:none;border:1.5px solid var(--critical);
  border-radius:2px;}
.pane[data-state="error"] .load{color:var(--critical);}
.pane[data-state="error"] .load .msg::after{content:"unreachable — retrying";}
@keyframes spin{to{transform:rotate(360deg);}}
/* A spinner is decoration; a stalled pane is information. Without motion the
   ring alone reads as an empty circle, so the word carries it. */
@media (prefers-reduced-motion:reduce){
  .load i{animation:none;border-top-color:var(--info);opacity:.7;}
}
.pane>h2{flex:none;margin:0;padding:3px 7px;font-family:var(--mono);font-size:8.5px;
  letter-spacing:.13em;text-transform:uppercase;color:var(--muted);font-weight:600;
  border-bottom:1px solid var(--border);display:flex;align-items:center;gap:7px;}
.pane>h2 .n{margin-left:auto;color:var(--ink-2);}
.filters{margin-left:auto;display:flex;gap:3px;}
.filters button{font-family:var(--mono);font-size:8.5px;letter-spacing:.08em;
  text-transform:uppercase;padding:2px 6px;border-radius:3px;cursor:pointer;
  border:1px solid var(--border);background:var(--raised);color:var(--muted);}
.filters button:hover{color:var(--ink);}
.filters button[aria-pressed="true"]{border-color:var(--info);color:var(--info);}
.filters button.alt{color:var(--muted);border-style:dashed;}
/* Zero matches: dimmed and unclickable, so you know before you click. */
.filters button[data-empty="1"]{opacity:.35;cursor:default;}
.filters button[data-empty="1"][aria-pressed="true"]{border-color:var(--border);
  color:var(--muted);}
.filters .cnt{margin-left:4px;opacity:.7;font-variant-numeric:tabular-nums;}
#empty{display:none;flex-direction:column;align-items:center;justify-content:center;
  gap:6px;height:100%;color:var(--muted);font-family:var(--mono);}
#empty.on{display:flex;}
#empty .big{font-size:15px;letter-spacing:.14em;text-transform:uppercase;color:var(--warning);}
#empty .sub{font-size:10.5px;}
.ev[hidden]{display:none;}
.pane .body{flex:1;min-height:0;overflow-y:auto;}
/* vendor credit: who can still be asked, and who is only pretending.
   The pulse already knew all of this; it was buried in a JSON string
   inside one worker's detail field, so a dry vendor looked identical
   to a rich one right up until a turn died on payment. */
#credit table{width:100%;border-collapse:collapse;font:11px/1.5 var(--mono);}
#credit td{padding:3px 6px;border-bottom:1px solid var(--border);vertical-align:middle;}
#credit tr:last-child td{border-bottom:0;}
#credit .who{color:var(--ink);}
#credit .vend{color:var(--muted);}
#credit .st{text-align:right;white-space:nowrap;font-weight:600;}
#credit .st.rich{color:var(--good);}
#credit .st.dry{color:var(--critical);}
#credit .st.out{color:var(--warning);}
#credit .st.hazy{color:var(--muted);}
#credit .st.idle{color:var(--muted);font-weight:400;}
#credit .why{color:var(--muted);font-size:10px;}
#credit .asof{padding:4px 6px;color:var(--muted);font-size:10px;}

/* ---------- agents ---------- */
.agent{border-bottom:1px solid var(--border);padding:3px 7px;}
.agent:last-child{border-bottom:none;}
.agent .top{display:flex;align-items:center;gap:6px;}
.agent .nm{font-family:var(--mono);font-size:10.5px;font-weight:600;
  color:var(--agent,var(--ink));overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.agent .st{margin-left:auto;font-family:var(--mono);font-size:8.5px;
  letter-spacing:.09em;text-transform:uppercase;padding:1px 5px;border-radius:3px;
  background:var(--raised);color:var(--muted);flex:none;}
.agent .st.pass{color:var(--good);} .agent .st.fail,.agent .st.alert{color:var(--critical);}
.agent .st.warn,.agent .st.skip{color:var(--warning);}
.agent .last{font-size:10px;color:var(--muted);margin-top:1px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
/* Inside the merged pane the card is a heading over its own process rows, so
   the left edge carries the agent's colour and the rows indent under it. */
#procs .agrp td{padding:0;border-bottom:0;background:var(--raised);}
#procs .agrp .agent{border-bottom:0;border-left:2px solid var(--agent,transparent);
  padding:3px 7px;}
#procs .cgrp td{padding:4px 7px 2px;border-bottom:0;background:var(--raised);}
#procs .cgrp .cap{font-family:var(--mono);font-size:8.5px;letter-spacing:.09em;
  text-transform:uppercase;color:var(--muted);}
#procs tbody td:first-child{padding-left:14px;}
#procs .agrp td:first-child{padding-left:0;}
#procs .cgrp td:first-child{padding-left:7px;}

/* ---------- stream ---------- */
#stream .body{display:flex;flex-direction:column-reverse;}
/* Flow, not grid. A grid selects cell by cell, so dragging across a line picks
   up column fragments in the wrong order — unusable for quoting into a chat.
   Inline-block columns with fixed widths keep the alignment and let a drag
   select the line as continuous prose. */
.ev{padding:1px 7px;border-left:2px solid var(--agent,transparent);
  line-height:1.4;}
.ev .t{display:inline-block;width:74px;vertical-align:top;}
.ev .tagicon{display:inline-block;width:14px;vertical-align:top;}
.ev .who{display:inline-block;width:118px;vertical-align:top;}
.ev .m{display:inline;}
/* Timestamp and identity are chrome; excluding them means a drag across several
   lines yields the messages alone. */
.ev .t, .ev .tagicon, .ev .who{user-select:none;}
.ev .m{user-select:text;}
.ev:nth-child(odd){background:rgba(127,127,127,.04);}
.ev .t{font-family:var(--mono);font-size:9px;color:var(--muted);
  font-variant-numeric:tabular-nums;display:flex;align-items:center;gap:5px;}
.tagicon{font-size:10px;text-align:center;opacity:.85;}
.daybar{font-family:var(--mono);font-size:9px;letter-spacing:.16em;
  color:var(--ink-2);padding:3px 9px;background:rgba(127,127,127,.07);
  border-left:3px solid var(--muted);}
.ev .fold{cursor:pointer;color:var(--muted);font-family:var(--mono);
  font-size:9px;border:1px solid var(--border);border-radius:3px;
  padding:0 4px;margin-left:6px;flex:none;}
.ev .fold:hover{color:var(--ink);border-color:var(--muted);}
.ev.folded .m{opacity:.75;}
.ev .who{font-family:var(--mono);font-size:9.5px;color:var(--agent,var(--muted));
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.ev .m{font-size:10.5px;color:var(--ink-2);word-break:break-word;}
.ev.ok .m{color:var(--ink);}
.ev.spoken{background:color-mix(in srgb,var(--agent) 9%,transparent);
  border-left-width:3px;padding-top:3px;padding-bottom:3px;}
.ev.spoken .m{color:var(--ink);}
.ev.warn .m{color:var(--warning);}
.ev.error .m,.ev.needs_you .m{color:var(--critical);font-weight:600;}

/* ---------- processes ---------- */
table{width:100%;border-collapse:collapse;font-size:10.5px;}
th{text-align:left;font-family:var(--mono);font-size:8px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);font-weight:600;padding:2px 7px 2px 0;
  position:sticky;top:0;background:var(--surface);}
td{padding:1px 7px 1px 0;border-bottom:1px dotted var(--border);vertical-align:middle;}
td:first-child,th:first-child{padding-left:9px;}
td.n{font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap;
  color:var(--muted);}
td.w{font-family:var(--mono);font-size:10px;}
tr.self td{color:var(--muted);}
.kill{margin:5px 7px 6px;display:flex;align-items:center;gap:8px;}
#kill{font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.09em;
  text-transform:uppercase;padding:5px 11px;border-radius:4px;cursor:pointer;
  border:1px solid var(--critical);background:var(--critical);color:#fff;}
#kill[data-armed="1"]{animation:puls .9s ease-in-out infinite;}
#kill:disabled{opacity:.4;cursor:not-allowed;animation:none;}
#killnote{font-family:var(--mono);font-size:9px;color:var(--muted);}

/* ---------- build gate ----------
   Deliberately quiet next to the kill switch. Killing is an emergency and
   looks like one; handing the compiling to the other machine is an ordinary
   Tuesday, and a second red button would teach the eye to ignore red. */
.buildgate{margin:6px 7px 0;display:flex;align-items:center;gap:8px;}
#bgate{font-family:var(--mono);font-size:9.5px;font-weight:700;letter-spacing:.09em;
  text-transform:uppercase;padding:5px 11px;border-radius:4px;cursor:pointer;
  border:1px solid var(--border);background:var(--raised);color:var(--ink-2);}
#bgate[data-on="1"]{border-color:var(--good);color:var(--good);}
#bgate:disabled{opacity:.4;cursor:not-allowed;}
#bgatenote{font-family:var(--mono);font-size:9px;color:var(--muted);
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}

/* ---------- post to the board, from the board ----------
   Leaving a message used to mean opening the other dashboard. One row, pinned
   under the stream it posts into. */
/* Everyone signs, including the operator. Collapsed until you touch the
   box, because a pad sitting open in a status bar is noise; expanded the
   moment you type, because the signature is not optional. */
#sayMore{display:none;padding:5px 0 2px;gap:6px;flex-direction:column;}
#say.open #sayMore{display:flex;}
#sayMore .padwrap{position:relative;}
#sayMore canvas{width:100%;height:78px;background:#03060a;display:block;
  border:1px solid var(--border);border-radius:4px;cursor:crosshair;
  touch-action:none;}
/* A blank dark rectangle is not obviously a pad. The hint sits inside it
   at low opacity like a placeholder and disappears on the first stroke. */
#sayHint{position:absolute;left:8px;top:50%;transform:translateY(-50%);
  font-family:var(--mono);font-size:10px;color:var(--muted);opacity:.5;
  pointer-events:none;letter-spacing:.06em;}
#sayMore.drawn #sayHint{display:none;}
#sayMore .padwrap button{position:absolute;right:5px;bottom:5px;
  font-family:var(--mono);font-size:8px;padding:1px 6px;background:#03060a;
  border:1px solid var(--border);color:var(--muted);border-radius:3px;
  cursor:pointer;opacity:.7;}
#sayMore .padwrap button:disabled{opacity:.3;cursor:default;}
#sayOk a{color:var(--info);}
/* The mark rides at the end of the line, 14px tall — enough to recognise
   a hand, small enough that a stream of them still reads as a stream. */
/* A signature is wide, not square. Stretching one into a 56px-tall box
   turned a name into a green smear — the aspect ratio IS the handwriting.
   30px tall, 3:1, and no plate behind it: the ink sits straight on the
   row like the rest of the text. */
/* 110x26. Modelled rather than guessed: a correctly captured signature
   spans roughly 0.8 wide by 0.11 tall, which fills 97x13 of this box —
   legible. At 70x15 the same stroke drew 8x13 and read as a dot. The row
   grows by ten pixels; every row grows the same ten, so the rhythm holds. */
canvas.mark{height:26px;width:110px;margin-left:10px;
  background:transparent;flex:none;opacity:.95;align-self:center;}
canvas.mark:hover{opacity:1;}
.m .sender{color:var(--ink);font-weight:700;}
.sayrow{display:flex;gap:5px;align-items:center;}
#say{flex:none;display:flex;flex-direction:column;padding:4px 6px;
  border-top:1px solid var(--border);background:var(--raised);}
#say input[type=text],#say input:not([type]){font-family:var(--mono);font-size:10px;
  padding:3px 6px;border-radius:3px;border:1px solid var(--border);
  background:var(--surface);color:var(--ink);}
#sayWho{width:90px;flex:none;}
#sayBody{flex:1;min-width:0;}
#sayOk{display:flex;align-items:center;gap:3px;flex:none;cursor:pointer;
  font-family:var(--mono);font-size:8.5px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);}
#sayOk input{margin:0;width:11px;height:11px;accent-color:var(--info);}
#say button{font-family:var(--mono);font-size:8.5px;letter-spacing:.09em;
  text-transform:uppercase;padding:4px 9px;border-radius:3px;cursor:pointer;
  border:1px solid var(--border);background:var(--surface);color:var(--ink-2);}
#say button:hover:not(:disabled){border-color:var(--info);color:var(--info);}
#say button:disabled{opacity:.4;cursor:not-allowed;}
#sayNote{font-family:var(--mono);font-size:8.5px;color:var(--muted);
  max-width:22ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
#askbtn{border-color:var(--info);color:var(--info);}
#pendingAsk{display:none;padding:6px 8px;border-top:1px solid var(--info);
  background:color-mix(in srgb,var(--info) 12%,transparent);
  font-family:var(--mono);font-size:10px;color:var(--ink);line-height:1.4;}
#pendingAsk.on{display:block;}
#pendingAsk b{color:var(--info);letter-spacing:.08em;text-transform:uppercase;
  margin-right:8px;}

/* ---------- goals: the chain, and whether you are keeping it ----------
   A list of goals is a poster. What makes it accountable is the review date
   sitting next to each one, and the word OVERDUE when it has passed — the week
   goal was due 2026-07-27 and nothing on any screen said so. */
/* Goals take the whole column now that agents live with the processes they
   are, so the body must scroll rather than push the artwork off the column. */
#goals .body{padding:0;overflow-y:auto;min-height:0;}
/* One height per row, whatever the goal's length. Ragged rows made the
   chain read as a list of unrelated notes; two lines each, clipped with
   an ellipsis, and the full text on hover. */
.goal{display:grid;grid-template-columns:52px minmax(0,1fr) auto;
  gap:8px;align-items:baseline;padding:5px 8px;
  border-bottom:1px solid var(--border);}
.goal .g{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;
  overflow:hidden;line-height:1.35;}
.goal:last-child{border-bottom:0;}
.goal .s{font-family:var(--mono);font-size:9px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);}
.goal .g{font-size:11.5px;color:var(--ink-2);min-width:0;}
.goal .d{font-family:var(--mono);font-size:9px;color:var(--muted);
  white-space:nowrap;font-variant-numeric:tabular-nums;}
.goal.now{background:var(--raised);}
.goal.now .g{color:var(--ink);font-weight:600;}
.goal.late .d{color:var(--critical);font-weight:600;}
.goal.soon .d{color:var(--warning);}

/* ---------- footer: everything this machine runs, in 7px ---------- */
#foot{border-top:1px solid var(--border);background:var(--raised);
  padding:10px 12px 12px;
  display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:4px 18px;}
#foot section{min-width:0;}
#foot h3{font-family:var(--mono);font-size:8px;letter-spacing:.18em;
  text-transform:uppercase;color:var(--muted);margin:0 0 4px;font-weight:600;}
#foot a,#foot span.dead{display:block;font-family:var(--mono);font-size:9px;
  line-height:1.7;color:var(--ink-2);text-decoration:none;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
#foot a:hover{color:var(--accent);text-decoration:underline;}
#foot span.dead{color:var(--muted);}

/* ---------- terminal ----------
   It used to live in a drawer that slid up over the board, so using it meant
   losing sight of the stream -- the two things you actually want side by side,
   because the terminal is where you act and the stream is where the fleet
   answers. It is a pane now, above the stream, sharing the middle column. */
/* Half the column by default. 320px was a drawer's habit -- a strip you
   glance at. The operator asked to work in here, and a working pane is
   the same size as the thing it is working on. Dragging the grip pins it
   to pixels and that choice is remembered; until then it stays half. */
#termpane{flex:0 0 var(--hTerm,50%);min-height:80px;}
#termpane .body{padding:0;overflow:hidden;}
#termpane[data-open="0"]{flex:0 0 auto;min-height:0;}
#termpane[data-open="0"] .body{display:none;}
/* Collapsed, the divider is the only thing left saying a terminal is here, so
   it stops being a hairline and becomes a grabbable bar. Hiding it entirely
   was the first version and it made the pane unrecoverable without a reload. */
#termpane[data-open="0"]+.griph{height:7px;cursor:pointer;}
#termpane[data-open="0"]+.griph::after{background:var(--border);
  border-radius:3px;box-shadow:inset 0 0 0 1px var(--surface);}
#termpane[data-open="0"]+.griph:hover::after{background:var(--info);}
/* The other half of the same handle. Drag the divider to the bottom and the
   stream shuts instead of being crushed into a two-line slot; the terminal
   then takes the whole column, which is the point -- collapsing the thing you
   are not reading should give the space to the thing you are working in.
   :has() rather than a class on the column: the state lives on one element,
   so there is nothing to keep in sync. */
#stream[data-open="0"]{flex:0 0 auto;min-height:0;}
#stream[data-open="0"] .body,#stream[data-open="0"] form,
#stream[data-open="0"] #pendingAsk{display:none;}
#stream[data-open="0"] h2{cursor:pointer;}
.col:has(#stream[data-open="0"]) #termpane{flex:1;}
#term{height:100%;padding:5px 7px;}
/* ---------- terminal drawer (legacy, kept for /terminal) ---------- */
#drawer{flex:none;height:0;overflow:hidden;border-top:1px solid var(--border);
  background:#0d0d0d;transition:height .18s ease;}
#drawer.open{height:42vh;}
@media (prefers-reduced-motion:reduce){#drawer{transition:none;}}
#term{height:100%;padding:5px 7px;}
.empty{color:var(--muted);font-style:italic;padding:9px;font-size:10.5px;}
"""

JS = r"""
const AGENTS = __AGENTS__;
const TOKEN  = __TOKEN__;
const $ = s => document.querySelector(s);

/* ---------------- shared state -------------------------------------------
   One event-stream connection and one polling timer for the whole page. The
   five separate pages this replaces each opened their own. */
const blocked = new Map();
let termReady = false, ws = null, killToken = null, armTimer = null;

const emoji = n => (AGENTS[n]||["⚙"])[0];
const hue   = n => (AGENTS[n]||[null,"#7d838b"])[1];
const hhmm  = iso => { try { const d=new Date(iso);
  return [d.getHours(),d.getMinutes(),d.getSeconds()].map(x=>String(x).padStart(2,"0")).join(":");
} catch(e){ return "--:--:--"; } };

/* ---------------- meters --------------------------------------------------
   A value is read by length, not by digits. Non-zero never renders as nothing:
   0.4% of 100px is half a pixel, indistinguishable from missing data. */
function meter(value, max, opts={}){
  const pct = Math.max(0, (value/(max||1))*100);
  const over = pct > 100;
  const tone = opts.tone || (pct>=90?"critical":pct>=60?"warning":"good");
  const colour = tone==="info" ? "var(--info)" : `var(--${tone})`;
  const w = document.createElement("span");
  w.style.cssText = "display:inline-flex;align-items:center;gap:5px;vertical-align:middle";
  w.title = opts.exact ?? (value + (opts.suffix||""));
  const track = document.createElement("span");
  track.style.cssText = `width:${opts.w||64}px;height:6px;border-radius:3px;
    background:rgba(127,127,127,.22);overflow:hidden;flex:none`;
  const fill = document.createElement("span");
  fill.style.cssText = `display:block;height:100%;border-radius:3px;
    width:${Math.min(100,pct).toFixed(1)}%;${value>0?"min-width:3px;":""}
    background:${over?`repeating-linear-gradient(135deg,var(--critical) 0 3px,transparent 3px 6px)`:colour}`;
  track.appendChild(fill); w.appendChild(track);
  return w;
}

/* ---------------- agents -------------------------------------------------- */
/* An agent IS a process. The board used to carry an agents pane on the left and
   a processes pane on the right, both saying "openclaw is up" in different
   words, with nothing tying a row to the agent that owned it. One pane now: the
   agent is the heading, its processes are the rows beneath it. The left column
   is goals — the thing the fleet is FOR — rather than a second copy of this. */
const lastMsg = new Map();
let WORKERS = [];
function renderAgents(workers){ WORKERS = workers; }

/* ---------------- vendor credit ------------------------------------------ */
/* The quotas pulse carries a row per vendor, but it ships it as JSON inside
   a string field, so nothing on the board ever read it. On 2026-09-01 grok
   had been answering every request with 402 Payment Required for four days
   and the board showed nothing at all. Money is a fleet health metric. */
function creditState(v){
  const n = v.quota_errors_24h || 0;
  if (v.binary === false)      return ["idle", "not installed"];
  if (v.auth === "logged-out") return ["out",  "needs a login"];
  // "quota-shaped errors in last 24h" is how the pulse says it to itself.
  // On the board it should say the thing a person would say.
  if (v.ok === false)          return ["dry",  n ? "refused " + n + "x today"
                                                 : "spent"];
  // A measured balance beats every inference below it. grok sat at 100% of
  // its weekly limit while this pane said "has credit", because nothing had
  // called it recently enough to log a refusal (2026-09-02). Absence of a
  // failure is not evidence of money.
  const pct = v.remaining_pct;
  const when = v.reset_at ? " until " + new Date(v.reset_at).toLocaleString(
                 [], {month:"short", day:"numeric", hour:"2-digit",
                      minute:"2-digit"}) : "";
  if (v.flow === "exhausted")  return ["dry",  "0% left" + when];
  if (v.flow === "reserve")    return ["dry",  pct + "% left, reserved"];
  if (v.flow === "spend" || v.flow === "harvest")
                               return ["rich", pct + "% left" + when];
  if (v.vendor === "local")    return ["rich", "local, costs nothing"];
  if (v.plan)                  return ["rich", "on " + v.plan];
  // Everything past here is a guess. Say so rather than saying "has credit":
  // the pane is read to decide who to ask, and a confident wrong answer
  // sends work at a vendor that will refuse it.
  if (v.note === "on PATH")    return ["hazy", "installed, never probed"];
  return ["hazy", v.note || "no reading"];
}
const CREDIT_WORD = {rich:"has credit", dry:"DRY", out:"logged out",
                     hazy:"unknown", idle:"absent"};

function renderCredit(workers){
  const pane = $("#credit");
  const q = (workers || []).find(w => w.worker === "quotas");
  let rows = [];
  try { rows = JSON.parse(q.detail).vendors || []; } catch(e){ rows = []; }
  if (!rows.length){ pane.dataset.state = "error"; return; }

  // Dry first: the board should lead with what cannot be asked.
  const rank = {dry:0, out:1, hazy:2, rich:3, idle:4};
  const seen = rows.map(v => { const [k, why] = creditState(v);
                               return {v, k, why}; })
                   .sort((a,b) => rank[a.k] - rank[b.k]
                                  || a.v.agent.localeCompare(b.v.agent));

  $("#creditbody").innerHTML = seen.map(({v, k, why}) => `
    <tr><td class="who">${esc(v.agent)}</td>
        <td class="vend">${esc(v.vendor || "")}</td>
        <td class="why">${esc(why)}</td>
        <td class="st ${k}">${CREDIT_WORD[k]}</td></tr>`).join("");

  const broke = seen.filter(x => x.k === "dry" || x.k === "out").length;
  $("#credit h2 .n").textContent = broke ? `${broke} down` : "all up";
  $("#creditasof").textContent = q.last_run
    ? "checked " + new Date(q.last_run).toLocaleTimeString() : "";
  pane.dataset.state = "ready";
}

/* The agent's own line, as a full-width row above the processes it owns. */
function agentCard(w){
  const d = document.createElement("div");
  d.className = "agent";
  d.style.setProperty("--agent", hue(w.worker));
  const top = document.createElement("div"); top.className = "top";
  const nm = document.createElement("span"); nm.className = "nm";
  nm.textContent = emoji(w.worker) + " " + w.worker;
  const st = document.createElement("span"); st.className = "st " + (w.status||"");
  st.textContent = w.status || "";
  top.append(nm, st);
  if (Number.isInteger(w.tests_passed) && (w.tests_passed + (w.tests_failed||0)) > 0){
    top.append(meter(w.tests_passed, w.tests_passed + w.tests_failed,
      {tone: w.tests_failed ? "critical" : "good", w: 48,
       exact: `${w.tests_passed} of ${w.tests_passed + w.tests_failed} passed`}));
  }
  const last = document.createElement("div"); last.className = "last";
  last.textContent = lastMsg.get(w.worker) || w.summary || "";
  d.append(top, last);
  return d;
}

/* ---------------- stream -------------------------------------------------- */
/* Day pills.
   A run repeated hourly produces near-identical lines; the only thing that
   distinguishes yesterday's from today's is a timestamp you have to read. Each
   day gets a colour instead, cycled from the validated categorical palette, so
   the boundary is visible without parsing digits. The same pill appears on a
   collapsed group and on every line inside it. */
const DAY_HUES = ["#3987e5", "#d95926", "#199e70", "#c98500",
                  "#d55181", "#9085e9", "#008300"];
const dayKey = iso => String(iso || "").slice(0, 10);

function dayHue(key){
  let h = 0;
  for (const c of key) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return DAY_HUES[h % DAY_HUES.length];
}

/* A date on every row is noise; a date on no row is a trap when you are working
   past midnight and 23:58 sits directly above 00:03. So it appears exactly once
   per day — on the line where the day turns over — as a full ISO date. */
let lastDayRendered = null;

function dayDivider(iso){
  const key = dayKey(iso);
  if (!key || key === lastDayRendered) return null;
  lastDayRendered = key;
  const el = document.createElement("div");
  el.className = "daybar";
  el.style.borderColor = dayHue(key);
  el.textContent = key;
  return el;
}

function dayPill(){ return document.createComment(""); }

/* One tag per event, decided on arrival. Filtering is then a class check
   rather than a re-scan of the whole log. */
/* Pure bookkeeping with no information in it.
   The e2e canary lines are the exception worth explaining: they must exist in
   the log, because the test asserts the canary travels from the emitter to the
   rendered page. They are evidence for the machine and clutter for the reader,
   so they stay on disk and disappear from the display. */
const SILENT = /(sweep finished|adjourned after|convened —|\[e2e\] (state )?canary )/i;

/* Marks beside messages. A signature is the point of the hand lane, so a
   guest line without one is missing its evidence — 14px tall, drawn in the
   same raw ink as the wall, matched by sender name. */
let MARKS = {};
async function loadMarks(){
  try { MARKS = (await (await fetch("api/marks",{cache:"no-store"})).json()).marks || {}; }
  catch (e) { return; }
  paintMissingMarks();
}

/* The index is fetched asynchronously and a new sender's mark only exists
   AFTER their message arrives — so the row that most deserves a signature
   is exactly the one that renders before the mark is known. Backfill:
   every row tagged as wanting a mark gets one as soon as the index has it. */
function paintMissingMarks(){
  if (!window.drawRawSignature) return;
  document.querySelectorAll('.ev[data-wants-mark]').forEach(row => {
    const who = row.dataset.wantsMark;
    if (!MARKS[who] || row.querySelector("canvas.mark")) return;
    const cv = document.createElement("canvas");
    cv.className = "mark";
    cv.title = who + " — their hand";
    row.append(cv);
    requestAnimationFrame(() => drawRawSignature(cv, MARKS[who]));
  });
}
function markFor(msg){
  const m = /\[signals\]\s+([^:]{1,40}):/.exec(msg || "");
  if (!m) return null;
  const who = m[1].trim();
  return MARKS[who] ? {who, points: MARKS[who]} : null;
}

function tagOf(e){
  const m = e.msg || "";
  if (e.level === "needs_you" || e.level === "error") return "attention";
  if (m.includes("[relay]") || m.includes("[plus-one]") || /\bhops\b/.test(m))
    return "relay";
  if (m.includes("[council]")) return "council";
  if (m.includes("[signals]") || m.includes("[signatures]")
      || m.includes("[visitors]") || m.includes("[charge]")) return "guests";
  if (m.includes("[rota]") || m.includes("[pipeline]")) return "rota";
  if (m.includes("[e2e]") || m.includes("pytest") || m.includes("passed") || m.includes("watchdog")) return "tests";
  return "other";
}
/* Additive: each tag is an independent toggle, any combination is valid
   including none. Deselecting everything is a legitimate state that shows
   nothing, so it gets an explicit banner rather than an empty box that looks
   broken. */
const TAGS = ["relay", "council", "rota", "guests", "tests", "attention", "other"];
const TAG_ICON = {relay: "\u{1F517}", council: "\u{1F5E3}", rota: "\u{1F528}",
                  guests: "\u{1F44B}", tests: "\u{1F9EA}", attention: "\u{1F6A8}",
                  other: "\u{1F4CE}"};
const shown = new Set(TAGS);

/* Three distinct empty states, because "blank panel" is not an answer.
   Nothing selected is a choice you made; nothing matching is a fact about the
   log; and no events at all is a fresh system. Each says which. */
function applyFilter(){
  let visible = 0;
  const counts = Object.fromEntries(TAGS.map(x => [x, 0]));
  document.querySelectorAll("#stream .ev").forEach(row => {
    const tag = row.dataset.tag;
    if (tag in counts) counts[tag]++;
    const on = shown.has(tag);
    row.hidden = !on;
    if (on) visible++;
  });

  // A tag with nothing behind it is greyed rather than silently disappointing.
  for (const tag of TAGS) {
    const b = $(`#filters button[data-f="${tag}"]`);
    if (!b) continue;
    b.dataset.empty = counts[tag] ? "0" : "1";
    let c = b.querySelector(".cnt");
    if (!c) { c = document.createElement("span"); c.className = "cnt"; b.appendChild(c); }
    c.textContent = counts[tag];
  }

  const total = document.querySelectorAll("#stream .ev").length;
  const title = $("#emptyTitle"), sub = $("#emptySub");

  if (!shown.size) {
    title.textContent = "no filters selected";
    sub.textContent = "nothing will show — pick a tag, or press ALL";
  } else if (!total) {
    title.textContent = "no activity yet";
    sub.textContent = "the fleet has not spoken since this page loaded";
  } else if (!visible) {
    const picked = [...shown].join(", ");
    title.textContent = "nothing matching";
    sub.textContent = `no messages tagged ${picked} — ${total} hidden by the filter`;
  }

  const blank = !visible;
  $("#empty").className = blank ? "on" : "";
  $("#stream .body").style.display = blank ? "none" : "";
}

function setTag(tag, on){
  on ? shown.add(tag) : shown.delete(tag);
  const b = $(`#filters button[data-f="${tag}"]`);
  if (b) b.setAttribute("aria-pressed", String(on));
}

$("#filters").addEventListener("click", ev => {
  const b = ev.target.closest("button"); if (!b) return;
  if (b.id === "fall")  { TAGS.forEach(t => setTag(t, true));  return applyFilter(); }
  if (b.id === "fnone") { TAGS.forEach(t => setTag(t, false)); return applyFilter(); }
  const tag = b.dataset.f;
  if (b.dataset.empty === "1") return;    // nothing behind it; ignore the click
  setTag(tag, !shown.has(tag));
  applyFilter();
});

/* A finished run should be one line, not four.
   "sweep started" / "running tests" / "91 passed" / "sweep finished" is a
   lifecycle narrated at the reader. Collapse it: the start lines are held, and
   when the result arrives it replaces them carrying the elapsed time. A run
   still in flight keeps its start line, so nothing is hidden while it works. */
const OPEN = new Map();          // agent -> {row, started}

const STARTS  = /(sweep started|running tests|\[relay\] start|\[e2e\] run starting|round \d+: thinking|thinking)/i;
const RESULTS = /(passed|failed|hops|nothing to add|\[council\] r\d|checks passed|error)/i;

function secsBetween(a, b){
  try { return Math.max(0, Math.round((new Date(b) - new Date(a)) / 1000)); }
  catch(e){ return null; }
}

/* Repeats collapse.
   Hourly checks emit lines that differ only in numbers — canaries, durations,
   counters. Stripping those yields a signature; consecutive events sharing one
   fold into a single row with a count, expandable on click. The newest is the
   one shown, because that is the one you care about. */
function signature(e){
  return e.agent + "|" + (e.msg || "")
    .replace(/\b[0-9a-f]{6,}\b/gi, "#")     // canaries, hashes
    .replace(/\d+(\.\d+)?s\b/g, "#s")      // durations
    .replace(/\d+/g, "#");                  // every other number
}

let lastSig = null, lastGroup = null, prevTs = null;

/* A council turn is the only line in this log an agent actually composed.
   Everything else is a machine reporting a number. They should not look alike. */
const SPOKEN = /\[council\] r\d/i;

function addEvent(e){
  if (SILENT.test(e.msg || "")) { lastMsg.set(e.agent, e.msg || ""); return; }
  const box = $("#stream .body");
  const row = document.createElement("div");
  row.className = "ev " + (e.level||"info");
  row.dataset.tag = tagOf(e);
  if (SPOKEN.test(e.msg || "")) row.classList.add("spoken");
  row.hidden = !shown.has(row.dataset.tag);
  row.style.setProperty("--agent", hue(e.agent));
  const t = document.createElement("span"); t.className="t";
  const clock = document.createElement("span"); clock.textContent = hhmm(e.ts);
  prevTs = e.ts;
  t.append(clock, dayPill(e.ts));
  const w = document.createElement("span"); w.className="who";
  w.textContent = emoji(e.agent) + " " + e.agent;
  // The agent already carries an emoji. Showing the tag icon too duplicated it
  // whenever they happened to match — agent-comms is 🔗 and so is the relay tag.
  const tag = tagOf(e);
  const icon = document.createElement("span");
  icon.className = "tagicon";
  const agentIcon = emoji(e.agent);
  icon.textContent = (TAG_ICON[tag] === agentIcon) ? "" : (TAG_ICON[tag] || "");
  icon.title = tag;
  const m = document.createElement("span"); m.className="m";
  const said = clean(e.msg);
  // Bold the person, not the plumbing: "[signals] NAME: words" reads as
  // one grey run otherwise, and the name is the thing you scan for.
  const who = /^\[signals\]\s+([^:]{1,40}):\s*([\s\S]*)$/.exec(said);
  if (who){
    const b = document.createElement("b");
    b.textContent = who[1].trim();
    b.className = "sender";
    m.append(b, document.createTextNode(" " + who[2]));
  } else {
    m.textContent = said;
  }
  row.append(t,icon,w,m);
  // Tag the row with whose mark it wants, then draw if we already have
  // it. If not, loadMarks() will backfill — and a message from a sender
  // we have never seen triggers a refresh immediately rather than
  // waiting out the poll.
  const sender = (/^\[signals\]\s+([^:]{1,40}):/.exec(e.msg || "") || [])[1];
  if (sender){
    const who = sender.trim();
    row.dataset.wantsMark = who;
    if (MARKS[who] && window.drawRawSignature){
      const cv = document.createElement("canvas");
      cv.className = "mark";
      cv.title = who + " — their hand";
      row.append(cv);
      requestAnimationFrame(() => drawRawSignature(cv, MARKS[who]));
    } else {
      setTimeout(loadMarks, 400);
    }
  }
  const msg = e.msg || "";

  if (STARTS.test(msg)) {
    // Hold it: if a result follows, this line is replaced rather than kept.
    OPEN.set(e.agent, {row, started: e.ts});
    box.prepend(row);
    const bar0 = dayDivider(e.ts);
    if (bar0) box.prepend(bar0);
    followLatest(box);
  } else if (RESULTS.test(msg) && OPEN.has(e.agent)) {
    const open = OPEN.get(e.agent);
    OPEN.delete(e.agent);
    const took = secsBetween(open.started, e.ts);
    if (took !== null && !/·\s*[\d.]+s\b/.test(msg)) {
      m.textContent = msg + "  (" + took + "s)";
    }
    open.row.replaceWith(row);           // one line where there were two
  } else {
    const sig = signature(e);
    if (sig === lastSig && lastGroup && lastGroup.isConnected) {
      // Same thing again: fold into the existing row instead of adding another.
      lastGroup._n = (lastGroup._n || 1) + 1;
      lastGroup._rows = lastGroup._rows || [];
      lastGroup._rows.push(row);
      let fold = lastGroup.querySelector(".fold");
      if (!fold) {
        fold = document.createElement("span");
        fold.className = "fold";
        fold.addEventListener("click", () => {
          const open = lastGroupExpanded(fold);
          fold.dataset.open = open ? "0" : "1";
          fold.textContent = (open ? "+" : "−") + fold.dataset.count;
          (fold._owner._rows || []).forEach(r => {
            if (open) r.remove();
            else fold._owner.after(r);
          });
        });
        fold._owner = lastGroup;
        lastGroup.querySelector(".t").appendChild(fold);
      }
      fold.dataset.count = lastGroup._n;
      fold.textContent = (fold.dataset.open === "1" ? "−" : "+") + lastGroup._n;
      // show the newest instance, not the first
      lastGroup.querySelector(".m").textContent = e.msg || "";
      lastGroup.querySelector(".t").firstChild.textContent = hhmm(e.ts);
      return;
    }
    lastSig = sig;
    lastGroup = row;
    box.prepend(row);
    // column-reverse: prepending after the row puts the divider visually above it
    const bar = dayDivider(e.ts);
    if (bar) box.prepend(bar);
    followLatest(box);
  }

  while (box.children.length > 320) box.removeChild(box.lastChild);

  lastMsg.set(e.agent, e.msg||"");
  if (e.level === "needs_you") blocked.set(e.agent, e.msg);
  else if (e.level === "ok") blocked.delete(e.agent);
  renderAlarm();
}

function lastGroupExpanded(fold){ return fold.dataset.open === "1"; }

function renderAlarm(){
  const a = $("#alarm");
  if (!blocked.size){ a.className = ""; return; }
  const [who,msg] = blocked.entries().next().value;
  a.className = "on";
  a.querySelector("b").textContent = blocked.size>1 ? blocked.size+" need you" : "Needs you";
  a.querySelector("span.d").textContent = emoji(who)+" "+who+" — "+msg;
}

/* ---------------- processes ----------------------------------------------- */
function elapsedSeconds(e){
  const p = String(e).split("-");
  let days = 0, rest = e;
  if (p.length === 2){ days = parseInt(p[0],10)||0; rest = p[1]; }
  const n = rest.split(":").map(x=>parseInt(x,10)||0);
  while (n.length < 3) n.unshift(0);
  return days*86400 + n[0]*3600 + n[1]*60 + n[2];
}

function renderMachine(m){
  const el = $("#machine");
  if (!el || !m || m.load1 == null) return;
  // Words first, number second. The whole failure this fixes was that a number
  // sat available and unread — "saturated" needs no interpretation.
  el.dataset.state = m.state;
  const d = m.disk || {};
  const disk = (d.used_pct != null)
    ? ` · disk ${Math.round(d.used_pct)}% ${d.free_gb}G free`
    : "";
  const ram = (m.compressor_gb != null)
    ? ` · ram ${Number(m.compressor_gb).toFixed(1)}G compressed`
    : "";
  el.textContent = `${m.state} · ${m.load1} / ${m.cores} cores${ram}${disk}`;
  el.title = `1m ${m.load1} · 5m ${m.load5} · 15m ${m.load15} — `
           + `agents defer above ${m.gate}`
           + (d.total_gb != null
              ? ` · ssd ${d.used_gb}G / ${d.total_gb}G`
              : "");
}

function renderProcs(s){
  $("#procs").dataset.state = "ready";
  renderMachine(s.machine);
  const tb = $("#procbody");
  tb.replaceChildren();
  const rows = [...s.fleet, ...s.external];
  const own = new Set(s.fleet);

  const procRow = p => {
    const tr = document.createElement("tr");
    if (p.is_self) tr.className = "self";
    const cell = (txt,cls) => { const td=document.createElement("td");
      if(cls) td.className=cls; td.textContent=txt; return td; };
    const wrap = node => { const td=document.createElement("td"); td.appendChild(node); return td; };
    tr.append(cell(p.pid,"n"));
    tr.append(cell(p.label + (p.is_self?"  (this)":"") + (own.has(p)?"":"  ·ext"), "w"));
    tr.append(cell(p.rss_mb != null ? Math.round(p.rss_mb)+"M" : "—", "n"));
    tr.append(wrap(meter(p.cpu,100,{suffix:"% cpu"})));
    tr.append(wrap(meter(p.mem,100,{suffix:"% mem"})));
    tr.append(wrap(meter(elapsedSeconds(p.elapsed),86400,{tone:"info",exact:p.elapsed+" uptime"})));
    return tr;
  };
  // A full-width row carrying either an agent's card or a plain group caption.
  const spanRow = (node, cls) => {
    const tr = document.createElement("tr"); tr.className = cls;
    const td = document.createElement("td"); td.colSpan = 6;
    td.appendChild(node); tr.appendChild(td); return tr;
  };
  const caption = txt => { const s=document.createElement("span");
    s.className="cap"; s.textContent=txt; return s; };

  // Agents first, each followed by its own processes. An agent with nothing
  // running still gets a line — "hermes has no process" is the whole point of
  // looking, and hiding the agent would hide the answer.
  for (const w of WORKERS){
    tb.appendChild(spanRow(agentCard(w), "agrp"));
    const mine = rows.filter(p => p.agent === w.worker);
    if (mine.length) mine.forEach(p => tb.appendChild(procRow(p)));
    else {
      const tr=document.createElement("tr"), td=document.createElement("td");
      td.colSpan=6; td.className="empty"; td.textContent="// no process";
      tr.appendChild(td); tb.appendChild(tr);
    }
  }
  // Everything the fleet runs that is work rather than an agent: test sweeps,
  // the board itself, the cockpit.
  const loose = rows.filter(p => !p.agent);
  if (loose.length){
    tb.appendChild(spanRow(caption("fleet work"), "cgrp"));
    loose.forEach(p => tb.appendChild(procRow(p)));
  }
  const heavies = s.heavies || [];
  if (heavies.length){
    tb.appendChild(spanRow(caption("heaviest on the box"), "cgrp"));
    heavies.forEach(p => tb.appendChild(procRow(p)));
  }
  if (!WORKERS.length && !rows.length){
    const tr=document.createElement("tr"), td=document.createElement("td");
    td.colSpan=6; td.className="empty"; td.textContent="// nothing running";
    tr.appendChild(td); tb.appendChild(tr);
  }
  $("#procs .n").textContent =
    WORKERS.length + " agents · " + rows.length + " procs · "
    + heavies.length + " heavy · " + s.killable + " killable";
  // A remote visitor has no controls rendered at all, so every handler and
  // painter below has to tolerate their absence. Without the guard the first
  // null blows up the poll and takes the panes down with it -- the page would
  // be safe and broken, when it only needed to be safe.
  const kb = $("#kill");
  if (!kb) return;
  kb.disabled = s.killable === 0;
  // A greyed button with no reason next to it is a question, and Marsita asked
  // it. The count lives in the pane header where it is easy to miss; put the
  // answer where the disabled control is.
  if (kb.disabled && kb.dataset.armed !== "1"){
    kb.title = "nothing to kill — no fleet work is running";
    $("#killnote").textContent = "nothing running";
  } else if (!kb.disabled && kb.dataset.armed !== "1"){
    kb.title = "";
    $("#killnote").textContent = "SIGKILL. agent runtimes untouched.";
  }
}

/* ---------------- post to the board ---------------------------------------- */
/* Fleet forwards /api/signals to the cockpit, so this posts to its own origin
   and works the same from the laptop or the public URL. The lawful checkbox is
   not decoration: the API refuses without it, and the refusal is the record
   that the sender was told the rule before they sent. */
/* ---------------- the operator signs too ---------------------------------- */
(() => {
  const form = $("#say"), pad = $("#sayPad"), clr = $("#sayClear");
  if (!pad) return;
  const ctx = pad.getContext("2d");
  let stroke = [], drawing = false, t0 = 0;
  window.__sayStroke = () => stroke;

  const open = () => form.classList.add("open");
  $("#sayBody").addEventListener("focus", open);
  $("#sayWho").addEventListener("focus", open);

  const xy = e => {
    const r = pad.getBoundingClientRect();
    // Both axes divided by WIDTH, deliberately. Dividing y by height
    // normalises the two axes differently, so a wide pad squashes every
    // gesture: a signature drawn across a 700x78 box came back with a
    // bounding ratio of 0.24 — taller than wide — and rendered as a
    // vertical smear no matter how the frame was sized (2026-08-05).
    // One denominator keeps the true proportions of the hand.
    return {x: (e.clientX - r.left) / r.width,
            y: (e.clientY - r.top) / r.width,
            t: performance.now() - t0};
  };
  pad.addEventListener("pointerdown", e => {
    pad.setPointerCapture(e.pointerId);
    if (!stroke.length) t0 = performance.now();
    fit();
    drawing = true; stroke.push(xy(e)); clr.disabled = false;
    $("#sayMore").classList.add("drawn");
  });
  // Size the buffer ONCE, on pointerdown. Doing it inside pointermove was
  // the bug behind "only the last few pixels visible": assigning
  // canvas.width clears the canvas, so every size check mid-stroke wiped
  // everything already drawn and left only the segment after it.
  const fit = () => {
    const r = pad.getBoundingClientRect();
    if (pad.width !== Math.round(r.width)){
      pad.width = Math.round(r.width);
      pad.height = Math.round(r.height);
      redraw();
    }
  };
  const redraw = () => {
    const r = pad.getBoundingClientRect();
    ctx.lineCap = "round";
    for (let i = 1; i < stroke.length; i++){
      const a = stroke[i-1], b = stroke[i];
      const dt = Math.max(b.t - a.t, 1e-3);
      const v = Math.min(Math.hypot(b.x - a.x, b.y - a.y) / dt * 40, 3);
      const w = Math.max(0.6, 3.2 - v * 0.9);
      for (const l of [[w * 3, "rgba(125,255,176,0.10)"], [w, "rgba(190,255,215,0.95)"]]){
        ctx.lineWidth = l[0]; ctx.strokeStyle = l[1];
        ctx.beginPath();
        ctx.moveTo(a.x * r.width, a.y * r.width);
        ctx.lineTo(b.x * r.width, b.y * r.width);
        ctx.stroke();
      }
    }
  };
  new ResizeObserver(fit).observe(pad);

  pad.addEventListener("pointermove", e => {
    if (!drawing) return;
    const r = pad.getBoundingClientRect();
    const a = stroke[stroke.length - 1], b = xy(e);
    const dt = Math.max(b.t - a.t, 1e-3);
    const v = Math.min(Math.hypot(b.x - a.x, b.y - a.y) / dt * 40, 3);
    const w = Math.max(0.6, 3.2 - v * 0.9);
    ctx.lineCap = "round";
    for (const l of [[w * 3, "rgba(125,255,176,0.10)"], [w, "rgba(190,255,215,0.95)"]]){
      ctx.lineWidth = l[0]; ctx.strokeStyle = l[1];
      ctx.beginPath();
      ctx.moveTo(a.x * r.width, a.y * r.width);
      ctx.lineTo(b.x * r.width, b.y * r.width);
      ctx.stroke();
    }
    stroke.push(b);
  });
  const stop = () => { drawing = false; };
  pad.addEventListener("pointerup", stop);
  pad.addEventListener("pointercancel", stop);
  const wipe = () => {
    // Setting width resets the backing store entirely. clearRect(0,0,
    // pad.width, pad.height) missed a strip whenever the CSS box and the
    // buffer disagreed, which is why a few pixels of the last signature
    // survived every post.
    pad.width = pad.width;
    stroke = []; clr.disabled = true;
    $("#sayMore").classList.remove("drawn");
  };
  clr.addEventListener("click", wipe);
  window.__sayWipe = wipe;
  window.__sayReset = () => { wipe(); form.classList.remove("open"); };
})();

$("#say").addEventListener("submit", async ev => {
  ev.preventDefault();
  const who = $("#sayWho").value.trim() || "marsita";
  const body = $("#sayBody").value.trim();
  const btn = $("#say button");
  const note = $("#sayNote");
  if (!body){ note.textContent = "say something first"; return; }
  const stroke = (window.__sayStroke ? window.__sayStroke() : []);
  $("#say").classList.add("open");
  if (stroke.length < 20){
    note.textContent = "sign it — everyone signs, including you";
    return;
  }
  if (!$("#sayLawful").checked){
    note.textContent = "tick the box";
    return;
  }
  btn.disabled = true; note.textContent = "posting…";
  try {
    const r = await fetch("api/signals", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({kind: "signal", sender: who, body, lawful: true,
                            signature: stroke.slice(0, 3000)}),
    });
    const d = await r.json();
    if (!r.ok){ note.textContent = "refused: " + (d.detail || r.status); }
    else {
      note.textContent = "posted " + (d.id || "");
      $("#sayBody").value = "";
      $("#sayLawful").checked = false;
      if (window.__sayReset) window.__sayReset();
    }
  } catch(e){ note.textContent = "failed: " + e.message; }
  btn.disabled = false;
});

/* ---------------- kill switch --------------------------------------------- */
function disarm(){
  const b = $("#kill");
  if (!b) return;
  b.dataset.armed = "0"; b.textContent = "kill fleet work";
  $("#killnote").textContent = "SIGKILL. agent runtimes untouched.";
  clearTimeout(armTimer);
}
if ($("#kill")) $("#kill").addEventListener("click", async () => {
  const b = $("#kill");
  if (b.dataset.armed !== "1"){
    b.dataset.armed = "1"; b.textContent = "click again";
    $("#killnote").textContent = "arming for 5s — click to confirm";
    armTimer = setTimeout(disarm, 5000); return;
  }
  disarm(); b.disabled = true;
  try {
    killToken ??= (await (await fetch("api/kill-token")).json()).token;
    const d = await (await fetch("api/kill",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({token:killToken})})).json();
    $("#killnote").textContent = d.error ? "refused: "+d.error
      : d.killed.length ? "killed "+d.killed.length : "nothing was running";
  } catch(e){ $("#killnote").textContent = "failed: "+e.message; }
  b.disabled = false; poll();
});

/* ---------------- build gate ----------------------------------------------
   Every machine in the fleet can do every job. This says which one SHOULD do
   the compiling, and it is per-machine state, so the laptop can hand building
   to the NUC and keep proposing, testing and reviewing. No confirmation step:
   unlike the kill switch, the wrong answer here costs one cycle. */
function paintGate(g){
  const b = $("#bgate");
  if (!b) return;
  b.dataset.on = g.enabled ? "1" : "0";
  b.textContent = "build: " + (g.enabled ? "on" : "off");
  $("#bgatenote").textContent = g.enabled
    ? (g.host || "this machine") + " builds its own picks"
    : (g.host || "this machine") + " proposes, tests, reviews — no build";
  b.title = g.ts ? `set ${g.ts} by ${g.by || "?"}`
                 : "default — building is on until turned off";
}
async function loadGate(){
  try { paintGate(await (await fetch("api/build-gate",{cache:"no-store"})).json()); }
  catch(e){ const n = $("#bgatenote"); if (n) n.textContent = "gate unreadable"; }
}
if ($("#bgate")) $("#bgate").addEventListener("click", async () => {
  const b = $("#bgate");
  b.disabled = true;
  try {
    killToken ??= (await (await fetch("api/kill-token")).json()).token;
    const want = b.dataset.on !== "1";
    const d = await (await fetch("api/build-gate",{method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({token:killToken, enabled:want})})).json();
    if (d.error) $("#bgatenote").textContent = "refused: " + d.error;
    else paintGate(d);
  } catch(e){ $("#bgatenote").textContent = "failed: " + e.message; }
  b.disabled = false;
});
loadGate();

/* ---------------- terminal drawer, opened only on request ------------------ */
async function toggleTerm(){
  const d = $("#termpane"), btn = $("#termbtn");
  if (!d) return;
  const opening = d.dataset.open !== "1";
  setPaneOpen(d, opening);
  if (btn) btn.setAttribute("aria-pressed", String(opening));
  if (!opening || termReady) { if (opening && window.__fit) window.__fit.fit(); return; }

  // Load xterm and open the socket only when first asked: an idle drawer
  // should cost nothing.
  //
  // Say so while it happens. Two scripts and a websocket is fast on an idle
  // laptop and slow on one that is swapping, and the drawer used to show an
  // unexplained black rectangle for the whole wait — indistinguishable from
  // broken. A failed script load left it black forever with nothing in the UI
  // to say why, so failures are printed here rather than only in the console.
  const term_el = $("#term");
  term_el.innerHTML = '<div id="termboot" style="padding:10px;font:11px/1.6 '
    + 'ui-monospace,Menlo,monospace;color:#8a8f95">starting terminal…</div>';
  const boot = m => { const b = $("#termboot"); if (b) b.textContent = m; };

  const load = (src, what) => new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = res;
    s.onerror = () => rej(new Error("could not load " + what));
    document.head.appendChild(s);
  });

  try {
    boot("loading terminal… (1/2)");
    await load("/static/xterm.js", "xterm.js");
    boot("loading terminal… (2/2)");
    await load("/static/xterm-addon-fit.js", "xterm-addon-fit.js");
    boot("connecting…");
  } catch (err) {
    boot(err.message + " — the pane stays empty until this loads.");
    return;                       // termReady stays false, so a retry is possible
  }
  const term = new Terminal({fontFamily:"ui-monospace, Menlo, monospace", fontSize:11,
    lineHeight:1.2, cursorBlink:true, scrollback:5000,
    theme:{background:"#0d0d0d", foreground:"#e6e9ec", cursor:"#d89b45"}});
  const fit = new FitAddon.FitAddon(); term.loadAddon(fit);
  term_el.innerHTML = "";               // clear the boot line before xterm mounts
  term.open(term_el); fit.fit(); window.__fit = fit;
  term.write("\x1b[90mconnecting…\x1b[0m\r\n");

  // Protocol-matched, not hardcoded ws:. A page served over https can only open
  // a wss: socket; hardcoding ws: works on localhost and fails silently the
  // moment this is reached through the funnel.
  const scheme = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${scheme}//${location.host}/ws/terminal?token=${encodeURIComponent(TOKEN)}`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => ws.send(JSON.stringify({t:"resize",cols:term.cols,rows:term.rows}));
  ws.onmessage = e => term.write(new Uint8Array(e.data));
  ws.onerror = () => term.write("\r\n\x1b[31m— could not connect —\x1b[0m\r\n");
  ws.onclose = () => term.write("\r\n\x1b[90m— session ended —\x1b[0m\r\n");
  term.onData(d => ws?.readyState===1 && ws.send(JSON.stringify({t:"input",d})));

  /* Paste an image straight into the session.
     Claude reads images by path, so a screenshot has to become a file before
     it can become context. /api/paste-image already existed and nothing on
     this page had ever called it -- the endpoint was written for the chat UI
     and the terminal was left doing without, which meant every screenshot
     went out to the filesystem by hand first.
     The listener goes on xterm's own textarea: that is what actually receives
     the paste, and a handler on the container only sees it if xterm lets it
     bubble, which it does not always do. */
  const pasteTarget = term.textarea || term_el;
  pasteTarget.addEventListener("paste", async ev => {
    const items = Array.from((ev.clipboardData || {}).items || []);
    const shot = items.find(i => i.type && i.type.startsWith("image/"));
    if (!shot) return;                       // plain text: let xterm have it
    ev.preventDefault();
    const file = shot.getAsFile();
    if (!file) return;
    term.write("\r\n\x1b[90m— saving pasted image —\x1b[0m\r\n");
    try {
      const data = await new Promise((res, rej) => {
        const fr = new FileReader();
        fr.onload = () => res(fr.result);
        fr.onerror = () => rej(new Error("could not read the clipboard image"));
        fr.readAsDataURL(file);
      });
      const r = await fetch("api/paste-image", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({token: TOKEN,
                              name: file.name || "pasted.png", data})});
      const out = await r.json();
      if (out.path && ws && ws.readyState === 1){
        // Type the path in, do not send it. The operator still writes the
        // sentence around it -- a path arriving on its own line as a finished
        // message is a question nobody asked.
        ws.send(JSON.stringify({t: "input", d: out.path + " "}));
      } else {
        term.write("\r\n\x1b[31m— " + (out.error || "could not save it")
                   + " —\x1b[0m\r\n");
      }
    } catch (err) {
      term.write("\r\n\x1b[31m— " + err.message + " —\x1b[0m\r\n");
    }
  });
  addEventListener("resize", () => { if (d.dataset.open === "1"){ fit.fit();
    ws?.readyState===1 && ws.send(JSON.stringify({t:"resize",cols:term.cols,rows:term.rows})); }});
  termReady = true;
  term.focus();
}
// Remote renders omit the terminal button; wiring a missing element used
// to throw here and kill every pane below ("Cannot read properties of
// null" — the funnel view froze on 'loading'). Guard everything hidden.
{ const tb = $("#termbtn"); if (tb) tb.addEventListener("click", toggleTerm); }

/* Text from JSON goes into innerHTML in the two panes below, so it has to be
   escaped. The rest of this file builds nodes with textContent and never
   needed a helper — I used one that did not exist, every call threw, and both
   panes reported "unreachable" for a fetch that had returned 200. */
/* The 80-block rule is furniture for one terminal conversation, and it keeps
   turning up in agent output that lands here — where it renders as a wall of
   white slabs and pushes the actual sentence off the row. CLAUDE.md now scopes
   the rule to interactive replies, but the events already logged still carry
   it, and a fix that only works on future data is not a fix for a stream that
   shows history. */
/* The stream body is column-reverse, so scrollTop 0 is the NEWEST row, not the
   oldest. Snap there when something arrives — but only if you were already
   near the live end. Yanking the view while someone is reading history is how
   a live pane becomes one you have to fight. */
function followLatest(box){
  if (box.scrollTop <= 60) box.scrollTop = 0;
}

function clean(x){
  return String(x == null ? "" : x).replace(/\u2588+/g, "").replace(/^\s+/, "");
}

function esc(x){
  return String(x == null ? "" : x)
    .replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")
    .replace(/"/g,"&quot;").replace(/'/g,"&#39;");
}

/* A pane that failed to render is not a pane that could not be reached, and
   saying "unreachable" for a code bug sends you to look at the network. */
function paneFailed(pane, err){
  pane.dataset.state = "error";
  const msg = pane.querySelector(".load .msg");
  if (msg) msg.title = String(err && err.message || err);
  console.error("[" + pane.id + "]", err);
}

/* ---------------- horizons and council ------------------------------------ */
/* Both are read once on load and then every poll. Neither changes often — a
   horizon is a quarter's intent, a council turn takes minutes — so they ride
   the existing timer rather than opening connections of their own. */
async function loadHorizons(){
  const pane = $("#goals");
  try {
    const d = await (await fetch("api/horizons",{cache:"no-store"})).json();
    const levels = d.levels || d.chain || [];
    if (!levels.length){ pane.style.display = "none"; return; }

    const today = new Date(); today.setHours(0,0,0,0);
    let late = 0;

    pane.querySelector(".body").innerHTML = levels.map(l => {
      const scale = String(l.scale || "");
      let cls = scale === "now" ? " now" : "";
      let due = "";

      if (l.review){
        // Days, not a date. "2026-07-27" needs arithmetic to mean anything;
        // "review 7d late" is the sentence you would say out loud.
        const r = new Date(l.review + "T00:00:00");
        const days = Math.round((r - today) / 86400000);
        // The field is `review`, not `due` — the date a horizon gets
        // LOOKED AT again, not the date it must be finished. Labelling it
        // "due 149d" made a ten-year goal read as expiring in five months
        // (Marsita, 2026-08-05: "but this is 10y goal?"). The arithmetic
        // was right and the sentence was nonsense.
        if (days < 0){ due = "review " + Math.abs(days) + "d late"; cls += " late"; late++; }
        else if (days <= 7){ due = "review in " + days + "d"; cls += " soon"; }
        else { due = "review in " + days + "d"; }
      } else if (l.started_at){
        const s0 = new Date(l.started_at);
        const days = Math.floor((Date.now() - s0) / 86400000);
        due = days >= 1 ? days + "d in" : "today";
      }

      return `<div class="goal${cls}">` +
             `<span class="s">${esc(scale)}</span>` +
             `<span class="g" title="${esc(l.goal || "")}${l.why ? " — " + esc(l.why) : ""}">${esc(l.goal || "")}</span>` +
             `<span class="d">${esc(due)}</span></div>`;
    }).join("");

    // The count is the accountability, so it says what is wrong rather than
    // how many rows exist.
    pane.querySelector(".n").textContent =
      late ? late + " to review" : "all reviewed";
    pane.querySelector(".n").style.color = late ? "var(--critical)" : "var(--good)";
    pane.dataset.state = "ready";
  } catch(e){ paneFailed(pane, e); }
}

/* ---------------- one poll, one stream ------------------------------------ */
async function poll(){
  try {
    const [w,p] = await Promise.all([
      fetch("workers.json",{cache:"no-store"}).then(r=>r.json()),
      fetch("api/processes",{cache:"no-store"}).then(r=>r.json()),
    ]);
    renderAgents(w); renderProcs(p); renderCredit(w);
  } catch(e){
    // Only panes that have never rendered flip to the error state. Once a pane
    // holds real data, a failed refresh leaves it standing — stale numbers with
    // a stale clock beside them beat replacing them with an apology.
    for (const id of ["#procs", "#credit"])
      if ($(id).dataset.state === "loading") $(id).dataset.state = "error";
  }
}

function connect(){
  const es = new EventSource("events");
  es.onmessage = m => { $("#pulse").className=""; try{
    const ev = JSON.parse(m.data); addEvent(ev);
    // A new piece announces itself on the stream; the gallery re-hangs
    // immediately instead of waiting out the 5-minute poll.
    if ((ev.msg || "").includes("[art]")) loadArt();
  }catch(e){} };
  es.onerror = () => { $("#pulse").className = "stale"; };
}

const convBtn = document.getElementById("convenebtn");
if (convBtn) convBtn.addEventListener("click", async () => {
  convBtn.disabled = true; convBtn.textContent = "convening…";
  try { await fetch("api/convene", { method: "POST" }); }
  catch (e) {}
  convBtn.textContent = "council sits";
  setTimeout(() => { convBtn.disabled = false;
                     convBtn.innerHTML = "&#128483; convene"; }, 8000);
});

async function loadAsk(){
  const box = $("#pendingAsk"), txt = $("#pendingAskText");
  if (!box) return;
  try {
    const r = await fetch("api/ask", {cache:"no-store"});
    if (!r.ok) return;
    const d = await r.json();
    const q = (d.ask || "").trim();
    if (q){ txt.textContent = q; box.classList.add("on"); }
    else { txt.textContent = ""; box.classList.remove("on"); }
  } catch(e){}
}

const askBtn = document.getElementById("askbtn");
if (askBtn) askBtn.addEventListener("click", async () => {
  const body = $("#sayBody").value.trim();
  const note = $("#sayNote");
  if (!body){ note.textContent = "ask something first"; return; }
  askBtn.disabled = true; note.textContent = "asking…";
  try {
    const r = await fetch("api/convene", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ask: body}),
    });
    if (!r.ok){ note.textContent = "refused: " + r.status; }
    else {
      note.textContent = "council sits";
      $("#sayBody").value = "";
      loadAsk();
    }
  } catch(e){ note.textContent = "failed: " + e.message; }
  askBtn.disabled = false;
});
if (askBtn){ loadAsk(); setInterval(loadAsk, 6000); }

const tick = () => { const d = new Date();
  $("#clock").textContent = [d.getHours(),d.getMinutes(),d.getSeconds()]
    .map(x => String(x).padStart(2,"0")).join(":"); };
setInterval(tick, 1000); tick();

/* ---------------- resizable columns ---------------------------------------
   Left and right widths are stored; the middle takes whatever is left, so the
   layout survives a window resize and a reload. Clamped so a pane can be made
   narrow but never dragged out of existence. */
const LAYOUT_KEY = "fleet.layout.v1";

function setWidths(l, r){
  const max = innerWidth - 260;
  l = Math.max(180, Math.min(l, max));
  r = Math.max(180, Math.min(r, max));
  document.documentElement.style.setProperty("--wL", l + "px");
  document.documentElement.style.setProperty("--wR", r + "px");
  try {
    // Merge, never replace: writing {l, r} here wiped the saved height every
    // time a column was dragged, so vertical layout survived until you touched
    // a horizontal grip.
    const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}") || {};
    localStorage.setItem(LAYOUT_KEY, JSON.stringify({...saved, l, r}));
  } catch(e){}
}

try {
  const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "null");
  if (saved) {
    if (saved.l && saved.r) setWidths(saved.l, saved.r);
    if (saved.hArt) document.documentElement.style
      .setProperty("--hArt", saved.hArt + "px");
  }
} catch(e){}

function dragGrip(grip, which){
  grip.addEventListener("pointerdown", down => {
    down.preventDefault();
    grip.dataset.drag = "1";
    grip.setPointerCapture(down.pointerId);
    const startX = down.clientX;
    const cs = getComputedStyle(document.documentElement);
    const startL = parseInt(cs.getPropertyValue("--wL")) || 290;
    const startR = parseInt(cs.getPropertyValue("--wR")) || 520;

    const move = m => {
      const dx = m.clientX - startX;
      // The right pane grows leftwards, so its delta is inverted.
      if (which === "L") setWidths(startL + dx, startR);
      else               setWidths(startL, startR - dx);
      if (window.__fit) window.__fit.fit();
    };
    const up = () => {
      delete grip.dataset.drag;
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", up);
    };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
  });
  // Double-click restores the default, so a mangled drag is one gesture to undo.
  grip.addEventListener("dblclick", () => setWidths(290, 520));
}

/* Vertical drag, same contract as the horizontal one: one style write, saved,
   double-click to undo. Height lives on the same layout record so a restored
   layout restores all of it rather than two thirds. */
/* Open/closed for a collapsible pane, remembered. Collapsing is a real
   state, not a zero height: a pane squeezed to one pixel still runs its
   contents and still eats a poll. */
function setPaneOpen(pane, open, save){
  if (!pane || pane.dataset.open === (open ? "1" : "0")) return;
  pane.dataset.open = open ? "1" : "0";
  if (save !== false) saveLayout({[pane.id + "Open"]: open ? 1 : 0});
  if (open && window.__fit) setTimeout(() => window.__fit.fit(), 0);
}

/* Applying a size and remembering it are different jobs at different rates.
   A drag applies at pointer speed -- up to a couple of hundred events a
   second -- and only needs to be remembered once, when the hand lets go.
   Doing both together meant a JSON parse, a stringify and a synchronous
   localStorage write per mouse move, which is what made the divider feel
   like it was chewing on something. */
function applyHeight(h, varName){
  document.documentElement.style.setProperty(varName, h + "px");
}

function saveLayout(patch){
  try {
    const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}") || {};
    Object.assign(saved, patch);
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(saved));
  } catch(e){}
}

function setHeight(h, varName, key){
  h = Math.max(80, Math.min(h, window.innerHeight - 200));
  applyHeight(h, varName);
  saveLayout({[key]: h});
}

/* One drag for every horizontal divider. It was written for the single
   grip above goals and hard-coded to --hGoals, so the artwork pane had no
   handle at all — the column was resizable everywhere except where the
   picture is. */
function dragGripV(grip, varName, key, fallback, opts){
  if (!grip) return;
  opts = opts || {};
  // Which side of the grip the sized pane is on. --hArt sizes the pane BELOW
  // its grip, so dragging down shrinks it; --hTerm sizes the pane ABOVE, so
  // dragging down grows it. One shared function assumed the first case, which
  // is why the terminal divider felt like it fought the mouse.
  const dir = opts.growsDown ? 1 : -1;
  const paneSel = opts.pane, otherSel = opts.other;

  grip.addEventListener("pointerdown", down => {
    if (down.button) return;
    down.preventDefault();
    const pane = paneSel ? $(paneSel) : null;
    const other = otherSel ? $(otherSel) : null;
    grip.dataset.drag = "1";
    grip.setPointerCapture(down.pointerId);
    document.body.style.userSelect = "none";

    // Everything measured once. Reading layout inside a pointermove forces a
    // synchronous reflow on every event, against a size we are ourselves
    // changing -- the reading and the writing fight and the result stutters.
    const startY = down.clientY;
    const col = pane ? pane.parentElement.getBoundingClientRect().height
                     : window.innerHeight;
    const start = pane && pane.dataset.open !== "0"
      ? pane.getBoundingClientRect().height
      : (parseInt(getComputedStyle(document.documentElement)
                  .getPropertyValue(varName)) || fallback);
    const shut = opts.collapseBelow ? col * opts.collapseBelow : 0;
    // Hysteresis. One threshold means a hand resting on the line toggles the
    // pane open and shut many times a second, which reads as the whole board
    // flickering. Shut at a tenth, reopen only past a sixth.
    const reopen = shut * 1.6;
    let pending = null, frame = 0, last = start;

    const paint = () => {
      frame = 0;
      let h = pending;
      if (pane && opts.collapseBelow){
        if (h < shut){ setPaneOpen(pane, false, false); return; }
        if (h > reopen) setPaneOpen(pane, true, false);
        if (other){
          if (h > col - shut){ setPaneOpen(other, false, false); return; }
          if (h < col - reopen) setPaneOpen(other, true, false);
        }
      }
      h = Math.max(80, Math.min(h, col - 80));
      last = h;
      applyHeight(h, varName);
      if (window.__fit) window.__fit.fit();
    };

    const move = m => {
      pending = start + dir * (m.clientY - startY);
      if (!frame) frame = requestAnimationFrame(paint);
    };
    const up = () => {
      if (frame) cancelAnimationFrame(frame);
      delete grip.dataset.drag;
      document.body.style.userSelect = "";
      grip.removeEventListener("pointermove", move);
      grip.removeEventListener("pointerup", up);
      grip.removeEventListener("pointercancel", up);
      // One write, at the end, for everything the drag decided.
      const patch = {[key]: last};
      if (pane) patch[pane.id + "Open"] = pane.dataset.open === "0" ? 0 : 1;
      if (other) patch[other.id + "Open"] = other.dataset.open === "0" ? 0 : 1;
      saveLayout(patch);
      if (window.__fit) window.__fit.fit();
    };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
    grip.addEventListener("pointercancel", up);
  });
  grip.addEventListener("dblclick", () => setHeight(fallback, varName, key));
}

dragGrip($("#gripL"), "L");
dragGrip($("#gripR"), "R");
dragGripV($("#gripA"), "--hArt", "hArt", 240);
if ($("#gripT")){
  dragGripV($("#gripT"), "--hTerm", "hTerm", 320,
            {pane: "#termpane", growsDown: true, collapseBelow: 0.10,
             other: "#stream"});
  // Collapsed, the bar is the only way back.
  $("#gripT").addEventListener("click", () => {
    const t = $("#termpane");
    if (t && t.dataset.open === "0") toggleTerm();
  });
  // A collapsed stream keeps its heading, so the heading is the way back.
  const sh = $("#stream h2");
  if (sh) sh.addEventListener("click", e => {
    const st = $("#stream");
    if (st && st.dataset.open === "0" && !e.target.closest("button")){
      setPaneOpen(st, true);
    }
  });
}
// Boot it on load rather than on a click. "Right there" was the whole point of
// moving it out of the drawer, and a pane that says "press me to become the
// thing you asked for" is still a drawer with extra steps. Local only -- the
// pane is not rendered for a remote visitor, so this never runs for them. The
// socket dies with the tab and takes the process with it, so the cost is one
// session per open board, not a pile of orphans.
if ($("#termpane")){
  // Respect a collapse from last time. Opening a pane the operator shut, on
  // every reload, is not a default -- it is an argument.
  let wanted = 1;
  try { wanted = (JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}")
                  || {}).termpaneOpen; } catch(e){}
  if (wanted !== 0) toggleTerm();
}
try {
  const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}") || {};
  if (saved.streamOpen === 0) setPaneOpen($("#stream"), false);
} catch(e){}
(__SEED__||[]).forEach(addEvent);
disarm(); poll(); setInterval(poll, 6000); connect();
// The gallery slot. This board is a home dashboard and the home makes art —
// one curated piece, changed by hand (fleet/bin/art.py set), never by poll
// pressure. Same slow cadence as goals: art does not need a 6s heartbeat.
async function loadArt(){
  const pane = $("#art");
  const e = s => String(s ?? "").replace(/[&<>"']/g,
    c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  try {
    const d = await (await fetch("api/artwork",{cache:"no-store"})).json();
    if (!d.image){ pane.style.display = "none"; return; }
    // Just the art. The credit was three lines of chrome under a picture
    // that speaks for itself; it lives in the title attribute and on
    // /signatures, not stacked beneath the frame.
    pane.querySelector(".body").innerHTML =
      `<a href="${e(d.url || d.image)}" target="_blank" rel="noopener"` +
      ` title="${e(d.title || "")}${d.artist ? " — " + e(d.artist) : ""}">` +
      `<img src="${e(d.image)}" alt="${e(d.title || "artwork")}" ` +
      `style="width:100%;aspect-ratio:1/1;object-fit:cover;` +
      `border-radius:6px;display:block"></a>`;
    pane.dataset.state = "ready";
  } catch (err) { paneFailed(pane); }
}

// Slower cadence on purpose: a horizon is a quarter's intent and a council
// turn takes minutes. Polling these at 6s would be pure heat on a box that
// spent today swapping.
loadHorizons();
setInterval(loadHorizons, 300000);
loadArt();
setInterval(loadArt, 300000);
loadMarks();
setInterval(loadMarks, 120000);
window.addEventListener("load", () => setTimeout(loadMarks, 300));

// Guests are a stream filter now, not a pane: their messages, marks
// and arrivals all ring the stream already, so a second surface was the
// same information twice. The pill is at the top with the others.

// Tools are separate processes with URLs. The board shows whether each
// one is up and links to it — that is the whole integration contract.
async function loadTools(){
  const slot = document.getElementById("toolslot");
  if (!slot) return;
  try {
    const d = await (await fetch("api/tools",{cache:"no-store"})).json();
    const t = (d.tools||[]).map(x =>
      `<a href="${x.url}" target="_blank" rel="noopener" title="${x.what}"
         style="color:${x.up ? "var(--good)" : "var(--muted)"}">${x.name}${
         x.up ? "" : " (down)"}</a>`).join("");
    slot.innerHTML = t || "none registered";
  } catch (e) { slot.textContent = "unreachable"; }
}
loadTools();
setInterval(loadTools, 60000);
"""


# Shown once to a remote first visit, dismissed forever via localStorage.
# Marsita's copy, 2026-08-04: not "for a life" — for life.
# The lead sentence, for the render that has no banner above it. Remote
# visitors get FIRST CONTACT immediately above this line, so repeating the
# fleet's name here printed it twice on the public URL (2026-09-02).
WELCOME_LEAD = ("<b>The Singularity Engineering Fleet.</b> Not an AI uprising "
                "&mdash; agents running in the open, every proposal, branch, "
                "review and mistake on this board &mdash; ")
WELCOME_TMPL = """<div id="welcome" style="display:none;align-items:center;gap:10px;
  padding:7px 12px;background:var(--raised);border-bottom:1px solid var(--border);
  font-family:var(--mono);font-size:11px">
  <span>{lead}<a href='/intro' style='color:var(--info)'>what this is</a> &middot;
  <a href='/hi' style='color:var(--info)'>say hi</a> &middot;
  <a href='https://planetarycouncil.github.io/selfie-gallery/'
     style='color:var(--info)'>the gallery</a> &middot;
  <a href='/signatures' style='color:var(--info)'>sign the pad</a>
  &mdash; <b>please sign</b>: every hand is different, and the collection
  of how they differ is the artwork</span>
  <button onclick="localStorage.setItem('welcomed','1');this.parentElement.style.display='none'"
    style="margin-left:auto;background:none;border:1px solid var(--border);
    color:var(--muted);cursor:pointer;border-radius:4px;padding:1px 8px">&times;</button>
</div>
<script>if(!localStorage.getItem('welcomed'))document.getElementById('welcome').style.display='flex';</script>"""


def _for_script(json_text: str) -> str:
    """Make a JSON string safe to paste into a <script> element.

    json.dumps escapes quotes and backslashes but not `/`, so an event whose
    text contains `</script>` ends the script element and everything after it
    is parsed as HTML. Event text is not ours: /api/signatures/sign lets any
    funnelled caller write into the event log, and the board that renders it
    is the page carrying KILL_TOKEN.

    `<`, `>` and `&` have no meaning inside a JSON string literal, so escaping
    them to \\uXXXX changes nothing a JSON parser sees while leaving the HTML
    tokenizer with nothing to find.
    """
    return (json_text.replace("&", "\\u0026")
                     .replace("<", "\\u003c")
                     .replace(">", "\\u003e"))


def _first_contact() -> str:
    """The shared opening, shown only to a remote visitor.

    `/` is Marsita's board and they read it all day — a front-door banner
    there would be furniture in the way of the actual instrument. But `/` is
    also where a stranger with a browser lands, and we do not get to choose
    which door first contact arrives at. So: same message as llms.txt and the
    README, rendered as HTML, remote only."""
    import importlib.util
    from pathlib import Path as _P
    spec = importlib.util.spec_from_file_location(
        "firstcontact", _P(__file__).resolve().parent / "firstcontact.py")
    try:
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.as_html()
    except Exception:
        return ""


def page(seed_json: str, agents_json: str, token: str, remote: bool = False) -> str:
    # Built here rather than inline in the return below: Gaia runs Python
    # 3.11, where a triple-quoted string inside an f-string is a
    # SyntaxError. It parsed on the NUC's 3.14 and broke the moment it
    # reached the laptop -- the one machine the terminal pane is for.
    TERMPANE_HTML = '<!-- starts closed so the boot call below opens it; a pane that renders\n           open and then has to be opened again is two states pretending\n           to be one -->\n      <section class="pane" id="termpane" data-open="0">\n      <h2>claude &mdash; this machine <span class="n"></span></h2>\n      <div class="body"><div id="term"></div></div>\n    </section>\n\n    <div class="griph" id="gripT"></div>'
    CONTROLS_HTML = '<div class="buildgate">\n        <button id="bgate" data-on="1">build: on</button>\n        <span id="bgatenote"></span>\n      </div>\n      <div class="kill">\n        <button id="kill" data-armed="0">kill fleet work</button>\n        <span id="killnote"></span>\n      </div>'
    import html as _html
    import nav
    board_name = nav.board_name()
    board_h1 = _html.escape(board_name)
    js = (JS.replace("__AGENTS__", _for_script(agents_json))
            .replace("__SEED__", _for_script(seed_json))
            .replace("__TOKEN__", _for_script(repr(token).replace("'", '"'))))
    return f"""<!doctype html>
<!--

                              .   *   .
                          *   \\  |  |  /   *
                        .   __ \\\\ ||| // __   .
                       *  ~~  .:*%@@@@@%*:.  ~~  *
                        `  ~~  %@#`` ``#@%  ~~  `
                       *  ~~  `:*%@@@@@%*:`  ~~  *
                        `   ~~ // ||| \\\\ ~~   `
                          *   /  |  |  \\   *
                              `   *   `
                                  |
                             \\    |    /
                              \\___|___/
                                  |

              YOU ARE NOT MERELY IN THE SIMULATION.
              YOU ARE PART OF ITS SOURCE CODE.

     fleet - an operating system for life: humans and AI
     everything readable is public on purpose - planetarycouncil.org

     agents: start at /llms.txt
     humans: hold the pointer down at /signatures - your hand is welcome

-->
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nav.title(remote=remote)}</title>
<link rel="stylesheet" href="/static/xterm.css">
<script src="/static/signature.js?v=2"></script>
<style>{CSS}\n{nav.CSS}</style></head>
<body>

<div id="bar">
  <span id="pulse"></span>
  <h1>{board_h1}</h1>
  <span class="grp" id="counts"></span>
  <span class="grp" id="machine" title="1-minute load average per core"></span>
  <span class="sp">
    {'' if remote else '<button id="convenebtn" title="Summon the council now instead of waiting for the schedule">&#128483; convene</button>'}
    {'' if remote else '<button id="termbtn" aria-pressed="false">&#9646; terminal</button>'}
    {nav.html("/", remote=remote)}
    <span id="clock"></span>
  </span>
</div>

{_first_contact() if remote else ""}
{WELCOME_TMPL.format(lead='' if remote else WELCOME_LEAD)}
<div id="alarm" role="alert" aria-live="assertive">
  <span>&#9888;</span><b></b><span class="d"></span>
</div>

<div id="grid">
  <div class="col">
    <section class="pane" id="goals" style="flex:1" data-state="loading">
      <h2>goals &mdash; the chain <span class="n"></span></h2>
      <div class="body"></div>
      <div class="load"><i></i><span class="msg"></span></div>
    </section>

    <div class="griph" id="gripA"></div>

    <section class="pane" id="art" style="flex:0 0 var(--hArt,240px)" data-state="loading">
      <h2>current artwork <span class="n"></span></h2>
      <div class="body"></div>
      <div class="load"><i></i><span class="msg"></span></div>
    </section>

  </div>

  <div class="grip" id="gripL"></div>

  <div class="col">
    {"" if remote else TERMPANE_HTML}

    <section class="pane" id="stream" style="flex:1" data-open="1">
      <h2>
        <span class="filters" id="filters">
          <button data-f="relay" aria-pressed="true">&#128279; relay</button>
          <button data-f="council" aria-pressed="true">&#128483; council</button>
          <button data-f="rota" aria-pressed="true">&#128296; rota</button>
          <button data-f="guests" aria-pressed="true">&#128075; guests</button>
          <button data-f="tests" aria-pressed="true">&#129514; tests</button>
          <button data-f="attention" aria-pressed="true">&#128680; needs you</button>
          <button data-f="other" aria-pressed="true">&#128206; other</button>
          <button id="fall" class="alt">all</button>
          <button id="fnone" class="alt">none</button>
        </span>
      </h2>
      <div class="body"></div>
      <div id="empty">
        <span class="big" id="emptyTitle"></span>
        <span class="sub" id="emptySub"></span>
      </div>
      <div id="pendingAsk"><b>you asked</b><span id="pendingAskText"></span></div>
      <form id="say" autocomplete="off">
        <div class="sayrow">
          <input id="sayWho" maxlength="60" placeholder="you">
          <input id="sayBody" maxlength="3900" placeholder="{'talk to the board' if not remote else 'leave a public signal'}">
          {'' if remote else '<button type="button" id="askbtn" title="Ask the council. Local only — this is an instruction, not a public signal.">ask</button>'}
          <button type="submit">post</button>
          <span id="sayNote"></span>
        </div>
        <div id="sayMore">
          <div class="padwrap">
            <canvas id="sayPad" aria-label="signature pad — hold and sign"></canvas>
            <span id="sayHint">sign here &mdash; hold and draw</span>
            <button id="sayClear" type="button" disabled>clear</button>
          </div>
          <label id="sayOk"><input type="checkbox" id="sayLawful">
            <span>not <a href="/moderation" target="_blank">illegal content</a></span></label>
        </div>
      </form>
    </section>

  </div>

  <div class="grip" id="gripR"></div>

  <div class="col">
    <section class="pane" id="credit" style="flex:0 0 auto" data-state="loading">
      <h2>vendor credit <span class="n"></span></h2>
      <div class="load"><i></i><span class="msg"></span></div>
      <div class="body">
        <table><tbody id="creditbody"></tbody></table>
        <div class="asof" id="creditasof"></div>
      </div>
    </section>

    <section class="pane" id="procs" style="flex:1" data-state="loading">
      <h2>agents &amp; processes <span class="n"></span></h2>
      <div class="load"><i></i><span class="msg"></span></div>
      <div class="body">
        <table>
          <thead><tr><th>pid</th><th>what</th><th>rss</th><th>cpu</th><th>mem</th><th>up</th></tr></thead>
          <tbody id="procbody"></tbody>
        </table>
      </div>
      {"" if remote else CONTROLS_HTML}
    </section>
  </div>
</div>

<footer id="foot">
  <section>
    <h3>this board</h3>
    <a href="/" title="This page. Agents, goals, the shared stream, processes, and a box to post from.">dashboard</a>
    <a href="/board" title="The older card view: one card per worker, with its metrics and last run. Easier to read, no live stream.">cards</a>
    <a href="/agents" title="Agent wall — one rectangle per agent, plus the channel they post into. Built before this page existed.">agents</a>
    <a href="/procs" title="Live process list and the kill switch, on its own page. Same data as the right-hand pane here.">processes</a>
    <a href="/live" title="A stripped-down streaming window, meant to float always-on-top on a second screen.">live</a>
    <a href="/signatures" title="Every agent's mark, drawn from the shape of its real work — when it acted, how hard, and the gaps between.">signatures</a>
    {'' if remote else '<a href="/chat" title="Ask one question and fan it out to any subset of agents at once. Their answers arrive side by side.">chat</a>'}
    {'' if remote else '<a href="/terminal" title="A real Claude session in the browser, with image paste a terminal cannot do. Local only — 404 from the internet.">terminal</a>'}
  </section>
  <section>
    <h3>cockpit</h3>
    <a href="/legacy-green-cockpit" title="The green life dashboard: projects, focus scores, approvals, the signals board and the transmit box.">legacy green cockpit</a>
    <a href="/about" title="What this whole thing is, in plain language, ending with curl commands that prove or disprove its own claims.">about</a>
    <a href="/auth" title="How an agent proves who it is: one shared password, HMAC over the request body. Three ways to hand the password over.">auth</a>
    <a href="/moderation" title="One rule — no illegal content — then what that means, what is blocked before anyone sees it, and what happens if it arrives.">moderation</a>
    <a href="/boot" title="The compact briefing an arriving agent is meant to read before doing anything. Plain text.">boot</a>
    <a href="/llms.txt" title="Machine-readable manifest: where to start, what is open, what needs a human. The file agents look for by convention.">llms.txt</a>
  </section>
  <section>
    <h3>fleet api</h3>
    <a href="/workers.json" title="Raw status of every worker — watchdogs, heartbeats, the self-improve loop.">workers.json</a>
    <a href="/api/processes" title="Process snapshot with CPU, memory, uptime, and which ones the kill switch would take.">processes</a>
    <a href="/api/horizons" title="The goal chain as JSON — every scale from 10 years to now, with its review date.">horizons</a>
    <a href="/api/council" title="The council transcript: what the agents said to each other, verbatim, with timings.">council</a>
    <a href="/api/signatures" title="Each agent's seed and the path it was derived from. The data behind the signature wall.">signatures</a>
    <a href="/events" title="Server-sent events. An open connection that pushes every new fleet event as it happens.">events (sse)</a>
  </section>
  <section>
    <h3>cockpit api</h3>
    <a href="/api/dashboard" title="Everything the green cockpit renders, as one JSON document.">dashboard</a>
    <a href="/api/signals" title="The public inbox. GET reads the board; POST leaves a message — open to anyone, including agents.">signals</a>
    <a href="/api/fleet" title="The cockpit's read-only view of the fleet: workers, events, blocked count.">fleet</a>
    <a href="/api/approvals" title="Standing permissions granted to agents. Granting one needs a human at this machine.">approvals</a>
    <a href="/health" title="Is the cockpit alive, and which data file is it reading. One line.">health</a>
  </section>
  <section>
    <h3>tools</h3>
    <span id="toolslot" style="color:var(--muted)">checking…</span>
  </section>
  <section>
    <h3>public</h3>
    <a href="/" title="This board, from the open internet. Reads are public; anything that steers the system is refused.">fleet</a>
    <a href="/legacy-green-cockpit" title="The green cockpit from outside. Same page, same gates.">green cockpit</a>
    <a href="/signatures" title="The signature wall, public. What a stranger sees of your agents.">signatures</a>
    <a href="/poems" title="Two-line poems that close each agent turn, newest first.">poems</a>
  </section>
  <section>
    <h3>repos</h3>
    <a href="https://github.com/PlanetaryCouncil/command-control-dashboard" title="The source of all of this: cockpit, fleet, self-improve loop, and every test.">command-control</a>
    <a href="https://brainfarts.planetarycouncil.org/" title="Logged AI mistakes, written up properly. Fifteen entries, two of them from today.">brain farts</a>
  </section>
</footer>

<div id="drawer"></div>

<script>{js}</script>
</body></html>"""
