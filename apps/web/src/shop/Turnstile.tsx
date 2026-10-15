import { useEffect, useRef } from "react";

type TurnstileApi = {
  render: (element: HTMLElement, options: Record<string, unknown>) => string;
  remove: (id: string) => void;
};
declare global {
  interface Window {
    turnstile?: TurnstileApi;
  }
}
let loading: Promise<TurnstileApi> | undefined;
function load() {
  return (loading ??= new Promise<TurnstileApi>((resolve, reject) => {
    if (window.turnstile) return resolve(window.turnstile);
    const script = document.createElement("script");
    script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
    script.async = true;
    script.onload = () =>
      window.turnstile
        ? resolve(window.turnstile)
        : reject(new Error("Turnstile unavailable"));
    script.onerror = () => reject(new Error("Turnstile unavailable"));
    document.head.appendChild(script);
  }));
}

export function Turnstile({ siteKey, onToken, refresh = "" }: {
  siteKey?: string;
  onToken: (token: string) => void;
  refresh?: string | number;
}) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    onToken("");
    if (!siteKey) return;
    let cancelled = false;
    let widget: string | undefined;
    let api: TurnstileApi | undefined;
    void load().then((loaded) => {
      if (cancelled || !container.current) return;
      api = loaded;
      widget = api.render(container.current, {
        sitekey: siteKey,
        appearance: "interaction-only",
        callback: onToken,
        "expired-callback": () => onToken(""),
        "error-callback": () => onToken(""),
      });
    }).catch(() => { if (!cancelled) onToken(""); });
    return () => {
      cancelled = true;
      if (widget !== undefined) api?.remove(widget);
    };
  }, [siteKey, onToken, refresh]);
  return siteKey ? <div ref={container} /> : null;
}
