"""Browser check of the dealer embed (ADR-150): the admin makes a dealer site in Shop → Dealer
embeds and sees the live preview price; the demo page with its two themed dealer sites and the
frame; a dealer's own page on another origin (listed) prices and sends an order through CORS;
a page on an origin that is not listed gets nothing.

Run against a running studio with a scratch data dir (never the live data), built pages
(make web-build), an admin `tester` (password browser-test-password), a B2B company
"Dealer Demo BV" and the shop setting dealer_embed_enabled (e2e/dealer_embed_seed.py does all):

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/embedtest:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:18391 \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/dealer_embed.py"
"""

import asyncio
import os
import re
import sys

from playwright.async_api import Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18391")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
DEALER_ORIGIN = "http://127.0.0.1:18392"  # listed for the dealer site
STRANGER = "http://localhost:18393"  # not listed
AMOUNT = re.compile(r"€\s?[\d.,]+|[\d.,]+\s?€")


async def shot(page: Page, name: str, full: bool = True) -> None:
    await page.wait_for_timeout(600)
    await page.screenshot(path=f"{SHOTS}/{name}.png", full_page=full)


def dealer_page(key: str, extra: str = "") -> str:
    return (
        "<!doctype html><html><head><meta charset=utf-8><title>Dealer</title>"
        f'<script type="module" src="{URL}/embed/v1/configurator.js"></script>'
        "<style>body{font-family:Georgia,serif;background:#fafafa;margin:24px}"
        "s2dio-configurator{--s2dio-primary:#8a2be2}</style></head><body>"
        f'<h1>A dealer\'s own page</h1><s2dio-configurator dealer="{key}" lang="en">'
        f"</s2dio-configurator>{extra}</body></html>"
    )


