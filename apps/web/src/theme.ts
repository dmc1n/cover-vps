// Light or dark for the whole studio (ADR-124): the computer's setting (prefers-color-scheme) by
// default; a person may choose Light or Dark in the header's menu, remembered in this browser.
// The stylesheet reads html[data-theme]; "auto" leaves the attribute off.
import { useEffect, useState } from "react";

export type Theme = "auto" | "light" | "dark";
const KEY = "studio.theme";
const EVENT = "studio-theme";

export function storedTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "auto";
  } catch {
    return "auto"; // a private window: the computer's setting
  }
}

export function applyTheme(t: Theme): void {
  const root = document.documentElement;
  if (t === "auto") delete root.dataset.theme;
  else root.dataset.theme = t;
}

export function setTheme(t: Theme): void {
  try {
    if (t === "auto") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, t);
  } catch {
    /* a private window: for this page only */
  }
  applyTheme(t);
  window.dispatchEvent(new Event(EVENT));
}

/** The theme in use: what was chosen, or the computer's when nothing was. */
export function effectiveTheme(t: Theme = storedTheme()): "light" | "dark" {
  if (t !== "auto") return t;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function useTheme(): Theme {
  const [t, setT] = useState<Theme>(storedTheme);
  useEffect(() => {
    const on = () => setT(storedTheme());
    window.addEventListener(EVENT, on);
    window.addEventListener("storage", on); // another tab chose
    return () => {
      window.removeEventListener(EVENT, on);
      window.removeEventListener("storage", on);
    };
  }, []);
  return t;
}

export const NEXT: Record<Theme, Theme> = {
  auto: "light",
  light: "dark",
  dark: "auto",
};
export const LABEL: Record<Theme, string> = {
  auto: "Theme: as the computer",
  light: "Theme: light",
  dark: "Theme: dark",
};
