"""Browser check of the studio's map (ADR-122, docs/plans/studio-ui.md): every section and every
page of its sub-menu opens for the roles that may see it, every old address (#/desk, #/admin,
#/catalogue, …) lands on its new page, a cover's tab and a Desk card's tab are in the address
(and another cover opens on its own tab, not the one before), each person starts on their own
page, the header stays on one line, and pages a role may not see say so.

Screenshots of every page at 1440 and 820 px go to $COVER_E2E_SHOTS/<width>/ (look at them).
Nothing is saved, approved, sent or run: the script only opens pages and tabs.

Run against a running studio with a scratch data copy (never the live data) and the users rick
(admin, approves), rens (editor, approves), eddy (editor) and vic (viewer), password below:

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/uinew:/shots" \\
      -e COVER_E2E_URL=http://127.0.0.1:18250 \\
      mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/uinav.py"

COVER_E2E_MODEL (a drawing cover), COVER_E2E_MODEL2 (another cover) and COVER_E2E_ARR (an
arrangement) choose the examples; COVER_E2E_SIZES the widths (default 1440x900,820x1180).
"""

import asyncio
import os
import re
import sys
from typing import Any

from playwright.async_api import Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18250")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
MODEL = os.environ.get("COVER_E2E_MODEL", "drawing-s45")
MODEL2 = os.environ.get("COVER_E2E_MODEL2", "suns-2-seater-kota")
ARR = os.environ.get("COVER_E2E_ARR", "arr-portofino-2-c")
SIZES = os.environ.get("COVER_E2E_SIZES", "1440x900,820x1180")
WIDTHS = [(int(w), int(h)) for w, h in (x.split("x") for x in SIZES.split(","))]
SLOW = 30_000

# section → its sub-menu, as each role sees it (nav.ts)
MENU = {
    "rick": {
        "Work": ["Desk", "Questions"],
        "Covers": ["All covers", "Arrangements", "New cover", "Learning", "Product list"],
        "Shop": ["Orders", "Requests", "Matches", "B2B customers", "Website (AI)", "Photo test"],
        "Prices": ["Materials", "Labour", "Exchange rate", "Channels & price lists",
                   "Import (Excel)", "Costing", "Versions"],
        "Settings": [],
    },
    "eddy": {
        "Work": ["Desk", "Questions"],
        "Covers": ["All covers", "Arrangements", "New cover", "Learning", "Product list"],
        "Shop": ["Website (AI)"],
        "Prices": ["Materials", "Labour", "Exchange rate", "Channels & price lists", "Costing",
                   "Versions"],
    },
    "vic": {
        "Work": ["Desk", "Questions"],
        "Covers": ["All covers", "Arrangements", "Learning"],
    },
}  # fmt: skip
START = {
    "rick": "#/work/desk",
    "rens": "#/work/desk",
    "eddy": "#/covers/all",
    "vic": "#/covers/all",
}
SETTINGS = ["Company & shop", "B2B terms", "Matching", "Users & rights", "Desk & approval",
            "Cover defaults", "Mail & notifications", "Website & API keys", "AI & spending",
            "System", "Logins & audit log"]  # fmt: skip
# every old address and where it must land (an admin)
OLD = [
    ("#/", "#/work/desk"),
    ("#/desk", "#/work/desk"),
    (f"#/desk/{MODEL}", f"#/work/desk/{MODEL}"),
    ("#/questions", "#/work/questions"),
    ("#/questions/71", "#/work/questions/71"),
    ("#/catalogue", "#/covers/all?view=cards"),
    ("#/arrangements", "#/covers/arrangements"),
    (f"#/arrangements/{ARR}", f"#/covers/arrangements/{ARR}"),
    ("#/learning", "#/covers/learning"),
    ("#/prices", "#/prices/materials"),
    ("#/website", "#/shop/website"),
    ("#/admin", "#/settings/users"),
    ("#/admin/orders", "#/shop/orders"),
    ("#/admin/b2b", "#/shop/b2b"),
    ("#/admin/shop", "#/settings/company"),
    ("#/admin/webshop", "#/shop/requests"),
    ("#/admin/mail", "#/settings/mail"),
    ("#/admin/system", "#/settings/system"),
    ("#/admin/prices", "#/prices/materials"),
    (f"#/model/{MODEL}", f"#/model/{MODEL}/3d"),
    (f"#/model/{MODEL}/downloads", f"#/model/{MODEL}/files"),
    (f"#/model/{MODEL}/settings", f"#/model/{MODEL}/adjust"),
    ("#/work", "#/work/desk"),
    ("#/covers", "#/covers/all"),
    ("#/shop", "#/shop/orders"),
    ("#/settings", "#/settings/company"),
    ("#/shop/nothing", "#/shop/orders"),
]
COUNTS_JS = """() => ({ buttons: document.querySelectorAll('main button').length,
  height: document.documentElement.scrollHeight })"""
problems: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what, flush=True)
    if not ok:
        problems.append(what)


