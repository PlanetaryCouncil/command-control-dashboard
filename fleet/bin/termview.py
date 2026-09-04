#!/usr/bin/env python3
"""The board pane: a one-way view of the session, and a box to send into it.

Weeks went into making a real xterm in the browser work, and the whole thing
was still the wrong product. Typing into a browser terminal is worse than
typing into a real one and always will be -- the latency, the key handling, the
output racing the cursor. Marsita has a terminal on the laptop that does this
perfectly (`tmux attach -t board` joins the very same session), so the browser
stops competing with it and does the thing it is genuinely better at: being
glanceable from across the room.

So the screen here is READ-ONLY. Keys do not reach the pseudo-terminal from
this page at all. What reaches it is whatever gets typed in the box and sent on
purpose -- composed locally, so it feels native, with none of the round trip.

Above the screen is the only question the pane exists to answer: is it done
yet? Working, waiting for you, or idle; how long it has been; how long turns
like this usually take; and a distinct shout when it has run past twice that,
because that is the moment worth walking over for.

Image paste survives the change. Pasting an image into a terminal normally does
nothing -- a terminal takes keystrokes. Here it is uploaded, written to disk,
and its path dropped into the box, so Claude reads it exactly as it would from
the command line.
"""

CSS = """
:root{
  --ground:#F4F6F8; --surface:#FFFFFF; --raised:#EDF0F3;
  --border:#DCE1E7; --ink:#171B21; --ink-2:#414B58; --muted:#5C6674;
  --good:#0ca30c; --warning:#fab219; --critical:#d03b3b;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{--ground:#0d0d0d;--surface:#1a1a19;--raised:#232322;
    --border:#2f2f2d;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;}
}
:root[data-theme="dark"]{--ground:#0d0d0d;--surface:#1a1a19;--raised:#232322;
  --border:#2f2f2d;--ink:#fff;--ink-2:#c3c2b7;--muted:#898781;}
:root[data-theme="light"]{--ground:#F4F6F8;--surface:#FFFFFF;--raised:#EDF0F3;
  --border:#DCE1E7;--ink:#171B21;--ink-2:#414B58;--muted:#5C6674;}
*{box-sizing:border-box;}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  font-size:14px;display:flex;flex-direction:column;height:100vh;overflow:hidden;}
header{display:flex;align-items:center;gap:11px;padding:9px 14px;flex:none;
  border-bottom:1px solid var(--border);background:var(--surface);flex-wrap:wrap;}
h1{font-family:var(--mono);font-size:13px;font-weight:600;margin:0;}
header .sub{font-family:var(--mono);font-size:10px;color:var(--muted);}
#dot{width:7px;height:7px;border-radius:50%;background:var(--muted);}
#dot.on{background:var(--good);} #dot.off{background:var(--critical);}
#term{flex:1;min-height:0;padding:6px 8px;background:#0d0d0d;}
#pane{flex:none;display:flex;align-items:baseline;gap:14px;padding:10px 14px;
  border-bottom:1px solid var(--border);background:var(--surface);flex-wrap:wrap;}
#state{font-family:var(--mono);font-size:26px;font-weight:600;letter-spacing:-.5px;
  line-height:1;}
#state.working{color:var(--good);} #state.waiting{color:var(--warning);}
#state.idle{color:var(--muted);} #state.over{color:var(--critical);}
#clock{font-family:var(--mono);font-size:26px;font-weight:600;line-height:1;
  color:var(--ink-2);font-variant-numeric:tabular-nums;}
#guess{font-family:var(--mono);font-size:11px;color:var(--muted);}
#over{font-family:var(--mono);font-size:12px;font-weight:600;color:var(--critical);
  display:none;}
#over.on{display:inline;}
#drop{position:fixed;inset:0;display:none;align-items:center;justify-content:center;
  background:rgba(13,13,13,.82);z-index:20;font-family:var(--mono);font-size:15px;
  color:#fff;border:3px dashed var(--good);pointer-events:none;}
#drop.on{display:flex;}
footer{flex:none;border-top:1px solid var(--border);background:var(--surface);
  padding:6px 14px;font-family:var(--mono);font-size:10px;color:var(--muted);
  display:flex;gap:12px;align-items:center;}
footer .sp{margin-left:auto;}
#compose{flex:none;display:flex;gap:10px;align-items:flex-end;padding:8px 10px;
  border-top:1px solid var(--border);background:var(--surface);}
#box{flex:1;resize:none;font-family:var(--mono);font-size:12.5px;line-height:1.45;
  padding:8px 10px;border:1px solid var(--border);border-radius:8px;
  background:var(--raised);color:var(--ink);height:36px;max-height:30vh;overflow-y:auto;}
#box:focus{outline:none;border-color:var(--good);}
#compose .hint{font-family:var(--mono);font-size:10px;color:var(--muted);
  white-space:nowrap;padding-bottom:9px;}
"""

