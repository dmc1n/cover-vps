"""Browser check of the B2B shop (ADR-104): an admin invites a company and gives it a fixed price;
its buyer sets a password from the invitation link, orders catalogue covers and a made-to-measure
cover with quantities, a PO number and a delivery address, on account; sees the order under
"previous orders" and orders it again; a wrong password; a request for an account that the
admin approves; the B2B lines under Admin → Orders; the shop on a phone and in German.

Run against a running studio with a scratch data copy (never the live data), built pages
(make web-build), an admin `tester` (password browser-test-password) and a few catalogue covers:

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/b2btest:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:18377 \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/b2b.py"
"""

import asyncio
import os
import re
import sys

from playwright.async_api import Browser, Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18377")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
DEALER = "inkoop@delinde.example"
DEALER_PASSWORD = "Tuin-centrum-2026!"
FIXED = "suns-2-seater-kota"


async def shot(page: Page, name: str, full: bool = True) -> None:
    await page.wait_for_timeout(500)
    await page.screenshot(path=f"{SHOTS}/{name}.png", full_page=full)


async def admin_page(browser: Browser, errors: list[str]) -> Page:
    page = await browser.new_page(viewport={"width": 1440, "height": 950})
    page.on("pageerror", lambda e: errors.append(f"admin: {e}"))
    await page.goto(URL)
    await page.get_by_label("User name").fill("tester")
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("link", name="Models")).to_be_visible()
    await page.goto(URL + "/#/admin")
    await page.get_by_role("button", name="B2B customers").click()
    await expect(page.get_by_role("heading", name="B2B customers")).to_be_visible()
    return page


