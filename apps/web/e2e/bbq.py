"""Browser check of the configurator's barbecue option (ADR-119): the Garden furniture /
Barbecue choice, each barbecue product with its fields, the 3D preview, the price, the note that
a cover goes on a cold barbecue, and "we already make a cover for your Big Green Egg Large in
nest" (an approved catalogue BBQ cover, matching on auto); on a desktop and on a phone, in Dutch
and German.

Run against a scratch studio (never the live data), e.g. on port 8791:

    COVER_DATA_DIR=out/bbq/e2e-data COVER_LOGIN=off COVER_PORT=8791 uv run cover-web
    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/bbq/browser:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:8791 \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/bbq.py"
"""

import asyncio
import json
import os

from playwright.async_api import Page, async_playwright

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:8791")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
PRODUCTS = {
    "nl": ["Kamado (ei) in onderstel", "Kamado in een tafel", "Gasbarbecue met zijtafels",
           "Pelletbarbecue", "Vuurtafel of plancha"],
    "de": ["Kamado (Ei) im Gestell", "Kamado in einem Tisch", "Gasgrill mit Seitenablagen",
           "Pelletgrill", "Feuertisch oder Plancha"],
}  # fmt: skip
GROUP = {"nl": "Barbecue", "de": "Grill"}
COLD = {"nl": "afgekoelde barbecue", "de": "abgekühlten Grill"}


async def price(page: Page) -> str:
    await page.wait_for_selector(".s-price strong", timeout=30000)
    await page.wait_for_timeout(1500)  # the quote after the last change
    return (await page.inner_text(".s-price strong")).strip()


async def run(page: Page, lang: str, label: str) -> dict[str, object]:
    out: dict[str, object] = {"lang": lang, "view": label}
    path = "shop/configure" if lang == "nl" else f"shop/{lang}/configure"
    await page.goto(f"{URL}/{path}", wait_until="load")
    await page.wait_for_selector(".s-groups", timeout=30000)
    await page.click(f".s-groups button:has-text('{GROUP[lang]}')")
    await page.wait_for_timeout(500)
    cards = [c.strip() for c in await page.locator(".s-products .s-card").all_inner_texts()]
    out["cards"] = cards
    out["cards_ok"] = cards == PRODUCTS[lang]
    out["cold_note"] = COLD[lang] in (await page.inner_text(".s-cold"))
    rows = []
    for i, name in enumerate(PRODUCTS[lang]):
        await page.click(f".s-products .s-card:has-text('{name}')")
        p = await price(page)
        fields = [
            f.strip()
            for f in await page.locator(".s-config-panel .s-range > span").all_inner_texts()
        ]  # noqa: E501
        match = ""
        if await page.locator(".s-match").count():
            match = (await page.inner_text(".s-match")).strip()
        await page.wait_for_timeout(1500)  # the 3D scene
        await page.screenshot(
            path=f"{SHOTS}/{lang}-{label}-{i + 1}.png", full_page=label == "phone"
        )
        rows.append({"product": name, "price": p, "fields": fields, "match": match[:160]})
    out["products"] = rows
    out["scrolls_sideways"] = await page.evaluate(
        "document.documentElement.scrollWidth > window.innerWidth + 1"
    )
    return out


async def main() -> None:
    report = []
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl"])
        for label, vp in (("desktop", {"width": 1366, "height": 900}),
                          ("phone", {"width": 390, "height": 844})):  # fmt: skip
            for lang in ("nl", "de"):
                ctx = await b.new_context(viewport=vp, locale=f"{lang}-{lang.upper()}")
                page = await ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
                r = await run(page, lang, label)
                r["errors"] = errors
                report.append(r)
                await ctx.close()
        await b.close()
    with open(f"{SHOTS}/report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    print(json.dumps(report, indent=1, ensure_ascii=False))


asyncio.run(main())
