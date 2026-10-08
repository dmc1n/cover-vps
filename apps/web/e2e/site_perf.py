"""How fast the website's pages show their 3D (ADR-106): the network waterfall, the bytes, the
time to the first frame of the 3D, and the frame rate, on a desktop and on a mid-range phone
(390 px, CPU 4x slower, a slow 4G line: 150 ms, 1.6 Mbit/s down).

Against the live website, the preview, or a local build served by site_serve.mjs:

    node apps/web/e2e/site_serve.mjs --port 18300 &            # this build, data from the preview
    node apps/web/e2e/site_serve.mjs --port 18310 --settings '{"home_story":false,"film_url":""}' &
    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/sitepolish:/shots" \\
      -e SITE_PAGES="story=http://127.0.0.1:18300/,home3d=http://127.0.0.1:18310/,\
configure=http://127.0.0.1:18300/configure" \\
      -e SITE_LABEL=after mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/site_perf.py"

Writes <label>-perf.json and a screenshot per page and profile into /shots, and prints a table.
The 3D's first frame is the first WebGL draw of anything but the ground disc (192 indices), the
model, or the first picture drawn on the story's canvas.
"""

import asyncio
import json
import os
import sys

from playwright.async_api import Page, async_playwright

PAGES = dict(
    p.split("=", 1)
    for p in os.environ.get(
        "SITE_PAGES",
        "story=https://preview.s2dio.living/,configure=https://preview.s2dio.living/configure",
    ).split(",")
)
LABEL = os.environ.get("SITE_LABEL", "run")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
RUNS = int(os.environ.get("SITE_RUNS", "2"))

PROFILES = {
    "desktop": {"viewport": {"width": 1440, "height": 900}, "dpr": 1, "cpu": 1, "net": None},
    "phone": {
        "viewport": {"width": 390, "height": 844},
        "dpr": 3,
        "cpu": 4,
        # Lighthouse's "slow 4G": 150 ms, 1.6 Mbit/s down, 750 kbit/s up
        "net": {"latency": 150, "down": 1.6e6 / 8, "up": 750e3 / 8},
    },
}

# first big WebGL draw (the model), first picture on a 2D canvas (the story's frames), paints
PROBE = """
(() => {
  const P = (window.__perf = { gl: 0, img: 0, lcp: 0, cls: 0, longtask: 0 });
  const GROUND = 192; // the shadow catcher under the model: a 64-segment disc
  const wrap = (proto, name, big) => {
    const f = proto && proto[name];
    if (!f) return;
    proto[name] = function (...a) {
      if (!P.gl && big(a)) P.gl = performance.now();
      return f.apply(this, a);
    };
  };
  for (const C of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
    if (!C) continue;
    wrap(C.prototype, "drawElements", (a) => a[1] !== GROUND);
    wrap(C.prototype, "drawArrays", (a) => a[2] !== GROUND);
  }
  const di = CanvasRenderingContext2D.prototype.drawImage;
  CanvasRenderingContext2D.prototype.drawImage = function (...a) {
    if (!P.img && a[0] instanceof HTMLImageElement) P.img = performance.now();
    return di.apply(this, a);
  };
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) P.lcp = e.startTime;
  }).observe({ type: "largest-contentful-paint", buffered: true });
  new PerformanceObserver((l) => {
    for (const e of l.getEntries()) if (!e.hadRecentInput) P.cls += e.value;
  }).observe({ type: "layout-shift", buffered: true });
  try {
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) P.longtask += Math.max(0, e.duration - 50);
    }).observe({ type: "longtask", buffered: true });
  } catch (e) {}
})();
"""

FPS = """
(ms) => new Promise((done) => {
  let n = 0;
  const t0 = performance.now();
  const step = (t) => {
    n++;
    if (t - t0 < ms) requestAnimationFrame(step);
    else done((n * 1000) / (t - t0));
  };
  requestAnimationFrame(step);
})
"""


