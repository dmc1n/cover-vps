// The dealer embed at the edge (ADR-150): `npm test` (node's own test runner, types stripped).
// The studio is a fake `fetch` that records what reached it.
import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import worker from "../src/worker.ts";

const reached: string[] = [];
const seen: { path: string; headers: Headers }[] = [];

beforeEach(() => {
  reached.length = 0;
  seen.length = 0;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = new Request(input, { ...init, duplex: "half" } as RequestInit);
    const path = new URL(req.url).pathname;
    reached.push(path);
    seen.push({ path, headers: req.headers });
    const frame = path === "/embed/v1/frame";
    return new Response("{}", {
      headers: {
        "content-type": frame ? "text/html" : "application/json",
        "set-cookie": "cover_session=secret",
        ...(frame ? { "content-security-policy": "frame-ancestors 'self' https://dealer.example" } : {}),
      },
    });
  }) as typeof fetch;
  (globalThis as unknown as { caches: unknown }).caches = {
    default: { match: async () => undefined, put: async () => undefined },
  };
});

const env = { STUDIO_URL: "https://studio.example", LINK_KEY: "k", PAGE_TTL: "0", MEDIA_TTL: "0" };
const ctx = { waitUntil: () => undefined, passThroughOnException: () => undefined };
const assets: string[] = [];
const penv = {
  ...env,
  PREVIEW: "1",
  ASSETS: {
    fetch: async (r: Request) => {
      assets.push(new URL(r.url).pathname);
      return new Response("export {}", { headers: { "content-type": "text/javascript" } });
    },
  },
};

function on(host: string, e: object) {
  return (path: string, init?: RequestInit) =>
    worker.fetch(new Request(`https://${host}${path}`, init) as never, e as never, ctx as never);
}

test("live without DEALER_EMBED: nothing of the embed exists at the edge", async () => {
  const get = on("shop.example", env);
  for (const path of ["/embed/v1/configurator.js", "/embed/v1/frame", "/api/embed/v1/dpk_x/config",
    "/embed/v1/checkout/abc", "/embed-demo", "/embed-demo.js"]) {
    assert.equal((await get(path)).status, 404, path);
  }
  assert.deepEqual(reached, []);
});

test("the script: this build's own file, with CORS for any page", async () => {
  assets.length = 0;
  const get = on("preview.example", penv);
  const js = await get("/embed/v1/configurator.js");
  assert.equal(js.status, 200);
  assert.equal(js.headers.get("access-control-allow-origin"), "*");
  assert.equal(js.headers.get("cross-origin-resource-policy"), "cross-origin");
  assert.match(js.headers.get("cache-control")!, /max-age=300/);
  assert.match((await get("/embed/v1/viewer3d-abc123.js")).headers.get("cache-control")!, /immutable/);
  assert.deepEqual(assets, ["/embed/v1/configurator.js", "/embed/v1/viewer3d-abc123.js"]);
  assert.deepEqual(reached, []); // the studio is not asked for the preview's own build
});

test("the API: the page's Origin passes to the studio, cookies never", async () => {
  const api = await on("preview.example", penv)("/api/embed/v1/dpk_x/quote", {
    method: "POST",
    body: "{}",
    headers: { origin: "https://dealer.example", cookie: "cover_session=private" },
  });
  assert.equal(api.status, 200);
  const got = seen.at(-1)!;
  assert.equal(got.path, "/api/embed/v1/dpk_x/quote");
  assert.equal(got.headers.get("origin"), "https://dealer.example");
  assert.equal(got.headers.get("cookie"), null);
  assert.equal(got.headers.get("x-link-key"), "k");
  assert.equal(got.headers.get("x-site-host"), "preview.example");
  assert.equal(api.headers.get("set-cookie"), null);
  assert.equal(api.headers.get("cache-control"), "no-store");
});

test("the frame keeps the studio's frame-ancestors and has no X-Frame-Options", async () => {
  const get = on("preview.example", penv);
  const frame = await get("/embed/v1/frame?dealer=dpk_x");
  assert.equal(frame.headers.get("x-frame-options"), null);
  assert.match(frame.headers.get("content-security-policy")!,
    /frame-ancestors 'self' https:\/\/dealer\.example/);
  assert.equal((await get("/embed/v1/checkout/abc")).headers.get("x-frame-options"), "SAMEORIGIN");
  assert.equal((await get("/")).headers.get("x-frame-options"), "SAMEORIGIN");
});

test("the demo: the preview only", async () => {
  assets.length = 0;
  const get = on("preview.example", penv);
  assert.equal((await get("/embed-demo")).status, 200);
  assert.equal((await get("/embed-demo.js")).status, 200);
  assert.deepEqual(assets, ["/embed-demo.html", "/embed-demo.js"]);
  const live = on("shop.example", { ...env, DEALER_EMBED: "1" });
  assert.equal((await live("/embed-demo")).status, 404);
});

test("the live site after the owner's go", async () => {
  const live = on("shop.example", { ...env, DEALER_EMBED: "1" });
  assert.equal((await live("/api/embed/v1/dpk_x/config")).status, 200);
  const js = await live("/embed/v1/configurator.js");
  assert.equal(js.headers.get("access-control-allow-origin"), "*");
  assert.deepEqual(reached, ["/api/embed/v1/dpk_x/config", "/embed/v1/configurator.js"]);
  assert.equal(seen.at(-1)!.headers.get("x-link-key"), "k");
});
