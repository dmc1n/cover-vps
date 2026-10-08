// Rain that keeps falling over the story's rain chapter (ADR-106). The rendered frames (ADR-071)
// carry the rain as streaks baked into each picture, and a picture changes only when the visitor
// scrolls: standing still, the rain stood still (the owner, 8 Oct 2026: "the rain on the scroll
// page stops moving"). This layer draws streaks that fall in time, not with the scroll, in the
// look of the rendered ones (thin, light, leaning with the wind, steeper further down), with a
// small splash where a drop lands.
//
// It runs only while it can be seen: the chapter is on screen, the rain has started and the page
// is visible. The clock restarts after a pause (a background tab, scrolling away), so the drops
// never jump or stop. A fixed pool of drops is recycled, nothing is allocated per frame. Visitors
// who asked for less motion see the frames' own, still rain.
import { useEffect, useRef } from "react";

const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));

// three depths of drops: far ones short, faint and slow, near ones long and fast (px at 900 px high)
const LAYERS = [
  { count: 150, len: [10, 18], speed: 950, alpha: 0.22, width: 0.8 },
  { count: 90, len: [20, 32], speed: 1450, alpha: 0.32, width: 1.1 },
  { count: 26, len: [42, 70], speed: 2300, alpha: 0.26, width: 1.6 },
];
const SPLASHES = 48;
const SPLASH_S = 0.16; // how long a splash shows

export function RainLayer({
  amount,
}: {
  /** 0..1: how hard it rains now (read every frame; follows the scroll) */
  amount: () => number;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    // drops: x, y (0..1 of the box), length and depth; seeded so every visit looks alike
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
    const drops = LAYERS.flatMap((l, depth) =>
      Array.from({ length: l.count }, () => ({
        x: rnd() * 1.2 - 0.1,
        y: rnd(),
        len: l.len[0] + rnd() * (l.len[1] - l.len[0]),
        depth,
        // where this drop meets the ground (lower part of the picture), for its splash
        land: 0.62 + rnd() * 0.38,
      })),
    );
    const splash = Array.from({ length: SPLASHES }, () => ({
      x: 0,
      y: 0,
      age: SPLASH_S,
    }));
    let nextSplash = 0;

    let W = 0;
    let H = 0;
    let k = 1;
    const resize = () => {
      const r = el.getBoundingClientRect();
      k = Math.min(window.devicePixelRatio || 1, 1.5);
      W = el.width = Math.max(1, Math.round(r.width * k));
      H = el.height = Math.max(1, Math.round(r.height * k));
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let raf = 0;
    let last = 0;
    let onScreen = true;
    let drawn = false; // something is on the canvas that may need clearing
    const frame = (t: number) => {
      raf = 0;
      // a pause (another tab, the chapter off screen) never makes the drops jump
      const dt = last ? Math.min((t - last) / 1000, 1 / 20) : 0;
      last = t;
      const a = clamp(amount());
      if (a <= 0.001) {
        if (drawn) ctx.clearRect(0, 0, W, H);
        drawn = false;
      } else {
        drawn = true;
        ctx.clearRect(0, 0, W, H);
        const scale = H / (900 * k); // the speeds and lengths are for a 900 px high picture
        ctx.lineCap = "round";
        for (let depth = 0; depth < LAYERS.length; depth++) {
          const L = LAYERS[depth];
          ctx.strokeStyle = `rgba(226, 232, 229, ${L.alpha * a})`;
          ctx.lineWidth = L.width * k;
          ctx.beginPath();
          // fewer drops while the rain begins
          const shown = Math.ceil(L.count * (0.35 + 0.65 * a));
          let n = 0;
          for (const d of drops) {
            if (d.depth !== depth) continue;
            if (n++ >= shown) continue;
            d.y += (L.speed * scale * dt * k) / H;
            const slant = 0.36 - 0.26 * clamp(d.y); // leaning with the wind, steeper below
            d.x += (L.speed * scale * dt * k * slant) / W;
            if (d.y > (depth === 0 ? 1.05 : d.land)) {
              if (depth > 0 && a > 0.3) {
                const s = splash[nextSplash];
                nextSplash = (nextSplash + 1) % SPLASHES;
                s.x = d.x * W;
                s.y = d.land * H;
                s.age = 0;
              }
              d.y -= depth === 0 ? 1.1 : d.land + 0.05;
              d.x = rnd() * 1.2 - 0.15;
            }
            const len = d.len * scale * k;
            const x = d.x * W;
            const y = d.y * H;
            ctx.moveTo(x, y);
            ctx.lineTo(x - len * slant, y - len);
          }
          ctx.stroke();
        }
        // splashes: a small crown that widens and fades
        ctx.lineWidth = 0.9 * k;
        for (const s of splash) {
          if (s.age >= SPLASH_S) continue;
          s.age += dt;
          const f = clamp(s.age / SPLASH_S);
          const r = (2 + 7 * f) * scale * k;
          ctx.strokeStyle = `rgba(226, 232, 229, ${0.35 * (1 - f) * a})`;
          ctx.beginPath();
          ctx.ellipse(s.x, s.y, r, r * 0.3, 0, Math.PI, 2 * Math.PI);
          ctx.stroke();
        }
      }
      schedule();
    };
    const schedule = () => {
      if (!raf && onScreen && document.visibilityState === "visible")
        raf = requestAnimationFrame(frame);
    };
    const stop = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
      last = 0;
    };
    const io =
      "IntersectionObserver" in window
        ? new IntersectionObserver(([e]) => {
            onScreen = e.isIntersecting;
            if (onScreen) schedule();
            else stop();
          })
        : null;
    io?.observe(el);
    const onVisible = () => {
      if (document.visibilityState === "visible") {
        last = 0;
        schedule();
      } else stop();
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("pageshow", onVisible);
    window.addEventListener("focus", onVisible);
    schedule();
    return () => {
      stop();
      io?.disconnect();
      ro.disconnect();
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("pageshow", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [amount]);
  return (
    <canvas
      ref={canvas}
      aria-hidden
      className="st-rainfall"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        pointerEvents: "none",
      }}
    />
  );
}
