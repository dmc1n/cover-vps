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
    assert.match(res.headers.get("content-security-policy")!, /frame-src https:\/\/challenges\.cloudflare\.com/);
    assert.match(res.headers.get("content-security-policy")!, /script-src 'self' https:\/\/challenges\.cloudflare\.com/);
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

const agentPaths = [
  "/api/v2/match", "/api/v2/openapi.json", "/llms-full.txt", "/measure",
  "/measure/sofa", "/covers/x", "/api/b2b/v2/match",
];

test("agent routes on live are closed by default while llms.txt still reaches studio", async () => {
  for (const path of agentPaths) {
    assert.equal((await get(path)).status, 404, path);
  }
  assert.deepEqual(reached, []);
  await get("/llms.txt");
  assert.deepEqual(reached, ["/llms.txt"]);
});

test("enabled live agent requests preserve JSON and strip cookies in both directions", async () => {
  const seen: { path: string; headers: Headers; method: string; body: string }[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = new Request(input, { ...init, duplex: "half" } as RequestInit);
    reached.push(new URL(req.url).pathname);
    seen.push({ path: new URL(req.url).pathname, headers: req.headers,
      method: req.method, body: await req.text() });
    return new Response("{}", { headers: { "set-cookie": "cover_session=secret" } });
  }) as typeof fetch;
  const body = JSON.stringify({ kind: "sofa", width: 230, depth: 90, height: 85 });
  for (const [path, target] of [
    ["/api/v2/match", "/api/v2/match"],
    ["/measure/sofa", "/shop/measure/sofa"],
    ["/llms-full.txt", "/llms-full.txt"],
  ]) {
    const res = await worker.fetch(new Request(`https://shop.example${path}`, {
      method: path.endsWith("match") ? "POST" : "GET",
      headers: { cookie: "cover_session=private", "x-link-key": "forged",
        "content-type": "application/json" },
      body: path.endsWith("match") ? body : undefined,
    }) as never, { ...env, AGENT_API: "1" } as never, ctx as never);
    assert.equal(res.status, 200);
    assert.equal(reached.at(-1), target);
    assert.equal(res.headers.get("set-cookie"), null);
    for (const k of Object.keys(SECURITY_HEADERS)) assert.ok(res.headers.get(k), k);
    assert.equal(seen.at(-1)!.headers.get("cookie"), null);
    assert.equal(seen.at(-1)!.headers.get("x-link-key"), env.LINK_KEY);
  }
  assert.equal(seen[0].method, "POST");
  assert.equal(seen[0].body, body);
  assert.equal(seen[0].headers.get("content-type"), "application/json");
});

test("preview agent routes and llms.txt always reach studio instead of assets", async () => {
  let assetCalls = 0;
  const penv = { ...env, PREVIEW: "1", ASSETS: {
    fetch: async () => { assetCalls++; return new Response("shop.html asset"); },
  } };
  for (const path of [...agentPaths, "/llms.txt"]) {
    const res = await worker.fetch(new Request(`https://preview.example${path}`) as never,
      penv as never, ctx as never);
    assert.equal(res.status, 200, path);
    assert.equal(reached.at(-1), /^\/(measure|covers)(\/|$)/.test(path) ? `/shop${path}` : path);
    assert.match(res.headers.get("x-robots-tag")!, /noindex/, path);
    assert.equal(res.headers.get("set-cookie"), null);
    for (const k of Object.keys(SECURITY_HEADERS)) assert.ok(res.headers.get(k), `${path}: ${k}`);
  }
  assert.equal(assetCalls, 0);
});

test("the studio is told the website's host in x-site-host (Caddy rewrites X-Forwarded-Host)", async () => {
  const seen: Headers[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    seen.push(new Request(input, init).headers);
    return new Response("{}");
  }) as typeof fetch;
  const penv = { ...env, PREVIEW: "1", ASSETS: { fetch: async () => new Response("asset") } };
  const forged = { "x-site-host": "preview.example", "x-forwarded-host": "preview.example" };
  // the preview's agent API: its own host, with the Worker's key
  await worker.fetch(new Request("https://preview.example/api/v2/kinds") as never,
    penv as never, ctx as never);
  assert.equal(seen.at(-1)!.get("x-site-host"), "preview.example");
  assert.equal(seen.at(-1)!.get("x-link-key"), env.LINK_KEY);
  // the live shop: a visitor cannot pass himself off as the preview
  for (const path of ["/api/shop/info", "/api/b2b/me", "/about"]) {
    await get(path, { headers: forged });
    assert.equal(seen.at(-1)!.get("x-site-host"), "shop.example", path);
  }
  await worker.fetch(new Request("https://shop.example/api/v2/kinds", { headers: forged }) as never,
    { ...env, AGENT_API: "1" } as never, ctx as never);
  assert.equal(seen.at(-1)!.get("x-site-host"), "shop.example");
});
