"""Browser check of the arrangement -> Desk approval workflow (ADR-115), in Chromium.

1. Vera (an editor) opens a built arrangement that is not at the Desk yet, sends it to the Desk;
   the page says "Waiting for approval", its DXF stays locked.
2. Rens (an approver) filters the Desk on ARR: the arrangements by name, "Ready for approval".
   The card: the plan from above (members and the cover's plan), the members with links to their
   own models, the 3D cover, the pieces, the check list. He approves: the DXF downloads.
3. The Arrangements page says "Approved by Rens"; another cover plan is chosen and the cover is
   built again: back to "Waiting for approval again" (changed after approval), the DXF locked,
   the Desk's history says so.
4. The Desk card on a phone-sized screen.

Run against a running studio with a scratch data copy (never the live data) holding built
arrangements (scripts/desk_arrangements.py --apply --only ... on the copy leaves one unsent) and
the users rens (admin) and vera (editor):

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/arrdesk:/shots" \\
      -e COVER_E2E_URL=http://127.0.0.1:18214 -e COVER_E2E_NEW=arr-arrangement \\
      -e COVER_E2E_ARR=arr-portofino-2-c \\
      mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/arrangements_desk.py"

Screenshots go to $COVER_E2E_SHOTS (default /shots).
"""

import asyncio
import os
from typing import Any

from playwright.async_api import Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18214")
NEW = os.environ.get("COVER_E2E_NEW", "arr-arrangement")  # built, not at the Desk yet
ARR = os.environ.get("COVER_E2E_ARR", "arr-portofino-2-c")  # waiting for approval
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
SLOW = 120_000  # software WebGL, and a cover built in the background


async def login(page: Page, user: str) -> None:
    await page.goto(URL)
    await page.get_by_label("User name").fill(user)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible()


async def shot(page: Page, name: str, full: bool = False) -> None:
    await page.screenshot(path=f"{SHOTS}/{name}.png", full_page=full)
    print("shot", name)


async def dxf(page: Page, model: str) -> int:
    r = await page.request.get(f"{URL}/api/models/{model}/files/cut.dxf")
    return r.status


async def main() -> None:
    os.makedirs(SHOTS, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        errors: list[str] = []

        async def as_user(user: str) -> tuple[Any, Page]:
            ctx = await browser.new_context(viewport={"width": 1440, "height": 1000})
            page = await ctx.new_page()
            page.on("pageerror", lambda e: errors.append(str(e)))
            await login(page, user)
            return ctx, page

        # 1. the maker sends it
        _, page = await as_user("vera")
        await page.goto(f"{URL}/#/arrangements/{NEW}")
        status = page.get_by_test_id("arr-desk-status")
        await expect(status).to_contain_text("Not at the Desk yet", timeout=SLOW)
        await expect(page.locator(".arrange-plans button")).to_have_count(3, timeout=SLOW)
        await expect(page.locator(".arrange-plan polygon").first).to_be_visible(timeout=SLOW)
        await shot(page, "01-arrangement-not-sent", full=True)
        assert await dxf(page, NEW) == 403
        await status.get_by_role("button", name="Send to the Desk").click()
        await expect(status).to_contain_text("Waiting for approval at the Desk")
        await expect(status).to_contain_text("sent by Vera")
        await expect(status.get_by_role("link", name="Open its Desk card ↗")).to_be_visible()
        pill = page.locator(".arrange-pill").first
        await expect(pill).to_have_text("waiting for approval")
        await shot(page, "02-arrangement-sent", full=True)
        assert await dxf(page, NEW) == 403

        # 2. the approver at the Desk
        ctx, page = await as_user("rens")
        await page.goto(f"{URL}/#/desk")
        await page.locator(".d-chips button", has_text="ARR").click()
        await page.locator(".d-seg-ctl button", has_text="All").click()
        rows = page.locator(".d-list li")
        await expect(rows).to_have_count(3)
        await expect(rows.first).to_contain_text("Ready for approval")
        await expect(page.locator(".d-list")).to_contain_text("portofino 2 + c")
        await page.goto(f"{URL}/#/desk/{ARR}")
        card = page.locator(".d-card")
        await expect(card.get_by_test_id("arr-status")).to_contain_text("Waiting for approval")
        await expect(card.locator("svg.arr-plan polygon")).to_have_count(3)  # 2 members + plan
        members = card.get_by_test_id("arr-members").locator("li")
        await expect(members).to_have_count(2)
        await expect(members.first.locator("a").first).to_have_attribute(
            "href", "#/model/suns-2-seater-portofino"
        )
        await expect(card.locator(".viewer canvas[data-loaded]")).to_be_visible(timeout=SLOW)
        await expect(card.get_by_role("link", name="Check list (PDF)").first).to_be_visible()
        await expect(card.get_by_role("heading", name="Pieces", exact=True)).to_be_visible()
        await page.wait_for_timeout(2500)
        await shot(page, "03-desk-arr-list-and-card")
        await shot(page, "04-desk-arr-card-full", full=True)
        assert await dxf(page, ARR) == 403
        await card.get_by_role("button", name="✓ Approve").click()
        # an approval moves on to the next card; back to this one
        await expect(page).not_to_have_url(f"{URL}/#/desk/{ARR}", timeout=SLOW)
        await page.goto(f"{URL}/#/desk/{ARR}")
        await expect(card.get_by_test_id("arr-status")).to_contain_text(
            "Approved by Rens", timeout=SLOW
        )
        assert await dxf(page, ARR) == 200

        # 3. changed after approval: back to waiting
        await page.goto(f"{URL}/#/arrangements/{ARR}")
        status = page.get_by_test_id("arr-desk-status")
        await expect(status).to_contain_text("Approved by Rens", timeout=SLOW)
        await shot(page, "05-arrangement-approved", full=True)
        plans = page.locator(".arrange-plans button")
        await expect(plans).to_have_count(3, timeout=SLOW)
        await plans.filter(has_text="One rectangle").click()
        await expect(status).to_contain_text("Waiting for approval at the Desk again", timeout=SLOW)
        await expect(status).to_contain_text("changed after approval")
        assert await dxf(page, ARR) == 403
        await expect(page.get_by_text("The cover is ready.")).to_be_visible(timeout=600_000)
        await shot(page, "06-arrangement-changed-after-approval", full=True)
        await page.goto(f"{URL}/#/desk/{ARR}")
        card = page.locator(".d-card")
        await expect(card.get_by_test_id("arr-status")).to_contain_text(
            "Waiting for approval again"
        )
        await expect(card.locator(".d-timeline")).to_contain_text("changed after approval")
        await expect(card.locator(".d-arr-legend")).to_contain_text("One rectangle")
        await page.wait_for_timeout(2500)
        await shot(page, "07-desk-card-reopened", full=True)

        # 4. a phone
        phone = await browser.new_context(
            viewport={"width": 390, "height": 844}, storage_state=await ctx.storage_state()
        )
        pp = await phone.new_page()
        await pp.goto(f"{URL}/#/desk/{ARR}")
        await expect(pp.get_by_test_id("arr-members")).to_be_visible(timeout=SLOW)
        await pp.wait_for_timeout(2000)
        await pp.screenshot(path=f"{SHOTS}/08-desk-card-phone.png", full_page=True)
        width = await pp.evaluate("document.documentElement.scrollWidth")
        assert width <= 392, f"the page scrolls sideways on a phone: {width}px"
        assert not errors, errors
        await browser.close()
    print("arrangements at the Desk: all steps passed")


if __name__ == "__main__":
    asyncio.run(main())