async def login(page: Page, user: str) -> None:
    await page.goto(f"{URL}/#/")
    await page.get_by_label("User name").fill(user)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible(timeout=SLOW)


async def hash_of(page: Page) -> str:
    return str(await page.evaluate("location.hash"))


async def landed(page: Page, want: str) -> bool:
    try:
        await page.wait_for_function(f"location.hash === {want!r}", timeout=SLOW)
        return True
    except Exception:  # noqa: BLE001 - reported below with the address it reached
        return False


async def shot(page: Page, width: int, name: str) -> None:
    os.makedirs(f"{SHOTS}/{width}", exist_ok=True)
    await page.wait_for_timeout(600)
    try:
        await page.screenshot(path=f"{SHOTS}/{width}/{name}.png", full_page=True, timeout=120_000)
    except Exception:  # noqa: BLE001 - a long page with software WebGL: the screen only
        await page.screenshot(path=f"{SHOTS}/{width}/{name}.png", timeout=120_000)


async def header_one_line(page: Page, where: str) -> None:
    h = await page.locator("header.hdr").evaluate("e => e.getBoundingClientRect().height")
    check(h <= 56, f"{where}: the header is on one line ({h:.0f} px)")


async def walk_menu(page: Page, user: str, width: int, n: list[int]) -> None:
    sections = page.get_by_role("navigation", name="Sections")
    seen = [t.strip() for t in await sections.locator("a").all_inner_texts()]
    seen = [re.sub(r"\d+$", "", s).strip() for s in seen]
    want = list(MENU[user])
    check(seen == want, f"{user} {width}: sections {seen} == {want}")
    for sec, pages in MENU[user].items():
        await sections.get_by_role("link", name=re.compile(f"^{re.escape(sec)}")).click()
        await page.wait_for_timeout(300)
        if not pages:
            continue
        sub = page.get_by_role("navigation", name=sec)
        got = [re.sub(r"\d+$", "", t).strip() for t in await sub.locator("a").all_inner_texts()]
        check(got == pages, f"{user} {width}: {sec} menu {got} == {pages}")
        for label in pages:
            await sub.get_by_role("link", name=re.compile(f"^{re.escape(label)}")).click()
            await page.wait_for_load_state("networkidle")
            cur = sub.locator("a[aria-current=page]")
            check(
                await cur.count() == 1 and label in (await cur.inner_text()),
                f"{user} {width}: {sec} → {label} is the current page ({await hash_of(page)})",
            )
            check(
                await page.get_by_text("Not for your account").count() == 0,
                f"{user} {width}: {sec} → {label} opens",
            )
            if user == "rick":
                n[0] += 1
                await shot(
                    page, width, f"{n[0]:02d}-{sec}-{label}".replace(" ", "_").replace("/", "_")
                )
            if label in ("Desk", "All covers"):
                await header_one_line(page, f"{user} {width} {sec}/{label}")