JS = r"""
const term = new Terminal({
  fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
  fontSize: 12, lineHeight: 1.2, cursorBlink: true, scrollback: 8000,
  theme: { background: '#0d0d0d', foreground: '#e6e9ec', cursor: '#d89b45' },
});
const fit = new FitAddon.FitAddon();
term.loadAddon(fit);
term.open(document.getElementById('term'));
fit.fit();

const dot = document.getElementById('dot');
const statusText = document.getElementById('status');
let ws = null;
let endedWhy = '';

function connect(){
  ws = new WebSocket(`ws://${location.host}/ws/terminal?token=${encodeURIComponent(TOKEN)}&s=board`);
  ws.binaryType = 'arraybuffer';

  ws.onopen = () => {
    endedWhy = '';
  dot.className = 'on'; statusText.textContent = 'connected';
    sendResize();
  };
  ws.onmessage = (e) => {
    // Terminal output arrives as raw bytes, not text: decoding here would
    // mangle partial multi-byte sequences that land across frame boundaries.
    // A *text* frame is the server talking about the session, not the
    // session talking -- so far, why it ended.
    if (typeof e.data === 'string'){
      try { const m = JSON.parse(e.data);
            if (m.t === 'state') showState(m);
            if (m.t === 'ended') endedWhy = m.why;
            if (m.t === 'attached' && m.resumed)
              term.write('\r\n\x1b[90m— reattached, ' + m.bytes +
                         ' bytes of scrollback —\x1b[0m\r\n');
      } catch(err){}
      return;
    }
    term.write(new Uint8Array(e.data));
  };
  ws.onclose = () => {
    dot.className = 'off';
    statusText.textContent = endedWhy ? 'ended: ' + endedWhy : 'session ended';
    term.write('\r\n\x1b[90m— session ended' + (endedWhy ? ': ' + endedWhy : '') +
               '. your work is on disk; reload to continue it —\x1b[0m\r\n');
  };
  ws.onerror = () => { dot.className = 'off'; statusText.textContent = 'connection failed'; };
}

function sendResize(){
  if (ws?.readyState === 1)
    ws.send(JSON.stringify({t:'resize', cols: term.cols, rows: term.rows}));
}

function sendRaw(d){ if (ws?.readyState === 1) ws.send(JSON.stringify({t:'input', d})); }

// Deliberately no `term.onData` handler. The screen is a view, not an input:
// keystrokes typed at it go nowhere, so the cursor never races the output and
// there is no half-typed line living in a place nothing can see. Everything
// that reaches the session goes through the box below, on purpose.
term.options.disableStdin = true;
term.options.cursorBlink = false;
addEventListener('resize', () => { fit.fit(); sendResize(); });

// ---- is it done yet? -------------------------------------------------------
// The whole reason the pane exists. Three states, because they mean three
// different things to somebody glancing over: carry on, come back, it needs
// you. The clock and the overrun are counted here rather than sent, so the
// number keeps moving between the server's once-a-second frames.
const stateEl = document.getElementById('state');
const clockEl = document.getElementById('clock');
const guessEl = document.getElementById('guess');
const overEl  = document.getElementById('over');
const WORDS = {working:'working', waiting:'waiting for you', idle:'idle'};
let cur = {state:'idle', since: Date.now()/1000, estimate: null};

function mmss(s){
  s = Math.max(0, Math.floor(s));
  const m = Math.floor(s/60);
  return m >= 60 ? Math.floor(m/60) + 'h' + String(m%60).padStart(2,'0')
                 : m + ':' + String(s%60).padStart(2,'0');
}

function showState(m){ cur = m; tick(); }

function tick(){
  const el = Math.max(0, Date.now()/1000 - cur.since);
  stateEl.textContent = WORDS[cur.state] || cur.state;
  stateEl.className = cur.state;
  clockEl.textContent = cur.state === 'idle' ? '' : mmss(el);
  // The estimate is a guess from history and is labelled as one, every time.
  // A bare number here would get read as a promise.
  guessEl.textContent = (cur.state === 'working' && cur.estimate)
    ? 'usually about ' + mmss(cur.estimate) + ' — a guess, from recent turns' : '';
  // A second, distinct message rather than a silently growing number: past
  // twice the guess is the moment worth interrupting for, and a clock that
  // just keeps climbing never says so.
  const over = cur.state === 'working' && cur.estimate && el > 2 * cur.estimate;
  overEl.className = over ? 'on' : '';
  if (over){
    overEl.textContent = 'running long — over 2x the usual';
    stateEl.className = 'over';
  }
}
setInterval(tick, 1000);

// ---- compose box: type locally, send whole lines ---------------------------
// Typing straight into the terminal is only as fast as the round trip to the
// pseudo-terminal — every character has to reach the shell and be echoed back
// before it appears. Composing in a plain textarea is local DOM and therefore
// instant; the whole line goes over the socket once, on Enter. The terminal
// itself still takes raw keys when it has focus, which is what interactive
// prompts need.
const box = document.getElementById('box');

function autogrow(){
  box.style.height = 'auto';
  box.style.height = Math.min(box.scrollHeight, innerHeight * 0.3) + 'px';
}

function submit(){
  const v = box.value;
  if (!v){ sendRaw('\r'); return; }   // empty Enter answers whatever is waiting
  // Bracketed paste keeps a multi-line message one message: without it the
  // first newline submits and the rest arrives as separate prompts.
  sendRaw(v.includes('\n') ? '\x1b[200~' + v + '\x1b[201~\r' : v + '\r');
  box.value = ''; autogrow();
}

box.addEventListener('input', autogrow);
box.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); submit(); return; }
  if (e.key === 'Escape'){ e.preventDefault(); sendRaw('\x1b'); return; }
  if (e.key === 'c' && e.ctrlKey){ e.preventDefault(); sendRaw('\x03'); box.value = ''; autogrow(); return; }
  // Shift+Tab cycles permission modes in Claude Code. It is a mode switch, not
  // text, so it always belongs to the terminal — the browser would otherwise
  // steal it to move focus out of the box.
  if (e.key === 'Tab' && e.shiftKey){ e.preventDefault(); sendRaw('\x1b[Z'); return; }
  // An empty box means you are steering the terminal, not writing: arrows walk
  // its history, Tab completes there.
  if (!box.value && (e.key === 'ArrowUp' || e.key === 'ArrowDown')){
    e.preventDefault(); sendRaw(e.key === 'ArrowUp' ? '\x1b[A' : '\x1b[B'); return;
  }
  if (!box.value && e.key === 'Tab'){ e.preventDefault(); sendRaw('\t'); return; }
});
// Clicking the screen used to hand raw keys back to it. There are no raw keys
// now, so a click there is just a click, and focus stays where typing works.

// ---- image paste: intercept, upload, type the path in ----------------------
async function sendImage(file){
  const buf = await file.arrayBuffer();
  const b64 = btoa(String.fromCharCode(...new Uint8Array(buf)));
  term.write('\x1b[90m  uploading…\x1b[0m');
  try {
    const r = await fetch('api/paste-image', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({token: TOKEN, name: file.name || 'pasted.png', data: b64}),
    });
    const d = await r.json();
    if (d.path) {
      // Always into the box. The path is text you are still writing around --
      // it belongs in the line being composed, not fired at the session on its
      // own, and the box is the only way in from this page now.
      box.value += (box.value && !box.value.endsWith(' ') ? ' ' : '') + d.path + ' ';
      autogrow(); box.focus();
    } else {
      term.write('\r\n\x1b[31m  upload failed\x1b[0m\r\n');
    }
  } catch(e){
    term.write('\r\n\x1b[31m  upload failed: ' + e.message + '\x1b[0m\r\n');
  }
}

addEventListener('paste', e => {
  const files = [...(e.clipboardData?.files ?? [])].filter(f => f.type.startsWith('image/'));
  if (!files.length) return;          // plain text paste goes to the terminal
  e.preventDefault();
  files.forEach(sendImage);
});

const drop = document.getElementById('drop');
addEventListener('dragover', e => { e.preventDefault(); drop.className = 'on'; });
addEventListener('dragleave', e => { if (e.target === document.documentElement) drop.className = ''; });
addEventListener('drop', e => {
  e.preventDefault(); drop.className = '';
  [...(e.dataTransfer?.files ?? [])].filter(f => f.type.startsWith('image/')).forEach(sendImage);
});

connect();
autogrow();
box.focus();
"""


