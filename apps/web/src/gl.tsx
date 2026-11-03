// The studio's 3D views on a tablet (ADR-154): fewer pixels and a way back when the device
// takes the graphics memory away. No three.js here, so a page without 3D never loads it.

/** A finger instead of a mouse: an iPad, a phone, a touch screen without a mouse. */
export const coarse = (): boolean =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(pointer: coarse)").matches;

/** Pixels drawn per CSS pixel: at most 2 with a mouse, 1.5 on a touch screen. An iPad's
 * 2x screen at 2 draws four times the pixels of 1x and runs out of graphics memory with a
 * few views open; at 1.5 a cover still looks sharp at arm's length. */
export const pixelRatio = (): number =>
  Math.min(window.devicePixelRatio || 1, coarse() ? 1.5 : 2);

/** Calls `lost` when the browser takes the canvas's WebGL context away (iPad Safari does so
 * when memory runs short or the tab sleeps) and `restored` when it gives it back. Returns
 * the function that stops listening. */
export function watchContext(
  canvas: HTMLCanvasElement,
  lost: () => void,
  restored: () => void,
): () => void {
  const onLost = (e: Event) => {
    e.preventDefault(); // without this the browser never gives the context back
    lost();
  };
  canvas.addEventListener("webglcontextlost", onLost);
  canvas.addEventListener("webglcontextrestored", restored);
  return () => {
    canvas.removeEventListener("webglcontextlost", onLost);
    canvas.removeEventListener("webglcontextrestored", restored);
  };
}

/** What a 3D view shows instead of an empty box once its context is gone. */
export function GlLost({ onReload }: { onReload: () => void }) {
  return (
    <div className="gl-lost" role="alert" data-testid="gl-lost">
      <p>The 3D view stopped: the device needed its graphics memory back.</p>
      <button type="button" className="btn" onClick={onReload}>
        Reload 3D
      </button>
    </div>
  );
}