async def main() -> int:  # noqa: PLR0915 - one story, step by step
    errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        # 1. the admin invites a company (no mail server here: the link is shown)
        admin = await admin_page(browser, errors)
        await shot(admin, "01-admin-b2b-empty")
        form = admin.locator("form", has=admin.get_by_role("button", name="Invite", exact=True))
        for label, value in (
            ("Company", "Tuincentrum De Linde"),
            ("VAT number", "NL001234567B01"),
            ("Contact person", "Joke de Vries"),
            ("E-mail (logs in)", DEALER),
            ("Street (invoice address)", "Lindelaan 4"),
            ("Postcode", "3511 AA"),
            ("City", "Utrecht"),
        ):
            await form.get_by_label(label, exact=True).fill(value)
        await form.get_by_label("Language of the mails").select_option("en")
        await form.get_by_role("button", name="Invite", exact=True).click()
        link_el = admin.locator("code", has_text="/b2b/welcome/")
        await expect(link_el).to_be_visible()
        link = (await link_el.inner_text()).strip()
        # a fixed price for this company on one catalogue cover
        await admin.get_by_role("cell", name=re.compile("Tuincentrum De Linde")).click()
        card = admin.locator("section.card", has=admin.get_by_role("button", name="Block"))
        await card.get_by_label(re.compile("Fixed prices for this company")).fill(f"{FIXED} = 289")
        await card.get_by_role("button", name="Save").click()
        await expect(admin.get_by_text("+ 1 fixed")).to_be_visible()
        await shot(admin, "02-admin-company")

        # 2. the buyer sets a password from the link
        ctx = await browser.new_context(viewport={"width": 1440, "height": 950}, locale="en-GB")
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"dealer: {e}"))
        # a 401 is expected twice: "who am I" before logging in, and the wrong password
        page.on("console", lambda m: m.type == "error" and "401" not in m.text
                and errors.append(f"console: {m.text}"))  # fmt: skip
        await page.goto(link)
        await expect(page.get_by_role("heading", name="Choose your password")).to_be_visible()
        await expect(page.get_by_text("Tuincentrum De Linde")).to_be_visible()
        await page.get_by_label("Password").fill(DEALER_PASSWORD)
        await shot(page, "03-set-password")
        await page.get_by_role("button", name="Save and log in").click()
        await expect(page.get_by_role("heading", name="Catalogue")).to_be_visible()
        await expect(page.locator(".b-item").first).to_be_visible()
        await shot(page, "04-catalogue")

        # 3. the catalogue: the company's fixed price, and a list price; quantities
        kota = page.locator(".b-item", has_text="289")
        await expect(kota).to_have_count(1)
        await kota.locator(".b-item-head").click()
        box = kota.locator(".b-pricebox")
        await expect(box).to_contain_text("Your fixed price", timeout=30000)
        await expect(box).to_contain_text("289")
        await box.get_by_label("Quantity").fill("4")
        await box.get_by_role("button", name="Add to the order list").click()
        await expect(box.get_by_text("Added to the order list")).to_be_visible()
        await shot(page, "05-catalogue-fixed-price")
        aspen = page.locator(".b-item", has_text="Aspen").first
        await aspen.locator(".b-item-head").click()
        abox = aspen.locator(".b-pricebox")
        await expect(abox).to_contain_text("ex VAT", timeout=30000)
        await abox.get_by_label("Quantity").fill("2")
        await abox.get_by_role("button", name="Add to the order list").click()
        await expect(page.get_by_role("button", name="Order list (6)")).to_be_visible()

        # 4. made to measure: the configurator with the 3D view and the rain check
        await page.get_by_role("button", name="Made to measure").click()
        cbox = page.locator(".b-pricebox")
        await expect(cbox).to_contain_text("ex VAT", timeout=90000)
        await page.wait_for_timeout(2500)  # the 3D scene
        await shot(page, "06-configure", full=False)
        await cbox.get_by_role("button", name="Add to the order list").click()
        await expect(page.get_by_role("button", name="Order list (7)")).to_be_visible()

        # 5. a delivery address of their own
        await page.get_by_role("button", name="Delivery addresses").click()
        for label, value in (
            ("Name of the address (e.g. the Utrecht store)", "Store Amersfoort"),
            ("Name", "De Linde Amersfoort"),
            ("Street and number", "Markt 1"),
            ("Postcode", "3811 AA"),
            ("City", "Amersfoort"),
        ):
            await page.get_by_label(label, exact=True).fill(value)
        await page.get_by_role("button", name="Save").click()
        await expect(page.locator(".b-box", has_text="Store Amersfoort")).to_be_visible()
        await shot(page, "07-addresses")

        # 6. the order list: PO number, delivery address, on account
        await page.get_by_role("button", name=re.compile("^Order list")).click()
        await expect(page.locator(".b-table tbody tr")).to_have_count(3)
        await page.get_by_label("Your order reference (PO number)").fill("PO-2026-118")
        await page.get_by_label("Deliver to").select_option(
            label="Store Amersfoort: Markt 1, Amersfoort NL"
        )
        await expect(page.get_by_text("On account: you receive an invoice")).to_be_visible()
        await shot(page, "08-cart")
        await page.get_by_role("button", name="Place the order").click()
        await expect(page.get_by_text("your order 1 has been received")).to_be_visible()
        await shot(page, "09-ordered")

        # 7. previous orders, and order again at today's prices
        await page.get_by_role("button", name="Previous orders").click()
        await expect(page.locator(".b-order")).to_contain_text("PO-2026-118")
        await shot(page, "10-previous-orders")
        await page.get_by_role("button", name="Order again").click()
        await expect(page.locator(".b-table tbody tr")).to_have_count(3)
        await shot(page, "11-order-again")

        # 8. log out; a wrong password; log in again
        await page.get_by_role("button", name="Account").click()
        await page.get_by_role("button", name="Log out").click()
        await expect(
            page.get_by_role("heading", name="Log in for business customers")
        ).to_be_visible()
        await page.get_by_label("E-mail").fill(DEALER)
        await page.get_by_label("Password").fill("not-the-password")
        await page.get_by_role("button", name="Log in").click()
        await expect(page.get_by_text("wrong e-mail address or password")).to_be_visible()
        await shot(page, "12-wrong-password")
        await page.get_by_label("Password").fill(DEALER_PASSWORD)
        await page.get_by_role("button", name="Log in").click()
        await expect(page.get_by_role("heading", name="Catalogue")).to_be_visible()

        # 9. on a phone
        phone = await ctx.new_page()
        await phone.set_viewport_size({"width": 390, "height": 844})
        await phone.goto(URL + "/shop/b2b/#cart")
        await expect(phone.locator(".b-table")).to_be_visible()
        await shot(phone, "13-phone-cart")
        await phone.get_by_role("button", name="Catalogue").click()
        await expect(phone.locator(".b-item").first).to_be_visible()
        await shot(phone, "14-phone-catalogue", full=False)

        # 10. in German
        de = await browser.new_context(viewport={"width": 1280, "height": 900}, locale="de-DE")
        dpage = await de.new_page()
        await dpage.goto(URL + "/shop/b2b/")
        await expect(
            dpage.get_by_role("heading", name="Anmelden für Geschäftskunden")
        ).to_be_visible()
        await shot(dpage, "15-login-de")

        # 11. a request for an account (in Dutch), then the admin approves it
        nl = await browser.new_context(viewport={"width": 1280, "height": 900}, locale="nl-NL")
        npage = await nl.new_page()
        await npage.goto(URL + "/shop/b2b/request")
        await expect(npage.get_by_role("heading", name="Account aanvragen")).to_be_visible()
        for label, value in (
            ("Bedrijf", "Buitenleven BV"),
            ("Btw-nummer", "BE0123456789"),
            ("Contactpersoon", "Pieter Janssens"),
            ("E-mail", "pieter@buitenleven.example"),
            ("Plaats", "Gent"),
        ):
            await npage.get_by_label(label, exact=True).fill(value)
        await npage.get_by_label("Land", exact=True).fill("BE")
        await npage.get_by_label("Bericht (optioneel)").fill("Drie winkels in Vlaanderen.")
        await shot(npage, "16-request-nl")
        await npage.get_by_role("button", name="Versturen").click()
        await expect(npage.get_by_text("Bedankt!")).to_be_visible()

        await admin.reload()
        await admin.get_by_role("button", name="B2B customers").click()
        await expect(admin.get_by_role("heading", name="Requests (1)")).to_be_visible()
        await shot(admin, "17-admin-request")
        await admin.get_by_role("button", name="Approve and invite").click()
        await expect(admin.locator("code", has_text="/b2b/welcome/")).to_be_visible()
        await admin.get_by_role("cell", name=re.compile("Tuincentrum De Linde")).click()
        await expect(admin.get_by_text("PO PO-2026-118")).to_be_visible()
        await shot(admin, "18-admin-companies-and-orders")
        await admin.get_by_role("button", name="Orders", exact=True).click()
        await expect(admin.get_by_text("B2B 1 · PO PO-2026-118").first).to_be_visible()
        await shot(admin, "19-admin-orders-flagged")
        await browser.close()
    if errors:
        print("\n".join(errors))
        return 1
    print("b2b browser check: all steps passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
