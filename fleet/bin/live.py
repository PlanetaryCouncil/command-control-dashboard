#!/usr/bin/env python3
"""The live view: a streaming, always-on-top-capable window.

Colors are the validated categorical slots (see dataviz palette reference),
assigned to agents in fixed order and never cycled — an agent keeps its hue
whether or not other agents are present. Every color is paired with an emoji
and a name, so identity never depends on color alone.
"""

# slot -> (emoji, dark hex, light hex). Fixed order; new agents take the next
# free slot rather than reusing one.
AGENT_STYLE = {
    "self-improve":              ("\U0001F501", "#3987e5", "#2a78d6"),  # blue
    "grok":                      ("\U0001F52D", "#5b6b7c", "#8fa3b8"),  # slate
    "agy":                       ("\u2693", "#1a73e8", "#4285f4"),  # google blue
    "hermes":                    ("\U0001FAB6", "#d95926", "#eb6834"),  # orange
    "openclaw":                  ("\U0001F980", "#199e70", "#1baf7a"),  # aqua
    "agent-comms":               ("\U0001F517", "#c98500", "#eda100"),  # yellow
    "command-control-dashboard": ("\U0001F39B️", "#d55181", "#e87ba4"),  # magenta
    "fleet":                     ("⚙️", "#898781", "#898781"),  # neutral: infra, not an agent
}
FALLBACK = ("\U0001F916", "#898781", "#898781")


def style_css():
    rows = []
    for name, (_emoji, dark, light) in AGENT_STYLE.items():
        slug = name.replace(".", "-")
        rows.append(f'.a-{slug}{{--agent:{light};}}')
        rows.append(f'@media (prefers-color-scheme:dark){{.a-{slug}{{--agent:{dark};}}}}')
        rows.append(f':root[data-theme="dark"] .a-{slug}{{--agent:{dark};}}')
        rows.append(f':root[data-theme="light"] .a-{slug}{{--agent:{light};}}')
    return "\n".join(rows)


