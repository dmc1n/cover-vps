"""Browser check of the prices (ADR-098; laid out by ADR-126): in Settings → Prices & costs an
admin changes a price (Costs: materials, labour and the rate on one page), previews which prices
move, publishes; on a cover's Price & shop tab he sets its fixed B2B price in the draft, sees the
draft's change, previews and publishes it from there, and looks at its costing (CSV, PDF); a page
that loaded an older draft cannot overwrite the newer one; a configurator product's costing on
Price rules; a rollback on Publish & versions; an editor only looks; the pages on a phone.
Every tab explains itself: an intro, a help line per field,
"placeholder — please confirm" marks with a counter, and live examples that follow the numbers
as they are typed (POST /api/prices/check).

Run against a running studio with a scratch data copy (never the live data) on which nothing is
published yet, with an admin `tester` and an editor `eddy` (password browser-test-password) and a
few calculated covers:

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/pricetest2:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:18190 -e COVER_E2E_MODEL=drawing-c1 \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/prices.py"
"""

import asyncio
import os
import re
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
    await expect(page.get_by_role("button", name="Log out")).to_be_visible()


async def shot(page: Page, name: str) -> None:
    await page.wait_for_timeout(400)
    await page.screenshot(path=f"{SHOTS}/{name}.png", full_page=True)


async def settings_tab(page: Page, label: str) -> None:
    await (
        page.get_by_role("navigation", name="Settings")
        .get_by_role("link", name=label, exact=True)
        .click()
    )
    await expect(page.locator("h1.page-title")).to_have_text(label)


