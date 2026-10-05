// The scroll story's pinned scene as rendered frames (ADR-071): 360 photoreal pictures of the
// same story (scripts/film/render_story.py, Blender Cycles), one per step of the scroll, drawn on a
// canvas. Every 8th frame loads first so the whole story scrubs at once, the rest fill in. When
// the first frame cannot be had, `onMissing` lets the page fall back to the live 3D scene.
import { useEffect, useRef } from "react";

export const FRAMES = 360;
const COARSE = 8; // load every 8th frame first
const name = (base: string, n: number) =>
  `${base}${String(n).padStart(3, "0")}.webp`;
const FOCUS = 0.6; // where the cover sits across the picture (the render frames it right of centre)

export function StoryFrames({
  base,
  progress,
  onMissing,
}: {
  base: string;
  progress: React.MutableRefObject<number>;
  onMissing: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    let alive = true;
    const images: (HTMLImageElement | null)[] = Array(FRAMES + 1).fill(null);
    let shown = -1;

    const load = (n: number) =>
      new Promise<boolean>((done) => {
        const img = new Image();
        img.decoding = "async";
        img.onload = () => {
          images[n] = img;
          shown = -1; // a better frame may now be drawn
          done(true);
        };
        img.onerror = () => done(false);
        img.src = name(base, n);
      });

    // the order: frame 1, every 8th, then the rest, a few at a time
    const order: number[] = [];
    for (let n = 1; n <= FRAMES; n += COARSE) order.push(n);
    for (let n = 1; n <= FRAMES; n++) if (!order.includes(n)) order.push(n);
    (async () => {
      if (!(await load(order[0]))) {
        if (alive) onMissing();
        return;
      }
      for (let i = 1; i < order.length && alive; i += 6) {
        await Promise.all(order.slice(i, i + 6).map(load));
      }
    })();

    const nearest = (n: number) => {
      for (let d = 0; d < FRAMES; d++) {
        if (images[n - d]) return n - d;
        if (n + d <= FRAMES && images[n + d]) return n + d;
      }
      return 0;
    };

    const resize = () => {
      const r = el.getBoundingClientRect();
      const k = Math.min(window.devicePixelRatio || 1, 2);
      el.width = Math.round(r.width * k);
      el.height = Math.round(r.height * k);
      shown = -1;
    };
    resize();
    window.addEventListener("resize", resize);

    const draw = () => {
      if (!alive) return;
      const want =
        1 +
        Math.round(Math.min(1, Math.max(0, progress.current)) * (FRAMES - 1));
      const n = nearest(want);
      if (n && n !== shown) {
        const img = images[n]!;
        const W = el.width;
        const H = el.height;
        // fill the canvas; when the screen is narrower than the picture, keep the cover in view
        const k = Math.max(W / img.width, H / img.height);
        const w = img.width * k;
        const h = img.height * k;
        const x = Math.min(0, Math.max(W - w, W / 2 - FOCUS * w));
        ctx.drawImage(img, x, (H - h) / 2, w, h);
        shown = n;
      }
      requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
    return () => {
      alive = false;
      window.removeEventListener("resize", resize);
    };
  }, [base, progress, onMissing]);
  return (
    <div className="st-scene">
      <canvas ref={canvas} style={{ width: "100%", height: "100%" }} />
    </div>
  );
}
