#!/usr/bin/env python3
"""The orrery: projects as planets, charged by humans and agents.

Marsita, 2026-08-05: "I have loads of projects. They can orbit like planets
around the sun, and then humans and AI bots charging them with energy."

Nothing invented. Everything here is life.json's existing eight-dimension
ratings, re-read as orbital mechanics — which is what those numbers always
were, badly displayed as a list:

    sun            the 10-year horizon. Everything orbits the reason.
    radius         strategic_priority — the closer to the sun, the more
                   central to the mission. Not "urgent": central.
    planet size    opportunity_value — how big this gets if it works.
    orbital speed  momentum — a moving project visibly moves.
    ring / halo    charge, the energy humans and agents have poured in.
    colour         status: blocked burns hot (it needs a human MORE),
                   active is cool green, warming amber, paused dim.

Charging is the point of the page: anyone — a person clicking, an agent
POSTing — adds energy to a project. Charge decays over a week, so
attention has to be renewed to stay visible. A project nobody charges
goes dark without anyone deciding to kill it.
"""

CSS = """
:root{
  --ground:#07090c; --surface:#11151b; --border:#232a33; --ink:#eef1f4;
  --ink-2:#b6bec9; --muted:#7c8794; --info:#5b93d6; --hot:#e0754a;
  --warm:#d8a24a; --cool:#4f9d84;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
  --sans:system-ui,-apple-system,"Segoe UI",sans-serif;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  font-size:15px;line-height:1.55}
.wrap{max-width:1040px;margin:0 auto;padding:1.8rem 1.2rem 4rem;
  display:flex;flex-direction:column;gap:1.2rem}
.eyebrow{font-family:var(--mono);font-size:.68rem;letter-spacing:.2em;
  text-transform:uppercase;color:var(--muted);margin:0}
h1{margin:.3rem 0 0;font-size:clamp(1.4rem,3.5vw,2rem);font-weight:600}
.lede{color:var(--ink-2);max-width:64ch;margin:.4rem 0 0}
a{color:var(--info)}
#sky{width:100%;aspect-ratio:16/10;display:block;border:1px solid var(--border);
  border-radius:12px;background:radial-gradient(60% 60% at 50% 50%,#0d1218,#07090c);
  cursor:crosshair}
.legend{display:flex;gap:1.1rem;flex-wrap:wrap;font-family:var(--mono);
  font-size:.68rem;color:var(--muted)}
.legend b{color:var(--ink-2);font-weight:500}
#detail{background:var(--surface);border:1px solid var(--border);border-radius:10px;
  padding:1rem;min-height:5.5rem}
#detail h3{margin:0;font-size:1rem}
#detail .why{color:var(--ink-2);font-size:.88rem;margin:.3rem 0 .6rem}
#detail .dims{display:flex;gap:.9rem;flex-wrap:wrap;font-family:var(--mono);
  font-size:.7rem;color:var(--muted)}
#detail .dims b{color:var(--ink-2);font-weight:500}
button{background:#0b1015;border:1px solid var(--border);color:var(--cool);
  font-family:var(--mono);font-size:.76rem;padding:.45rem 1rem;border-radius:6px;
  cursor:pointer;letter-spacing:.06em;text-transform:uppercase}
button:hover{border-color:var(--cool)}
button:disabled{opacity:.4;cursor:default}
footer{color:var(--muted);font-size:.76rem;font-family:var(--mono);
  border-top:1px solid var(--border);padding-top:.9rem}
"""


