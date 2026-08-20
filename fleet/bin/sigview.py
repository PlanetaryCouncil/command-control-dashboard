#!/usr/bin/env python3
"""Every worker's hand, drawn by the same function that draws yours.

The page is deliberately just a wall of marks. There is a table view of this
data one click away (`/api/signatures`) and it tells you nothing — the whole
claim of the thing is that an agent's working rhythm has a *shape*, and a shape
has to be looked at. Numbers next to each mark, not instead of it.

Clicking a mark re-folds it from the same seed. That is the honest demo of what
the seed does: the path is fixed, the folding is chosen, and a different fold of
the same work is still that agent's work.
"""

CSS = """
:root{
  --ground:#05090b; --surface:#080f11; --rule:#143026; --rule-hot:#1d4735;
  --phosphor:#7dffb0; --phosphor-d:#4bbd7d; --amber:#ffc46b; --body:#cfe9da;
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
  line-height:1.1;color:var(--phosphor);text-shadow:0 0 18px rgba(125,255,176,.3);
  text-wrap:balance}
.lede{margin:.9rem 0 0;max-width:64ch}
.lede b{color:var(--phosphor);font-weight:600}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));
  gap:1px;background:var(--rule);border:1px solid var(--rule)}
.card{background:var(--surface);padding:1rem;display:flex;flex-direction:column;gap:.7rem}
.card canvas{display:block;width:100%;aspect-ratio:1/1;background:#03060a;
  border:1px solid var(--rule);cursor:pointer;transition:border-color 140ms ease}
.card canvas:hover{border-color:var(--rule-hot)}
.card canvas:focus-visible{outline:2px solid var(--phosphor);outline-offset:2px}
.name{color:var(--phosphor);letter-spacing:.04em;word-break:break-all}
.meta{display:flex;justify-content:space-between;gap:.5rem;font-size:.72rem;
  color:var(--phosphor-d);letter-spacing:.1em;text-transform:uppercase}
.meta b{color:var(--amber);font-weight:400;font-variant-numeric:tabular-nums}
.seed{font-size:.68rem;color:var(--rule-hot);word-break:break-all;line-height:1.4}
.empty{padding:3rem 1rem;text-align:center;color:var(--phosphor-d);
  letter-spacing:.2em;text-transform:uppercase;font-size:.72rem}
footer{font-size:.72rem;color:var(--phosphor-d);border-top:1px solid var(--rule);
  padding-top:1rem}
"""


def page(nav_html: str = "", nav_css: str = "") -> str:
    import nav
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nav.title("signatures")}</title>
<style>{nav_css}{CSS}</style>
</head><body>
<div class="wrap">
  <header>
    {nav_html}
    <p class="eyebrow">fleet · the signature archive</p>
    <h1>Every hand, ever</h1>
    <p class="lede">
      A person signs by moving a pointer for five seconds. An agent has no
      pointer, so it signs with <b>the shape of its work</b> — when it acted,
      how hard, and the gaps in between. Same three numbers, same projector,
      so the marks are comparable. Click any one to re-fold it from its seed.
    </p>
  </header>

  <section>
    <p class="eyebrow">the pad · sign it</p>
    <p class="lede">Hold the pointer down and move for a few seconds —
      <b>your hand is the entropy</b>. The same projector that draws the
      agents will draw you, and your mark joins the collection below.</p>
    <div class="card" style="max-width:420px">
      <canvas id="pad" style="touch-action:none;aspect-ratio:1/1;width:100%;
        background:#03060a;border:1px solid var(--rule);cursor:crosshair"></canvas>
      <div style="display:flex;gap:.5rem">
        <input id="signame" placeholder="your name (optional)" maxlength="40"
          style="flex:1;background:#03060a;border:1px solid var(--rule);
          color:var(--body);font-family:var(--mono);padding:.45rem .6rem">
        <button id="sigsend" disabled
          style="background:#03060a;border:1px solid var(--rule);
          color:var(--phosphor);font-family:var(--mono);padding:.45rem .9rem;
          cursor:pointer">sign</button>
      </div>
      <div class="meta"><span id="sigstate">draw first</span></div>
    </div>
  </section>

  <section>
    <p class="eyebrow">collected · every hand that signed</p>
    <div class="grid" id="collected"><div class="empty">nobody has signed yet</div></div>
  </section>


  <section id="purgsec" style="display:none">
    <p class="eyebrow" style="color:var(--amber)">purgatory · held by the spam gate</p>
    <p class="lede">Marks too regular to be a living hand wait here.
      They hang on the wall only if the operator blesses them.</p>
    <div class="grid" id="purgatory"></div>
  </section>

  <section>
    <p class="eyebrow">agents · signed by their work</p>
    <div class="grid" id="grid"><div class="empty">reading traces…</div></div>
  </section>

  <section>
    <p class="eyebrow">evolution · the hand learning to write</p>
    <p class="lede">A seed moves as the agent works. Each row is one agent at
      four ages — quarter, half, three-quarters, now. The mark is
      <b>not fixed at birth</b>; this is the proof.</p>
    <div id="evolution"></div>
  </section>



  <footer>
    Seeds are SHA-256 over each agent's path and move as it works — a mark is
    not fixed at birth, it is the accumulated shape of everything the worker
    has done. Agents with fewer than eight events are not drawn: too few
    strokes to be a signature.
  </footer>