CSS = """
:root{
  --ground:#F4F6F8; --surface:#FFFFFF; --raised:#EDF0F3;
  --border:#DCE1E7; --ink:#171B21; --ink-2:#414B58; --muted:#5C6674;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
}
@media (prefers-color-scheme:dark){
  :root{ --ground:#0d0d0d; --surface:#1a1a19; --raised:#232322;
    --border:#2f2f2d; --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781; }
}
:root[data-theme="dark"]{ --ground:#0d0d0d; --surface:#1a1a19; --raised:#232322;
  --border:#2f2f2d; --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781; }
:root[data-theme="light"]{ --ground:#F4F6F8; --surface:#FFFFFF; --raised:#EDF0F3;
  --border:#DCE1E7; --ink:#171B21; --ink-2:#414B58; --muted:#5C6674; }

*{box-sizing:border-box;}
body{margin:0;background:var(--ground);color:var(--ink);
  font-family:var(--sans);font-size:14px;line-height:1.5;
  -webkit-font-smoothing:antialiased;}
#live{display:flex;flex-direction:column;height:100vh;overflow:hidden;}

#lvhead{display:flex;align-items:center;gap:11px;padding:9px 13px;flex:none;
  border-bottom:1px solid var(--border);background:var(--surface);flex-wrap:wrap;}
#lvhead h1{font-family:var(--mono);font-size:13px;font-weight:600;margin:0;}
#lvhead .sub{font-family:var(--mono);font-size:10px;color:var(--muted);}

/* ---- blocked banner: impossible to miss ---- */
#banner{display:none;background:var(--critical);color:#fff;
  padding:13px 16px;gap:12px;align-items:center;flex:none;}
#banner.on{display:flex;}
#banner .bang{font-size:22px;line-height:1;flex:none;}
#banner .btxt{min-width:0;}
#banner .bt{font-family:var(--mono);font-weight:700;font-size:12px;
  letter-spacing:.1em;text-transform:uppercase;}
#banner .bd{font-size:13px;opacity:.95;overflow:hidden;text-overflow:ellipsis;
  white-space:nowrap;}
@media (prefers-reduced-motion:no-preference){
  #banner.on{animation:pulse 2s ease-in-out infinite;}
  @keyframes pulse{0%,100%{opacity:1;}50%{opacity:.82;}}
}

/* ---- agent chips ---- */
#chips{display:flex;flex-wrap:wrap;gap:7px;padding:11px 13px;flex:none;
  border-bottom:1px solid var(--border);background:var(--surface);}
.chip{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);
  font-size:11px;padding:4px 9px 4px 7px;border-radius:20px;
  background:var(--raised);border:1px solid var(--border);}
.chip .dot{width:8px;height:8px;border-radius:50%;background:var(--agent);flex:none;}
.chip .nm{color:var(--ink-2);}
.chip .st{font-size:9.5px;letter-spacing:.07em;text-transform:uppercase;}
.chip.pass .st{color:var(--good);} .chip.fail .st,.chip.alert .st{color:var(--critical);}
.chip.skip .st,.chip.idle .st{color:var(--warning);}

/* ---- feed ---- */
#feed{flex:1;overflow-y:auto;padding:6px 0;background:var(--ground);}
.ev{display:grid;grid-template-columns:58px 1fr;gap:9px;
  padding:5px 13px 5px 10px;border-left:3px solid var(--agent);
  align-items:baseline;}
.ev .t{font-family:var(--mono);font-size:10px;color:var(--muted);
  font-variant-numeric:tabular-nums;}
.ev .m{font-size:12.5px;color:var(--ink-2);word-break:break-word;}
.ev .who{color:var(--agent);font-family:var(--mono);font-size:11px;}
.ev.ok .m{color:var(--ink);}
.ev.error .m,.ev.needs_you .m{color:var(--critical);font-weight:600;}
.ev.warn .m{color:var(--warning);}
.ev:nth-child(odd){background:color-mix(in srgb,var(--surface) 45%,transparent);}

#bar{display:flex;align-items:center;gap:10px;padding:8px 13px;flex:none;
  border-top:1px solid var(--border);background:var(--surface);
  font-family:var(--mono);font-size:10.5px;color:var(--muted);}
#bar .sp{margin-left:auto;display:flex;gap:8px;}
button{font-family:var(--mono);font-size:10.5px;padding:5px 11px;
  border-radius:6px;border:1px solid var(--border);background:var(--raised);
  color:var(--ink);cursor:pointer;}
button:hover{border-color:var(--muted);}
button:focus-visible{outline:2px solid var(--ink);outline-offset:2px;}
#pulse{width:7px;height:7px;border-radius:50%;background:var(--good);flex:none;}
#pulse.stale{background:var(--warning);}
"""


