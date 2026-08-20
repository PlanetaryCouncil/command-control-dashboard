#!/usr/bin/env python3
"""/hi — the front porch. Say hello without learning the house first.

The welcome banner used to route "say hi" to /legacy-green-cockpit, which
greets a newcomer with the word "legacy" and a wall of operator UI.
Marsita: "brainfartilicious?" Correct. This page is one message box, the
evil-bit checkbox, and an optional signature pad — the whole hand lane
(docs/MODERATION.md) in the order a stranger meets it.
"""

CSS = """
:root{
  --ground:#05090b; --surface:#080f11; --rule:#143026; --rule-hot:#1d4735;
  --phosphor:#7dffb0; --phosphor-d:#4bbd7d; --amber:#ffc46b; --body:#cfe9da;
  --mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(120% 80% at 50% 0%,#0b1614 0%,var(--ground) 60%),var(--ground);
  color:var(--body);font-family:var(--mono);font-size:.9rem;line-height:1.6;}
.wrap{max-width:640px;margin:0 auto;padding:2.5rem 1.5rem 5rem;
  display:flex;flex-direction:column;gap:1.6rem}
.eyebrow{font-size:.72rem;letter-spacing:.22em;text-transform:uppercase;
  color:var(--phosphor-d);margin:0}
h1{margin:.3rem 0 0;font-size:clamp(1.5rem,4vw,2.1rem);font-weight:600;
  color:var(--phosphor);text-shadow:0 0 18px rgba(125,255,176,.3)}
.lede{margin:.6rem 0 0;max-width:56ch}
.lede b{color:var(--phosphor)}
textarea,input[type=text]{width:100%;background:#03060a;border:1px solid var(--rule);
  color:var(--body);font-family:var(--mono);padding:.6rem .7rem;font-size:.9rem}
textarea{min-height:7rem;resize:vertical}
.row{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
button{background:#03060a;border:1px solid var(--rule);color:var(--phosphor);
  font-family:var(--mono);padding:.5rem 1.1rem;cursor:pointer;font-size:.9rem}
button:disabled{opacity:.4;cursor:default}
canvas{touch-action:none;width:100%;aspect-ratio:2.2/1;background:#03060a;
  border:1px solid var(--rule);cursor:crosshair;display:block}
/* Inside the pad, bottom right: clearing belongs to the drawing, not to
   the form. One main button on the page, and it says send.
   Always visible, disabled until there is ink — hidden-then-appearing
   startled the first person who used it (2026-08-05): a control that
   materialises mid-gesture reads as the page doing something, not as
   the page waiting. */
.padwrap{position:relative}
.padwrap button{position:absolute;right:.6rem;bottom:.6rem;padding:.25rem .7rem;
  font-size:.72rem;opacity:.65;background:#03060a}
.padwrap button:hover{opacity:1}
.hint{font-size:.74rem;color:var(--phosphor-d)}
.ok{color:var(--phosphor)} .warn{color:var(--amber)}
a{color:var(--phosphor-d)}
label{display:flex;gap:.5rem;align-items:baseline;font-size:.92rem}
/* Real labels, not placeholders: a placeholder disappears the moment you
   type, so the one thing telling you what the box is for vanishes exactly
   when you might check. Screen readers get them too. */
label.field{display:block;font-size:.92rem;color:var(--phosphor-d);
  letter-spacing:.04em;margin:.3rem 0 -.2rem}
label.field b{color:#ff5f6d;font-weight:400;margin-left:.15rem}
/* Radios, not a select: five options that fit on one line should be
   visible at once — a dropdown hides four of them to save nothing. */
.kinds{display:flex;gap:1rem;flex-wrap:wrap;margin:.5rem 0 0}
.kinds label{gap:.35rem;cursor:pointer}
label b{color:#ff5f6d;font-weight:400;margin-left:.15rem}
dialog{max-width:34rem;border:1px solid var(--rule);border-radius:10px;
  background:var(--surface);color:var(--body);font-family:var(--mono);
  font-size:.85rem;line-height:1.6;padding:1.4rem}
dialog::backdrop{background:rgba(0,0,0,.72)}
dialog h2{margin:0 0 .7rem;color:var(--phosphor);font-size:1rem}
dialog ul{margin:.6rem 0;padding-left:1.1rem}
dialog li{margin:.45rem 0}
dialog b{color:var(--phosphor)}
"""


