"""Browser check of an existing cover ordered directly (ADR-118): the configurator with a dining
set of 240 x 100, the match card's "pick this cover", then the existing-cover state (its own
name and sizes, its price, the delivery promise, "Bestel direct"), the checkout and the thanks,
at 1440 and 390 px. Also: the custom price is never shown while the existing cover is chosen.

Run against a scratch studio (never the live data), e.g. `COVER_DATA_DIR=<scratch> COVER_PORT=8391
uv run cover-web` with the shop link open and `stock_delivery_note` set:

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/stockorder:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:8391/shop \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/stock_order.py"
"""

import asyncio
import json
import os
import urllib.parse

from playwright.async_api import async_playwright

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:8391/shop")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
SIZES = {"table_length_cm": 240, "table_width_cm": 100, "table_height_cm": 75, "chairs": True}


async def run(width: int, height: int, name: str) -> dict[str, object]:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={"width": width, "height": height}, locale="nl-NL")
        q = urllib.parse.urlencode({"product": "dining_set", "sizes": json.dumps(SIZES)})
        await page.goto(f"{URL}/configure?{q}", wait_until="load")
        await page.wait_for_selector(".s-price strong", timeout=60000)
        custom = await page.inner_text(".s-price strong")
        pick = page.locator(".s-match .s-btn")
        await pick.wait_for(timeout=60000)
        await pick.click()
        # the custom price disappears at once; the existing cover's comes with its own quote
        assert await page.locator(".s-config-panel .s-price").count() == 0
        await page.wait_for_selector(".s-stock-order", timeout=60000)
        box = page.locator(".s-stock")
        out: dict[str, object] = {
            "width": width,
            "custom_price": custom,
            "name": await page.inner_text(".s-stock-name"),
            "size": await page.inner_text(".s-stock-size"),
            "price": await page.inner_text(".s-stock-price strong"),
            "delivery": await page.inner_text(".s-stock-delivery"),
            "button": await page.inner_text(".s-stock-order"),
            "vents_hidden": await page.get_by_text("Ventilatie").count() == 0,
            "scroll_x": await page.evaluate(
                "document.documentElement.scrollWidth > window.innerWidth"
            ),
        }
        await box.scroll_into_view_if_needed()
        await page.wait_for_timeout(600)
        await page.screenshot(path=f"{SHOTS}/stock-{name}.png")
        await box.screenshot(path=f"{SHOTS}/stock-{name}-card.png")
        await page.click(".s-stock-order")
        await page.wait_for_selector(".s-checkout .s-stock-line")
        out["checkout"] = await page.inner_text(".s-checkout .s-stock-line")
        for k, v in {"name": "Test Klant", "email": "test@example.com",
                     "street": "Dorpsstraat 1", "postcode": "1234 AB",
                     "city": "Utrecht"}.items():  # fmt: skip
            await (
                page.locator(".s-checkout input:not([type=checkbox])")
                .nth(["name", "email", "phone", "street", "postcode", "city"].index(k))
                .fill(v)
            )
        await page.locator(".s-checkout input[type=checkbox]").first.check()
        await page.screenshot(path=f"{SHOTS}/stock-{name}-checkout.png", full_page=True)
        await page.click(".s-checkout button.s-btn.wide")
        await page.wait_for_selector(".s-done", timeout=30000)
        out["thanks"] = await page.inner_text(".s-done")
        await page.screenshot(path=f"{SHOTS}/stock-{name}-thanks.png")
        await browser.close()
        return out


async def main() -> None:
    for w, h, n in ((1440, 900, "1440"), (390, 844, "390")):
        r = await run(w, h, n)
        print(json.dumps(r, ensure_ascii=False, indent=1))
        assert r["price"] != r["custom_price"], "the existing cover shows the custom price"
        assert "Bestel direct" in str(r["button"]) and r["delivery"]
        assert not r["scroll_x"]


asyncio.run(main())
