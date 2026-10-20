// The dealer embed (ADR-150): our configurator on dealers' own websites. The script
// (/embed/v1/configurator.js and its 3D chunk) is for any page, so it carries CORS and a
// cross-origin resource policy; the entry is cached briefly (its name never changes), the
// chunks for a year (hashed). The API (/api/embed/v1/…) and the hosted pages (the frame, our
// checkout in the dealer's look, the status and confirm pages) pass to the studio with the
// website's key; the page's Origin passes (the studio checks it per dealer), cookies never.
// Only where it is switched on: the preview always, the live site with DEALER_EMBED = "1"
// (after the owner's go). /embed-demo: the preview only.

import type { Env } from "./worker.ts";

export const EMBED = /^\/(embed\/|api\/embed\/)/;
export const DEMO = /^\/embed-demo(\/|\.html|\.js|\.css)?$/;
const SCRIPT = /^\/embed\/v1\/[A-Za-z0-9_.-]+\.js$/;
const ENTRY = "/embed/v1/configurator.js";
const YEAR = 31536000;
const HOP = ["cookie", "host", "x-link-key", "x-site-host", "x-client-ip", "cf-connecting-ip"];

export function embedOn(env: Env): boolean {
  return Boolean(env.PREVIEW) || env.DEALER_EMBED === "1";
}

export async function embed(req: Request, url: URL, env: Env): Promise<Response> {
  if (SCRIPT.test(url.pathname) && ["GET", "HEAD"].includes(req.method)) {
    const res =
      env.PREVIEW && env.ASSETS
        ? await env.ASSETS.fetch(new Request(new URL(url.pathname, url), { method: req.method }))
        : await fetch(new URL(url.pathname, env.STUDIO_URL), {
            method: req.method,
            headers: { "x-link-key": env.LINK_KEY },
          });
    const out = new Response(res.body, res);
    out.headers.delete("set-cookie");
    out.headers.set("access-control-allow-origin", "*");
    out.headers.set("cross-origin-resource-policy", "cross-origin");
    if (res.ok)
      out.headers.set(
        "cache-control",
        url.pathname === ENTRY ? "public, max-age=300" : `public, max-age=${YEAR}, immutable`,
      );
    out.headers.set("x-served-by", "cover-site");
    return out;
  }
  const headers = new Headers();
  for (const [k, v] of req.headers) if (!HOP.includes(k.toLowerCase())) headers.set(k, v);
  headers.set("x-link-key", env.LINK_KEY);
  headers.set("x-client-ip", req.headers.get("cf-connecting-ip") ?? "");
  headers.set("x-forwarded-host", url.host);
  // Caddy replaces X-Forwarded-Host with its own host: the studio reads this one
  headers.set("x-site-host", url.host);
  headers.set("x-forwarded-proto", "https");
  const res = await fetch(new URL(url.pathname + url.search, env.STUDIO_URL), {
    method: req.method,
    headers,
    body: ["GET", "HEAD"].includes(req.method) ? undefined : req.body,
    redirect: "manual",
  });
  const out = new Response(res.body, res);
  out.headers.delete("set-cookie"); // the website never carries the studio's sessions
  out.headers.set("x-served-by", "cover-site");
  out.headers.set("x-robots-tag", "noindex, nofollow");
  if (!out.headers.has("cache-control")) out.headers.set("cache-control", "no-store");
  return out;
}

/** The preview's demo: two made-up dealer sites around the component (this build's files). */
export async function demo(req: Request, url: URL, env: Env): Promise<Response> {
  if (!env.PREVIEW || !env.ASSETS) return new Response("not here", { status: 404 });
  const file = /^\/embed-demo\/?$/.test(url.pathname) ? "/embed-demo.html" : url.pathname;
  const res = await env.ASSETS.fetch(new Request(new URL(file, url), { method: req.method }));
  const out = new Response(res.body, res);
  out.headers.set("x-robots-tag", "noindex, nofollow");
  out.headers.set("cache-control", "no-store");
  return out;
}
