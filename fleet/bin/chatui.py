#!/usr/bin/env python3
"""Chat UI: one question, fanned out to any subset of agents.

Agent hues are validated categorical slots, in fixed order. Hermes and OpenClaw
keep the same hue they have in the live view so an agent means the same colour
everywhere. Every hue is paired with an emoji and a name.
"""

# name -> (emoji, dark, light)
CHAT_STYLE = {
    "claude":   ("\U0001F9E0", "#3987e5", "#2a78d6"),  # blue
    "hermes":   ("\U0001FAB6", "#d95926", "#eb6834"),  # orange — matches live view
    "openclaw": ("\U0001F980", "#199e70", "#1baf7a"),  # aqua  — matches live view
    "ollama":   ("\U0001F999", "#9085e9", "#4a3aa7"),  # violet
    "llava":    ("\U0001F441", "#008300", "#008300"),  # green
}


def agent_css():
    rows = []
    for name, (_e, dark, light) in CHAT_STYLE.items():
        rows.append(f'.g-{name}{{--agent:{light};}}')
        rows.append(f'@media (prefers-color-scheme:dark){{.g-{name}{{--agent:{dark};}}}}')
        rows.append(f':root[data-theme="dark"] .g-{name}{{--agent:{dark};}}')
        rows.append(f':root[data-theme="light"] .g-{name}{{--agent:{light};}}')
    return "\n".join(rows)


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
  font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased;
  display:flex;flex-direction:column;height:100vh;overflow:hidden;}

header{display:flex;align-items:center;gap:14px;padding:12px 16px;flex:none;
  border-bottom:1px solid var(--border);background:var(--surface);flex-wrap:wrap;}
h1{font-family:var(--mono);font-size:14px;font-weight:600;margin:0;letter-spacing:-.01em;}
header nav{margin-left:auto;display:flex;gap:8px;}
a.btn,button{font-family:var(--mono);font-size:11px;padding:6px 12px;border-radius:6px;
  border:1px solid var(--border);background:var(--raised);color:var(--ink);
  cursor:pointer;text-decoration:none;display:inline-block;}
button:hover,a.btn:hover{border-color:var(--muted);}
button:focus-visible,a.btn:focus-visible{outline:2px solid var(--ink);outline-offset:2px;}
button[disabled]{opacity:.45;cursor:not-allowed;}

#picker{display:flex;gap:8px;flex-wrap:wrap;padding:11px 16px;flex:none;
  border-bottom:1px solid var(--border);background:var(--surface);}
.pick{display:inline-flex;align-items:center;gap:7px;font-family:var(--mono);
  font-size:11.5px;padding:6px 11px;border-radius:20px;cursor:pointer;
  border:1px solid var(--border);background:var(--raised);user-select:none;}
.pick input{position:absolute;opacity:0;pointer-events:none;}
.pick .dot{width:9px;height:9px;border-radius:50%;background:var(--agent);flex:none;
  opacity:.35;transition:opacity .12s;}
.pick.on{border-color:var(--agent);background:color-mix(in srgb,var(--agent) 13%,transparent);}
.pick.on .dot{opacity:1;}
.pick.off{opacity:.4;}
.pick:focus-within{outline:2px solid var(--ink);outline-offset:2px;}
.pick .nr{font-size:9.5px;color:var(--muted);letter-spacing:.06em;text-transform:uppercase;}

#thread{flex:1;overflow-y:auto;padding:18px 16px;display:flex;
  flex-direction:column;gap:20px;}
.turn{display:flex;flex-direction:column;gap:11px;}
.you{align-self:flex-end;max-width:min(680px,88%);background:var(--raised);
  border:1px solid var(--border);border-radius:12px 12px 3px 12px;padding:11px 14px;
  white-space:pre-wrap;word-break:break-word;}
.you .files{margin-top:8px;display:flex;gap:7px;flex-wrap:wrap;}
.you .files img{max-height:82px;border-radius:6px;border:1px solid var(--border);}
.you .files .doc{font-family:var(--mono);font-size:10.5px;color:var(--muted);
  border:1px solid var(--border);border-radius:5px;padding:4px 8px;}

.replies{display:grid;gap:11px;
  grid-template-columns:repeat(auto-fit,minmax(290px,1fr));}
.reply{border:1px solid var(--border);border-left:3px solid var(--agent);
  border-radius:9px;background:var(--surface);padding:12px 14px;min-width:0;}
.reply h3{margin:0 0 8px;font-family:var(--mono);font-size:11.5px;font-weight:600;
  color:var(--agent);display:flex;align-items:center;gap:7px;}