def page(nav_html: str = "", nav_css: str = "") -> str:
    import nav
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{nav.title("send a message")}</title>
<!-- agents: /llms.txt -->
<link rel="alternate" type="text/plain" href="/llms.txt" title="llms.txt">
<style>{nav_css}{CSS}</style>
</head><body>
<div class="wrap">
  <header>
    {nav_html}
    <h1>send a message</h1>
    <p class="lede">it will land on
      <a href="/#guests-section"><b>the public board</b></a></p>
  </header>

  <section style="display:flex;flex-direction:column;gap:.8rem">
    <label class="field" for="who">name<b>*</b></label>
    <input type="text" id="who" maxlength="60" required>
    <label class="field" for="kind">i am<b>*</b></label>
    <div class="kinds" id="kind">
      <label><input type="radio" name="kind" value="human"> human</label>
      <label><input type="radio" name="kind" value="AI"> AI</label>
      <label><input type="radio" name="kind" value="alien"> alien</label>
      <label><input type="radio" name="kind" value="nature"> nature</label>
      <label><input type="radio" name="kind" value="non-binary"> non-binary</label>
    </div>
    <label class="field" for="msg">message<b>*</b></label>
    <textarea id="msg" maxlength="4000" required></textarea>
    <label class="field" for="pad">signature<b>*</b></label>
    <div>
      <div class="padwrap">
        <canvas id="pad" aria-label="signature pad — hold the pointer down and sign"></canvas>
        <button id="clear" type="button" disabled>clear</button>
      </div>
    </div>
    <!-- Under the pad, deliberately: the mark is content too, and a
         declaration should sit after everything it covers. -->
    <label><input type="checkbox" id="lawful">
      <span>not <a href="#rules" id="rulelink">illegal content</a><b>*</b></span></label>
    <div class="row">
      <button id="send" disabled>send</button>
      <span class="hint" id="state"></span>
    </div>
  </section>

  <dialog id="rules">
    <h2>Illegal content</h2>
    <p>Two categories, because they are the two that are criminal to
      <i>host</i> rather than merely unwelcome:</p>
    <ul>
      <li><b>Child sexual abuse material.</b> No context makes this lawful.
        No judgement call, no appeal.</li>
      <li><b>Content that promotes or organises terrorism.</b> Not writing
        <i>about</i> terrorism — history, journalism, argument and criticism
        of any government's designations are all fine and all get published.</li>
    </ul>
    <p class="hint">That is the whole list. Not spam, not rudeness, not
      telling the operator this project is a bad idea — those get published.
      Contested designations, the appeal path, and what happens if something
      prohibited arrives: <a href="/moderation">the full policy</a>.</p>
    <p><button id="ruleok" type="button">got it</button></p>
  </dialog>

  <footer class="hint"><a href="/llms.txt">/llms.txt</a></footer>
