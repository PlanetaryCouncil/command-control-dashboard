#!/usr/bin/env python3
"""Live process list and the kill switch.

The button is deliberately two-step. A single click that SIGKILLs everything is
one stray tap away from ending a run you wanted, and this page is meant to stay
open. Arming it first costs a second and removes that whole class of accident.
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
  font-size:14px;line-height:1.5;-webkit-font-smoothing:antialiased;}
.wrap{max-width:1000px;margin:0 auto;padding:20px 18px 60px;}
header{display:flex;align-items:center;gap:12px;margin-bottom:18px;flex-wrap:wrap;}
h1{font-family:var(--mono);font-size:15px;font-weight:600;margin:0;}
header .sub{font-family:var(--mono);font-size:10.5px;color:var(--muted);}
nav{margin-left:auto;display:flex;gap:7px;}
a.btn{font-family:var(--mono);font-size:10.5px;padding:5px 10px;border-radius:6px;
  border:1px solid var(--border);background:var(--raised);color:var(--ink);
  text-decoration:none;}
a.btn:hover{border-color:var(--muted);}

h2{font-family:var(--mono);font-size:11px;letter-spacing:.14em;
  text-transform:uppercase;color:var(--muted);margin:22px 0 8px;font-weight:600;}
table{width:100%;border-collapse:collapse;font-size:12.5px;}
th{text-align:left;font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--muted);font-weight:600;
  padding:0 8px 6px 0;border-bottom:1px solid var(--border);}
td{padding:7px 8px 7px 0;border-bottom:1px dotted var(--border);vertical-align:top;}
td.num{font-family:var(--mono);font-variant-numeric:tabular-nums;white-space:nowrap;}
td.cmd{font-family:var(--mono);font-size:11px;color:var(--muted);
  word-break:break-all;}
tr.self td{color:var(--muted);}
.tag{font-family:var(--mono);font-size:9px;letter-spacing:.09em;
  text-transform:uppercase;border:1px solid var(--border);border-radius:4px;
  padding:2px 5px;color:var(--muted);white-space:nowrap;}
.empty{color:var(--muted);font-style:italic;padding:14px 0;}

/* ---- kill switch ---- */
.danger{margin-top:26px;border:1px solid var(--critical);border-radius:11px;
  background:color-mix(in srgb,var(--critical) 7%,transparent);padding:16px 18px;}
.danger h2{margin-top:0;color:var(--critical);}
.danger p{margin:0 0 13px;font-size:13px;color:var(--ink-2);}
#kill{font-family:var(--mono);font-size:13px;font-weight:700;letter-spacing:.1em;
  text-transform:uppercase;padding:14px 26px;border-radius:9px;cursor:pointer;
  border:2px solid var(--critical);background:var(--critical);color:#fff;}
#kill:hover{filter:brightness(1.1);}
#kill:focus-visible{outline:3px solid var(--ink);outline-offset:3px;}
#kill[data-armed="1"]{animation:throb .9s ease-in-out infinite;}
#kill:disabled{opacity:.5;cursor:not-allowed;animation:none;}
@keyframes throb{0%,100%{transform:scale(1)}50%{transform:scale(1.03)}}
@media (prefers-reduced-motion:reduce){#kill[data-armed="1"]{animation:none;}}
#killnote{font-family:var(--mono);font-size:11px;color:var(--muted);margin-top:10px;}
#result{margin-top:12px;font-family:var(--mono);font-size:11.5px;
  white-space:pre-wrap;color:var(--ink-2);}
"""

