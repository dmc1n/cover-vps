// The scroll story's pinned scene as rendered frames (ADR-071): 360 photoreal pictures of the
// same story (scripts/film/render_story.py, Blender Cycles), one per step of the scroll, drawn on a
// canvas. Every 8th frame loads first so the whole story scrubs at once, the rest fill in. When
// the first frame cannot be had, `onMissing` lets the page fall back to the live 3D scene.
//
// ADR-101: the rest of the frames load only once the story comes near the screen, so they do
// not share the line with the first screen; and the rain chapter gets rain that keeps falling
// (RainLayer), because the rain in the pictures moves only while the visitor scrolls.
import { useCallback, useEffect, useRef } from "react";
import { RainLayer } from "./RainLayer";

export const FRAMES = 360;
const COARSE = 8; // load every 8th frame first
const name = (base: string, n: number) =>
  `${base}${String(n).padStart(3, "0")}.webp`;
const FOCUS = 0.6; // where the cover sits across the picture (the render frames it right of centre)
// where the rain begins and is in full in the rendered timeline (frames 306 to 316 of 360)
const RAIN_FROM = 0.845;
const RAIN_FULL = 0.875;

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
    const coarse = order.length;
    for (let n = 1; n <= FRAMES; n++) if (!order.includes(n)) order.push(n);
    // the rest of the frames once the visitor scrolls (or the story is on screen, for a page
    // opened further down): until then the opening clip has the line to itself
    const watch: IntersectionObserver[] = [];
    let onScroll = () => {};
    const near = new Promise<void>((ready) => {
      if (!("IntersectionObserver" in window)) return ready();
      onScroll = () => ready();
      window.addEventListener("scroll", onScroll, {
        passive: true,
        once: true,
      });
      const io = new IntersectionObserver(([e]) => {
        if (e.isIntersecting) ready();
      });
      io.observe(el);
      watch.push(io);
    });
    const batch = (from: number, to: number) => async () => {
      for (let i = from; i < to && alive; i += 6)
        await Promise.all(order.slice(i, Math.min(i + 6, to)).map(load));
    };
    (async () => {
      if (!(await load(order[0]))) {
        if (alive) onMissing();
        return;
      }
      await batch(1, coarse)();
      await near;
      await batch(coarse, order.length)();
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
      for (const io of watch) io.disconnect();
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", resize);
    };
  }, [base, progress, onMissing]);
  // how hard it rains: nothing before the rain chapter, in full within a few frames of its start
  const rain = useCallback(() => {
    const x = Math.min(
      1,
      Math.max(0, (progress.current - RAIN_FROM) / (RAIN_FULL - RAIN_FROM)),
    );
    return x * x * (3 - 2 * x);
  }, [progress]);
  return (
    <div className="st-scene">
      <canvas ref={canvas} style={{ width: "100%", height: "100%" }} />
      <RainLayer amount={rain} />
    </div>
  );
}
