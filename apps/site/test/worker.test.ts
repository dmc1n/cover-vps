// The website's Worker without Cloudflare (ADR-103): `npm test` (node's own test runner, types
// stripped). The studio is a fake `fetch` that records what reached it; the edge cache a Map.
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { SECURITY_HEADERS } from "../src/security.ts";
import worker from "../src/worker.ts";

const reached: string[] = [];
const store = new Map<string, Response>();

beforeEach(() => {
  reached.length = 0;
  store.clear();
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const u = new URL(String(input instanceof Request ? input.url : input));
    reached.push(u.pathname);
    if (u.pathname === "/robots.txt")
      return new Response("User-agent: *\nAllow: /\nDisallow: /api/\n");
    return new Response(`<html>${u.pathname}</html>`, {
      headers: { "content-type": "text/html", "set-cookie": "cover_session=x" },
    });
  }) as typeof fetch;
  (globalThis as unknown as { caches: unknown }).caches = {
    default: {
      match: async (r: Request) => store.get(r.url)?.clone(),
      put: async (r: Request, res: Response) => void store.set(r.url, res),
    },
  };
});

const env = { STUDIO_URL: "https://studio.example", LINK_KEY: "k", PAGE_TTL: "0", MEDIA_TTL: "0" };
const ctx = { waitUntil: () => undefined, passThroughOnException: () => undefined };

async function get(path: string, init?: RequestInit): Promise<Response> {
  const req = new Request(`https://shop.example${path}`, init);
  return worker.fetch(req as never, env as never, ctx as never);
}

test("every answer carries the security headers", async () => {
  for (const path of ["/", "/configure", "/robots.txt", "/api/admin/users"]) {
    const res = await get(path);
    for (const k of Object.keys(SECURITY_HEADERS)) assert.ok(res.headers.get(k), `${path}: ${k}`);
    assert.match(res.headers.get("content-security-policy")!, /script-src 'self'/);
    assert.equal(res.headers.get("set-cookie"), null); // never the studio's session
  }
});

test("the studio's own routes are not reachable through the shop's domain", async () => {
  for (const path of ["/api/admin/shop/settings", "/api/auth/me", "/api/models", "/api/prices"]) {
    const res = await get(path);
    assert.equal(res.status, 404, path);
  }
  assert.deepEqual(reached, []); // none of them even reached the studio
  await get("/index.html");
  await get("/configure");
  assert.deepEqual(reached, ["/shop/index.html", "/shop/configure"]); // pages only as the shop's
  await get("/api/shop/info");
  assert.equal(reached.at(-1), "/api/shop/info");
});

test("www and http go to the one https address", async () => {
  const res = await worker.fetch(
    new Request("https://www.shop.example/configure") as never,
    env as never,
    ctx as never,
  );
  assert.equal(res.status, 301);
  assert.equal(res.headers.get("location"), "https://shop.example/configure");
});

test("the preview is never indexed", async () => {
  const assets = {
    fetch: async () => new Response("<html>preview</html>", { headers: { "content-type": "text/html" } }),
  };
  const penv = { ...env, PREVIEW: "1", ASSETS: assets };
  const robots = await worker.fetch(
    new Request("https://preview.example/robots.txt") as never,
    penv as never,
    ctx as never,
  );
  assert.equal(await robots.text(), "User-agent: *\nDisallow: /\n");
  const page = await worker.fetch(
    new Request("https://preview.example/configure") as never,
    penv as never,
    ctx as never,
  );
  assert.match(page.headers.get("x-robots-tag")!, /noindex/);
  assert.ok(page.headers.get("content-security-policy"));
});
