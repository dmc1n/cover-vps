"""The website's 3D loads only where it is shown, and shows without a flash (ADR-101).

In a real browser, against a local build (site_serve.mjs) or the preview:

- the scroll story (home page) never fetches three.js;
- the configurator fetches it at once, its 3D box is there before the model (same size, so
  nothing shifts), and the model fades in (`data-state="ready"`);
- a new size swaps the model in the same canvas (one WebGL canvas, never an empty box);
- the see-through slider redraws the cover; a phone draws at most 1.5 pixels per CSS pixel.

    node apps/web/e2e/site_serve.mjs --port 18300 &
    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/sitepolish:/shots" \\
      -e SITE_URL=http://127.0.0.1:18300/ mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/site_3d.py"
"""

import asyncio
import hashlib
import os
import sys

from playwright.async_api import Page, async_playwright, expect

URL = os.environ.get("SITE_URL", "https://preview.s2dio.living/").rstrip("/")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")


def three_fetched(urls: list[str]) -> bool:
    return any("/assets/three-" in u for u in urls)


async def shot(page: Page, name: str) -> None:
    """A picture for the eye; slow in a software-drawn browser on a busy machine, never fatal."""
    try:
        await page.screenshot(path=f"{SHOTS}/{name}.png", timeout=120000)
    except Exception as e:  # noqa: BLE001 - the picture is a courtesy, the checks are the test
        print(f"  (no picture {name}: {str(e)[:60]})")


async def canvas_pixels(page: Page) -> str:
    """A fingerprint of what the 3D canvas shows (a WebGL canvas cannot be read back, so a
    picture of it; quick here, because the view draws only when something changed)."""
    png = await page.locator(".s-config-view canvas").screenshot(timeout=120000)
    return hashlib.sha1(png).hexdigest()


async def main() -> int:
    errors: list[str] = []
    failed: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            failed.append(what)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"]
        )
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        urls: list[str] = []
        page.on("request", lambda r: urls.append(r.url))
        await page.goto(URL + "/")
        await page.wait_for_selector(".st-chapters", timeout=60000)
        await page.wait_for_timeout(3000)
        check(not three_fetched(urls), "the scroll story does not fetch three.js")

        urls.clear()
        await page.goto(URL + "/configure")
        box = page.locator(".s-config-view .s-scene")
        await expect(box).to_be_visible(timeout=30000)
        size_before = await box.bounding_box()
        await expect(box).to_have_attribute("data-state", "ready", timeout=90000)
        check(three_fetched(urls), "the configurator fetches three.js")
        size_after = await box.bounding_box()
        check(size_before == size_after, "the 3D box keeps its size when the model arrives")
        await page.wait_for_timeout(1000)
        await shot(page, "3d-configure")
        canvases = await page.locator(".s-config-view canvas").count()
        check(canvases == 1, "one canvas")

        # the see-through slider redraws the cover
        before = await canvas_pixels(page)
        await page.locator(".s-solid input").fill("1")
        await page.wait_for_timeout(600)
        check(await canvas_pixels(page) != before, "the slider redraws the cover")

        # a new size: the model swaps in the same canvas, no empty box in between
        shown = await canvas_pixels(page)
        size = page.locator(".s-range input[type=range]").first
        await size.fill(str(int(float(await size.input_value())) + 40))
        scene = await page.evaluate("document.querySelector('.s-config-view canvas') !== null")
        check(scene, "the canvas stays while the new size is calculated")
        empty = 0
        for _ in range(40):
            await page.wait_for_timeout(150)
            state = await box.get_attribute("data-state")
            opacity = await page.evaluate(
                "getComputedStyle(document.querySelector('.s-config-view canvas')).opacity"
            )
            if state != "ready" or float(opacity) < 0.99:
                empty += 1
        check(empty == 0, "a new size never shows an empty box")
        check(await canvas_pixels(page) != shown, "the new size is drawn")
        check(await page.locator(".s-config-view canvas").count() == 1, "still one canvas")
        await ctx.close()

        phone = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
        )
        page = await phone.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(URL + "/configure")
        box = page.locator(".s-config-view .s-scene")
        await expect(box).to_have_attribute("data-state", "ready", timeout=120000)
        ratio = await page.evaluate(
            """() => { const c = document.querySelector('.s-config-view canvas');
            return c.width / c.getBoundingClientRect().width; }"""
        )
        check(ratio <= 1.51, f"a phone draws {ratio:.2f} pixels per CSS pixel (at most 1.5)")
        await shot(page, "3d-configure-phone")
        await phone.close()
        await browser.close()

    for e in errors:
        print("page error:", e)
    return 1 if failed or errors else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
