/* The projector. One function, and it does not know or care whether the path
 * it was handed came from a hand on a trackpad or an agent's week of work.
 *
 * That indifference is the point. If humans and agents were drawn by different
 * code the marks would only look comparable, and looking comparable is what a
 * decorative avatar does. Same projector means two signatures differ only where
 * the underlying movement differed.
 *
 *   drawSignature(canvas, seedHex, points, variant)
 *
 * `points` are {x, y, t}. The seed decides how the path folds — how many times,
 * which way it twists, what hue — so the same path with a different seed is a
 * different mark, and the same seed always reproduces exactly. That determinism
 * is what makes a signature checkable rather than merely pretty.
 */
(function (global) {
  "use strict";

  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function rngFromSeed(hex, salt) {
    let h = (0x9e3779b9 ^ (salt || 0)) >>> 0;
    for (let i = 0; i < hex.length; i++) {
      h = Math.imul(h ^ hex.charCodeAt(i), 0x01000193) >>> 0;
    }
    return mulberry32(h);
  }

  function fitCanvas(canvas, ctx) {
    const dpr = Math.min(global.devicePixelRatio || 1, 2);
    const r = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(r.width * dpr));
    canvas.height = Math.max(1, Math.round(r.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return r;
  }

  function drawSignature(canvas, seedHex, points, variant) {
    if (!canvas || !seedHex || !points || points.length < 3) return;
    const ctx = canvas.getContext("2d");
    const rect = fitCanvas(canvas, ctx);
    const W = rect.width, H = rect.height;
    const rnd = rngFromSeed(seedHex, variant || 0);

    const folds = [3, 4, 5, 6, 7, 8, 9, 12][Math.floor(rnd() * 8)];
    const hue = Math.floor(rnd() * 360);
    const spread = 30 + rnd() * 90;
    const twist = (rnd() - 0.5) * 0.9;
    const mirror = rnd() > 0.45;
    const weight = 0.7 + rnd() * 1.9;

    ctx.fillStyle = "#03060a";
    ctx.fillRect(0, 0, W, H);

    // Centre and scale the path. Agents and humans arrive in different units —
    // pixels versus normalised lifetime — so everything is rescaled to its own
    // bounding box. A mark is a shape, not a measurement.
    const xs = points.map(p => p.x), ys = points.map(p => p.y);
    const minX = Math.min.apply(null, xs), maxX = Math.max.apply(null, xs);
    const minY = Math.min.apply(null, ys), maxY = Math.max.apply(null, ys);
    const span = Math.max(maxX - minX, maxY - minY, 1e-6);
    const pts = points.map(p => ({
      x: (p.x - (minX + maxX) / 2) / span,
      y: (p.y - (minY + maxY) / 2) / span,
      t: p.t,
    }));

    const R = Math.min(W, H) * 0.44;
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    for (let f = 0; f < folds; f++) {
      const base = (f / folds) * Math.PI * 2;
      const passes = mirror ? 2 : 1;
      for (let m = 0; m < passes; m++) {
        const flip = m === 1 ? -1 : 1;
        for (let i = 1; i < pts.length; i++) {
          const a = pts[i - 1], b = pts[i];
          const prog = i / pts.length;
          const ang = base + twist * prog;
          const ca = Math.cos(ang), sa = Math.sin(ang);

          const ax = (a.x * ca - a.y * sa) * flip * R + W / 2;
          const ay = (a.x * sa + a.y * ca) * R + H / 2;
          const bx = (b.x * ca - b.y * sa) * flip * R + W / 2;
          const by = (b.x * sa + b.y * ca) * R + H / 2;

          // Speed sets weight. For a hand that is how fast it moved; for an
          // agent it is the gap since it last did anything. A burst of work
          // draws thin and nervous, a long silence draws heavy.
          const dt = Math.max(b.t - a.t, 1e-3);
          const v = Math.min(Math.hypot(b.x - a.x, b.y - a.y) / dt * 40, 3);
          const h = (hue + prog * spread + f * (spread / folds)) % 360;

          ctx.strokeStyle = "hsla(" + h.toFixed(1) + ", 85%, 58%, 0.30)";
          ctx.lineWidth = (0.4 + v * 2.4) * weight;
          ctx.beginPath();
          ctx.moveTo(ax, ay);
          ctx.lineTo(bx, by);
          ctx.stroke();
        }
      }
    }

    ctx.globalCompositeOperation = "source-over";
    const g = ctx.createRadialGradient(W / 2, H / 2, R * 0.5, W / 2, H / 2, R * 1.6);
    g.addColorStop(0, "rgba(3, 6, 10, 0)");
    g.addColorStop(1, "rgba(3, 6, 10, 0.85)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, W, H);
  }

  global.drawSignature = drawSignature;
})(window);
