"""Browser check of the public consumer shop (ADR-103): every consumer page without a login, on a
desktop and on a phone (390 px); the configurator's price with the "indicative" note, the
checkout with delivery and the honeypot, the legal drafts, a real 404; load times, the size of
what each page downloads, and no horizontal scrolling on the phone.

Run against the website's Worker (`wrangler dev --local --local-protocol https`) in front of a
scratch studio (never the live data):

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/b2ctest:/shots" \
      -e COVER_E2E_URL=https://127.0.0.1:8787 \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/b2c.py"
"""

import asyncio
import json
import os
import time

from playwright.async_api import Page, async_playwright

URL = os.environ.get("COVER_E2E_URL", "https://127.0.0.1:8787")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
PAGES = ["", "configure", "terms", "privacy", "returns", "cookies", "contact", "warranty",
         "en/", "de/configure", "en/returns", "order/abcdefghijkl", "no-such-page"]  # fmt: skip


async def visit(page: Page, path: str, name: str) -> dict[str, object]:
    sizes: list[int] = []

    def on_response(r):  # type: ignore[no-untyped-def]
        cl = r.headers.get("content-length")
        if cl:
            sizes.append(int(cl))

    page.on("response", on_response)
    t = time.time()
    resp = await page.goto(f"{URL}/{path}", wait_until="load")
    load = time.time() - t
    await page.wait_for_timeout(800)
    page.remove_listener("response", on_response)
    wide = await page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
    imgs = await page.evaluate(
        "[...document.images].map(i => [i.currentSrc, i.naturalWidth, i.clientWidth])"
    )
    await page.screenshot(path=f"{SHOTS}/{name}.png", full_page=True)
    return {"path": path or "/", "status": resp.status if resp else None,
            "load_s": round(load, 2), "kb": round(sum(sizes) / 1024), "scrolls_sideways": wide,
            "title": await page.title(), "images": imgs}  # fmt: skip


async def main() -> None:
    report = []
    async with async_playwright() as p:
        b = await p.chromium.launch()
        for label, vp in (("desktop", {"width": 1366, "height": 860}),
                          ("phone", {"width": 390, "height": 844})):  # fmt: skip
            ctx = await b.new_context(viewport=vp, ignore_https_errors=True, locale="nl-NL")
            page = await ctx.new_page()
            for path in PAGES:
                name = f"{label}-{(path or 'home').strip('/').replace('/', '-')}"
                report.append({"view": label, **await visit(page, path, name)})
            # the configurator: a price, the "indicative" note, then the checkout
            await page.goto(f"{URL}/configure", wait_until="load")
            await page.locator(".s-price strong").first.wait_for(timeout=30000)
            await page.locator(".s-indicative").first.wait_for(timeout=5000)
            await page.screenshot(path=f"{SHOTS}/{label}-configure-price.png", full_page=True)
            await page.locator(".s-price button").first.click()
            await page.locator("form.s-checkout").wait_for()
            trap_seen = await page.locator(".s-trap").is_visible()
            assert not trap_seen or (await page.locator(".s-trap").bounding_box() or {}).get(
                "x", 0) < -1000, "the honeypot shows"  # fmt: skip
            await page.select_option("form.s-checkout select", "BE")
            await page.screenshot(path=f"{SHOTS}/{label}-checkout.png", full_page=True)
            total = await page.locator("form.s-checkout .s-price").inner_text()
            report.append({"view": label, "checkout": total.replace("\n", " | ")})
            await ctx.close()
        await b.close()
    print(json.dumps(report, indent=1, ensure_ascii=False))


asyncio.run(main())
