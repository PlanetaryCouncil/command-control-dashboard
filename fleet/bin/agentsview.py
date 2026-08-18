#!/usr/bin/env python3
"""Agent wall: one rectangle per agent, plus the shared channel they post into.

The live view merges everything into a single stream, which is right for
"what just happened" and wrong for "what is each agent doing". This splits the
same event log per agent so you can watch five of them work at once, with the
orchestrator's channel across the top — the surface they post to and read from.

Colours are the validated categorical slots, fixed per agent, always paired with
an emoji and a name so identity never rests on colour alone.
"""

# name -> (emoji, dark, light, role shown under the name)
AGENTS = {
    # claude speaks in council and in every relay but was never registered, so
    # it rendered with the neutral gear — the fleet's own icon. Violet is the
    # next free slot in the validated palette.
    "claude": ("\U0001F9E0", "#9085e9", "#4a3aa7",
               "reasons about the fleet in council and carries relay hops"),
    # Registered on arrival rather than after the fact: claude ran unregistered
    # for weeks and rendered as the fleet's own neutral gear, which made it look
    # like infrastructure instead of a voice. Slate, the next free slot.
    "grok": ("\U0001F52D", "#5b6b7c", "#8fa3b8",
             "cloud agent with a tool loop; reasons and searches"),
    "self-improve": ("\U0001F501", "#3987e5", "#2a78d6",
                     "reads its own transcripts, proposes tooling"),
    "hermes": ("\U0001FAB6", "#d95926", "#eb6834",
               "local agent runtime, own skill store"),
    "openclaw": ("\U0001F980", "#199e70", "#1baf7a",
                 "message router, reaches chat platforms"),
    "agent-comms": ("\U0001F517", "#c98500", "#eda100",
                    "relay check — proves agents still pass messages"),
    "fleet": ("\u2699\ufe0f", "#7d838b", "#898781",
              "the shared channel itself; no agent holds this role"),
    "e2e": ("\U0001F9EA", "#008300", "#008300",
            "end-to-end check against live infrastructure"),
    "command-control-dashboard": ("\U0001F39B️", "#d55181", "#e87ba4",
                                  "watchdog on this repo's test suite"),
}
ORCHESTRATOR = ("⚙️", "#898781", "#898781")


def agent_css():
    rows = []
    for name, (_e, dark, light, _r) in AGENTS.items():
        rows.append(f'.w-{name}{{--agent:{light};}}')
        rows.append(f'@media (prefers-color-scheme:dark){{.w-{name}{{--agent:{dark};}}}}')
        rows.append(f':root[data-theme="dark"] .w-{name}{{--agent:{dark};}}')
        rows.append(f':root[data-theme="light"] .w-{name}{{--agent:{light};}}')
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
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;
  display:flex;flex-direction:column;height:100vh;overflow:hidden;}

header{display:flex;align-items:center;gap:12px;padding:10px 16px;flex:none;
  border-bottom:1px solid var(--border);background:var(--surface);flex-wrap:wrap;}
h1{font-family:var(--mono);font-size:13px;font-weight:600;margin:0;letter-spacing:.02em;}
header .sub{font-family:var(--mono);font-size:10.5px;color:var(--muted);}
header nav{margin-left:auto;display:flex;gap:7px;}
a.btn,button{font-family:var(--mono);font-size:10.5px;padding:5px 10px;
  border-radius:6px;border:1px solid var(--border);background:var(--raised);
  color:var(--ink);cursor:pointer;text-decoration:none;}
a.btn:hover,button:hover{border-color:var(--muted);}
a.btn:focus-visible,button:focus-visible{outline:2px solid var(--ink);outline-offset:2px;}

/* ---- blocked banner ---- */
#banner{display:none;background:var(--critical);color:#fff;padding:11px 16px;
  gap:11px;align-items:center;flex:none;}
#banner.on{display:flex;}
#banner .bang{font-size:20px;line-height:1;}
#banner .bt{font-family:var(--mono);font-weight:700;font-size:11px;
  letter-spacing:.1em;text-transform:uppercase;}
#banner .bd{font-size:13px;opacity:.95;}
@media (prefers-reduced-motion:no-preference){
  #banner.on{animation:pulse 2s ease-in-out infinite;}
  @keyframes pulse{0%,100%{opacity:1}50%{opacity:.82}}
}

/* ---- the shared channel ---- */
#bus{flex:none;border-bottom:1px solid var(--border);background:var(--surface);
  padding:9px 16px 11px;}
