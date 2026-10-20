// The cover website at the edge (ADR-066). Everything comes from the studio (covers.suns.nu)
// with the website's key, so the studio stays the one place for the catalogue, the match, the
// prices, orders, the content and the shop's own build (its scripts always match its pages).
// The build's files (named by their content) are cached at the edge for a year; pages, the demo
// 3D and the film for a while, so a busy day does not reach the studio; quotes, matches and
// orders always do.

import { AGENT, AGENT_B2B, agent, agentOn } from "./agent.ts"; // ADR-139
import { B2B, b2b } from "./b2b.ts"; // .ts: node runs the tests on the sources
import { DEMO, EMBED, demo, embed, embedOn } from "./embed.ts"; // ADR-150

export interface Env {
  ASSETS?: Fetcher; // the preview only: its own fresh build of the shop
  PREVIEW?: string;
  // the API for AI agents and its pages (ADR-139): on the preview always, on the live site only
  // with AGENT_API = "1" (after the owner's go; the studio's shop setting agent_api_enabled too)
  AGENT_API?: string;
  // the dealer embed (ADR-150): on the preview always, on the live site only with
  // DEALER_EMBED = "1" (after the owner's go; the studio's shop setting dealer_embed_enabled too)
  DEALER_EMBED?: string;
  // the commit this Worker was built from (`git describe`, set by `npm run deploy[:preview]`).
  // A secret change makes a new version from the last deployed code, so a stale Worker can look
  // fresh in the dashboard; every answer's x-site-build shows which code really answers.
  BUILD?: string;
  STUDIO_URL: string;
  LINK_KEY: string;
  PAGE_TTL: string;
  MEDIA_TTL: string;
}

import { secure } from "./security.ts"; // .ts: node runs the tests on the sources

const FILES = /^\/(assets|brand)\//; // the shop's build (hashed names: never change)
const YEAR = 31536000;
const API = /^\/(api\/shop\/|media\/)/;
const MODELS =
  /^\/api\/shop\/(demo\.glb|story\/[\w-]+\.(bin|json|glb)|scene\/[0-9a-f]{16}(-\w+)?\.glb)$/;
const FEEDS = new Set(["/robots.txt", "/sitemap.xml", "/llms.txt"]);
const HOP = ["cookie", "host", "x-link-key", "x-site-host", "x-client-ip", "cf-connecting-ip"];

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
  // Caddy replaces X-Forwarded-Host with its own host: the studio reads this one
  headers.set("x-site-host", url.host);
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
  // the media and the 3D files (ADR-106): the demo, the story's model, a quote's scene (named by
  // its hash), kept at the edge like the media
  if (url.pathname.startsWith("/media/") || MODELS.test(url.pathname)) return Number(env.MEDIA_TTL);
  if (API.test(url.pathname)) return 0; // quotes, matches, orders: always fresh
  return Number(env.PAGE_TTL); // the pages and the feeds
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    // ADR-103: every answer with the headers; the dealer frame without X-Frame-Options (its
    // own CSP lists the dealer's sites, ADR-150)
    const framed = new URL(req.url).pathname === "/embed/v1/frame";
    const out = secure(await route(req, env, ctx), framed);
    out.headers.set("x-site-build", env.BUILD || "unknown");
    return out;
  },
} satisfies ExportedHandler<Env>;

async function route(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  {
    const url = new URL(req.url);
    if (url.protocol === "http:") {
      url.protocol = "https:";
      return Response.redirect(url.toString(), 301);
    }
    // the dealer embed (ADR-150): its script, API and hosted pages, where it is switched on;
    // the demo on the preview only
    if (EMBED.test(url.pathname))
      return embedOn(env) ? embed(req, url, env) : new Response("not here", { status: 404 });
    if (DEMO.test(url.pathname)) return demo(req, url, env);
    // the API for AI agents, llms-full.txt, the measuring guide and the cover pages (ADR-139):
    // only where they are switched on (the preview); elsewhere they do not exist
    if (AGENT.test(url.pathname) || AGENT_B2B.test(url.pathname)) {
      if (!agentOn(env)) return new Response("not here", { status: 404 });
      if (AGENT.test(url.pathname)) return agent(req, url, env);
    }
    // the preview's llms.txt with its agent section (the live one is the studio's, unchanged)
    if (url.pathname === "/llms.txt" && env.PREVIEW && env.ASSETS) return agent(req, url, env);
    if (B2B.test(url.pathname)) return b2b(req, url, env); // the B2B shop, its login (ADR-104)
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
          env.ASSETS.fetch(new Request(new URL("/preview/overlay.json", url))).then((r) =>
            r.ok ? (r.json() as Promise<Info>) : { content: {}, settings: {} },
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
        // the build's files are named by their content: the browser keeps them (ADR-106)
        if (url.pathname.startsWith("/assets/") && res.ok)
          out.headers.set("cache-control", `public, max-age=${YEAR}, immutable`);
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
    // Caddy replaces X-Forwarded-Host with its own host: the studio reads this one
    headers.set("x-site-host", url.host);
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
  }
}
