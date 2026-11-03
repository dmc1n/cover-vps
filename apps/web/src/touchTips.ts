// Explanations for a finger (ADR-154). The studio explains its controls in `title=` (about 170
// of them; icon buttons depend on them), which a mouse shows on hover and a finger never does.
// One listener for the whole page: hold a control for half a second and its title shows in the
// same card as the (i) (`.info-pop`); lift the finger and the card stays until the next touch,
// a scroll or Escape. The tap that a long hold would have ended in is swallowed, so holding
// "Reject" to read what it does never rejects. A short tap, a swipe and a scroll are untouched:
// the touch listeners are passive, and only the end of a hold that showed a card cancels its
// click. A mouse never sees any of this (no touch events), so the desktop keeps its hover.

export const HOLD_MS = 500;
const SLOP_PX = 10; // a finger that moves further is scrolling, not holding
const GAP_PX = 8;

/** The element whose title a touch at `target` should show, or null. */
export function titled(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof Element)) return null;
  // typing: a hold in a field places the caret or selects, it must stay the browser's
  if (target.closest("input, textarea, select, [contenteditable]")) return null;
  const el = target.closest<HTMLElement>("[title]");
  if (!el || !el.title.trim()) return null;
  if (el === document.body || el === document.documentElement) return null;
  // a title on a 3D view or a drawing would fire on every orbit or pan: not there
  if (el.matches("canvas, svg") || el.querySelector("canvas")) return null;
  return el;
}

export function installTouchTips(): () => void {
  let timer: number | undefined;
  let start: { x: number; y: number } | null = null;
  let pending: HTMLElement | null = null;
  let tip: HTMLDivElement | null = null;
  let shownThisTouch = false;
  let swallowUntil = 0;
  let held: HTMLElement | null = null; // the control whose card a hold showed
  let touching = false; // a finger is down

  const hide = () => {
    if (!tip) return;
    try {
      (tip as HTMLElement & { hidePopover?: () => void }).hidePopover?.();
    } catch {
      /* not open in the top layer */
    }
    tip.remove();
    tip = null;
  };
  const cancel = () => {
    window.clearTimeout(timer);
    timer = undefined;
    pending = null;
  };

  const show = (el: HTMLElement) => {
    hide();
    const t = document.createElement("div");
    t.className = "info-pop touch-tip";
    t.setAttribute("role", "tooltip");
    t.dataset.testid = "touch-tip";
    t.textContent = el.title.trim();
    document.body.appendChild(t);
    // in the top layer where the browser has one, so an open dialog does not cover it
    if (typeof t.showPopover === "function") {
      t.setAttribute("popover", "manual");
      try {
        t.showPopover();
      } catch {
        /* an older engine: the fixed position and z-index do */
      }
    }
    const b = el.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const vh = window.innerHeight;
    const w = t.offsetWidth;
    const h = t.offsetHeight;
    const left = Math.max(12, Math.min(b.left + b.width / 2 - w / 2, vw - w - 12));
    // above the finger's control (the finger covers what is below it), else below
    const above = b.top - h - GAP_PX;
    const top = above >= 8 ? above : Math.min(b.bottom + GAP_PX, vh - h - 8);
    t.style.left = `${left}px`;
    t.style.top = `${Math.max(8, top)}px`;
    tip = t;
    shownThisTouch = true;
    held = el;
    navigator.vibrate?.(10);
  };

  const onStart = (e: TouchEvent) => {
    shownThisTouch = false;
    swallowUntil = 0; // a new touch: whatever it taps is meant
    held = null;
    touching = true;
    if (tip &&!(e.target instanceof Node && tip.contains(e.target))) hide();
    cancel();
    if (e.touches.length !== 1) return; // a pinch or a two-finger pan
    const el = titled(e.target);
    if (!el) return;
    const p = e.touches[0];
    start = { x: p.clientX, y: p.clientY };
    pending = el;
    timer = window.setTimeout(() => {
      timer = undefined;
      if (pending && pending.isConnected) show(pending);
      pending = null;
    }, HOLD_MS);
  };
  const onMove = (e: TouchEvent) => {
    if (!pending || !start) return;
    const p = e.touches[0];
    if (!p || Math.hypot(p.clientX - start.x, p.clientY - start.y) > SLOP_PX)
      cancel();
  };
  const onEnd = (e: TouchEvent) => {
    cancel();
    touching = false;
    if (!shownThisTouch) return;
    shownThisTouch = false; // the gesture is over: nothing of it may linger
    // the hold showed a card: this finger's lift is not a tap on the control
    if (e.cancelable) e.preventDefault();
    swallowUntil = Date.now() + 700;
  };
  const onCancel = () => {
    cancel();
    touching = false;
    shownThisTouch = false;
  };
  const onClick = (e: MouseEvent) => {
    // only the held control's own click, only right after the hold: never the next tap
    if (Date.now() > swallowUntil) return;
    if (!held || !(e.target instanceof Node) || !held.contains(e.target)) return;
    swallowUntil = 0;
    held = null;
    e.preventDefault();
    e.stopPropagation();
  };
  // Chrome on Android (and its touch emulation) opens the context menu on a long press
  // only while that finger is down, only on the held control: a later right-click is the user's
  const onMenu = (e: Event) => {
    const on = pending ?? (shownThisTouch ? held : null);
    if (touching && on && e.target instanceof Node && on.contains(e.target))
      e.preventDefault();
  };
  const onScroll = () => {
    cancel();
    hide();
  };
  const onKey = (e: KeyboardEvent) => {
    if (e.key === "Escape") hide();
  };

  const passive = { capture: true, passive: true } as const;
  document.addEventListener("touchstart", onStart, passive);
  document.addEventListener("touchmove", onMove, passive);
  document.addEventListener("touchend", onEnd, { capture: true, passive: false });
  document.addEventListener("touchcancel", onCancel, passive);
  document.addEventListener("click", onClick, true);
  document.addEventListener("contextmenu", onMenu, true);
  window.addEventListener("scroll", onScroll, passive);
  window.addEventListener("hashchange", onScroll);
  document.addEventListener("keydown", onKey);
  return () => {
    cancel();
    hide();
    document.removeEventListener("touchstart", onStart, passive);
    document.removeEventListener("touchmove", onMove, passive);
    document.removeEventListener("touchend", onEnd, { capture: true });
    document.removeEventListener("touchcancel", onCancel, passive);
    document.removeEventListener("click", onClick, true);
    document.removeEventListener("contextmenu", onMenu, true);
    window.removeEventListener("scroll", onScroll, passive);
    window.removeEventListener("hashchange", onScroll);
    document.removeEventListener("keydown", onKey);
  };
}
