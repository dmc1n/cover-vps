"""Browser check of Import prices (Excel), ADR-113: an admin uploads a price list on Prices &
costing → Channels & price lists, sees what matched (exact / probable), the conflicts and the
rows to choose by hand, looks at B2B (stored ex VAT) and back, puts the prices in the draft,
previews and publishes with the note "Imported from …"; an editor sees no import; a phone.

Make the sample list (apps/web/e2e/priceimport_sheet.py), run a studio on a scratch data copy
(never the live data) with an admin `tester` and an editor `eddy2` (password
browser-test-password), then:

    uv run python apps/web/e2e/priceimport_sheet.py out/priceimport/prijslijst-2027.xlsx
    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/priceimport:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:18193 \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/priceimport.py"
"""

import asyncio
import os
import sys

from playwright.async_api import Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18193")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
SHEET = os.environ.get("COVER_E2E_SHEET", "/repo/out/priceimport/prijslijst-2027.xlsx")


async def login(page: Page, user: str) -> None:
    await page.goto(URL)
    await page.get_by_label("User name").fill(user)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("link", name="Models")).to_be_visible()


async def channels(page: Page) -> None:
    await page.goto(URL + "#/prices")
    await page.get_by_role("button", name="Channels & price lists").click()


async def shot(page: Page, name: str, full: bool = True) -> None:
    await page.wait_for_timeout(400)
    await page.screenshot(path=f"{SHOTS}/{name}.png", full_page=full)


async def main() -> int:
    errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 950})
        page.on("pageerror", lambda e: errors.append(str(e)))
        await login(page, "tester")
        await channels(page)
        box = page.get_by_test_id("price-import")
        await expect(box).to_contain_text("Import prices (Excel)")
        await page.get_by_test_id("price-import-file").set_input_files(SHEET)
        matched = page.get_by_test_id("pi-matched")
        await expect(matched).to_contain_text("drawing-s40", timeout=30_000)
        await expect(box).to_contain_text("prijslijst-2027.xlsx")
        await expect(page.get_by_label("price column")).to_have_value("Verkoopprijs incl. BTW")
        await expect(page.get_by_label("prices incl or ex VAT")).to_have_value("true")
        await expect(matched).to_contain_text("€ 1,234.95")  # "€ 1.234,95" read the Dutch way
        await expect(matched).to_contain_text("suns-2-seater-kota")
        await expect(page.get_by_test_id("pi-open")).to_contain_text("Unknown Fantasy Sofa XL")
        await box.scroll_into_view_if_needed()
        await box.screenshot(path=f"{SHOTS}/01-matched.png")
        # B2B keeps its prices ex VAT: the sheet's price incl. VAT stays the same to the cent
        await page.get_by_label("import channel").select_option("b2b")
        await expect(box).to_contain_text("stored ex VAT", timeout=30_000)
        await expect(matched).to_contain_text("1,020.619835")
        await box.screenshot(path=f"{SHOTS}/02-b2b-ex-vat.png")
        await page.get_by_label("import channel").select_option("b2c")
        await expect(box).not_to_contain_text("stored ex VAT")
        # a person decides: the conflict, the ambiguous row, the unknown row
        conflicts = page.get_by_test_id("pi-conflicts")
        await expect(conflicts).to_contain_text("suns-lounge-chair-bellano")
        sel = page.get_by_label("price for suns-lounge-chair-bellano")
        await sel.select_option(index=1)
        cand = page.locator("select[aria-label^='candidates for row']").first
        await cand.select_option(index=1)
        unknown = page.get_by_label("cover for row 7")
        await unknown.fill("suns-3-seater-aspen")
        await expect(page.get_by_test_id("pi-open")).to_contain_text("SUNS-3 Seater-Aspen")
        await page.get_by_label("cover for row 11").fill("no-such-cover")
        await expect(page.get_by_test_id("pi-open")).to_contain_text("no such cover")
        await page.get_by_label("cover for row 11").fill("")
        await page.get_by_label("import balloon").uncheck()  # not this one
        await box.screenshot(path=f"{SHOTS}/03-chosen.png")
        put = page.get_by_role("button", name="prices in the draft")
        label = await put.inner_text()
        await put.click()
        await expect(page.get_by_text("prices put in the draft")).to_be_visible()
        await expect(page.get_by_text("not live")).to_be_visible()
        note = page.get_by_placeholder("What changed (for the history)")
        await expect(note).to_have_value(
            f"Imported from prijslijst-2027.xlsx ({label.split()[1]} prices, B2C)"
        )
        await shot(page, "04-draft", full=False)
        await page.get_by_role("button", name="Preview changes").click()
        await expect(page.get_by_text("prices move")).to_be_visible()
        await shot(page, "05-preview")
        await page.get_by_role("button", name="Publish", exact=True).click()
        await expect(page.get_by_text("Published version").first).to_be_visible()
        await page.get_by_role("button", name="Versions").click()
        await expect(page.get_by_text("Imported from prijslijst-2027.xlsx").first).to_be_visible()
        await shot(page, "06-versions", full=False)
        # the fixed prices are in the price list now
        await page.get_by_role("button", name="Channels & price lists").click()
        await expect(page.get_by_label("b2c fixed drawing-s40")).to_have_value("1234.95")
        # a phone
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.get_by_test_id("price-import-file").set_input_files(SHEET)
        await expect(page.get_by_test_id("pi-matched")).to_contain_text(
            "drawing-s40", timeout=30_000
        )
        wide = await page.evaluate("document.documentElement.scrollWidth")
        if wide > 400:  # noqa: PLR2004 - the page itself never scrolls sideways
            culprits = await page.evaluate(
                "[...document.querySelectorAll('body *')].filter(e => "
                "e.getBoundingClientRect().right > 400).slice(0, 6).map(e => "
                "e.tagName + '.' + e.className + ' ' + Math.round(e.getBoundingClientRect().right))"
            )
            errors.append(f"the page is {wide} px wide on a phone: {culprits}")
        await box.screenshot(path=f"{SHOTS}/07-phone.png")
        # an editor only looks: no import
        ed = await browser.new_page(viewport={"width": 1280, "height": 900})
        await login(ed, "eddy2")
        await channels(ed)
        await expect(ed.get_by_text("Fixed prices").first).to_be_visible()
        await expect(ed.get_by_test_id("price-import")).to_have_count(0)
        await browser.close()
    if errors:
        print("page errors:", *errors, sep="\n  ")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
