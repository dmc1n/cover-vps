// The cover website at the edge (ADR-066). The shop's own files (scripts, styles, pictures) are
// served here; every page and every question about covers goes to the studio (covers.suns.nu)
// with the website's key, so the studio stays the one place for the catalogue, the match, the
// prices, orders and the content. Pages, the demo 3D and the film are cached at the edge, so a
// busy day does not reach the studio; quotes, matches and orders always do.

export interface Env {
  ASSETS: Fetcher;
  STUDIO_URL: string;
  LINK_KEY: string;
  PAGE_TTL: string;
  MEDIA_TTL: string;
}

const FILES = /^\/(assets|brand)\//; // the build's own files (never the studio's app)
const API = /^\/(api\/shop\/|media\/)/;
const FEEDS = new Set(["/robots.txt", "/sitemap.xml", "/llms.txt"]);
const HOP = ["cookie", "host", "x-link-key", "x-client-ip", "cf-connecting-ip"];

function cacheFor(url: URL, method: string, env: Env): number {
  if (method !== "GET" || url.searchParams.has("preview")) return 0;
  if (url.pathname.startsWith("/media/") || url.pathname === "/api/shop/demo.glb")
    return Number(env.MEDIA_TTL);
  if (API.test(url.pathname)) return 0; // quotes, matches, orders: always fresh
  return Number(env.PAGE_TTL); // the pages and the feeds
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);
    if (FILES.test(url.pathname)) return env.ASSETS.fetch(req);
    if (url.pathname.startsWith("/api/") && !API.test(url.pathname))
      return new Response("not here", { status: 404 });
    // the studio's address for this: the API and feeds as they are, a page under /shop/
    const path =
      API.test(url.pathname) || FEEDS.has(url.pathname)
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