#bus .lbl{font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);display:flex;gap:8px;align-items:center;}
#bus .lbl .ln{flex:1;height:1px;background:var(--border);}
#buslog{margin-top:7px;max-height:74px;overflow-y:auto;display:flex;
  flex-direction:column-reverse;}
#buslog .m{font-family:var(--mono);font-size:11.5px;color:var(--ink-2);
  padding:2px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
#buslog .m .t{color:var(--muted);}
#buslog .m .who{color:var(--agent,var(--muted));}

/* ---- the wall ---- */
#wall{flex:1;display:grid;gap:10px;padding:12px 16px 16px;overflow:auto;
  grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
  align-content:start;}
.panel{background:var(--surface);border:1px solid var(--border);
  border-top:3px solid var(--agent);border-radius:10px;
  display:flex;flex-direction:column;min-height:210px;max-height:46vh;min-width:0;}
.phead{padding:10px 12px 8px;flex:none;}
.ptitle{display:flex;align-items:center;gap:7px;font-family:var(--mono);
  font-size:12.5px;font-weight:600;}
.ptitle .nm{color:var(--agent);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.ptitle .st{margin-left:auto;font-size:9px;letter-spacing:.09em;
  text-transform:uppercase;padding:2px 6px;border-radius:4px;
  background:var(--raised);color:var(--muted);flex:none;}
.st.pass{color:var(--good);} .st.fail,.st.alert{color:var(--critical);}
.st.warn,.st.skip{color:var(--warning);}
.prole{font-size:11px;color:var(--muted);margin-top:3px;line-height:1.35;}
.plog{flex:1;overflow-y:auto;padding:6px 12px 10px;border-top:1px solid var(--border);
  display:flex;flex-direction:column-reverse;}
.plog .e{font-size:11.5px;padding:3px 0;border-bottom:1px dotted var(--border);
  word-break:break-word;color:var(--ink-2);}
.plog .e:last-child{border-bottom:none;}
.plog .e .t{font-family:var(--mono);font-size:9.5px;color:var(--muted);margin-right:6px;}
.plog .e.ok{color:var(--ink);}
.plog .e.warn{color:var(--warning);}
.plog .e.error,.plog .e.needs_you{color:var(--critical);font-weight:600;}
.plog .empty{color:var(--muted);font-style:italic;font-size:11.5px;padding:6px 0;}

footer{flex:none;border-top:1px solid var(--border);background:var(--surface);
  padding:7px 16px;font-family:var(--mono);font-size:10px;color:var(--muted);
  display:flex;gap:10px;align-items:center;}
#pulse{width:7px;height:7px;border-radius:50%;background:var(--good);}
#pulse.stale{background:var(--warning);}
footer .sp{margin-left:auto;display:flex;gap:7px;}
"""

JS = r"""
const AGENTS = __AGENTS__;
const ORCH = __ORCH__;
const wall = document.getElementById('wall');
const buslog = document.getElementById('buslog');
const banner = document.getElementById('banner');
const pulse = document.getElementById('pulse');
const blocked = new Map();
const MAX = 60;

function emoji(n){ return (AGENTS[n] || [ORCH[0]])[0]; }
function hhmm(iso){
  try { const d=new Date(iso);
    return [d.getHours(),d.getMinutes(),d.getSeconds()]
      .map(x=>String(x).padStart(2,'0')).join(':');
  } catch(e){ return '--:--:--'; }
}

function trim(el){ while (el.children.length > MAX) el.removeChild(el.lastChild); }

function toBus(e){
  const m = document.createElement('div'); m.className='m';
  const t = document.createElement('span'); t.className='t'; t.textContent=hhmm(e.ts)+' ';
  const w = document.createElement('span'); w.className='who';
  w.textContent = emoji(e.agent)+' '+e.agent+' ';
  m.append(t,w,document.createTextNode(e.msg||''));
  // column-reverse: newest is prepended so it renders at the top
  buslog.prepend(m); trim(buslog);
}

function toPanel(e){
  const log = document.getElementById('log-'+e.agent);
  if (!log) return;                       // an agent with no panel goes to the bus only
  const empty = log.querySelector('.empty'); if (empty) empty.remove();
  const row = document.createElement('div');
  row.className = 'e ' + (e.level||'info');
  const t = document.createElement('span'); t.className='t'; t.textContent=hhmm(e.ts);
  row.append(t, document.createTextNode(e.msg||''));
  log.prepend(row); trim(log);
}

function applyState(e){
  if (e.level === 'needs_you') blocked.set(e.agent, e.msg);
  else if (e.level === 'ok') blocked.delete(e.agent);
}

function renderBanner(){
  if (!blocked.size){ banner.className=''; return; }
  const [who,msg] = blocked.entries().next().value;
  banner.className='on';
  banner.querySelector('.bt').textContent =
    blocked.size>1 ? blocked.size+' need you' : 'Needs you';
  banner.querySelector('.bd').textContent = emoji(who)+' '+who+' — '+msg;
}

function ingest(e){
  applyState(e);
  // The orchestrator's own line is the shared channel; agent lines also show
  // there so you can read the conversation in order, not just per-agent.
  toBus(e);
  toPanel(e);
  renderBanner();
}

async function refreshStatus(){
  try {
    const ws = await (await fetch('workers.json',{cache:'no-store'})).json();
    for (const w of ws){
      const el = document.getElementById('st-'+w.worker);
      if (el){ el.textContent = w.status||''; el.className = 'st '+(w.status||''); }
    }
  } catch(e){}
}

function connect(){
  const es = new EventSource('events');
  es.onmessage = m => { pulse.className=''; try{ ingest(JSON.parse(m.data)); }catch(e){} };
  es.onerror = () => { pulse.className='stale'; };
}

(__SEED__ || []).forEach(ingest);
refreshStatus(); setInterval(refreshStatus, 15000); connect();
"""


# Kept out of the page f-string: JavaScript braces would otherwise need
# doubling everywhere, which is unreadable and easy to get wrong.
PIP_JS = """
const popBtn = document.getElementById('pop');
if (!('documentPictureInPicture' in window)) {
  popBtn.disabled = true; popBtn.textContent = 'float needs chrome';
}
popBtn.addEventListener('click', async () => {
  if (!('documentPictureInPicture' in window)) return;
  try {
    const w = await documentPictureInPicture.requestWindow({width: 900, height: 620});
    for (const s of document.styleSheets) {
      try {
        const css = [...s.cssRules].map(r => r.cssText).join('');
        const el = w.document.createElement('style'); el.textContent = css;
        w.document.head.appendChild(el);
      } catch (e) {}
    }
    while (document.body.firstChild) w.document.body.append(document.body.firstChild);
  } catch (e) {}
});
"""


def page(events, seed_json, agents_json, orch_json):
    import nav
    panels = []
    for name, (em, _d, _l, role) in AGENTS.items():
        recent = [e for e in events if e.get("agent") == name][-40:]
        rows = "".join(
            f'<div class="e {e.get("level","info")}">'
            f'<span class="t">{(e.get("ts") or "")[11:19]}</span>{_esc(e.get("msg",""))}</div>'
            for e in reversed(recent)
        ) or '<div class="empty">// quiet</div>'
        panels.append(f"""
      <section class="panel w-{name}">
        <div class="phead">
          <div class="ptitle"><span>{em}</span><span class="nm">{name}</span>
            <span class="st" id="st-{name}">—</span></div>
          <div class="prole">{_esc(role)}</div>
        </div>
        <div class="plog" id="log-{name}">{rows}</div>
      </section>""")

    bus = "".join(
        f'<div class="m"><span class="t">{(e.get("ts") or "")[11:19]} </span>'
        f'<span class="who">{AGENTS.get(e.get("agent"), (ORCHESTRATOR[0],))[0]} '
        f'{_esc(e.get("agent",""))} </span>{_esc(e.get("msg",""))}</div>'
        for e in reversed(events[-40:])
    )

    js = (JS.replace("__AGENTS__", agents_json)
            .replace("__ORCH__", orch_json)
            .replace("__SEED__", seed_json))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Fleet — agents</title>
<style>{CSS}\n{nav.CSS}\n{agent_css()}</style></head>
<body>
<header>
  <h1>Agent wall</h1>
  <span class="sub">{len(AGENTS)} agents &middot; live</span>
  {nav.html('/agents')}
</header>

<div id="banner" role="alert" aria-live="assertive">
  <span class="bang">&#9888;</span>
  <span><span class="bt"></span> <span class="bd"></span></span>
</div>

<div id="bus">
  <div class="lbl">{ORCHESTRATOR[0]} orchestrator &mdash; shared channel <span class="ln"></span></div>
  <div id="buslog">{bus}</div>
</div>

<main id="wall">{''.join(panels)}</main>

<footer>
  <span id="pulse"></span><span>live</span>
  <span class="sp"><button id="pop">float on top</button></span>
</footer>
<script>{js}</script>
<script>{PIP_JS}</script>
</body></html>"""


def _esc(s):
    import html
    return html.escape(str(s))