async def as_rick(page: Page, width: int) -> None:
    n = [0]
    await login(page, "rick")
    check(await landed(page, START["rick"]), f"rick {width}: starts on {START['rick']}")
    await walk_menu(page, "rick", width, n)
    # Settings: every tab
    await page.goto(f"{URL}/#/settings/company")
    tabs = page.get_by_role("navigation", name="Settings")
    got = [t.strip() for t in await tabs.locator("a").all_inner_texts()]
    check(got == SETTINGS, f"rick {width}: Settings tabs {got}")
    for label in SETTINGS:
        await tabs.get_by_role("link", name=label, exact=True).click()
        await page.wait_for_load_state("networkidle")
        await expect(page.locator("h1.page-title")).to_have_text(label)
        n[0] += 1
        await shot(page, width, f"{n[0]:02d}-Settings-{label}".replace(" ", "_").replace("/", "_"))
    # the shop settings in plain words: no raw "0 / 1 / 2" list and every row explained
    await page.goto(f"{URL}/#/settings/company")
    await expect(page.locator(".set-name", has_text="Trade name")).to_be_visible(timeout=SLOW)
    check(
        await page.locator(".set-row").count() >= 25, f"rick {width}: Company & shop has its rows"
    )
    await page.goto(f"{URL}/#/settings/matching")
    await expect(page.get_by_text("Offer the existing cover from")).to_be_visible(timeout=SLOW)
    check(
        await page.get_by_text(re.compile("uses the company default: 90")).count() >= 1,
        f"rick {width}: Matching shows the threshold that applies (90)",
    )
    # every old address
    # an admin's start page is his last section page (remembered); a fresh browser: the Desk
    await page.goto(f"{URL}/#/shop/orders")
    await page.goto(f"{URL}/#/")
    check(await landed(page, "#/shop/orders"), f"rick {width}: #/ is the page he was on last")
    await page.evaluate("localStorage.removeItem('studio.last')")
    for old, new in OLD:
        await page.goto(f"{URL}/{old}")
        ok = await landed(page, new)
        check(ok, f"rick {width}: {old} → {new} (got {await hash_of(page)})")
    # a cover: seven tabs in the address; another cover opens on its own tab
    await page.goto(f"{URL}/#/model/{MODEL}/files")
    tabs = page.get_by_role("navigation", name="Cover")
    await expect(tabs.locator("a[aria-current=page]")).to_have_text("Files", timeout=SLOW)
    got = [re.sub(r"\d+$", "", t).strip() for t in await tabs.locator("a").all_inner_texts()]
    check(got == ["3D", "Pieces", "Seams", "Adjust", "Compare", "History", "Files"],
          f"rick {width}: a cover's tabs {got}")  # fmt: skip
    await page.goto(f"{URL}/#/model/{MODEL2}")
    check(await landed(page, f"#/model/{MODEL2}/3d"), f"rick {width}: another cover opens on 3D")
    await expect(tabs.locator("a[aria-current=page]")).to_have_text("3D", timeout=SLOW)
    for t, sub in [("3d", ""), ("pieces", "cut"), ("pieces", "flat"), ("pieces", "sizes"),
                   ("seams", ""), ("adjust", ""), ("compare", "drawing"),
                   ("compare", "reference"), ("compare", "ai"), ("history", "changes"),
                   ("history", "revisions"), ("history", "log"), ("files", "")]:  # fmt: skip
        await page.goto(f"{URL}/#/model/{MODEL2}/{t}{'/' + sub if sub else ''}")
        await page.wait_for_load_state("networkidle")
        n[0] += 1
        await shot(page, width, f"{n[0]:02d}-cover-{t}{'-' + sub if sub else ''}")
    # the 3D toolbar: Show, the view switch, Measure, Simulate, Check list
    await page.goto(f"{URL}/#/model/{MODEL2}/3d")
    bar = page.get_by_role("toolbar", name="3D view")
    await expect(bar).to_be_visible(timeout=SLOW)
    vis = await bar.evaluate(
        "b => [...b.querySelectorAll('button, summary, a, input')].filter(e => e.checkVisibility())"
        ".length"
    )
    check(vis <= 12, f"rick {width}: the 3D toolbar shows {vis} controls (was up to 15)")
    await bar.get_by_label("Show", exact=True).click()
    for name in ["Furniture", "Panels", "Overall dimensions"]:
        await expect(bar.get_by_label(name)).to_be_visible()
    n[0] += 1
    await shot(page, width, f"{n[0]:02d}-cover-3d-show-menu")
    await page.keyboard.press("Escape")
    if await bar.get_by_text("Simulate ▾").count():
        await bar.get_by_text("Simulate ▾").click()
        await expect(bar.get_by_role("button", name=re.compile("Rain|Drape"))).not_to_have_count(0)
        await page.keyboard.press("Escape")
    # a Desk card: four tabs in the address
    for t in ["check", "pieces", "correct", "history"]:
        await page.goto(f"{URL}/#/work/desk/{MODEL}{'' if t == 'check' else '/' + t}")
        card = page.locator(".d-card")
        await expect(card.get_by_role("navigation", name="Card")).to_be_visible(timeout=SLOW)
        cur = card.get_by_role("navigation", name="Card").locator("a[aria-current=page]")
        check(await cur.count() == 1, f"rick {width}: Desk card tab {t} is current")
        n[0] += 1
        await shot(page, width, f"{n[0]:02d}-desk-card-{t}")
    await page.goto(f"{URL}/#/work/desk/{ARR}")
    await expect(page.locator(".d-card")).to_be_visible(timeout=SLOW)
    n[0] += 1
    await shot(page, width, f"{n[0]:02d}-desk-card-arrangement")


async def as_other(page: Page, user: str, width: int) -> None:
    await login(page, user)
    check(await landed(page, START[user]), f"{user} {width}: starts on {START[user]}")
    if user in MENU:
        await walk_menu(page, user, width, [0])
    # pages for other roles say so; nothing breaks
    for h in ["#/settings/users", "#/shop/orders"] + (
        ["#/prices/materials"] if user == "vic" else []
    ):
        await page.goto(f"{URL}/{h}")
        await expect(page.get_by_text("Not for your account")).to_be_visible(timeout=SLOW)
    check(True, f"{user} {width}: pages for other roles say so")


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        for w, h in WIDTHS:
            for user in ["rick", "rens", "eddy", "vic"]:
                ctx: Any = await browser.new_context(viewport={"width": w, "height": h})
                page = await ctx.new_page()
                page.on(
                    "pageerror", lambda e, u=user, w=w: problems.append(f"{u} {w}: page error {e}")
                )
                try:
                    if user == "rick":
                        await as_rick(page, w)
                    else:
                        await as_other(page, user, w)
                except Exception as exc:  # noqa: BLE001 - one role's failure, the rest still run
                    problems.append(f"{user} {w}: {type(exc).__name__}: {exc}"[:400])
                    try:
                        await page.screenshot(path=f"{SHOTS}/fail-{user}-{w}.png", timeout=60_000)
                    except Exception:  # noqa: BLE001 - the failure is already recorded
                        pass
                await ctx.close()
        await browser.close()
    print("\n".join(["", "PROBLEMS:", *problems]) if problems else "\nall good")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
