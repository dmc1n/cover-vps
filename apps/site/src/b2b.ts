// The B2B shop on the website (ADR-104): /b2b (the page) and /api/b2b/ (its API) pass to the
// studio like the rest of the site, with the website's key, but they carry the B2B login: the
// B2B session cookie (b2b_*) goes through in both directions, and nothing else does (the studio's
// own cookies never pass). Nothing here is cached at the edge or indexed.

import type { Env } from "./worker.ts";

export const B2B = /^\/(b2b(\/|$)|api\/b2b\/)/;
const OURS = /^b2b_[a-z_]+=/i;
const HOP = ["cookie", "host", "x-link-key", "x-client-ip", "cf-connecting-ip"];

// only the B2B shop's own cookies, from the browser to the studio
function b2bCookies(req: Request): string {
  return (req.headers.get("cookie") ?? "")
    .split(/;\s*/)
    .filter((c) => OURS.test(c))
    .join("; ");
}

export async function b2b(req: Request, url: URL, env: Env): Promise<Response> {
  const api = url.pathname.startsWith("/api/");
  // the preview (preview.<domain>): this build's own page, the studio's API
  if (!api && env.PREVIEW && env.ASSETS) {
    const res = await env.ASSETS.fetch(new Request(new URL("/b2b.html", url), req));
    const out = new Response(res.body, res);
    out.headers.set("x-robots-tag", "noindex, nofollow");
    out.headers.set("cache-control", "no-store");
    return out;
  }
  const headers = new Headers();
  for (const [k, v] of req.headers) if (!HOP.includes(k.toLowerCase())) headers.set(k, v);
  const cookies = b2bCookies(req);
  if (api && cookies) headers.set("cookie", cookies);
  headers.set("x-link-key", env.LINK_KEY);
  headers.set("x-client-ip", req.headers.get("cf-connecting-ip") ?? "");
  headers.set("x-forwarded-host", url.host);
  headers.set("x-forwarded-proto", "https");
  const path = api ? url.pathname : `/shop${url.pathname}`;
  const res = await fetch(new URL(path + url.search, env.STUDIO_URL), {
    method: req.method,
    headers,
    body: ["GET", "HEAD"].includes(req.method) ? undefined : req.body,
    redirect: "manual",
  });
  const out = new Response(res.body, res);
  const set = res.headers.getSetCookie();
  out.headers.delete("set-cookie");
  for (const c of set) if (api && OURS.test(c)) out.headers.append("set-cookie", c);
  out.headers.set("x-served-by", "cover-site");
  out.headers.set("x-robots-tag", "noindex, nofollow");
  out.headers.set("cache-control", "no-store");
  return out;
}
