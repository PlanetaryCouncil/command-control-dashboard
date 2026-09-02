#!/usr/bin/env python3
"""The terminal page: real Claude, plus image paste that a terminal cannot do.

Pasting an image into a terminal normally does nothing — a terminal takes
keystrokes. Here the paste is intercepted, the image is uploaded and written to
disk, and the resulting path is *typed into the terminal for you*. Claude then
reads it exactly as it would from the command line. The feature that motivated
moving to a browser survives the move back to a terminal.
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
  ws = new WebSocket(`ws://${location.host}/ws/terminal?token=${encodeURIComponent(TOKEN)}`);
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
            if (m.t === 'ended') endedWhy = m.why; } catch(err){}
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

term.onData(sendRaw);
addEventListener('resize', () => { fit.fit(); sendResize(); });

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
  if (e.key === 'Escape'){ e.preventDefault(); term.focus(); return; }
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
// Clicking the terminal hands raw keys back to it; clicking the box takes over.
document.getElementById('term').addEventListener('mousedown', () => term.focus());

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
    if (d.path && document.activeElement === box) {
      // Composing: the path belongs in the line being written, not the pty.
      box.value += (box.value && !box.value.endsWith(' ') ? ' ' : '') + d.path + ' ';
      autogrow(); box.focus();
    } else if (d.path && ws?.readyState === 1) {
      // Typed as input, so Claude sees exactly what it would from the CLI.
      ws.send(JSON.stringify({t:'input', d: d.path + ' '}));
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
  <h1>Terminal</h1>
  <span class="sub" id="status">connecting…</span>
  {nav_html}
</header>
<div id="term"></div>
<div id="drop">drop an image — the path will be typed in</div>
<div id="compose">
  <textarea id="box" rows="1" spellcheck="false" autocomplete="off"
            placeholder="type here — instant, nothing leaves the browser until Enter"></textarea>
  <span class="hint">Enter sends &middot; Shift+Enter newline &middot; Esc to the terminal</span>
</div>
<footer>
  <span>real <code>claude</code> on a pseudo-terminal &mdash; permissions, plan mode and slash commands all work</span>
  <span class="sp">paste or drop an image to insert its path</span>
</footer>
<script src="/static/xterm.js"></script>
<script src="/static/xterm-addon-fit.js"></script>
<script>const TOKEN = {token!r};</script>
<script>{JS}</script>
</body></html>"""
