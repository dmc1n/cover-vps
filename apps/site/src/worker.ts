// The cover website at the edge (ADR-066). Everything comes from the studio (covers.suns.nu)
// with the website's key, so the studio stays the one place for the catalogue, the match, the
// prices, orders, the content and the shop's own build (its scripts always match its pages).
// The build's files (named by their content) are cached at the edge for a year; pages, the demo
// 3D and the film for a while, so a busy day does not reach the studio; quotes, matches and
// orders always do.

import { B2B, b2b } from "./b2b";

export interface Env {
  ASSETS?: Fetcher; // the preview only: its own fresh build of the shop
  PREVIEW?: string;
  STUDIO_URL: string;
  LINK_KEY: string;
  PAGE_TTL: string;
  MEDIA_TTL: string;
}

const FILES = /^\/(assets|brand)\//; // the shop's build (hashed names: never change)
const YEAR = 31536000;
const API = /^\/(api\/shop\/|media\/)/;
const FEEDS = new Set(["/robots.txt", "/sitemap.xml", "/llms.txt"]);
const HOP = ["cookie", "host", "x-link-key", "x-client-ip", "cf-connecting-ip"];

interface Info {
  content: Record<string, unknown>;
  settings: Record<string, unknown>;
}

// one request to the studio with the website's key and the visitor's address
function studio(req: Request, url: URL, env: Env, path: string): Promise<Response> {
  const headers = new Headers();
  for (const [k, v] of req.headers) if (!HOP.includes(k.toLowerCase())) headers.set(k, v);
  headers.set("x-link-key", env.LINK_KEY);
  headers.set("x-client-ip", req.headers.get("cf-connecting-ip") ?? "");
  headers.set("x-forwarded-host", url.host);
  headers.set("x-forwarded-proto", "https");
  return fetch(new URL(path + url.search, env.STUDIO_URL), {
    method: req.method,
    headers,
    body: ["GET", "HEAD"].includes(req.method) ? undefined : req.body,
    redirect: "manual",
  });
}

function cacheFor(url: URL, method: string, env: Env): number {
  if (method !== "GET" || url.searchParams.has("preview")) return 0;
  if (FILES.test(url.pathname)) return YEAR;
  if (url.pathname.startsWith("/media/") || url.pathname === "/api/shop/demo.glb")
    return Number(env.MEDIA_TTL);
  if (API.test(url.pathname)) return 0; // quotes, matches, orders: always fresh
  return Number(env.PAGE_TTL); // the pages and the feeds
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);
    if (url.protocol === "http:") {
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }
    if (B2B.test(url.pathname)) return b2b(req, url, env); // the B2B shop, its login (ADR-101)
    // the preview (preview.<domain>): this build's own pages and files, the studio's data,
    // never indexed; the live site changes only with a studio release
    if (env.PREVIEW && env.ASSETS) {
      if (url.pathname === "/robots.txt") return new Response("User-agent: *\nDisallow: /\n");
      // a bridge until the studio's next release: the story's data and texts from this build
      if (url.pathname.startsWith("/api/shop/story/")) {
        const own = await env.ASSETS.fetch(
          new Request(new URL(url.pathname.replace("/api/shop/story/", "/preview/story/"), url)),
        );
        if (own.ok) return own;
      }
      if (url.pathname === "/api/shop/info") {
        const [live, extra] = await Promise.all([
          studio(req, url, env, "/api/shop/info").then((r) => r.json() as Promise<Info>),
          env.ASSETS.fetch(new Request(new URL("/preview/overlay.json", url))).then(
            (r) => (r.ok ? (r.json() as Promise<Info>) : { content: {}, settings: {} }),
          ),
        ]);
        live.content = { ...extra.content, ...live.content };
        live.settings = { ...live.settings, ...extra.settings };
        return Response.json(live, { headers: { "x-robots-tag": "noindex" } });
      }
      if (!API.test(url.pathname)) {
        const asset = FILES.test(url.pathname) ? url.pathname : "/shop.html";
        const res = await env.ASSETS.fetch(new Request(new URL(asset, url), req));
        const out = new Response(res.body, res);
        out.headers.set("x-robots-tag", "noindex, nofollow");
        return out;
      }
    }
    if (url.hostname.startsWith("www.")) {
      url.hostname = url.hostname.slice(4); // one address for search engines: without www
      return Response.redirect(url.toString(), 301);
    }
    if (url.pathname.startsWith("/api/") && !API.test(url.pathname))
      return new Response("not here", { status: 404 });
    // the studio's address for this: the API and feeds as they are, a page under /shop/
    const path =
      API.test(url.pathname) || FEEDS.has(url.pathname) || FILES.test(url.pathname)
        ? url.pathname
        : `/shop${url.pathname}`;
    const target = new URL(path + url.search, env.STUDIO_URL);
    const ttl = cacheFor(url, req.method, env);
    const cache = caches.default;
    const key = new Request(url.toString(), { method: "GET" });
    if (ttl) {
      const hit = await cache.match(key);
      if (hit) return hit;
    }
    const headers = new Headers();
    for (const [k, v] of req.headers) if (!HOP.includes(k.toLowerCase())) headers.set(k, v);
    headers.set("x-link-key", env.LINK_KEY);
    headers.set("x-client-ip", req.headers.get("cf-connecting-ip") ?? "");
    headers.set("x-forwarded-host", url.host);
    headers.set("x-forwarded-proto", "https");
    const res = await fetch(target, {
      method: req.method,
      headers,
      body: ["GET", "HEAD"].includes(req.method) ? undefined : req.body,
      redirect: "manual",
    });
    const out = new Response(res.body, res);
    out.headers.delete("set-cookie"); // the website never carries the studio's sessions
    out.headers.set("x-served-by", "cover-site");
    if (ttl && res.status === 200 && !req.headers.has("range")) {
      out.headers.set("cache-control", `public, max-age=${ttl}`);
      ctx.waitUntil(cache.put(key, out.clone()));
    }
    return out;
  },
} satisfies ExportedHandler<Env>;