async def main() -> int:
    errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1440, "height": 950})
        page.on("pageerror", lambda e: errors.append(str(e)))
        await login(page, "tester")
        await page.goto(URL + "#/prices/materials")  # the old address: Settings → Costs
        await expect(page.locator("h1.page-title")).to_have_text("Costs")
        await expect(page.get_by_text("the documented defaults")).to_be_visible()
        count = page.get_by_test_id("placeholder-count")
        await expect(count).to_contain_text("values are still placeholders")
        first = int((await count.inner_text()).split()[0])
        example = page.get_by_test_id("live-example").first
        await expect(example).to_contain_text("in the cut plan")
        await shot(page, "01-costs")
        # a placeholder kept as it is: the counter goes down
        waste = page.locator(".ph[data-field='fabric:coverlast.waste_pct']")
        await waste.get_by_role("button", name="keep this value").click()
        await expect(waste).to_have_count(0)
        await expect(count).to_contain_text(f"{first - 1} of")
        # a change: the fabric costs more, and in rupiah; the example follows before saving
        price = page.get_by_label("fabric price")
        await price.fill("450000")
        await page.get_by_label("fabric currency").select_option("IDR")
        await expect(page.get_by_text("unsaved changes", exact=True)).to_be_visible()
        await expect(example).to_contain_text("Rp 450,000")
        await expect(count).to_contain_text(f"{first - 2} of")
        await page.get_by_role("button", name="Preview changes").click()
        await expect(page.get_by_text("prices move")).to_be_visible()
        await shot(page, "02-preview")
        # labour and the rate are on the same page
        await page.get_by_label("seam minutes").fill("4")
        labour = page.get_by_test_id("live-example").filter(has_text="takes")
        await expect(labour.first).to_be_visible()
        await expect(
            page.get_by_test_id("live-example").filter(has_text="Rp 450,000/m").first
        ).to_be_visible()
        # moving to Price rules keeps the typed numbers (no question, still unsaved)
        await settings_tab(page, "Price rules")
        await expect(page.get_by_text("unsaved changes", exact=True)).to_be_visible()
        await expect(page.get_by_text("landed cost").first).to_be_visible()
        await page.get_by_text("Terms explained").click()
        await expect(page.get_by_text("markup 87.5 % = margin 46.7 %").first).to_be_visible()
        await expect(page.get_by_text("Fixed prices of other products").first).to_be_visible()
        await shot(page, "03-price-rules")
        await page.get_by_placeholder("What changed (for the history)").fill("fabric in rupiah")
        await page.get_by_role("button", name="Publish").click()
        await expect(page.get_by_text("Published version 1")).to_be_visible()
        # a configurator product's costing stays here
        await page.get_by_label("configurator product", exact=True).select_option("dining_set")
        costing = page.get_by_test_id("costing")
        await expect(costing.get_by_text("Configurator:")).to_be_visible()
        await shot(page, "04-costing-configurator")
        # the cover's own page: its fixed B2B price into the draft, then published from there
        await page.goto(URL + f"#/model/{MODEL}/price")
        prices = page.get_by_test_id("cover-prices")
        await expect(prices.locator("tr[data-channel=b2b]")).to_contain_text("calculated")
        await page.get_by_label("b2b fixed price").fill("999")
        await (
            prices.locator("tr[data-channel=b2b]")
            .get_by_role("button", name="Save in draft")
            .click()
        )
        await expect(page.get_by_text("saved in the draft")).to_be_visible()
        bar = page.get_by_test_id("draft-bar")
        await expect(bar).to_contain_text("1 fixed-price change")
        await expect(prices.locator("tr[data-channel=b2b]")).to_contain_text("€ 999.00")
        await shot(page, "05-cover-draft")
        state = await (await page.request.get(URL + "/api/prices")).json()
        assert state["draft"]["data"]["channels"]["b2b"]["fixed"][MODEL] == 999
        assert MODEL not in state["current"]["channels"]["b2b"]["fixed"], "published by accident"
        # a page that loaded the draft before cannot overwrite it
        other = await browser.new_page(viewport={"width": 1440, "height": 950})
        await login(other, "tester")
        await other.goto(URL + "#/settings/costs")
        await expect(other.get_by_label("fabric price")).to_be_visible()
        await page.get_by_label("b2b fixed price").fill("1001")
        await (
            prices.locator("tr[data-channel=b2b]")
            .get_by_role("button", name="Save in draft")
            .click()
        )
        await expect(page.get_by_text("€ 1,001.00").first).to_be_visible()
        await other.get_by_label("vent_set price").fill("7")
        await other.get_by_role("button", name="Save draft").click()
        await expect(other.get_by_text("Someone changed the draft")).to_be_visible()
        await shot(other, "06-stale-page")
        state = await (await page.request.get(URL + "/api/prices")).json()
        assert state["draft"]["data"]["channels"]["b2b"]["fixed"][MODEL] == 1001
        await other.close()
        # publish from the cover: preview's count first, then a confirmation
        await bar.get_by_role("button", name="Preview").click()
        pub = bar.get_by_role("button", name=re.compile("^Publish"))
        await expect(pub).to_be_visible()
        page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await pub.click()
        await expect(page.get_by_text("Published version 2")).to_be_visible()
        await expect(page.get_by_test_id("draft-bar")).to_have_count(0)
        await expect(prices.locator("tr[data-channel=b2b]")).to_contain_text("fixed price")
        cost = page.get_by_test_id("cover-cost")
        await expect(cost.get_by_text("(fixed price)")).to_be_visible()
        await shot(page, "07-cover-published")
        csv = await page.request.get(URL + f"/api/prices/costing.csv?model={MODEL}")
        assert csv.ok and "cost price" in await csv.text()
        pdf = await page.request.get(URL + f"/api/prices/costing.pdf?model={MODEL}")
        assert pdf.ok and (await pdf.body())[:4] == b"%PDF"
        # a third version, then back to the first
        await page.goto(URL + "#/settings/costs")
        await page.get_by_label("vent_set price").fill("9")
        await page.get_by_role("button", name="Publish").click()
        await expect(page.get_by_text("Published version 3")).to_be_visible()
        await settings_tab(page, "Publish & versions")
        await expect(page.get_by_text("The history of the prices")).to_be_visible()
        page.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await page.get_by_role("button", name="Roll back to this").last.click()
        await expect(page.get_by_role("cell", name="rolled back to version 1")).to_be_visible()
        await shot(page, "08-versions")
        # an editor looks, and cannot change
        editor = await browser.new_page(viewport={"width": 1440, "height": 950})
        editor.on("pageerror", lambda e: errors.append(str(e)))
        await login(editor, "eddy")
        await (
            editor.get_by_role("navigation", name="Sections")
            .get_by_role("link", name="Settings")
            .click()
        )
        await expect(editor.locator("h1.page-title")).to_have_text("Costs")
        await expect(editor.get_by_text("You can look; an admin changes")).to_be_visible()
        await expect(editor.get_by_role("button", name="Publish")).to_have_count(0)
        await expect(editor.get_by_label("fabric price")).to_be_disabled()
        await shot(editor, "09-editor")
        await editor.goto(URL + f"#/model/{MODEL}/price")
        await expect(editor.get_by_test_id("cover-prices")).to_be_visible()
        await expect(editor.get_by_role("button", name="Save in draft")).to_have_count(0)
        await shot(editor, "09b-editor-cover")
        # on a phone
        phone = await browser.new_page(viewport={"width": 390, "height": 844})
        await login(phone, "tester")
        await phone.goto(URL + "#/settings/costs")
        await expect(phone.get_by_test_id("live-example").first).to_contain_text("cut plan")
        await shot(phone, "10-phone-costs")
        await phone.goto(URL + "#/settings/pricing")
        await expect(phone.get_by_text("landed cost").first).to_be_visible()
        await shot(phone, "11-phone-price-rules")
        wide = await phone.evaluate("document.documentElement.scrollWidth")
        assert wide <= 390, f"the phone page scrolls sideways ({wide} px)"
        await phone.goto(URL + f"#/model/{MODEL}/price")
        await expect(phone.get_by_test_id("cover-cost")).to_be_visible()
        await shot(phone, "12-phone-cover-price")
        await browser.close()
    if errors:
        print("page errors:", errors)
        return 1
    print("prices: ok")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
