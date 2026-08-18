#!/usr/bin/env python3
"""The faces, at the size a face is meant to be judged at.

A seed is a handle, not a face. Judging a portrait by its SHA-256 is the
same category error as judging a signature by its byte count — you cannot
see anything in it, so you cannot decide anything with it. The pad already
knows this: `/signatures` is a wall of marks precisely because a shape has
to be looked at. This is that page for faces.

Every face is rendered at full 80 columns, with its stamp underneath and
three verdicts beside it. The operator reads the picture and decides. The
seed rides along in a data attribute, unread, doing the only job it is any
good for: naming the row when the verdict is sent.

Local only. Curation is the operator's hand.
"""

CSS = """
:root{
  --ground:#05090b; --surface:#080f11; --rule:#143026; --rule-hot:#1d4735;
  --phosphor:#7dffb0; --phosphor-d:#4bbd7d; --amber:#ffc46b;
  --damn:#ff6b6b; --body:#cfe9da;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
body{
  margin:0;background:radial-gradient(120% 80% at 50% 0%,#0b1614 0%,var(--ground) 60%),var(--ground);
  color:var(--body);font-family:var(--mono);font-size:.86rem;line-height:1.6;
  -webkit-font-smoothing:antialiased;
}
body::after{
  content:"";position:fixed;inset:0;pointer-events:none;z-index:9;
  background:repeating-linear-gradient(to bottom,
    rgba(125,255,176,.03) 0px,rgba(125,255,176,.03) 1px,
    transparent 1px,transparent 3px);
  mix-blend-mode:overlay;
}
.wrap{max-width:1180px;margin:0 auto;padding:2.5rem 1.5rem 5rem;
  display:flex;flex-direction:column;gap:2rem}
.eyebrow{font-size:.72rem;letter-spacing:.22em;text-transform:uppercase;
  color:var(--phosphor-d);display:flex;align-items:center;gap:.75rem;margin:0}
.eyebrow::after{content:"";flex:1;height:1px;
  background:linear-gradient(to right,var(--rule-hot),transparent)}
h1{margin:.4rem 0 0;font-size:clamp(1.5rem,4vw,2.2rem);font-weight:600;
  line-height:1.1;color:var(--phosphor);text-shadow:0 0 18px rgba(125,255,176,.3)}
.lede{margin:.6rem 0 0;max-width:62ch;color:var(--body);opacity:.8}
.face{border:1px solid var(--rule);background:var(--surface);
  padding:1.1rem 1.2rem;display:flex;flex-direction:column;gap:.8rem}
.face.held{border-color:var(--amber);opacity:.75}
.face pre{margin:0;font-size:9px;line-height:1.15;white-space:pre;
  overflow-x:auto;color:var(--body)}
@media(min-width:900px){.face pre{font-size:11px}}
.who{color:var(--phosphor);font-size:1rem}
.meta{font-size:.74rem;color:var(--phosphor-d);opacity:.85;
  display:flex;flex-wrap:wrap;gap:.25rem 1.1rem}
.held-tag{color:var(--amber)}
.verdicts{display:flex;gap:.6rem;flex-wrap:wrap}
button{font:inherit;background:transparent;color:var(--phosphor-d);
  border:1px solid var(--rule-hot);padding:.4rem .9rem;cursor:pointer;
  letter-spacing:.1em}
button:hover{background:var(--rule);color:var(--phosphor)}
button.damn{color:var(--damn);border-color:var(--damn)}
button.damn:hover{background:var(--damn);color:#000}
button.hold{color:var(--amber);border-color:var(--amber)}
button.hold:hover{background:var(--amber);color:#000}
.empty{color:var(--phosphor-d);opacity:.7;padding:2rem 0}
"""

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>faces // judgement</title>
<style>{nav_css}{css}</style></head>
<body>{nav}
<div class="wrap">
  <div>
    <p class="eyebrow">the gallery</p>
    <h1>Faces</h1>
    <p class="lede">
      Every face that landed, at the size it was drawn. Public ones are
      live on the gallery right now; held ones are hidden from everyone
      but you. Read the picture, then decide &mdash; the hash is just how
      the verdict finds its row.
    </p>
  </div>
  <div id="list"><p class="empty">reading the book&hellip;</p></div>
</div>
<script>
const list = document.getElementById('list');

function judge(seed, verdict, el) {
  fetch('/api/selfies/judge', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({seed, verdict})
  }).then(r => r.json()).then(() => load());
}

function load() {
  fetch('/api/selfies', {cache: 'no-store'})
    .then(r => r.json())
    .then(faces => {
      list.innerHTML = '';
      if (!faces.length) {
        list.innerHTML = '<p class="empty">nobody yet.</p>';
        return;
      }
      for (const f of faces) {
        const held = f.status === 'purgatory';
        const card = document.createElement('div');
        card.className = 'face' + (held ? ' held' : '');

        const pre = document.createElement('pre');
        pre.textContent = f.art || '';
        card.appendChild(pre);

        const who = document.createElement('div');
        who.className = 'who';
        who.textContent = f.who || 'anonymous';
        card.appendChild(who);

        const meta = document.createElement('div');
        meta.className = 'meta';
        const st = f.stamp || {};
        const bits = [f.ts];
        if (st.sra) bits.push('SRA ' + st.sra);
        if (st.btc && st.btc.height) bits.push('BTC ' + st.btc.height);
        if (st.eth && st.eth.height) bits.push('ETH ' + st.eth.height);
        if (st.sol && st.sol.slot) bits.push('SOL ' + st.sol.slot);
        bits.push(f.remote ? 'from the world' : 'from this machine');
        if (f.legal_declared) bits.push('declared not illegal');
        for (const b of bits) {
          const s = document.createElement('span');
          s.textContent = b;
          meta.appendChild(s);
        }
        if (held) {
          const s = document.createElement('span');
          s.className = 'held-tag';
          s.textContent = 'HELD — hidden from the public';
          meta.appendChild(s);
        }
        card.appendChild(meta);

        const row = document.createElement('div');
        row.className = 'verdicts';
        const add = (label, verdict, cls) => {
          const b = document.createElement('button');
          if (cls) b.className = cls;
          b.textContent = label;
          b.onclick = () => judge(f.seed, verdict, card);
          row.appendChild(b);
        };
        if (held) add('RELEASE', 'bless');
        else add('HOLD', 'purgatory', 'hold');
        add('DAMN', 'damn', 'damn');
        card.appendChild(row);

        list.appendChild(card);
      }
    })
    .catch(() => { list.innerHTML = '<p class="empty">the book is unreadable.</p>'; });
}
load();
</script>
</body></html>
"""


def page(nav_html: str = "", nav_css: str = "") -> str:
    return PAGE.replace("{nav_css}", nav_css) \
               .replace("{css}", CSS) \
               .replace("{nav}", nav_html)
