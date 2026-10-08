"""Browser check of Prices & costing (ADR-098): an admin changes a price, previews which prices
move, publishes, looks at a costing (a cover and a configurator product), rolls back; an editor
only looks; the page on a phone. Every tab explains itself: an intro, a help line per field,
"placeholder — please confirm" marks with a counter, and live examples that follow the numbers
as they are typed (POST /api/prices/check).

Run against a running studio with a scratch data copy (never the live data), with an admin
`tester` and an editor `eddy` (password browser-test-password) and a few calculated covers:

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/pricetest2:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:18190 -e COVER_E2E_MODEL=drawing-c1 \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/prices.py"
"""

import asyncio
import os
import sys

from playwright.async_api import Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18190")
MODEL = os.environ.get("COVER_E2E_MODEL", "drawing-c1")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")


async def login(page: Page, user: str) -> None:
    await page.goto(URL)
    await page.get_by_label("User name").fill(user)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("link", name="Models")).to_be_visible()


async def shot(page: Page, name: str) -> None:
    await page.wait_for_timeout(400)
    await page.screenshot(path=f"{SHOTS}/{name}.png", full_page=True)


async def main() -> int:
    errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 950})
        page.on("pageerror", lambda e: errors.append(str(e)))
        await login(page, "tester")
        await page.goto(URL + "#/admin")
        await page.get_by_role("button", name="Prices & costing").click()
        await expect(page.get_by_text("the documented defaults")).to_be_visible()
        count = page.get_by_test_id("placeholder-count")
        await expect(count).to_contain_text("values are still placeholders")
        first = int((await count.inner_text()).split()[0])
        example = page.get_by_test_id("live-example").first
        await expect(example).to_contain_text("in the cut plan")
        await shot(page, "01-materials")
        # a placeholder kept as it is: the counter goes down
        waste = page.locator(".ph[data-field='fabric:coverlast.waste_pct']")
        await waste.get_by_role("button", name="keep this value").click()
        await expect(waste).to_have_count(0)
        await expect(count).to_contain_text(f"{first - 1} of")
        # a change: the fabric costs more, and in rupiah; the example follows before saving
        price = page.get_by_label("fabric price")
        await price.fill("450000")
        await page.get_by_label("fabric currency").select_option("IDR")
        await expect(page.get_by_text("unsaved changes")).to_be_visible()
        await expect(example).to_contain_text("Rp 450,000")
        await expect(count).to_contain_text(f"{first - 2} of")
        await shot(page, "01b-materials-typed")
        await page.get_by_role("button", name="Preview changes").click()
        await expect(page.get_by_text("prices move")).to_be_visible()
        await shot(page, "02-preview")
        await page.get_by_role("button", name="Labour", exact=True).click()
        await expect(page.get_by_test_id("live-example")).to_contain_text("takes")
        await page.get_by_label("seam minutes").fill("4")
        await expect(page.get_by_test_id("live-example")).to_contain_text("takes")
        await shot(page, "03-labour")
        await page.get_by_role("button", name="Exchange rate").click()
        await expect(page.get_by_test_id("live-example")).to_contain_text("Rp 450,000/m")
        await shot(page, "04-rate")
        await page.get_by_role("button", name="Channels & price lists").click()
        await expect(page.get_by_text("landed cost").first).to_be_visible()
        await page.get_by_text("Terms explained").click()
        await expect(page.get_by_text("markup 87.5 % = margin 46.7 %").first).to_be_visible()
        await page.get_by_label("b2b fixed product").fill(MODEL)
        await page.get_by_role("button", name="Add fixed price").last.click()
        await page.get_by_label(f"b2b fixed {MODEL}").fill("999")
        await shot(page, "05-channels")
        await page.get_by_placeholder("What changed (for the history)").fill("fabric in rupiah")
        await page.get_by_role("button", name="Publish").click()
        await expect(page.get_by_text("Published version 1")).to_be_visible()
        await page.get_by_role("button", name="Costing", exact=True).click()
        await page.get_by_label("cover to cost").fill(MODEL)
        costing = page.get_by_test_id("costing")
        await expect(costing.get_by_text("Cost price").first).to_be_visible()
        await expect(costing.get_by_text("(fixed price)")).to_be_visible()
        await shot(page, "06-costing-cover")
        csv = await page.request.get(URL + f"/api/prices/costing.csv?model={MODEL}")
        assert csv.ok and "cost price" in await csv.text()
        pdf = await page.request.get(URL + f"/api/prices/costing.pdf?model={MODEL}")
        assert pdf.ok and (await pdf.body())[:4] == b"%PDF"
        await page.get_by_text("A configurator product", exact=True).click()
        await page.get_by_label("configurator product", exact=True).select_option("dining_set")
        await expect(costing.get_by_text("Configurator:")).to_be_visible()
        await shot(page, "07-costing-configurator")
        # a second version, then back to the first
        await page.get_by_role("button", name="Materials").click()
        await page.get_by_label("vent_set price").fill("9")
        await page.get_by_role("button", name="Publish").click()
        await expect(page.get_by_text("Published version 2")).to_be_visible()
        await page.get_by_role("button", name="Versions").click()
        await expect(page.get_by_text("The history of the prices")).to_be_visible()
        page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await page.get_by_role("button", name="Roll back to this").last.click()
        await expect(page.get_by_role("cell", name="rolled back to version 1")).to_be_visible()
        await shot(page, "08-versions")
        # an editor looks, and cannot change
        editor = await browser.new_page(viewport={"width": 1440, "height": 950})
        editor.on("pageerror", lambda e: errors.append(str(e)))
        await login(editor, "eddy")
        await editor.get_by_role("link", name="Prices").click()
        await expect(editor.get_by_text("You can look; an admin changes")).to_be_visible()
        await expect(editor.get_by_role("button", name="Publish")).to_have_count(0)
        await expect(editor.get_by_label("fabric price")).to_be_disabled()
        await shot(editor, "09-editor")
        # on a phone
        phone = await browser.new_page(viewport={"width": 390, "height": 844})
        await login(phone, "tester")
        await phone.goto(URL + "#/prices")
        await expect(phone.get_by_test_id("live-example").first).to_contain_text("cut plan")
        await shot(phone, "10-phone-materials")
        await phone.get_by_role("button", name="Labour", exact=True).click()
        await shot(phone, "11-phone-labour")
        await phone.get_by_role("button", name="Channels & price lists").click()
        await expect(phone.get_by_text("landed cost").first).to_be_visible()
        await shot(phone, "12-phone-channels")
        await phone.get_by_role("button", name="Costing", exact=True).click()
        await phone.get_by_label("cover to cost").fill(MODEL)
        await expect(phone.get_by_test_id("costing")).to_be_visible()
        await shot(phone, "13-phone-costing")
        wide = await phone.evaluate("document.documentElement.scrollWidth")
        assert wide <= 390, f"the phone page scrolls sideways ({wide} px)"
        await browser.close()
    if errors:
        print("page errors:", errors)
        return 1
    print("prices: ok")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
