// A local stand-in for the preview website (apps/site, ADR-066) for browser checks of the shop's
// pages: this build's own files (apps/web/dist) and the data and media from an upstream website
// (by default preview.s2dio.living, which adds its own key). No secrets, no studio needed.
//
//   node apps/web/e2e/site_serve.mjs [--dist apps/web/dist] [--port 18300] [--upstream URL]
//                                    [--settings '{"home_story": false}']
//                                    [--media DIR]
//
// --settings is laid over the shop settings in /api/shop/info, to look at a page the way the live
// website shows it (for example the landing page without the scroll story). --media serves
// /media/<file> from a local folder first (renders not yet on the website, ADR-121).
//
// Used by apps/web/e2e/site_perf.py and site_rain.py.
import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { brotliCompressSync, constants } from "node:zlib";
import { createHash } from "node:crypto";

const arg = (name, fallback) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const DIST = resolve(arg("dist", "apps/web/dist"));
const PORT = Number(arg("port", "18300"));
const UPSTREAM = arg("upstream", "https://preview.s2dio.living");
const SETTINGS = JSON.parse(arg("settings", "{}"));
const MEDIA = arg("media", "") ? resolve(arg("media", "")) : "";
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".webp": "image/webp",
  ".json": "application/json",
  ".glb": "model/gltf-binary",
  ".bin": "application/octet-stream",
  ".wasm": "application/wasm",
  ".mp4": "video/mp4",
};

// text is sent brotli-compressed, as the edge does, so the measured sizes are the real ones
const TEXT = /^(text\/|application\/(json|javascript)|image\/svg)/;
const packed = new Map();
function send(req, res, status, headers, body) {
  const type = String(headers["content-type"] ?? "");
  if (
    TEXT.test(type) &&
    /\bbr\b/.test(req.headers["accept-encoding"] ?? "") &&
    status === 200
  ) {
    const key = createHash("sha1").update(body).digest("hex");
    let z = packed.get(key);
    if (!z) {
      z = brotliCompressSync(body, {
        params: { [constants.BROTLI_PARAM_QUALITY]: 9 },
      });
      if (packed.size < 200) packed.set(key, z);
    }
    headers["content-encoding"] = "br";
    body = z;
  }
  headers["content-length"] = body.length;
  res.writeHead(status, headers);
  res.end(req.method === "HEAD" ? undefined : body);
}

async function file(req, res, path, cache) {
  const body = await readFile(path);
  send(
    req,
    res,
    200,
    {
      "content-type": TYPES[extname(path)] ?? "application/octet-stream",
      "cache-control": cache,
    },
    body,
  );
}

// a local media file, with byte ranges (video seeks and Safari ask for them)
async function media(req, res, path, size) {
  const type = TYPES[extname(path)] ?? "application/octet-stream";
  const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? "");
  const body = await readFile(path);
  if (m) {
    const start = m[1] ? Number(m[1]) : Math.max(0, size - Number(m[2]));
    const end = m[1] && m[2] ? Math.min(Number(m[2]), size - 1) : size - 1;
    res.writeHead(206, {
      "content-type": type,
      "content-range": `bytes ${start}-${end}/${size}`,
      "content-length": end - start + 1,
      "accept-ranges": "bytes",
      "cache-control": "public, max-age=0",
    });
    return res.end(body.subarray(start, end + 1));
  }
  res.writeHead(200, {
    "content-type": type,
    "content-length": size,
    "accept-ranges": "bytes",
    "cache-control": "public, max-age=0",
  });
  res.end(req.method === "HEAD" ? undefined : body);
}

createServer(async (req, res) => {
  const url = new URL(req.url, "http://x");
  try {
    // media rendered here and not yet on the website (ADR-121): served from --media first
    if (MEDIA && /^\/media\/[a-z0-9_-]+\.[a-z0-9]+$/.test(url.pathname)) {
      const local = join(MEDIA, url.pathname.slice(7));
      const s = await stat(local).catch(() => null);
      if (s?.isFile()) return await media(req, res, local, s.size);
    }
    // as the preview's Worker (ADR-135): the agent pages and feeds from the studio, the
    // measuring guide and the cover pages under its /shop/
    const agentPage = /^\/(measure|covers)(\/|$)/.test(url.pathname);
    if (
      /^\/(api|media)\//.test(url.pathname) ||
      agentPage ||
      ["/llms.txt", "/llms-full.txt"].includes(url.pathname)
    ) {
      const upPath = agentPage ? `/shop${url.pathname}` : url.pathname;
      const headers = {};
      for (const h of ["range", "accept", "content-type"])
        if (req.headers[h]) headers[h] = req.headers[h];
      const body =
        req.method === "GET" || req.method === "HEAD"
          ? undefined
          : Buffer.concat(await req.toArray());
      const up = await fetch(UPSTREAM + upPath + url.search, {
        method: req.method,
        headers,
        body,
        redirect: "manual", // as the Worker: a redirect goes to the browser
      });
      const out = {};
      for (const [k, v] of up.headers)
        if (
          !["content-encoding", "content-length", "transfer-encoding"].includes(
            k,
          )
        )
          out[k] = v;
      let data = Buffer.from(await up.arrayBuffer());
      if (
        url.pathname === "/api/shop/info" &&
        up.ok &&
        Object.keys(SETTINGS).length
      ) {
        const info = JSON.parse(data.toString());
        info.settings = { ...info.settings, ...SETTINGS };
        data = Buffer.from(JSON.stringify(info));
      }
      send(req, res, up.status, out, data);
      return;
    }
    const own = normalize(join(DIST, url.pathname));
    if (own.startsWith(DIST) && url.pathname !== "/") {
      const s = await stat(own).catch(() => null);
      if (s?.isFile())
        return await file(
          req,
          res,
          own,
          url.pathname.startsWith("/assets/")
            ? "public, max-age=31536000, immutable"
            : "public, max-age=0",
        );
    }
    return await file(req, res, join(DIST, "shop.html"), "no-cache");
  } catch (e) {
    res.writeHead(502, { "content-type": "text/plain" });
    res.end(String(e));
  }
}).listen(PORT, "127.0.0.1", () =>
  console.log(
    `site on http://127.0.0.1:${PORT} (${DIST}, data from ${UPSTREAM})`,
  ),
);