JS = """
const AGENTS = __AGENTS__;
const fallback = ["\\uD83E\\uDD16","#898781"];
const feed = document.getElementById('feed');
const banner = document.getElementById('banner');
const chips = document.getElementById('chips');
const pulse = document.getElementById('pulse');
let blocked = new Map();

function slug(n){ return 'a-' + String(n).replace(/\\./g,'-'); }
function emoji(n){ return (AGENTS[n] || fallback)[0]; }

function hhmm(iso){
  try { const d = new Date(iso);
    return String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0')
      +':'+String(d.getSeconds()).padStart(2,'0');
  } catch(e){ return '--:--:--'; }
}

// A needs_you event stays raised until that same agent reports ok. Applied to
// both the seeded history and the live stream, so the banner survives a reload
// — otherwise an alarm raised overnight is invisible by morning.
function applyState(e){
  if (e.level === 'needs_you') blocked.set(e.agent, e.msg);
  else if (e.level === 'ok') blocked.delete(e.agent);
}

function addEvent(e, prepend){
  const row = document.createElement('div');
  row.className = 'ev ' + (e.level||'info') + ' ' + slug(e.agent);
  const t = document.createElement('span'); t.className='t'; t.textContent = hhmm(e.ts);
  const m = document.createElement('span'); m.className='m';
  const who = document.createElement('span'); who.className='who';
  who.textContent = emoji(e.agent) + ' ' + e.agent + ' ';
  m.appendChild(who);
  m.appendChild(document.createTextNode(e.msg||''));
  row.appendChild(t); row.appendChild(m);
  if (prepend) feed.appendChild(row); else feed.appendChild(row);

  // keep the DOM bounded during long sessions
  while (feed.children.length > 400) feed.removeChild(feed.firstChild);

  const nearBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 120;
  if (nearBottom) feed.scrollTop = feed.scrollHeight;

  applyState(e);
  renderBanner();
}

function renderBanner(){
  if (blocked.size === 0){ banner.className=''; return; }
  const [who, msg] = blocked.entries().next().value;
  banner.className = 'on';
  banner.querySelector('.bt').textContent =
    blocked.size > 1 ? blocked.size + ' things need you' : 'Needs you';
  banner.querySelector('.bd').textContent = emoji(who) + ' ' + who + ' — ' + msg;
}

async function loadChips(){
  try {
    const r = await fetch('workers.json', {cache:'no-store'});
    const ws = await r.json();
    chips.replaceChildren();
    for (const w of ws){
      const c = document.createElement('span');
      c.className = 'chip ' + (w.status||'idle') + ' ' + slug(w.worker);
      const d = document.createElement('span'); d.className='dot';
      const n = document.createElement('span'); n.className='nm';
      n.textContent = emoji(w.worker) + ' ' + w.worker;
      const s = document.createElement('span'); s.className='st'; s.textContent = w.status||'';
      c.append(d,n,s); chips.appendChild(c);
    }
  } catch(e){}
}

function connect(){
  const es = new EventSource('events');
  es.onmessage = (m) => {
    pulse.className = '';
    try { addEvent(JSON.parse(m.data)); } catch(e){}
  };
  es.onerror = () => { pulse.className = 'stale'; };
}

// ---- Document Picture-in-Picture: a real always-on-top window ----
const popBtn = document.getElementById('pop');
if (!('documentPictureInPicture' in window)) {
  popBtn.disabled = true;
  popBtn.textContent = 'float needs chrome';
  popBtn.title = 'Document Picture-in-Picture is Chrome/Edge only';
}
popBtn.addEventListener('click', async () => {
  if (!('documentPictureInPicture' in window)) return;
  try {
    const w = await documentPictureInPicture.requestWindow({width:430, height:560});
    for (const s of document.styleSheets) {
      try {
        const css = [...s.cssRules].map(r => r.cssText).join('');
        const el = w.document.createElement('style'); el.textContent = css;
        w.document.head.appendChild(el);
      } catch(e){}
    }
    w.document.body.append(document.getElementById('live'));
    w.addEventListener('pagehide', () => {
      document.body.append(w.document.getElementById('live'));
    });
  } catch(e){}
});

// Seed alarm state from the history the server already rendered.
try { (__SEED__ || []).forEach(applyState); } catch(e){}
renderBanner();

loadChips(); setInterval(loadChips, 15000); connect();
"""


def page(events, agents_json):
    import nav
    nav_html = nav.html('/live')
    nav_css = nav.CSS
    rows = "".join(
        f'<div class="ev {e.get("level","info")} a-{e.get("agent","?").replace(".","-")}">'
        f'<span class="t">{e.get("ts","")[11:19]}</span>'
        f'<span class="m"><span class="who">'
        f'{AGENT_STYLE.get(e.get("agent"), FALLBACK)[0]} {e.get("agent","")} </span>'
        f'{_esc(e.get("msg",""))}</span></div>'
        for e in events
    )
    import json as _json
    seed = _json.dumps([{"agent": e.get("agent", ""), "level": e.get("level", "info"),
                         "msg": e.get("msg", "")} for e in events])
    js = JS.replace("__AGENTS__", agents_json).replace("__SEED__", seed)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nav.title("stream")}</title>
<style>{CSS}\n{nav_css}
{style_css()}</style></head>
<body>
<div id="live">
  <div id="lvhead">
    <h1>Stream</h1><span class="sub">every agent, in order</span>
    {nav_html}
  </div>
  <div id="banner" role="alert" aria-live="assertive">
    <span class="bang">&#9888;</span>
    <span class="btxt"><span class="bt"></span><span class="bd"></span></span>
  </div>
  <div id="chips"></div>
  <div id="feed">{rows}</div>
  <div id="bar">
    <span id="pulse"></span><span>live</span>
    <span class="sp"><button id="pop">float on top</button></span>
  </div>
</div>
<script>{js}</script>
</body></html>"""


def _esc(s):
    import html
    return html.escape(str(s))