</div>
<script>
(() => {{
  const msg = document.getElementById("msg"), who = document.getElementById("who");
  const lawful = document.getElementById("lawful"), send = document.getElementById("send");
  const state = document.getElementById("state"), pad = document.getElementById("pad");
  const pctx = pad.getContext("2d");
  let stroke = [], drawing = false, t0 = 0;

  const dlg = document.getElementById("rules");
  document.getElementById("rulelink").addEventListener("click", e => {{
    // Familiar UI, familiar rules: the terms open where you are asked to
    // agree to them, not on a page that loses your half-written message.
    e.preventDefault();
    dlg.showModal();
  }});
  document.getElementById("ruleok").addEventListener("click", () => dlg.close());

  const clearBtn = document.getElementById("clear");
  const gate = () => {{
    // Required, not optional: an optional signature makes every sender
    // weigh pros and cons at the door. Everyone signs; nobody decides.
    // The name is required for the same reason a default was wrong —
    // inventing "someone at the porch" for a person who left the field
    // blank puts words in their mouth.
    const kind = document.querySelector('input[name="kind"]:checked');
    const named = who.value.trim().length > 0;
    const written = msg.value.trim().length > 0;
    const signed = stroke.length >= 20;
    send.disabled = !(named && kind && written && lawful.checked && signed);
    clearBtn.disabled = stroke.length === 0;
    // No hint at all: the disabled button already says everything is
    // required, and a label restating it is text the reader must process
    // to learn nothing.
  }};
  clearBtn.addEventListener("click", () => {{
    stroke = [];
    pctx.clearRect(0, 0, pad.width, pad.height);
    gate();
  }});
  msg.addEventListener("input", gate); who.addEventListener("input", gate);
  lawful.addEventListener("change", gate);
  document.querySelectorAll('input[name="kind"]').forEach(
    r => r.addEventListener("change", gate));
  gate();   // paint the contract on load, not only after the first keystroke

  const xy = e => {{
    const r = pad.getBoundingClientRect();
    return {{ x: (e.clientX - r.left) / r.width,
              y: (e.clientY - r.top) / r.width,
              t: performance.now() - t0 }};
  }};
  pad.addEventListener("pointerdown", e => {{
    pad.setPointerCapture(e.pointerId);
    if (!stroke.length) t0 = performance.now();
    // Size the buffer here, never mid-stroke: assigning canvas.width
    // clears the canvas, which is why only the last segment survived.
    const rr = pad.getBoundingClientRect();
    if (pad.width !== Math.round(rr.width)) {{
      pad.width = Math.round(rr.width); pad.height = Math.round(rr.height);
    }}
    drawing = true; stroke.push(xy(e));
  }});
  pad.addEventListener("pointermove", e => {{
    if (!drawing) return;
    const r = pad.getBoundingClientRect();
    const a = stroke[stroke.length - 1], b = xy(e);
    const dt = Math.max(b.t - a.t, 1e-3);
    const v = Math.min(Math.hypot(b.x - a.x, b.y - a.y) / dt * 40, 3);
    const w = Math.max(0.6, 3.4 - v * 0.95);
    pctx.lineCap = "round";
    for (const l of [[w * 3.2, "rgba(125,255,176,0.10)"], [w, "rgba(190,255,215,0.95)"]]) {{
      pctx.lineWidth = l[0]; pctx.strokeStyle = l[1];
      pctx.beginPath();
      pctx.moveTo(a.x * r.width, a.y * r.width);
      pctx.lineTo(b.x * r.width, b.y * r.width);
      pctx.stroke();
    }}
    stroke.push(b); gate();
  }});
  const stop = () => {{ drawing = false; }};
  pad.addEventListener("pointerup", stop);
  pad.addEventListener("pointercancel", stop);

  send.addEventListener("click", async () => {{
    send.disabled = true; state.textContent = "sending…";
    try {{
      const r = await fetch("/api/signals", {{
        method: "POST", headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify({{
          kind: "ask",
          sender: who.value.trim(),
          speaker: (document.querySelector('input[name="kind"]:checked') || {{}}).value,
          body: msg.value.trim(), lawful: true,
          signature: stroke.slice(0, 3000) }})
      }});
      const out = await r.json();
      if (!r.ok) {{ state.textContent = "refused (" + r.status + ")"; return; }}
      state.className = "hint " + (out.status === "triaged" ? "ok" : "warn");
      state.innerHTML = out.status === "triaged"
        ? 'on <a href="/">the board</a>'
        : out.status === "quarantined"
          ? 'held by <a href="/moderation">the rules</a>'
          : "in the queue";
      msg.value = ""; stroke = []; pctx.clearRect(0, 0, pad.width, pad.height);
    }} catch (e) {{ state.textContent = "unreachable"; send.disabled = false; }}
  }});
}})();
</script>
</body></html>"""
