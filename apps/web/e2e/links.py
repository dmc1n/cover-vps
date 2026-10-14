"""Browser check of Covers → Links (ADR-132) on a scratch data copy (never the live data).

An admin opens the queue, finds D2 (the product list linked "Evora normal D- Bed" to the Evora
sunlounger: the score is low and the row says why), says "Not a pair", and the Desk card of D2
no longer shows the sunlounger as a linked SUNS model; he confirms D1 with the Portofino daybed
and the cover page shows "Linked to …"; the picker ("Choose another") and the bulk confirmation
step open (and are cancelled); No partner lists the drawings without one. A viewer sees the rows
without actions; the workshop login gets "Not for your account" and a 403 from the API.

Make the scratch copy first (a fresh app.db with test users, the models' small files, the
proposals applied there), start the studio on it, then:

    docker run --rm --network host --user 1000:1000 -e HOME=/tmp \\
      -v "$PWD:/repo:ro" -v "$PWD/out/links:/shots" -e COVER_E2E_URL=http://127.0.0.1:18311 \\
      mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q --user playwright==1.63.0 && python /repo/apps/web/e2e/links.py"

Users rick (admin), vic (viewer) and werkplaats (workshop), password below. Screenshots go to
$COVER_E2E_SHOTS (look at them).
"""

import asyncio
import os
import re
import sys

from playwright.async_api import Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18311")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
SLOW = 30_000
FAILED: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what)
    if not ok:
        FAILED.append(what)


async def login(page: Page, user: str) -> None:
    await page.goto(URL)
    await page.get_by_label("User name").fill(user)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible(timeout=SLOW)


async def shot(page: Page, name: str, full: bool = True) -> None:
    await page.wait_for_timeout(500)
    await page.screenshot(path=f"{SHOTS}/{name}.png", full_page=full)


def row(page: Page, drawing: str, model: str):  # noqa: ANN201 - a locator
    return page.locator(f'article[aria-label="{drawing} and {model}"]')


async def admin(page: Page, theme: str) -> None:
    await login(page, "rick")
    await page.goto(f"{URL}/#/covers/links")
    await expect(page.locator("h1.page-title")).to_have_text("Links", timeout=SLOW)
    await expect(page.get_by_test_id("link-row").first).to_be_visible(timeout=SLOW)
    await shot(page, f"01-queue-{theme}", full=False)
    if theme != "light":
        return
    # D2: the product list's link, scored low, with its reasons
    await page.get_by_label("Search a cover").fill("drawing-d2")
    d2 = row(page, "drawing-d2", "suns-sunlounger-evora")
    await expect(d2).to_be_visible(timeout=SLOW)
    text = await d2.inner_text()
    check("says no" in text and "sizes differ" in text, "D2 ↔ Evora sunlounger says why it doubts")
    await shot(page, "02-d2-worked-example")
    await d2.get_by_role("button", name="Not a pair", exact=True).click()
    await expect(d2).to_have_count(0, timeout=SLOW)
    await page.get_by_role("button", name=re.compile("^Not a pair")).first.click()
    await expect(row(page, "drawing-d2", "suns-sunlounger-evora")).to_be_visible(timeout=SLOW)
    await shot(page, "03-d2-not-a-pair")
    # the Desk card: the sunlounger is no longer a linked SUNS model of D2
    await page.goto(f"{URL}/#/work/desk/drawing-d2")
    panel = page.locator(".dp-panel")
    await expect(panel).to_be_visible(timeout=SLOW)
    ptext = await panel.inner_text()
    check("sunlounger evora" not in ptext.lower(), "D2's Desk card no longer shows the sunlounger")
    await panel.scroll_into_view_if_needed()
    await shot(page, "04-d2-desk-products", full=False)
    # D1 with the Portofino daybed: confirm, then the cover page's chip
    await page.goto(f"{URL}/#/covers/links")
    await page.get_by_label("Search a cover").fill("drawing-d1")
    d1 = row(page, "drawing-d1", "suns-daybed-portofino")
    await expect(d1).to_be_visible(timeout=SLOW)
    await d1.get_by_role("button", name="Confirm", exact=True).click()
    await expect(d1).to_have_count(0, timeout=SLOW)
    await page.goto(f"{URL}/#/model/drawing-d1/3d")
    chip = page.get_by_test_id("link-chip")
    await expect(chip).to_contain_text("Linked to", timeout=SLOW)
    await shot(page, "05-d1-cover-linked-chip", full=False)
    await page.goto(f"{URL}/#/model/suns-daybed-portofino/3d")
    await expect(page.get_by_test_id("link-chip")).to_contain_text("Linked to", timeout=SLOW)
    check(True, "the model's page shows the link too")
    # Choose another: the picker
    await page.goto(f"{URL}/#/covers/links")
    await page.get_by_label("Search a cover").fill("drawing-t1")
    first = page.get_by_test_id("link-row").first
    await expect(first).to_be_visible(timeout=SLOW)
    await first.get_by_role("button", name="Choose another", exact=True).click()
    dlg = first.get_by_role("dialog", name="Choose another")
    await dlg.get_by_label("Search a 3D model").fill("table savona")
    await expect(dlg.locator(".lk-hits button").first).to_be_visible(timeout=SLOW)
    await shot(page, "06-choose-another")
    # bulk: the confirmation step, then cancel
    await page.get_by_label("Search a cover").fill("")
    bulk = page.get_by_role("button", name=re.compile("^Confirm all high"))
    await expect(bulk).to_be_visible(timeout=SLOW)
    await bulk.click()
    await expect(page.get_by_role("button", name="Cancel")).to_be_visible(timeout=SLOW)
    await shot(page, "07-bulk-confirm-step", full=False)
    await page.get_by_role("button", name="Cancel").click()
    # No partner
    await page.get_by_role("button", name=re.compile("^No partner")).click()
    await expect(page.get_by_test_id("nopartner-row").first).to_be_visible(timeout=SLOW)
    await shot(page, "08-no-partner", full=False)
    await page.set_viewport_size({"width": 820, "height": 1180})
    await page.get_by_role("button", name=re.compile("^Proposed")).click()
    await expect(page.get_by_test_id("link-row").first).to_be_visible(timeout=SLOW)
    await shot(page, "09-queue-820", full=False)


async def viewer(page: Page) -> None:
    await login(page, "vic")
    await page.goto(f"{URL}/#/covers/links")
    first = page.get_by_test_id("link-row").first
    await expect(first).to_be_visible(timeout=SLOW)
    decisions = re.compile("^(Confirm|Not a pair|Choose another)$")
    n = await page.get_by_role("button", name=decisions).count()
    check(n == 0, f"a viewer sees no decisions ({n})")
    await shot(page, "10-viewer", full=False)


async def workshop(page: Page) -> None:
    await login(page, "werkplaats")
    await page.goto(f"{URL}/#/covers/links")
    await expect(page.get_by_text("Not for your account")).to_be_visible(timeout=SLOW)
    code = await page.evaluate("async () => (await fetch('/api/links')).status")
    check(code == 403, f"the workshop login gets {code} from /api/links")


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for theme in ("light", "dark"):
            ctx = await browser.new_context(viewport={"width": 1440, "height": 900},
                                            color_scheme=theme)  # fmt: skip
            await admin(await ctx.new_page(), theme)
            await ctx.close()
        for fn in (viewer, workshop):
            ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
            await fn(await ctx.new_page())
            await ctx.close()
        await browser.close()
    print("FAILED:\n  " + "\n  ".join(FAILED) if FAILED else "all checks passed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