async def main() -> int:  # noqa: PLR0915 - one story, step by step
    errors: list[str] = []
    async with async_playwright() as p:
        # the dealer's pages are made up by page.route (no address): Chrome would take them for
        # public pages reaching a loopback server; on the real web both are public
        browser = await p.chromium.launch(
            args=["--disable-features=LocalNetworkAccessChecks,BlockInsecurePrivateNetworkRequests"]
        )
        # 1. the admin makes a dealer site and sees the live preview
        admin = await browser.new_page(viewport={"width": 1440, "height": 950})
        admin.on("pageerror", lambda e: errors.append(f"admin: {e}"))
        await admin.goto(URL)
        await admin.get_by_label("User name").fill("tester")
        await admin.get_by_label("Password").fill(PASSWORD)
        await admin.get_by_role("button", name="Log in").click()
        await expect(admin.get_by_role("button", name="Log out")).to_be_visible()
        await admin.goto(URL + "/#/shop/dealers")
        await expect(admin.get_by_role("heading", name="Dealer embeds", level=1)).to_be_visible()
        await admin.get_by_label("Dealer (B2B customer)").select_option(label="Dealer Demo BV")
        await admin.get_by_label("Name of the site").fill("Dealer Demo website")
        await admin.get_by_role("button", name="New dealer site").click()
        await admin.get_by_label("Domains (one per line, https://…)").fill(DEALER_ORIGIN)
        await admin.get_by_label("Buttons").fill("#8a2be2")
        await admin.get_by_role("button", name="Save", exact=True).click()
        await expect(admin.get_by_text("Saved.")).to_be_visible()
        key = (
            await admin.locator("p", has_text="Public key").locator("code").first.inner_text()
        ).strip()
        preview = admin.locator("s2dio-configurator")
        await preview.get_by_role("button", name=re.compile("price", re.I)).first.click()
        await expect(preview.locator(".amount")).to_have_text(AMOUNT, timeout=20000)
        await shot(admin, "01-studio-dealer-embeds")
        # the draft look applies as you type (before saving)
        await admin.get_by_label("Layout").select_option("compact")
        await expect(preview.locator(".root.compact")).to_be_visible()

        # 2. the demo page: two dealer sites, the frame, the events (a colleague's session)
        await admin.goto(URL + "/embed-demo.html")
        cfgs = admin.locator("s2dio-configurator.cfg")
        await expect(cfgs).to_have_count(2)
        first, second = cfgs.nth(0), cfgs.nth(1)
        await expect(
            first.get_by_role("heading", name=re.compile("Hoezen op maat"))
        ).to_be_visible()
        await expect(
            second.get_by_role("heading", name=re.compile("housse parfaite"))
        ).to_be_visible()
        await first.get_by_role("button", name="Bereken de prijs").click()
        await expect(first.locator(".amount")).to_have_text(AMOUNT, timeout=20000)
        await second.get_by_role("button", name="Calculer le prix").click()
        await expect(second.locator(".amount")).to_have_text(AMOUNT, timeout=20000)
        await expect(second.locator(".viewer canvas")).to_be_visible(timeout=20000)
        await expect(admin.locator("#log")).to_contain_text("s2dio:priced")
        await admin.locator("iframe").scroll_into_view_if_needed()  # loading="lazy"
        frame = admin.frame_locator("iframe")
        await expect(
            frame.get_by_role("heading", name=re.compile("made to measure"))
        ).to_be_visible()
        await shot(admin, "02-embed-demo")
        # the demo's dealer mode: the form, then "sent" (nothing is ordered)
        await first.get_by_role("button", name=re.compile("Verstuur naar")).click()
        await first.get_by_label("Naam").fill("Eva Test")
        await first.get_by_label("E-mail").fill("eva@example.com")
        await first.locator("form").get_by_role("button", name=re.compile("Verstuur")).click()
        await expect(first.get_by_text(re.compile("DEMO-")).first).to_be_visible()
        await expect(admin.locator("#log")).to_contain_text("s2dio:order-sent")
        await admin.set_viewport_size({"width": 390, "height": 844})
        await shot(admin, "03-embed-demo-phone")

        # 3. the dealer's own page on its own (listed) origin, without our cookies
        ctx = await browser.new_context(viewport={"width": 1100, "height": 900})
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(f"dealer: {e}"))
        page.on("console", lambda m: print("console:", m.text) if m.type == "error" else None)
        await page.route(
            f"{DEALER_ORIGIN}/**",
            lambda r: r.fulfill(status=200, content_type="text/html", body=dealer_page(key)),
        )
        events: list[str] = []
        await page.expose_function("note", lambda t: events.append(t))
        await page.goto(f"{DEALER_ORIGIN}/covers")
        await page.evaluate(
            "for (const t of ['s2dio:ready','s2dio:priced','s2dio:order-sent'])"
            " document.addEventListener(t, () => window.note(t))"
        )
        cfg = page.locator("s2dio-configurator")
        await cfg.get_by_role("button", name="Calculate the price").click()
        await expect(cfg.locator(".amount")).to_have_text(AMOUNT, timeout=20000)
        await cfg.get_by_role("button", name=re.compile("Send to")).click()
        await cfg.get_by_label("Name").fill("Eva Test")
        await cfg.get_by_label("E-mail").fill("eva@example.com")
        await cfg.locator("form").get_by_role("button", name=re.compile("Send to")).click()
        await expect(cfg.get_by_text(re.compile(r"Reference: D\d+")).first).to_be_visible()
        await shot(page, "04-dealer-own-origin")
        if "s2dio:priced" not in events or "s2dio:order-sent" not in events:
            errors.append(f"events on the dealer's page: {events}")

        # 4. a page on an origin that is not listed gets nothing
        other = await ctx.new_page()
        await other.route(
            f"{STRANGER}/**",
            lambda r: r.fulfill(status=200, content_type="text/html", body=dealer_page(key)),
        )
        await other.goto(f"{STRANGER}/covers")
        await other.wait_for_timeout(2000)
        if await other.locator("s2dio-configurator .amount").count():
            errors.append("an unlisted origin got a price")
        if await other.locator("s2dio-configurator").get_by_role("button").count():
            errors.append("an unlisted origin got the configurator")
        await shot(other, "05-unlisted-origin")
        await browser.close()
    for e in errors:
        print("ERROR", e)
    print("dealer embed e2e:", "FAILED" if errors else "ok")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