def page(token: str, nav_html: str, nav_css: str) -> str:
    import nav
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nav.title("terminal")}</title>
<link rel="stylesheet" href="/static/xterm.css">
<style>{CSS}
{nav_css}</style></head>
<body>
<header>
  <span id="dot"></span>
  <h1>Board</h1>
  <span class="sub" id="status">connecting…</span>
  {nav_html}
</header>
<div id="pane">
  <span id="state" class="idle">idle</span>
  <span id="clock"></span>
  <span id="guess"></span>
  <span id="over"></span>
</div>
<div id="term"></div>
<div id="drop">drop an image — the path will be typed in</div>
<div id="compose">
  <textarea id="box" rows="1" spellcheck="false" autocomplete="off"
            placeholder="type here — instant, nothing leaves the browser until Enter"></textarea>
  <span class="hint">Enter sends &middot; Shift+Enter newline &middot; Ctrl+C interrupts</span>
</div>
<footer>
  <span>read-only view &mdash; drive it from the laptop with <code>tmux attach -t board</code>, same session</span>
  <span class="sp">paste or drop an image to insert its path</span>
</footer>
<script src="/static/xterm.js"></script>
<script src="/static/xterm-addon-fit.js"></script>
<script>const TOKEN = {token!r};</script>
<script>{JS}</script>
</body></html>"""