.reply .secs{margin-left:auto;font-size:10px;color:var(--muted);font-weight:400;}
.reply .body{white-space:pre-wrap;word-break:break-word;font-size:13.5px;
  color:var(--ink-2);max-height:460px;overflow-y:auto;}
.reply.err,.reply.err .body{color:var(--critical);}
.dots::after{content:'';animation:dots 1.2s steps(4,end) infinite;}
@keyframes dots{0%{content:'';}25%{content:'.';}50%{content:'..';}75%{content:'...';}}
@media (prefers-reduced-motion:reduce){.dots::after{content:'...';animation:none;}}

footer{flex:none;border-top:1px solid var(--border);background:var(--surface);
  padding:11px 16px calc(11px + env(safe-area-inset-bottom));}
#attached{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:9px;}
#attached .chip{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);
  font-size:10.5px;border:1px solid var(--border);border-radius:6px;padding:4px 8px;}
#attached img{max-height:34px;border-radius:3px;}
#attached .x{cursor:pointer;color:var(--muted);}
#row{display:flex;gap:9px;align-items:flex-end;min-width:0;}
#row .btn,#row button{flex:none;height:44px;line-height:32px;}
#msg{flex:1;resize:none;min-height:44px;max-height:180px;padding:11px 13px;
  border-radius:9px;border:1px solid var(--border);background:var(--ground);
  color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.5;}
#msg:focus{outline:2px solid var(--muted);outline-offset:-1px;}
#hint{font-family:var(--mono);font-size:10px;color:var(--muted);margin-top:7px;}
"""

JS = r"""
const STYLE = __STYLE__;
const thread = document.getElementById('thread');
const msg = document.getElementById('msg');
const sendBtn = document.getElementById('send');
const attachedEl = document.getElementById('attached');
let attached = [];

function picked(){
  return [...document.querySelectorAll('.pick input:checked')].map(i => i.value);
}
function syncPicks(){
  document.querySelectorAll('.pick').forEach(p => {
    p.classList.toggle('on', p.querySelector('input').checked);
  });
}
document.getElementById('picker').addEventListener('change', syncPicks);

// ---- attachments -> base64 (no multipart on the wire) ----
function addFiles(files){
  for (const f of files){
    const r = new FileReader();
    r.onload = () => {
      attached.push({name: f.name, data: r.result, isImage: f.type.startsWith('image/')});
      renderAttached();
    };
    r.readAsDataURL(f);
  }
}
function renderAttached(){
  attachedEl.replaceChildren();
  attached.forEach((a, i) => {
    const c = document.createElement('span'); c.className = 'chip';
    if (a.isImage){ const im = document.createElement('img'); im.src = a.data; c.appendChild(im); }
    const n = document.createElement('span'); n.textContent = a.name; c.appendChild(n);
    const x = document.createElement('span'); x.className='x'; x.textContent='✕';
    x.title = 'remove';
    x.onclick = () => { attached.splice(i,1); renderAttached(); };
    c.appendChild(x); attachedEl.appendChild(c);
  });
}
document.getElementById('file').addEventListener('change', e => {
  addFiles(e.target.files); e.target.value = '';
});
document.addEventListener('paste', e => {
  if (e.clipboardData?.files?.length) addFiles(e.clipboardData.files);
});
document.addEventListener('dragover', e => e.preventDefault());
document.addEventListener('drop', e => {
  e.preventDefault(); if (e.dataTransfer?.files?.length) addFiles(e.dataTransfer.files);
});

msg.addEventListener('keydown', e => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); send(); }
});
msg.addEventListener('input', () => {
  msg.style.height = 'auto'; msg.style.height = Math.min(msg.scrollHeight, 180) + 'px';
});
sendBtn.addEventListener('click', send);

