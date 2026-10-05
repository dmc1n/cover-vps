// The scroll story's pinned scene as rendered frames (ADR-071): 240 photoreal pictures of the
// same story (scripts/film/render_story.py, Blender Cycles), one per step of the scroll, drawn on a
// canvas. Every 8th frame loads first so the whole story scrubs at once, the rest fill in. When
// the first frame cannot be had, `onMissing` lets the page fall back to the live 3D scene.
import { useEffect, useRef } from "react";

export const FRAMES = 240;
const COARSE = 8; // load every 8th frame first
const ZOOM = 0.74; // on a wide screen the frame is drawn this size, right of the captions
const MAX_W = 0.7; // and never wider than this share of the screen
const PHONE = 1.4; // on a phone the frame is this times the screen's width (its middle shown)
const EDGE = 0.05; // the share of the frame's left side that makes the backdrop
const FEATHER = 0.08; // its edges fade over this share of its size

// the frame with its edges faded out (kept per frame: made once)
const softened = new WeakMap<HTMLImageElement, HTMLCanvasElement>();
function soft(img: HTMLImageElement): HTMLCanvasElement {
  const done = softened.get(img);
  if (done) return done;
  const c = document.createElement("canvas");
  c.width = img.width;
  c.height = img.height;
  const g = c.getContext("2d")!;
  g.drawImage(img, 0, 0);
  g.globalCompositeOperation = "destination-in";
  const fx = img.width * FEATHER;
  const fy = img.height * FEATHER;
  const across = g.createLinearGradient(0, 0, img.width, 0);
  across.addColorStop(0, "rgba(0,0,0,0)");
  across.addColorStop(fx / img.width, "rgba(0,0,0,1)");
  across.addColorStop(1 - fx / img.width, "rgba(0,0,0,1)");
  across.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = across;
  g.fillRect(0, 0, img.width, img.height);
  const down = g.createLinearGradient(0, 0, 0, img.height);
  down.addColorStop(0, "rgba(0,0,0,0)");
  down.addColorStop(fy / img.height, "rgba(0,0,0,1)");
  down.addColorStop(1 - fy / img.height, "rgba(0,0,0,1)");
  down.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = down;
  g.fillRect(0, 0, img.width, img.height);
  softened.set(img, c);
  return c;
}

const name = (base: string, n: number) =>
  `${base}${String(n).padStart(3, "0")}.webp`;

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
        const wide = W > 900 * (window.devicePixelRatio || 1);
        const cover = Math.max(W / img.width, H / img.height);
        // behind: the frame's own left edge (studio wall and floor, no cover) stretched over the
        // whole canvas and blurred, so the backdrop runs on without a halo of the cover
        ctx.filter = "blur(30px)";
        ctx.drawImage(
          img,
          0,
          0,
          img.width * EDGE,
          img.height,
          -40,
          -40,
          W + 80,
          H + 80,
        );
        ctx.filter = "none";
        // in front: the frame itself with soft edges; on a wide screen a little smaller and to
        // the right, so the captions on the left sit on the backdrop, not on the cover; on a
        // phone a picture across the upper part, the captions below it
        const s = wide
          ? Math.min(cover * ZOOM, (W * MAX_W) / img.width)
          : (W / img.width) * PHONE;
        const w = img.width * s;
        const h = img.height * s;
        const x = wide ? W - w - 0.02 * W : (W - w) / 2;
        const y = wide ? (H - h) / 2 : H * 0.1;
        ctx.drawImage(soft(img), x, y, w, h);
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