JS = r"""
const fleetBody = document.getElementById('fleetBody');
const extBody   = document.getElementById('extBody');
const killBtn   = document.getElementById('kill');
const killNote  = document.getElementById('killnote');
const result    = document.getElementById('result');
let token = null, armTimer = null;

// Mirrors meter.py: same 100px track, same tone thresholds, so a row drawn
// here is indistinguishable from one rendered server-side.
function meter(value, max, opts){
  opts = opts || {};
  const pct = Math.max(0, (value / (max || 1)) * 100);
  const over = pct > 100;
  let tone = opts.tone;
  if (!tone) tone = pct >= 90 ? 'critical' : pct >= 60 ? 'warning' : 'good';
  const wrap = document.createElement('span');
  wrap.className = 'meter ' + tone + (over ? ' over' : '');
  wrap.title = opts.exact != null ? opts.exact : (value + (opts.suffix || ''));
  const track = document.createElement('span'); track.className = 'track';
  const fill = document.createElement('span'); fill.className = 'fill';
  fill.style.width = Math.min(100, pct).toFixed(1) + '%';
  if (value === 0) fill.dataset.zero = '1';
  track.appendChild(fill); wrap.appendChild(track);
  const sr = document.createElement('span'); sr.className='sr'; sr.textContent = wrap.title;
  wrap.appendChild(sr);
  return wrap;
}

// Uptime has no natural ceiling, so it is scaled against a day. Anything older
// pins full — an invented maximum would misstate magnitude.
function elapsedSeconds(e){
  const p = String(e).split('-');
  let days = 0, rest = e;
  if (p.length === 2){ days = parseInt(p[0], 10) || 0; rest = p[1]; }
  const n = rest.split(':').map(x => parseInt(x, 10) || 0);
  while (n.length < 3) n.unshift(0);
  return days*86400 + n[0]*3600 + n[1]*60 + n[2];
}

function row(p, killable){
  const tr = document.createElement('tr');
  if (p.is_self) tr.className = 'self';
  const text = (v, cls) => {
    const td = document.createElement('td');
    if (cls) td.className = cls;
    td.textContent = v;
    return td;
  };
  const cell = (node) => { const td = document.createElement('td'); td.appendChild(node); return td; };

  tr.appendChild(text(p.pid, 'num'));
  tr.appendChild(text(p.label + (p.is_self ? '  (this server)' : ''), ''));
  tr.appendChild(text((p.rss_mb != null ? Math.round(p.rss_mb) + 'M' : '—'), 'num'));
  tr.appendChild(cell(meter(p.cpu, 100, {suffix:'% cpu'})));
  tr.appendChild(cell(meter(p.mem, 100, {suffix:'% memory'})));
  tr.appendChild(cell(meter(elapsedSeconds(p.elapsed), 86400,
                            {tone:'info', exact: p.elapsed + ' uptime'})));
  tr.appendChild(text(p.cmd, 'cmd'));
  return tr;
}

async function refresh(){
  let s;
  try { s = await (await fetch('api/processes', {cache:'no-store'})).json(); }
  catch(e){ return; }

  fleetBody.replaceChildren();
  if (!s.fleet.length){
    const tr = document.createElement('tr'); const td = document.createElement('td');
    td.colSpan = 7; td.className='empty'; td.textContent = '// nothing running';
    tr.appendChild(td); fleetBody.appendChild(tr);
  } else s.fleet.forEach(p => fleetBody.appendChild(row(p, true)));

  extBody.replaceChildren();
  s.external.forEach(p => extBody.appendChild(row(p, false)));

  const heavyBody = document.getElementById('heavyBody');
  if (heavyBody){
    heavyBody.replaceChildren();
    (s.heavies || []).forEach(p => heavyBody.appendChild(row(p, false)));
  }

  document.getElementById('count').textContent =
    s.killable + ' killable · ' + s.external.length + ' runtimes · '
    + (s.heavies || []).length + ' heavy';
  killBtn.disabled = s.killable === 0;
  if (s.killable === 0 && killBtn.dataset.armed !== '1')
    killNote.textContent = 'Nothing to kill right now.';
}

async function getToken(){
  try { token = (await (await fetch('api/kill-token')).json()).token; } catch(e){}
}

function disarm(){
  killBtn.dataset.armed = '0';
  killBtn.textContent = 'Kill all fleet processes';
  killNote.textContent = 'Sends SIGKILL (kill -9). Agent runtimes below are not touched.';
  clearTimeout(armTimer);
}

killBtn.addEventListener('click', async () => {
  if (killBtn.dataset.armed !== '1'){
    killBtn.dataset.armed = '1';
    killBtn.textContent = 'Click again to confirm';
    killNote.textContent = 'Arming for 5 seconds — click again to send SIGKILL, or wait to cancel.';
    armTimer = setTimeout(disarm, 5000);
    return;
  }
  disarm();
  killBtn.disabled = true;
  result.textContent = 'sending SIGKILL…';
  try {
    const r = await fetch('api/kill', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({token})
    });
    const d = await r.json();
    if (d.error){ result.textContent = 'refused: ' + d.error; }
    else if (!d.killed.length){ result.textContent = 'nothing was running.'; }
    else {
      result.textContent = 'killed ' + d.killed.length + ':\n' +
        d.killed.map(k => '  ' + k.pid + '  ' + k.label).join('\n') +
        (d.failed.length ? '\nfailed:\n' + d.failed.map(f => '  ' + f.pid + '  ' + f.error).join('\n') : '');
    }
  } catch(e){ result.textContent = 'request failed: ' + e.message; }
  killBtn.disabled = false;
  refresh();
});

disarm(); getToken(); refresh(); setInterval(refresh, 8000);
"""


def page():
    import meter
    import nav
    head = ("<tr><th>PID</th><th>What</th><th>RSS</th><th>CPU</th><th>MEM</th>"
            "<th>Uptime</th><th>Command</th></tr>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nav.title("processes")}</title>
<style>{CSS}\n{nav.CSS}\n{meter.CSS}</style></head>
<body>
<div class="wrap">
  <header>
    <h1>Processes</h1>
    <span class="sub" id="count">…</span>
    {nav.html('/procs')}
  </header>

  <h2>Fleet work &mdash; started by the fleet, killable</h2>
  <table><thead>{head}</thead><tbody id="fleetBody"></tbody></table>

  <div class="danger">
    <h2>&#9888; Kill switch</h2>
    <p>Sends <strong>SIGKILL</strong> to every fleet process above. Scheduled jobs
    will start again at their next interval &mdash; this stops what is running now,
    it does not disable the schedule.</p>
    <button id="kill" data-armed="0">Kill all fleet processes</button>
    <div id="killnote"></div>
    <div id="result"></div>
  </div>

  <h2>Agent runtimes &mdash; not touched by the kill switch</h2>
  <table><thead>{head}</thead><tbody id="extBody"></tbody></table>

  <h2>Heaviest on the box &mdash; RSS, any process, never killable here</h2>
  <table><thead>{head}</thead><tbody id="heavyBody"></tbody></table>
</div>
<script>{JS}</script>
</body></html>"""