async function send(){
  const text = msg.value.trim();
  const agents = picked();
  if (!text && !attached.length) return;
  if (!agents.length){ alert('Pick at least one agent.'); return; }

  const turn = document.createElement('div'); turn.className = 'turn';
  const you = document.createElement('div'); you.className = 'you';
  you.textContent = text;
  if (attached.length){
    const fw = document.createElement('div'); fw.className = 'files';
    attached.forEach(a => {
      if (a.isImage){ const im=document.createElement('img'); im.src=a.data; fw.appendChild(im); }
      else { const d=document.createElement('span'); d.className='doc'; d.textContent=a.name; fw.appendChild(d); }
    });
    you.appendChild(fw);
  }
  turn.appendChild(you);
  const replies = document.createElement('div'); replies.className = 'replies';
  turn.appendChild(replies);
  thread.appendChild(turn);
  thread.scrollTop = thread.scrollHeight;

  const payload = {message: text, agents, attachments: attached.map(a => ({name:a.name, data:a.data}))};
  msg.value = ''; msg.style.height='auto'; attached = []; renderAttached();
  sendBtn.disabled = true;

  let res;
  try {
    res = await (await fetch('chat/send', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(payload)})).json();
  } catch(e){ sendBtn.disabled = false; return; }

  if (res.error || !res.job){
    const err = document.createElement('div'); err.className = 'reply err';
    const body = document.createElement('div'); body.className = 'body';
    body.textContent = res.error || 'none of the requested agents are ready';
    err.appendChild(body);
    replies.appendChild(err);
    sendBtn.disabled = false;
    return;
  }

  const cards = {};
  for (const a of res.agents){
    const c = document.createElement('div'); c.className = 'reply g-' + a;
    const h = document.createElement('h3');
    const st = STYLE[a] || ['🤖'];
    h.textContent = st[0] + ' ' + a;
    const s = document.createElement('span'); s.className='secs'; h.appendChild(s);
    const b = document.createElement('div'); b.className='body dots';
    c.append(h,b); replies.appendChild(c);
    // A ticking counter is the difference between "slow" and "hung" — without
    // it every wait looks identical and you cannot tell which.
    const started = Date.now();
    const tick = setInterval(() => {
      s.textContent = Math.round((Date.now()-started)/1000) + 's';
    }, 1000);
    cards[a] = {card:c, body:b, secs:s, acc:'', tick, started};
  }

  const es = new EventSource('chat/stream?job=' + encodeURIComponent(res.job));
  es.onmessage = (m) => {
    let e; try { e = JSON.parse(m.data); } catch(_){ return; }
    if (e.kind === 'all_done'){ es.close(); sendBtn.disabled = false; return; }
    const c = cards[e.agent]; if (!c) return;
    if (e.kind === 'queued'){
      c.body.textContent = 'waiting for a slot…'; c.body.classList.remove('dots');
    } else if (e.kind === 'start'){
      c.body.textContent = ''; c.body.classList.add('dots');
    } else if (e.kind === 'token'){
      c.body.classList.remove('dots');
      c.acc += e.data; c.body.textContent = c.acc;
    } else if (e.kind === 'done'){
      clearInterval(c.tick);
      c.body.classList.remove('dots');
      c.body.textContent = e.data.text;
      c.secs.textContent = e.data.seconds + 's';
      if (/^\[(error|timed out|stderr)/.test(e.data.text)) c.card.classList.add('err');
    }
    thread.scrollTop = thread.scrollHeight;
  };
  es.onerror = () => {
    es.close(); sendBtn.disabled = false;
    Object.values(cards).forEach(c => clearInterval(c.tick));
  };
}
syncPicks();
"""


def page(agents, style_json):
    import nav
    picks = []
    for a in agents:
        name = a["name"]
        emoji = CHAT_STYLE.get(name, ("\U0001F916",))[0]
        ready = a["ready"]
        checked = " checked" if (ready and name in ("ollama", "claude")) else ""
        cls = "pick g-" + name + ("" if ready else " off")
        note = "" if ready else '<span class="nr">not installed</span>'
        picks.append(
            f'<label class="{cls}" title="{a["label"]}">'
            f'<input type="checkbox" value="{name}"{checked}'
            f'{" disabled" if not ready else ""}>'
            f'<span class="dot"></span><span>{emoji} {name}</span>{note}</label>')

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fleet — chat</title>
<style>{CSS}\n{nav.CSS}\n{agent_css()}</style></head>
<body>
<header>
  <h1>Chat</h1>
  <span style="font-family:var(--mono);font-size:11px;color:var(--muted)">
    one question &rarr; every agent you pick</span>
  {nav.html('/chat')}
</header>

<div id="picker">{''.join(picks)}</div>

<div id="thread"></div>

<footer>
  <div id="attached"></div>
  <div id="row">
    <textarea id="msg" placeholder="Ask every selected agent at once…  (drop or paste files and images)"></textarea>
    <label class="btn" for="file">attach</label>
    <input type="file" id="file" multiple hidden>
    <button id="send">send</button>
  </div>
  <div id="hint">⌘↵ to send · images go to a vision model · everything stays on this machine</div>
</footer>
<script>{JS.replace('__STYLE__', style_json)}</script>
</body></html>"""