async def measure(page: Page, url: str, name: str, profile: str, run: int) -> dict:
    prof = PROFILES[profile]
    cdp = await page.context.new_cdp_session(page)
    await cdp.send("Network.enable")
    await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    if prof["net"]:
        n = prof["net"]
        await cdp.send(
            "Network.emulateNetworkConditions",
            {
                "offline": False,
                "latency": n["latency"],
                "downloadThroughput": n["down"],
                "uploadThroughput": n["up"],
            },
        )
    await cdp.send("Emulation.setCPUThrottlingRate", {"rate": prof["cpu"]})
    reqs: dict[str, dict] = {}

    def on_req(e: dict) -> None:
        reqs[e["requestId"]] = {"url": e["request"]["url"], "start": e["timestamp"]}

    def on_resp(e: dict) -> None:
        r = reqs.get(e["requestId"])
        if r:
            r["status"] = e["response"]["status"]
            r["type"] = e["type"]

    def on_done(e: dict) -> None:
        r = reqs.get(e["requestId"])
        if r:
            r["end"] = e["timestamp"]
            r["bytes"] = e["encodedDataLength"]

    cdp.on("Network.requestWillBeSent", on_req)
    cdp.on("Network.responseReceived", on_resp)
    cdp.on("Network.loadingFinished", on_done)
    await page.goto(url, wait_until="commit")
    t0 = min((r["start"] for r in reqs.values()), default=0)
    # wait for the 3D (at most 60 s on the phone profile)
    want = "img" if name == "story" else "gl"
    for _ in range(600):
        if await page.evaluate(f"window.__perf && window.__perf.{want} > 0"):
            break
        await page.wait_for_timeout(100)
    await page.wait_for_timeout(1500)
    fps = await page.evaluate(FPS, 3000)
    perf = await page.evaluate("window.__perf")
    nav = await page.evaluate(
        "(() => { const n = performance.getEntriesByType('navigation')[0];"
        " const f = performance.getEntriesByName('first-contentful-paint')[0];"
        " return { ttfb: n ? n.responseStart : 0, fcp: f ? f.startTime : 0 }; })()"
    )
    await page.screenshot(path=f"{SHOTS}/{LABEL}-{name}-{profile}.png")
    rows = sorted(
        (
            {
                "url": r["url"].split("//", 1)[-1].split("/", 1)[-1][:70],
                "type": r.get("type", ""),
                "kB": round(r.get("bytes", 0) / 1024, 1),
                "start_ms": round((r["start"] - t0) * 1000),
                "end_ms": round((r.get("end", r["start"]) - t0) * 1000),
            }
            for r in reqs.values()
        ),
        key=lambda r: r["start_ms"],
    )
    await cdp.detach()
    return {
        "page": name,
        "profile": profile,
        "run": run,
        "ttfb_ms": round(nav["ttfb"]),
        "fcp_ms": round(nav["fcp"]),
        "lcp_ms": round(perf["lcp"]),
        "first_3d_ms": round(perf[want]),
        "cls": round(perf["cls"], 3),
        "blocking_ms": round(perf["longtask"]),
        "fps": round(fps, 1),
        "requests": len(rows),
        "total_kB": round(sum(r["kB"] for r in rows)),
        "js_kB": round(sum(r["kB"] for r in rows if r["type"] == "Script")),
        "waterfall": rows,
    }


async def main() -> int:
    out: list[dict] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"]
        )
        for profile, prof in PROFILES.items():
            for name, url in PAGES.items():
                for run in range(RUNS):
                    ctx = await browser.new_context(
                        viewport=prof["viewport"],
                        device_scale_factor=prof["dpr"],
                        is_mobile=profile == "phone",
                        has_touch=profile == "phone",
                        locale="nl-NL",
                    )
                    await ctx.add_init_script(PROBE)
                    page = await ctx.new_page()
                    try:
                        out.append(await measure(page, url, name, profile, run))
                    except Exception as e:  # noqa: BLE001 - a page that fails is reported, not fatal
                        print(f"{name} {profile}: {e}", file=sys.stderr)
                    await ctx.close()
        await browser.close()
    with open(f"{SHOTS}/{LABEL}-perf.json", "w") as f:
        json.dump(out, f, indent=1)
    keys = ["ttfb_ms", "fcp_ms", "lcp_ms", "first_3d_ms", "cls", "blocking_ms", "fps",
            "requests", "total_kB", "js_kB"]  # fmt: skip
    print(f"{'page':10} {'profile':8} " + " ".join(f"{k:>11}" for k in keys))
    for r in out:
        print(f"{r['page']:10} {r['profile']:8} " + " ".join(f"{r[k]:>11}" for k in keys))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
