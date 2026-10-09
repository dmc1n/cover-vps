// All the falling rain over the story's rain chapter, drawn in time (ADR-106, ADR-114).
//
// The rendered frames (ADR-071) are scrubbed by the scroll, so anything baked into them moves
// only when the visitor scrolls: baked drops stood still while reading and rose when scrolling
// up (the owner, 9 Oct 2026: "when scrolling we still have the static rain"). The frames now
// carry only what may follow the scroll (the canvas darkening, beads on the coating, the runs
// down the computed paths, the wet stone); every falling drop is drawn here, by the clock, so it
// falls the same whether the visitor stands still, scrolls down or scrolls up.
//
// The look is the start film's rain (render_hero.py): near-upright streaks as a camera's shutter
// draws them, light against the scene, in three depths (far ones short and faint, near ones
// long, wide and soft as if out of focus), each streak brightest at its head. Streaks are drawn
// from three small pre-rendered sprites, so a frame is a few hundred drawImage calls.
//
// It runs only while it can be seen: on screen, rain under way, the page visible. The clock
// restarts after a pause (a background tab, scrolling away), so the drops never jump or stop.
// A fixed pool of drops is recycled; nothing is allocated per frame. Visitors who asked for less
// motion get no falling rain (the frames show the wet scene).
import { useEffect, useRef } from "react";

const clamp = (x: number, a = 0, b = 1) => Math.min(b, Math.max(a, x));

// three depths, sizes in px at a 900 px high picture: the streak's length (the distance a drop
// falls while the shutter is open, 1/48 s), its width and brightness
export const LAYERS = [
  { count: 110, len: [34, 62], width: 1.0, alpha: 0.2, blur: 0 },
  { count: 70, len: [70, 120], width: 1.4, alpha: 0.27, blur: 0 },
  { count: 16, len: [150, 230], width: 3.2, alpha: 0.16, blur: 1.6 },
];
const SHUTTER = 48; // a streak is what the drop travels in 1/48 s: speed = length × 48 per s
const SLANT = 0.045; // the start film's light wind: a few degrees from upright
const SPLASHES = 40;
const SPLASH_S = 0.14; // how long a splash shows
const COLOUR = "226, 232, 230";

function sprite(width: number, blur: number, k: number): HTMLCanvasElement {
  // one streak, 64 px long (scaled to each drop's length): faint tail, bright head
  const pad = Math.ceil((blur + 1) * 2 * k);
  const c = document.createElement("canvas");
  c.width = Math.ceil(width * k) + 2 * pad;
  c.height = 64 + 2 * pad;
  const x = c.getContext("2d")!;
  const g = x.createLinearGradient(0, pad, 0, pad + 64);
  g.addColorStop(0, `rgba(${COLOUR}, 0)`);
  g.addColorStop(0.55, `rgba(${COLOUR}, 0.55)`);
  g.addColorStop(0.92, `rgba(${COLOUR}, 1)`);
  g.addColorStop(1, `rgba(${COLOUR}, 0.3)`);
  if (blur) x.filter = `blur(${blur * k}px)`;
  x.fillStyle = g;
  x.fillRect(pad, pad, Math.ceil(width * k), 64);
  return c;
}

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

    // drops: x, y (0..1 of the box, y the head), length; seeded so every visit looks alike
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
    const drops = LAYERS.flatMap((l, depth) =>
      Array.from({ length: l.count }, () => ({
        x: rnd() * 1.1 - 0.05,
        y: rnd() * 1.4 - 0.2,
        len: l.len[0] + rnd() * (l.len[1] - l.len[0]),
        depth,
        // where this drop meets the ground (the lower part of the picture), for its splash
        land: 0.7 + rnd() * 0.3,
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
    let sprites: HTMLCanvasElement[] = [];
    const resize = () => {
      const r = el.getBoundingClientRect();
      k = Math.min(window.devicePixelRatio || 1, 1.5);
      W = el.width = Math.max(1, Math.round(r.width * k));
      H = el.height = Math.max(1, Math.round(r.height * k));
      sprites = LAYERS.map((l) => sprite(l.width, l.blur, k));
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
      // (never backwards: a clock that steps back must not lift the drops)
      const dt = last ? clamp((t - last) / 1000, 0, 1 / 20) : 0;
      last = t;
      const a = clamp(amount());
      if (a <= 0.001) {
        if (drawn) ctx.clearRect(0, 0, W, H);
        drawn = false;
      } else {
        drawn = true;
        ctx.clearRect(0, 0, W, H);
        const px = H / 900; // the sizes are for a 900 px high picture
        for (let depth = 0; depth < LAYERS.length; depth++) {
          const L = LAYERS[depth];
          const img = sprites[depth];
          const pad = (img.width - Math.ceil(L.width * k)) / 2;
          // fewer drops while the rain begins
          const shown = Math.ceil(L.count * (0.3 + 0.7 * a));
          let n = 0;
          for (const d of drops) {
            if (d.depth !== depth) continue;
            const on = n++ < shown;
            const len = d.len * px;
            const fall = len * SHUTTER * dt; // px this frame (always down)
            d.y += fall / H;
            d.x += (fall * SLANT) / W;
            if (d.y > (depth === 0 ? 1.0 + len / H : d.land)) {
              if (on && depth > 0 && a > 0.3) {
                const s = splash[nextSplash];
                nextSplash = (nextSplash + 1) % SPLASHES;
                s.x = d.x * W;
                s.y = d.land * H;
                s.age = 0;
              }
              d.y = -rnd() * 0.25 - len / H;
              d.x = rnd() * 1.1 - 0.05;
            }
            if (!on) continue;
            ctx.globalAlpha = L.alpha * (0.35 + 0.65 * a);
            const scale = len / 64;
            ctx.drawImage(
              img,
              d.x * W - pad,
              d.y * H - len - pad * scale,
              img.width,
              img.height * scale,
            );
          }
        }
        // splashes: a small crown that widens and fades
        ctx.globalAlpha = 1;
        ctx.lineWidth = 0.9 * k;
        for (const s of splash) {
          if (s.age >= SPLASH_S) continue;
          s.age += dt;
          const f = clamp(s.age / SPLASH_S);
          const r = (2 + 6 * f) * px;
          ctx.strokeStyle = `rgba(${COLOUR}, ${0.3 * (1 - f) * a})`;
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