</div>

<script src="/static/signature.js"></script>
<script>
(async () => {{
  const grid = document.getElementById("grid");
  let data;
  try {{
    data = await (await fetch("/api/signatures")).json();
  }} catch (e) {{
    grid.innerHTML = '<div class="empty">could not read /api/signatures</div>';
    return;
  }}
  const sigs = (data && data.signatures) || [];
  if (!sigs.length) {{
    grid.innerHTML = '<div class="empty">no agent has enough history yet</div>';
    return;
  }}

  grid.innerHTML = "";
  const variants = new Map();

  for (const s of sigs) {{
    const card = document.createElement("div");
    card.className = "card";

    const cv = document.createElement("canvas");
    cv.tabIndex = 0;
    cv.setAttribute("role", "img");
    cv.setAttribute("aria-label", s.agent + " signature");
    cv.title = "click to re-fold from the same seed";

    const name = document.createElement("div");
    name.className = "name";
    name.textContent = s.agent;

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.innerHTML = "<span>events <b>" + s.events + "</b></span>" +
                     "<span>" + s.last_seen.slice(5, 16).replace("T", " ") + "</span>";

    const seed = document.createElement("div");
    seed.className = "seed";
    seed.textContent = s.seed.slice(0, 32);

    card.append(cv, name, meta, seed);
    grid.append(card);

    const redraw = () => {{
      const v = variants.get(s.agent) || 0;
      drawSignature(cv, s.seed, s.points, v);
    }};
    const bump = () => {{
      variants.set(s.agent, (variants.get(s.agent) || 0) + 1);
      redraw();
    }};
    cv.addEventListener("click", bump);
    cv.addEventListener("keydown", e => {{
      if (e.key === "Enter" || e.key === " ") {{ e.preventDefault(); bump(); }}
    }});
    requestAnimationFrame(redraw);
    window.addEventListener("resize", redraw);
  }}

  // ------------------------------------------------ evolution rows
  const evo = document.getElementById("evolution");
  for (const a of (data && data.evolution) || []) {{
    const row = document.createElement("div");
    row.className = "grid";
    row.style.marginBottom = "1px";
    for (const st of a.stages) {{
      const card = document.createElement("div");
      card.className = "card";
      const cv = document.createElement("canvas");
      cv.setAttribute("role", "img");
      cv.setAttribute("aria-label", a.agent + " at " + st.events + " events");
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.innerHTML = "<span>" + a.agent + "</span><span>at <b>"
        + st.events + "</b> events</span>";
      card.append(cv, meta);
      row.append(card);
      requestAnimationFrame(() => drawSignature(cv, st.seed, st.points, 0));
    }}
    evo.append(row);
  }}

  // ------------------------------------------------ the collected hands
  const wall = document.getElementById("collected");
  const collected = ((data && data.collected) || []).slice()
    .sort((a, b) => ((b.pinned ? 1 : 0) - (a.pinned ? 1 : 0))
      || String(b.ts || "").localeCompare(String(a.ts || "")));
  if (collected.length) {{
    wall.innerHTML = "";
    for (const c of collected) {{
      const card = document.createElement("div");
      card.className = "card";
      const cv = document.createElement("canvas");
      cv.setAttribute("role", "img");
      cv.setAttribute("aria-label", (c.name || "anonymous") + " signature");
      const name = document.createElement("div");
      name.className = "name";
      name.textContent = c.name || "anonymous";
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.innerHTML = "<span>" + (c.kind || "human")
        + (c.pinned ? " · pinned" : "") + "</span><span>"
        + String(c.ts || "").slice(5, 16).replace("T", " ") + "</span>";
      if (c.pinned) cv.style.borderColor = "var(--amber)";
      card.append(cv, name, meta);
      wall.append(card);
      // Everything on the pad wall is a drawing — human hand or agent
      // soul — and drawings render as ink. Folds stay upstairs where the
      // marks are made of work, not intent.
      requestAnimationFrame(() => drawRawSignature(cv, c.points));
    }}
  }}

  // ------------------------------------------------ purgatory
  const purg = (data && data.purgatory) || [];
  if (purg.length) {{
    document.getElementById("purgsec").style.display = "";
    const box = document.getElementById("purgatory");
    const local = location.hostname === "127.0.0.1"
      || location.hostname === "localhost";
    for (const c of purg.slice().reverse()) {{
      const card = document.createElement("div");
      card.className = "card";
      card.style.opacity = "0.55";
      const cv = document.createElement("canvas");
      const nm = document.createElement("div");
      nm.className = "name"; nm.textContent = c.name || "anonymous";
      const mt = document.createElement("div");
      mt.className = "meta";
      mt.innerHTML = "<span>entropy " + (c.entropy ?? "?")
        + "</span><span>" + String(c.ts || "").slice(5, 16).replace("T", " ")
        + "</span>";
      card.append(cv, nm, mt);
      if (local) {{
        const row = document.createElement("div");
        row.className = "meta";
        for (const v of ["bless", "damn"]) {{
          const b = document.createElement("button");
          b.textContent = v;
          b.style.cssText = "background:#03060a;border:1px solid var(--rule);"
            + "color:var(--" + (v === "bless" ? "phosphor" : "amber")
            + ");font-family:var(--mono);padding:.25rem .7rem;cursor:pointer";
          b.onclick = async () => {{
            await fetch("/api/signatures/judge", {{ method: "POST",
              headers: {{ "Content-Type": "application/json" }},
              body: JSON.stringify({{ seed: c.seed, verdict: v }}) }});
            card.remove();
          }};
          row.append(b);
        }}
        card.append(row);
      }}
      box.append(card);
      requestAnimationFrame(() => drawRawSignature(cv, c.points));
    }}
  }}

  // ------------------------------------------------ the pad
  const pad = document.getElementById("pad");
  const send = document.getElementById("sigsend");
  const state = document.getElementById("sigstate");
  const pctx = pad.getContext("2d");
  let stroke = [], drawing = false, t0 = 0;

  function padXY(e) {{
    const r = pad.getBoundingClientRect();
    return {{ x: (e.clientX - r.left) / r.width,
              y: (e.clientY - r.top) / r.width,
              t: performance.now() - t0 }};
  }}
  function padLine(a, b) {{
    // The WOW is the ink answering the hand in real time: dash and it
    // thins to a whisper, linger and it swells and glows. Same physics
    // the wall uses, felt live under the touchpad.
    const r = pad.getBoundingClientRect();
    if (pad.width !== r.width) {{ pad.width = r.width; pad.height = r.height; }}
    const dt = Math.max(b.t - a.t, 1e-3);
    const v = Math.min(Math.hypot(b.x - a.x, b.y - a.y) / dt * 40, 3);
    const w = Math.max(0.6, 3.4 - v * 0.95);
    pctx.lineCap = "round";
    for (const layer of [[w * 3.2, "rgba(125,255,176,0.10)"],
                         [w, "rgba(190,255,215,0.95)"]]) {{
      pctx.lineWidth = layer[0]; pctx.strokeStyle = layer[1];
      pctx.beginPath();
      pctx.moveTo(a.x * r.width, a.y * r.width);
      pctx.lineTo(b.x * r.width, b.y * r.width);
      pctx.stroke();
    }}
  }}
  pad.addEventListener("pointerdown", e => {{
    pad.setPointerCapture(e.pointerId);
    if (!stroke.length) t0 = performance.now();
    drawing = true; stroke.push(padXY(e));
  }});
  pad.addEventListener("pointermove", e => {{
    if (!drawing) return;
    const p = padXY(e);
    if (stroke.length) padLine(stroke[stroke.length - 1], p);
    stroke.push(p);
    state.textContent = stroke.length + " points of entropy";
    send.disabled = stroke.length < 20;
  }});
  const stop = () => {{ drawing = false; }};
  pad.addEventListener("pointerup", stop);
  pad.addEventListener("pointercancel", stop);

  send.addEventListener("click", async () => {{
    // Read the name FIRST — Marsita signed twice on 2026-08-04 and both
    // marks arrived anonymous while a 900ms auto-reload ate the page under
    // them ("I signed and nothing happened"). No reloads: the new mark
    // walks into the wall while you watch.
    const who = document.getElementById("signame").value;
    send.disabled = true; state.textContent = "signing…";
    try {{
      const r = await fetch("/api/signatures/sign", {{
        method: "POST", headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{ name: who, points: stroke.slice(0, 3000) }})
      }});
      const out = await r.json();
      if (!r.ok) {{ state.textContent = "refused (" + r.status + ")";
                    send.disabled = false; return; }}
      state.textContent = "signed, " + (out.name || "friend")
        + " — seed " + String(out.seed || "").slice(0, 12) + "…";
      const card = document.createElement("div");
      card.className = "card";
      const cv = document.createElement("canvas");
      const nm = document.createElement("div");
      nm.className = "name"; nm.textContent = out.name || "anonymous";
      const mt = document.createElement("div");
      mt.className = "meta";
      mt.innerHTML = "<span>human · just now</span>";
      card.append(cv, nm, mt);
      const wallEl = document.getElementById("collected");
      if (wallEl.querySelector(".empty")) wallEl.innerHTML = "";
      wallEl.prepend(card);
      requestAnimationFrame(() =>
        drawRawSignature(cv, stroke.map(p => ({{x:p.x, y:p.y, t:p.t}}))));
      stroke = []; pctx.clearRect(0, 0, pad.width, pad.height);
    }} catch (e) {{ state.textContent = "unreachable"; send.disabled = false; }}
  }});
}})();
</script>
</body></html>"""
