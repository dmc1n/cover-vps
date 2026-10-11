// Unsaved edits (ADR-122): a form with changes registers itself; leaving the page by a link in
// the studio asks first, and closing or reloading the browser tab warns.
import { useEffect } from "react";

// key → the addresses that keep the form (its own sub-tabs), "" for none
const dirty = new Map<string, string>();

export const anyUnsaved = () => dirty.size > 0;

/** Mark a form as holding unsaved edits while `isDirty` is true; links that start with `keeps`
 * (its own sub-tabs, where the form stays) do not ask. */
export function useUnsaved(key: string, isDirty: boolean, keeps = ""): void {
  useEffect(() => {
    if (isDirty) dirty.set(key, keeps);
    else dirty.delete(key);
    return () => {
      dirty.delete(key);
    };
  }, [key, isDirty, keeps]);
}

/** May the studio go to `href` now? Asks when unsaved edits would be lost (and forgets them
 * when the person says yes). */
export function mayLeave(href: string): boolean {
  if (!anyUnsaved()) return true;
  const keeps = (k: string) =>
    !!k &&
    (k.endsWith("/")
      ? href.startsWith(k)
      : href === k || href.startsWith(`${k}/`));
  if ([...dirty.values()].every(keeps)) return true;
  if (!window.confirm("You have changes that are not saved. Leave this page?"))
    return false;
  dirty.clear();
  return true;
}

/** Install the guards once (App). */
export function installUnsavedGuard(): () => void {
  const unload = (e: BeforeUnloadEvent) => {
    if (!anyUnsaved()) return;
    e.preventDefault();
    e.returnValue = "";
  };
  const click = (e: MouseEvent) => {
    if (!anyUnsaved() || e.defaultPrevented) return;
    const a = (e.target as Element | null)?.closest?.("a[href^='#']");
    const href = a?.getAttribute("href") ?? "";
    if (!a || href === window.location.hash) return;
    if (!mayLeave(href)) {
      e.preventDefault();
      e.stopPropagation();
    }
  };
  window.addEventListener("beforeunload", unload);
  document.addEventListener("click", click, true);
  return () => {
    window.removeEventListener("beforeunload", unload);
    document.removeEventListener("click", click, true);
  };
}
