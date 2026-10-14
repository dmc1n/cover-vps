// The API for AI agents and its pages on the website (ADR-135): /api/v2/* (JSON, its OpenAPI and
// docs), /llms-full.txt, the measuring guide (/measure, /measure/<kind>) and the existing covers
// (/covers, /covers/<code>). They pass to the studio with the website's key, like the shop, but
// only where they are switched on: the preview (preview.<domain>) always, the live site only with
// AGENT_API = "1" in wrangler.toml (after the owner's go). Never cached at the edge (prices and
// limits are per caller); no cookies either way (the API answers without them, CORS open).

import type { Env } from "./worker.ts";

export const AGENT = /^\/(api\/v2(\/|$)|llms-full\.txt$|measure(\/|$)|covers(\/|$))/;
export const AGENT_B2B = /^\/api\/b2b\/v2(\/|$)/; // a B2B session's own prices (b2b.ts passes it)
const PAGES = /^\/(measure|covers)(\/|$)/; // pages: the studio serves them under /shop/
const HOP = ["cookie", "host", "x-link-key", "x-client-ip", "cf-connecting-ip"];

export function agentOn(env: Env): boolean {
  return Boolean(env.PREVIEW) || env.AGENT_API === "1";
}

export async function agent(req: Request, url: URL, env: Env): Promise<Response> {
  const headers = new Headers();
  for (const [k, v] of req.headers) if (!HOP.includes(k.toLowerCase())) headers.set(k, v);
  headers.set("x-link-key", env.LINK_KEY);
  headers.set("x-client-ip", req.headers.get("cf-connecting-ip") ?? "");
  headers.set("x-forwarded-host", url.host);
  headers.set("x-forwarded-proto", "https");
  const path = PAGES.test(url.pathname) ? `/shop${url.pathname}` : url.pathname;
  const res = await fetch(new URL(path + url.search, env.STUDIO_URL), {
    method: req.method,
    headers,
    body: ["GET", "HEAD"].includes(req.method) ? undefined : req.body,
    redirect: "manual",
  });
  const out = new Response(res.body, res);
  out.headers.delete("set-cookie"); // the website never carries the studio's sessions
  out.headers.set("x-served-by", "cover-site");
  if (env.PREVIEW) out.headers.set("x-robots-tag", "noindex, nofollow");
  return out;
}