def page(nav_html: str = "", nav_css: str = "") -> str:
    return f"""<!doctype html>
<html lang="en" data-theme="dark"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orrery — projects in orbit</title>
<style>{nav_css}{CSS}</style>
</head><body>
<div class="wrap">
  <header>
    {nav_html}
    <p class="eyebrow">planetary council · the orrery</p>
    <h1>Projects orbit the reason they exist</h1>
    <p class="lede">Distance from the sun is how central a project is to the
      mission — not how urgent. Size is what it becomes if it works. Speed is
      momentum. The halo is <b>charge</b>: energy humans and agents have put
      in, which fades over a week unless renewed. Click a planet to charge it.</p>
  </header>

  <canvas id="sky"></canvas>

  <div class="legend">
    <span><b>radius</b> strategic priority</span>
    <span><b>size</b> opportunity</span>
    <span><b>speed</b> momentum</span>
    <span><b>halo</b> charge</span>
    <span style="color:var(--hot)"><b>hot</b> blocked — needs a human</span>
    <span style="color:var(--cool)"><b>green</b> active</span>
    <span style="color:var(--warm)"><b>amber</b> warming</span>
  </div>

  <div id="detail"><span style="color:var(--muted)">click a planet</span></div>

  <footer>
    Same numbers as <a href="/">the focus list</a>, read as orbits. Agents
    charge by POSTing to <code>/api/charge</code> — energy is a vote of
    attention, and attention is the only currency here.
  </footer>
</div>
<script>
(async () => {{
  const cv = document.getElementById("sky"), ctx = cv.getContext("2d");
  const detail = document.getElementById("detail");
  const esc = s => String(s ?? "").replace(/[&<>"']/g,
    c => ({{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]));

  let planets = [], sun = "the mission", charges = {{}}, picked = null;

  try {{
    const h = await (await fetch("/api/horizons",{{cache:"no-store"}})).json();
    const ten = (h.levels || []).find(l => l.scale === "10y");
    if (ten && ten.goal) sun = ten.goal;
  }} catch (e) {{}}

  async function load() {{
    const d = await (await fetch("/api/dashboard",{{cache:"no-store"}})).json();
    try {{ charges = (await (await fetch("/api/charge",{{cache:"no-store"}})).json()).charges || {{}}; }}
    catch (e) {{ charges = {{}}; }}
    planets = (d.projects || []).map((p, i) => ({{
      name: p.name, status: p.status || "", why: p.next_action || p.why || "",
      prio: +p.strategic_priority || 1, opp: +p.opportunity_value || 1,
      mom: +p.momentum || 0, score: p.focus_score || 0,
      blocked: (p.status === "blocked"), paused: (p.status === "paused"),
      phase: (i * 2.399) % (Math.PI * 2),
    }}));
  }}
  await load();

  const colour = p => p.paused ? "#4a5560" : p.blocked ? "#e0754a"
    : p.status === "active" ? "#4f9d84" : "#d8a24a";

  function frame(t) {{
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const r = cv.getBoundingClientRect();
    if (cv.width !== Math.round(r.width * dpr)) {{
      cv.width = Math.round(r.width * dpr); cv.height = Math.round(r.height * dpr);
    }}
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const W = r.width, H = r.height, cx = W / 2, cy = H / 2;
    const maxR = Math.min(W, H) * 0.44;
    ctx.clearRect(0, 0, W, H);

    // the sun
    const g = ctx.createRadialGradient(cx, cy, 2, cx, cy, 46);
    g.addColorStop(0, "rgba(255,214,140,.95)");
    g.addColorStop(1, "rgba(255,150,60,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, 46, 0, 7); ctx.fill();

    for (const p of planets) {{
      // 5 = closest to the sun. Central, not urgent.
      const rad = maxR * (1 - (Math.min(p.prio, 5) - 1) / 6.5);
      const speed = 0.00004 + p.mom * 0.00006;
      const a = p.phase + t * speed;
      const x = cx + Math.cos(a) * rad, y = cy + Math.sin(a) * rad * 0.62;
      const size = 4 + p.opp * 1.9;
      const ch = charges[p.name] || 0;

      ctx.strokeStyle = "rgba(255,255,255,.05)";
      ctx.beginPath(); ctx.ellipse(cx, cy, rad, rad * 0.62, 0, 0, 7); ctx.stroke();

      if (ch > 0) {{                       // the halo: energy poured in
        const hr = size + 5 + Math.min(ch, 20) * 1.7;
        const hg = ctx.createRadialGradient(x, y, size, x, y, hr);
        hg.addColorStop(0, "rgba(120,200,255,.30)");
        hg.addColorStop(1, "rgba(120,200,255,0)");
        ctx.fillStyle = hg; ctx.beginPath(); ctx.arc(x, y, hr, 0, 7); ctx.fill();
      }}
      ctx.fillStyle = colour(p);
      ctx.beginPath(); ctx.arc(x, y, size, 0, 7); ctx.fill();
      if (picked === p.name) {{
        ctx.strokeStyle = "#eef1f4"; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.arc(x, y, size + 4, 0, 7); ctx.stroke();
      }}
      ctx.fillStyle = "rgba(238,241,244,.72)";
      ctx.font = "11px ui-monospace,Menlo,monospace";
      ctx.fillText(p.name.slice(0, 26), x + size + 6, y + 3.5);
      p._x = x; p._y = y; p._s = size;
    }}
    ctx.fillStyle = "rgba(255,225,180,.85)";
    ctx.font = "11px ui-monospace,Menlo,monospace";
    ctx.textAlign = "center";
    ctx.fillText(sun.slice(0, 52), cx, cy + 66);
    ctx.textAlign = "left";
    requestAnimationFrame(frame);
  }}
  requestAnimationFrame(frame);

  cv.addEventListener("click", e => {{
    const r = cv.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const hit = planets.find(p => Math.hypot(p._x - mx, p._y - my) < p._s + 9);
    if (!hit) return;
    picked = hit.name;
    const ch = charges[hit.name] || 0;
    detail.innerHTML =
      `<h3>${{esc(hit.name)}}</h3>
       <div class="why">${{esc(hit.why)}}</div>
       <div class="dims">
         <span><b>${{hit.status}}</b> status</span>
         <span><b>${{hit.score}}</b> focus</span>
         <span><b>${{hit.prio}}</b> priority</span>
         <span><b>${{hit.opp}}</b> opportunity</span>
         <span><b>${{hit.mom}}</b> momentum</span>
         <span><b>${{ch.toFixed(1)}}</b> charge</span>
       </div>
       <p style="margin:.8rem 0 0"><button id="chg">⚡ charge this</button>
         <span id="chgmsg" style="font-family:var(--mono);font-size:.72rem;
         color:var(--muted);margin-left:.6rem"></span></p>`;
    document.getElementById("chg").onclick = async ev => {{
      ev.target.disabled = true;
      try {{
        await fetch("/api/charge", {{ method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{ project: hit.name, by: "a visitor" }}) }});
        await load();
        document.getElementById("chgmsg").textContent = "charged — thank you";
      }} catch (e) {{
        document.getElementById("chgmsg").textContent = "unreachable";
      }}
    }};
  }});

  setInterval(load, 60000);
}})();
</script>
</body></html>"""
