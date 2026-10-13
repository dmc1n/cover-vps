"""End-to-end check of the web app in a real browser (Playwright): upload the test chair, wait
for the run, open every tab, change a setting and try it. Run with `make e2e` (the browser
comes from the Playwright Docker image; the app runs on this machine with an empty data dir)."""

import asyncio
import os
import re
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
        await page.get_by_label("User name").fill("tester")
        await page.get_by_label("Password").fill("browser-test-password")
        await page.get_by_role("button", name="Log in").click()
        await expect(page.get_by_role("button", name="Log out")).to_be_visible()
        await page.goto(URL + "#/covers/new")  # Covers → New cover: three uploads (ADR-124)
        await expect(page.get_by_role("heading", name="From a 3D file")).to_be_visible()
        await page.get_by_label("3D file", exact=True).set_input_files(CHAIR)
        await page.get_by_role("button", name="Upload and run").click()
        await expect(page.get_by_text("Check: what is this file?")).to_be_visible(timeout=RUN_MS)
        await page.get_by_role("button", name="Yes, the complete product (furniture)").click()
        await expect(page.get_by_text("Check: what is this file?")).to_be_hidden()
        await expect(page.locator(".job .jobstep")).to_have_count(4, timeout=RUN_MS)  # the rest
        await expect(page.get_by_text("Last run finished.")).to_be_visible(timeout=RUN_MS)
        tabs = page.get_by_role("navigation", name="Cover")
        show = page.get_by_role("group", name="In this tab")
        views = [("3D", ""), ("Seams", ""), ("Pieces", "Flat patterns"), ("Pieces", "Size drawing"),
                 ("Pieces", "Cut pieces"), ("Pieces", "Files")]  # fmt: skip
        for tab, sub in views:
            await tabs.get_by_role("link", name=tab, exact=True).click()
            if sub:
                await show.get_by_role("link", name=sub, exact=True).click()
            await page.wait_for_timeout(1000)
        await expect(page.get_by_text("cut.dxf").first).to_be_visible()
        # the cover's own price and shop (ADR-126): its costing from its own cut pieces
        await tabs.get_by_role("link", name="Price & shop", exact=True).click()
        await expect(page.get_by_test_id("cover-cost")).to_be_visible(timeout=RUN_MS)
        await page.get_by_role("button", name="Edit details").click()
        status = page.locator(".info select", has=page.locator("option", has_text="checked"))
        await status.select_option("checked")  # the status (category and family come first)
        await page.locator(".info").get_by_role("button", name="Save").click()
        await expect(page.locator(".info").get_by_text("Saved.")).to_be_visible()
        await tabs.get_by_role("link", name=re.compile(r"^History")).click()
        await show.get_by_role("link", name="Revisions", exact=True).click()
        await expect(page.get_by_role("cell").filter(has_text="pattern.json").first).to_be_visible()
        # one approval, the Desk's (ADR-128): the cover page points there; the approval stamps
        # the size drawing and the cutting list
        card = page.locator(".card.approval")
        await expect(card.get_by_text("Not approved yet")).to_be_visible()
        cover_url = page.url
        await card.get_by_role("link", name=re.compile("Its Desk card")).click()
        await page.locator(".d-actions").get_by_role("button", name=re.compile("Approve")).click()
        await expect(page.locator(".d-msg").first).to_contain_text("Approved", timeout=RUN_MS)
        await page.goto(cover_url)
        await expect(card.get_by_text("Approved on the Desk by Tester")).to_be_visible()
        await expect(card.get_by_role("link", name="Approved size drawing")).to_be_visible()
        await tabs.get_by_role("link", name="Adjust", exact=True).click()
        await page.get_by_placeholder("Search settings…").fill("clearance_mm")
        field = page.locator(".param", has_text="clearance_mm").first.locator("input")
        await field.fill("15")
        await page.get_by_role("button", name="Try without saving").click()
        await expect(page.get_by_text("not saved")).to_be_visible(timeout=RUN_MS)  # the trial run
        await expect(page.get_by_text("Last run finished.")).to_be_visible(timeout=RUN_MS)
        await tabs.get_by_role("link", name=re.compile(r"^History")).click()  # since the run before
        await expect(page.get_by_text("hull.clearance_mm: 10 → 15")).to_be_visible()
        await page.screenshot(path="/tmp/e2e.png")
        await page.goto(URL + "#/admin")  # → Settings → Users & rights
        await expect(page.get_by_role("cell", name="tester", exact=True)).to_be_visible()
        await page.get_by_role("button", name="Log out").click()
        await expect(page.get_by_role("button", name="Log in")).to_be_visible()
        await browser.close()
        if errors:
            print("page errors:", errors)
            return 1
        print("e2e: ok")
        return 0


sys.exit(asyncio.run(main()))
