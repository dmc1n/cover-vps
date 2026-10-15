"""The website for AI agents in a real browser (ADR-139): llms.txt and llms-full.txt are served,
the measuring guide and a cover page carry their schema.org JSON-LD, the API's docs render
under the website's CSP, and an order link opens the configurator at the checkout with nothing
ordered.

Against a local build (site_serve.mjs, which routes these paths as the preview's Worker does)
in front of a scrubbed scratch studio with `agent_api_enabled` on, or against the preview:

    COVER_DATA_DIR=<scratch> uv run uvicorn coverapi.main:default_app --factory --port 18310 &
    node apps/web/e2e/site_serve.mjs --port 18300 --upstream http://127.0.0.1:18310 &
    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/agentapi:/shots" \\
      -e SITE_URL=http://127.0.0.1:18300/ mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/agent_site.py"
"""

import asyncio
import json
import os
import sys

from playwright.async_api import Page, async_playwright

URL = os.environ.get("SITE_URL", "https://preview.s2dio.living/").rstrip("/")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")


async def ld_of(page: Page) -> list[dict]:
    texts = await page.eval_on_selector_all(
        'script[type="application/ld+json"]', "els => els.map(e => e.textContent)"
    )
    out = []
    for t in texts:
        doc = json.loads(t)
        out += doc if isinstance(doc, list) else [doc]
    return out


async def shot(page: Page, name: str) -> None:
    try:
        await page.screenshot(path=f"{SHOTS}/{name}.png", full_page=True, timeout=60000)
    except Exception as e:  # noqa: BLE001 - the picture is a courtesy, the checks are the test
        print(f"  (no picture {name}: {str(e)[:60]})")


async def main() -> int:
    failed: list[str] = []
    console: list[str] = []

    def check(ok: bool, what: str) -> None:
        print(("ok   " if ok else "FAIL ") + what)
        if not ok:
            failed.append(what)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await ctx.new_page()
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))

        r = await page.goto(f"{URL}/llms.txt")
        text = await page.inner_text("body")
        check(r is not None and r.ok, "llms.txt answers")
        check("## For AI agents" in text and "/api/v2/docs" in text, "llms.txt: the agent section")
        check("never orders or pays" in text or "never orders" in text, "llms.txt: humans pay")
        r = await page.goto(f"{URL}/llms-full.txt")
        full = await page.inner_text("body")
        check(r is not None and r.ok and "## How to measure" in full, "llms-full.txt: the guide")
        check("## Existing covers" in full, "llms-full.txt: the covers with their sizes")

        r = await page.goto(f"{URL}/measure/sofa")
        check(r is not None and r.ok, "the measuring guide for a sofa")
        ld = await ld_of(page)
        types = [x.get("@type") for x in ld]
        check("Product" in types and "HowTo" in types, f"guide JSON-LD: {types}")
        prod = next((x for x in ld if x.get("@type") == "Product"), {})
        check(len(prod.get("additionalProperty", [])) >= 3, "guide: sizes as additionalProperty")
        await shot(page, "measure-sofa")

        r = await page.goto(f"{URL}/covers")
        check(r is not None and r.ok, "the covers index")
        ld = await ld_of(page)
        items = ld[0].get("itemListElement", []) if ld else []
        check(bool(items), f"covers index ItemList: {len(items)} covers")
        if items:
            # the page URL is the website's; open it on this server
            code = items[0]["url"].rstrip("/").rsplit("/", 1)[-1]
            r = await page.goto(f"{URL}/covers/{code}")
            ld = await ld_of(page)
            prod = next((x for x in ld if x.get("@type") == "Product"), {})
            offer = prod.get("offers") or {}
            check(prod.get("sku") == code, f"cover page {code}: Product sku")
            check(
                offer.get("priceCurrency") == "EUR" and "." in str(offer.get("price", "")),
                f"cover page: Offer {offer.get('price')} EUR",
            )
            check(
                offer.get("availability") == "https://schema.org/MadeToOrder",
                "cover page: availability",
            )
            await shot(page, "cover-page")

        r = await page.goto(f"{URL}/api/v2/docs")
        body = await page.inner_text("body")
        check(r is not None and r.ok and "/api/v2/match" in body, "the API docs render")
        await shot(page, "api-docs")

        link = await page.evaluate(
            """async () => {
              const r = await fetch('/api/v2/order-link', {method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({kind: 'sofa', width: 230, depth: 90, height: 85})});
              return {status: r.status, body: await r.json()};
            }"""
        )
        check(link["status"] == 200, f"order-link from the page: {link['status']}")
        url = link["body"].get("order_url", "")
        check(link["body"].get("agent_may_pay") is False, "the link says an agent never pays")
        # the link points at the website it was asked on; locally: this server
        local = URL + url[url.index("/api/v2/go/") :]
        go = await page.request.get(local, max_redirects=0)
        where = go.headers.get("location", "")
        check(go.status == 302 and "checkout=1" in where, f"the link redirects: {go.status}")
        # the configurator on the website it names; locally (no Worker host) the studio's /shop/
        path = where[where.index("/", where.index("//") + 2) :].removeprefix("/shop")
        await page.goto(URL + path)
        await page.wait_for_url("**/configure?**", timeout=30000)
        check("checkout=1" in page.url, "the link opens the configurator with checkout=1")
        try:
            await page.locator("form.s-checkout").wait_for(timeout=60000)
            check(True, "the configurator went to the checkout form")
        except Exception:  # noqa: BLE001
            check(False, "the configurator went to the checkout form")
        await shot(page, "order-link-checkout")
        csp = [c for c in console if "Content Security Policy" in c]
        check(not csp, f"no CSP errors ({len(csp)}) {csp[:3]}")
        await browser.close()
    print("FAILED: " + "; ".join(failed) if failed else "all ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
