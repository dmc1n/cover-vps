// The scroll story's pinned scene as rendered frames (ADR-071): 360 photoreal pictures of the
// same story (scripts/film/render_reel.py, Blender Cycles), one per step of the scroll, drawn on a
// canvas. Every 8th frame loads first so the whole story scrubs at once, the rest fill in. When
// the first frame cannot be had, `onMissing` lets the page fall back to the live 3D scene.
//
// ADR-106: the rest of the frames load only once the story comes near the screen, so they do
// not share the line with the first screen.
//
// ADR-121: the pictures carry no falling rain (only the wet look, which may follow the scroll);
// every falling drop is RainLayer's, drawn by the clock, so it falls the same whether the visitor
// stands still or scrolls either way. An upright screen shows the 960 × 900 cut round the cover
// across its width, above the caption, on a soft blur of the picture (filled, it showed only a
// hand's breadth of the cover); it loads the set's upright cuts (`<set>u-001.webp`) when there
// are any.
// Visitors who asked for less motion get one still per chapter (its last picture, all its work
// done) and no falling rain.
import { useCallback, useEffect, useRef } from "react";
import { RainLayer } from "./RainLayer";

export const FRAMES = 360;
export const CHAPTERS = 6;
const COARSE = 8; // load every 8th frame first
const name = (base: string, n: number) =>
  `${base}${String(n).padStart(3, "0")}.webp`;
const FOCUS = 0.6; // where the cover sits across the picture (the render frames it right of centre)
// where the rain begins and is in full: just into the last chapter (pictures 302 to 314 of 360)
const RAIN_FROM = 0.84;
const RAIN_FULL = 0.872;
/** the still per chapter for less motion: the chapter's last picture */
export const keyFrame = (chapter: number) =>
  Math.round(((chapter + 1) * FRAMES) / CHAPTERS) - 1;
/** the upright screen's pictures beside a set: /media/story6- → /media/story6u- */
export const smallSet = (base: string) => base.replace(/-$/, "u-");
// an upright screen (a phone, a tablet held upright) shows the cut round the cover, 960 of the
// 1600 pixels, across its width: it loads just that cut, at full sharpness
const UPRIGHT_CUT = 960;
const upright = () => window.innerHeight > window.innerWidth * 1.2;

export function StoryFrames({
  base,
  progress,
  onMissing,
  calm = false,
}: {
  base: string;
  progress: React.MutableRefObject<number>;
  onMissing: () => void;
  /** less motion asked: one still per chapter */
  calm?: boolean;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;
    let alive = true;
    const images: (HTMLImageElement | null)[] = Array(FRAMES + 1).fill(null);
    let shown = -1;
    let set = base;

    const load = (n: number, from = set) =>
      new Promise<boolean>((done) => {
        const img = new Image();
        img.decoding = "async";
        img.onload = () => {
          images[n] = img;
          shown = -1; // a better frame may now be drawn
          done(true);
        };
        img.onerror = () => done(false);
        img.src = name(from, n);
      });

    // the order: frame 1, every 8th, then the rest, a few at a time; for less motion only the
    // chapters' stills
    const keys = Array.from({ length: CHAPTERS }, (_, c) => keyFrame(c));
    const order: number[] = [];
    if (calm) order.push(...keys);
    else for (let n = 1; n <= FRAMES; n += COARSE) order.push(n);
    const coarse = order.length;
    if (!calm)
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
        await Promise.all(
          order.slice(i, Math.min(i + 6, to)).map((n) => load(n)),
        );
    };
    (async () => {
      // a phone takes the small pictures when the set has them
      if (upright() && (await load(order[0], smallSet(base))))
        set = smallSet(base);
      else if (!(await load(order[0]))) {
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
      const p = Math.min(1, Math.max(0, progress.current));
      const want = calm
        ? keys[Math.min(CHAPTERS - 1, Math.floor(p * CHAPTERS))]
        : 1 + Math.round(p * (FRAMES - 1));
      const n = nearest(want);
      if (n && n !== shown) {
        const img = images[n]!;
        const W = el.width;
        const H = el.height;
        // fill the canvas; when the screen is narrower than the picture, keep the cover in view
        const k = Math.max(W / img.width, H / img.height);
        const w = img.width * k;
        const h = img.height * k;
        // (a picture of the upright set is already cut round the cover)
        const focus = img.width < 1200 ? 0.5 : FOCUS;
        const x = Math.min(0, Math.max(W - w, W / 2 - focus * w));
        if (H > W * 1.2) {
          // an upright screen: filled, the picture would show a hand's breadth of the cover;
          // instead its cut round the cover across the full width, in the upper half above
          // the caption, on a soft blur of itself
          const f = W / Math.min(img.width, UPRIGHT_CUT);
          ctx.filter = "blur(28px) brightness(0.92)";
          ctx.drawImage(img, x, (H - h) / 2, w, h);
          ctx.filter = "none";
          const top = Math.round(H * 0.07);
          const left = Math.min(
            Math.max(focus * img.width - W / f / 2, 0),
            img.width - W / f,
          );
          ctx.drawImage(
            img,
            left,
            0,
            W / f,
            img.height,
            0,
            top,
            W,
            img.height * f,
          );
        } else ctx.drawImage(img, x, (H - h) / 2, w, h);
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
  }, [base, progress, onMissing, calm]);
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
