"""Screenshots of the static UI prototype (out/uiaudit/prototype/, docs/plans/studio-ui.md) at
1440 and 820 px, light and dark, for the before/after comparison. No studio needed:

    docker run --rm -v "$PWD:/repo:ro" -v "$PWD/out/uiaudit/after:/shots" \\
      mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/uiaudit_proto.py"

Page errors fail the run.
"""

import asyncio
import os
import sys

from playwright.async_api import async_playwright

PROTO = os.environ.get("COVER_PROTO", "file:///repo/out/uiaudit/prototype/index.html")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
PAGES = [
    ("work-desk", "#/work/desk/drawing-c27"),
    ("work-desk-correct", "#/work/desk/drawing-c27/correct"),
    ("work-desk-arr", "#/work/desk/arr-portofino-2-c"),
    ("work-questions", "#/work/questions"),
    ("work-workshop", "#/work/workshop"),
    ("covers-table", "#/covers/all"),
    ("covers-cards", "#/covers/all?view=cards"),
    ("covers-new", "#/covers/new"),
    ("model-3d", "#/model/drawing-c1/3d"),
    ("model-pieces", "#/model/drawing-c27/pieces"),
    ("model-adjust", "#/model/drawing-c1/adjust"),
    ("model-history", "#/model/drawing-c1/history"),
    ("shop-orders", "#/shop/orders"),
    ("prices-materials", "#/prices/materials"),
    ("settings-company", "#/settings/company"),
    ("settings-users", "#/settings/users"),
    ("settings-desk", "#/settings/desk"),
    ("settings-defaults", "#/settings/defaults"),
    ("settings-mail", "#/settings/mail"),
    ("old-link-admin", "#/admin"),
    ("old-link-catalogue", "#/catalogue"),
]


async def main() -> None:
    errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for width, height in ((1440, 900), (820, 1180)):
            for scheme in ("light", "dark"):
                ctx = await browser.new_context(
                    viewport={"width": width, "height": height}, color_scheme=scheme
                )
                page = await ctx.new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                os.makedirs(f"{SHOTS}/{width}-{scheme}", exist_ok=True)
                for n, (name, hash_) in enumerate(PAGES, 1):
                    if scheme == "dark" and n > 3:
                        break  # dark: a few pages are enough to check the tokens
                    await page.goto(PROTO + hash_)
                    await page.wait_for_timeout(250)
                    if name == "model-3d":  # the viewer's Show menu open
                        await page.locator(".vbar [data-dd]").first.click()
                    await page.screenshot(
                        path=f"{SHOTS}/{width}-{scheme}/{n:02d}-{name}.png", full_page=True
                    )
                    print(width, scheme, name, page.url.split("#")[-1])
                await ctx.close()
        await browser.close()
    if errors:
        print("page errors:", errors)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
