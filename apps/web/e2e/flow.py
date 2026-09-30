"""End-to-end check of the web app in a real browser (Playwright): upload the test chair, wait
for the run, open every tab, change a setting and try it. Run with `make e2e` (the browser
comes from the Playwright Docker image; the app runs on this machine with an empty data dir)."""

import asyncio
import os
import sys

from playwright.async_api import async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18181")
CHAIR = os.environ.get("COVER_E2E_FILE", "/repo/testdata/generated/chair.stl")
RUN_MS = 600_000


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1300, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(URL)
        await page.set_input_files("input[type=file]", CHAIR)
        await page.get_by_role("button", name="Upload and run").click()
        await expect(page.get_by_text("Last run finished.")).to_be_visible(timeout=RUN_MS)
        for tab in ("3D", "Seams", "Patterns", "Size drawing", "Cut pieces", "Downloads"):
            await page.get_by_role("button", name=tab, exact=True).click()
            await page.wait_for_timeout(1000)
        await expect(page.get_by_text("cut.dxf").first).to_be_visible()
        await page.get_by_role("button", name="Settings", exact=True).click()
        await page.get_by_placeholder("Search settings…").fill("clearance_mm")
        field = page.locator(".param", has_text="clearance_mm").first.locator("input")
        await field.fill("15")
        await page.get_by_role("button", name="Try without saving").click()
        await expect(page.get_by_text("not saved")).to_be_visible(timeout=RUN_MS)  # the trial run
        await expect(page.get_by_text("Last run finished.")).to_be_visible(timeout=RUN_MS)
        await expect(page.get_by_text("hull.clearance_mm: 10 → 15")).to_be_visible()
        await page.screenshot(path="/tmp/e2e.png")
        await browser.close()
        if errors:
            print("page errors:", errors)
            return 1
        print("e2e: ok")
        return 0


sys.exit(asyncio.run(main()))
