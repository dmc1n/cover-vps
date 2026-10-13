"""Browser check of the studio's map (ADR-122, ADR-124, docs/plans/studio-ui.md): every section
and every page of its sub-menu opens for the roles that may see it, every old address (#/desk,
#/admin, #/catalogue, …) lands on its new page, a cover's tab and a Desk card's tab are in the
address (and another cover opens on its own tab, not the one before), each person starts on their
own page, the header stays on one line, and pages a role may not see say so. Since ADR-124 also:
All covers keeps its filters and selection between Table and Cards, New cover has the three
uploads, Learning none, the Workshop opens for every role, the header's search finds covers,
Desk codes and questions, and the theme button cycles auto → light → dark and is remembered.
Since ADR-126: four sections (no Prices), the price settings in Settings → Prices & costs (editors
see only those), a cover's seventh tab Price & shop with its parts and the summary on top, All
covers' optional price columns, and every Prices, Shop and Settings address that moved.
Since ADR-128: the workshop login (werkplaats) starts on Work → Workshop, sees Work only, gets
"Not for your account" elsewhere (a cover's page too), has no Approve on a Desk card but Comment
and After sewing, and the API refuses it prices and settings; the cover page's approval card is
the Desk's.

Every pass runs light and dark (COVER_E2E_THEMES, the browser's prefers-color-scheme), with a
contrast check of the text on every page (WCAG: 4.5:1, 3:1 for large text).

Screenshots of every page go to $COVER_E2E_SHOTS/<width>-<theme>/ (look at them).
Nothing is saved, approved, sent or run: the script only opens pages and tabs.

Run against a running studio with a scratch data copy (never the live data) and the users rick
(admin, approves), rens (editor, approves), eddy (editor), vic (viewer) and werkplaats
(workshop), password below:

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
THEMES = os.environ.get("COVER_E2E_THEMES", "light,dark").split(",")
WIDTHS = [(int(w), int(h)) for w, h in (x.split("x") for x in SIZES.split(","))]
SLOW = 30_000

# section → its sub-menu, as each role sees it (nav.ts)
MENU = {
    "rick": {
        "Work": ["Desk", "Questions", "Workshop"],
        "Covers": ["All covers", "Arrangements", "New cover", "Learning", "Product list"],
        "Shop": ["Orders", "Requests", "B2B customers", "Website (AI)"],
        "Settings": [],
    },
    "eddy": {
        "Work": ["Desk", "Questions", "Workshop"],
        "Covers": ["All covers", "Arrangements", "New cover", "Learning", "Product list"],
        "Shop": ["Website (AI)"],
        "Settings": [],
    },
    "vic": {
        "Work": ["Desk", "Questions", "Workshop"],
        "Covers": ["All covers", "Arrangements", "Learning"],
    },
    "werkplaats": {  # the workshop login: Work only (ADR-128)
        "Work": ["Desk", "Questions", "Workshop"],
    },
}  # fmt: skip
START = {
    "rick": "#/work/desk",
    "rens": "#/work/desk",
    "eddy": "#/covers/all",
    "vic": "#/covers/all",
    "werkplaats": "#/work/workshop",
}
SETTINGS = ["Company & shop", "Selling", "Costs", "Price rules", "Publish & versions",
            "Users & rights", "Rules & defaults", "Mail & notifications", "Website & API keys",
            "AI & spending", "System & logs"]  # fmt: skip
SETTINGS_EDITOR = ["Costs", "Price rules", "Publish & versions"]
COVER_TABS = ["3D", "Pieces", "Seams", "Adjust", "Compare", "History", "Price & shop"]
# every old address and where it must land (an admin)
OLD = [
    ("#/", "#/work/desk"),
    ("#/nothing-at-all", "#/work/desk"),
    ("#/desk", "#/work/desk"),
    (f"#/desk/{MODEL}", f"#/work/desk/{MODEL}"),
    ("#/questions", "#/work/questions"),
    ("#/questions/71", "#/work/questions/71"),
    ("#/catalogue", "#/covers/all?view=cards"),
    ("#/models", "#/covers/all"),
    ("#/arrangements", "#/covers/arrangements"),
    (f"#/arrangements/{ARR}", f"#/covers/arrangements/{ARR}"),
    ("#/learning", "#/covers/learning"),
    ("#/prices", "#/settings/costs"),
    ("#/prices/materials", "#/settings/costs"),
    ("#/prices/labour", "#/settings/costs"),
    ("#/prices/rate", "#/settings/costs"),
    ("#/prices/channels", "#/settings/pricing"),
    ("#/prices/costing", "#/settings/pricing"),
    ("#/prices/import", "#/settings/publish"),
    ("#/prices/versions", "#/settings/publish"),
    ("#/shop/matches", "#/shop/requests"),
    ("#/shop/phototest", "#/settings/ai"),
    ("#/settings/matching", "#/settings/selling"),
    ("#/settings/b2b", "#/settings/selling"),
    ("#/settings/desk", "#/settings/defaults"),
    ("#/settings/activity", "#/settings/system"),
    ("#/admin/matches", "#/shop/requests"),
    ("#/admin/phototest", "#/settings/ai"),
    ("#/admin/sessions", "#/settings/system"),
    ("#/website", "#/shop/website"),
    ("#/admin", "#/settings/users"),
    ("#/admin/orders", "#/shop/orders"),
    ("#/admin/b2b", "#/shop/b2b"),
    ("#/admin/shop", "#/settings/company"),
    ("#/admin/webshop", "#/shop/requests"),
    ("#/admin/mail", "#/settings/mail"),
    ("#/admin/system", "#/settings/system"),
    ("#/admin/prices", "#/settings/costs"),
    (f"#/model/{MODEL}", f"#/model/{MODEL}/3d"),
    (f"#/model/{MODEL}/downloads", f"#/model/{MODEL}/pieces/files"),
    (f"#/model/{MODEL}/files", f"#/model/{MODEL}/pieces/files"),
    (f"#/model/{MODEL}/settings", f"#/model/{MODEL}/adjust"),
    ("#/work", "#/work/desk"),
    ("#/covers", "#/covers/all"),
    ("#/shop", "#/shop/orders"),
    ("#/settings", "#/settings/company"),
    ("#/shop/nothing", "#/shop/orders"),
]
# text against its own background, every visible element with text of its own (WCAG 2.x)
CONTRAST_JS = """() => {
  const lin = c => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  const rgb = s => (s.match(/[\\d.]+/g) || []).map(Number);
  const lum = ([r, g, b]) => 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
  const bgOf = el => {
    for (let e = el; e; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage !== 'none' && e !== document.body) return null;  // a picture: skip
      const c = rgb(cs.backgroundColor);
      if (c.length === 3 || (c.length === 4 && c[3] > 0.9)) return c.slice(0, 3);
      if (c.length === 4 && c[3] > 0) return null;  // see-through: skip, not guessable
    }
    return [255, 255, 255];
  };
  const out = [];
  for (const el of document.querySelectorAll('body *')) {
    if (['SCRIPT', 'STYLE', 'svg', 'CANVAS', 'OPTION', 'IMG'].includes(el.tagName)) continue;
    if (el.closest('svg, canvas, .svgbox, .d-drawing, [aria-hidden=true]')) continue;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim());
    if (!own || !el.checkVisibility({opacityProperty: true, visibilityProperty: true})) continue;
    if (el.closest('button:disabled, [disabled]')) continue;
    const cs = getComputedStyle(el);
    if (parseFloat(cs.opacity) < 0.95) continue;
    const bg = bgOf(el);
    if (!bg) continue;
    const fg = rgb(cs.color);
    if (fg.length === 4 && fg[3] < 0.95) continue;
    const a = lum(fg.slice(0, 3)), b = lum(bg);
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    const size = parseFloat(cs.fontSize), bold = parseInt(cs.fontWeight) >= 600;
    const need = size >= 24 || (bold && size >= 18.6) ? 3 : 4.5;
    if (ratio < need) out.push({text: el.textContent.trim().slice(0, 40), ratio: +ratio.toFixed(2),
      need, cls: (el.className && el.className.baseVal === undefined ? el.className : '') + ''});
  }
  return out;
}"""
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


THEME = {"now": "light"}  # the pass that runs (a screenshot folder per width and theme)
low_contrast: dict[str, list[Any]] = {}


async def contrast(page: Page, where: str) -> None:
    """Text too faint for its background: listed (and a problem when well below the line)."""
    try:
        bad = await page.evaluate(CONTRAST_JS)
    except Exception:  # noqa: BLE001 - a page in the middle of loading: the next shot checks
        return
    if bad:
        low_contrast[f"{THEME['now']} {where}"] = bad[:6]
    worst = [b for b in bad if b["ratio"] < b["need"] - 1]
    check(not worst, f"{THEME['now']} {where}: text contrast ({len(bad)} under the line, "
                     f"worst {min((b['ratio'] for b in bad), default='-')}: "
                     f"{[b['text'] for b in worst[:3]]})")  # fmt: skip


async def shot(page: Page, width: int, name: str) -> None:
    folder = f"{SHOTS}/{width}-{THEME['now']}"
    os.makedirs(folder, exist_ok=True)
    await page.wait_for_timeout(600)
    await contrast(page, f"{width} {name}")
    try:
        await page.screenshot(path=f"{folder}/{name}.png", full_page=True, timeout=120_000)
    except Exception:  # noqa: BLE001 - a long page with software WebGL: the screen only
        await page.screenshot(path=f"{folder}/{name}.png", timeout=120_000)


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
    await page.goto(f"{URL}/#/settings/selling")
    await expect(page.get_by_text("Offer the existing cover from")).to_be_visible(timeout=SLOW)
    await expect(page.get_by_role("heading", name="B2B terms")).to_be_visible(timeout=SLOW)
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
    await page.goto(f"{URL}/#/model/{MODEL}/price")
    tabs = page.get_by_role("navigation", name="Cover")
    await expect(tabs.locator("a[aria-current=page]")).to_have_text("Price & shop", timeout=SLOW)
    got = [re.sub(r"\d+$", "", t).strip() for t in await tabs.locator("a").all_inner_texts()]
    check(got == COVER_TABS, f"rick {width}: a cover's tabs {got}")
    await price_and_shop(page, width, n)
    await page.goto(f"{URL}/#/model/{MODEL2}")
    check(await landed(page, f"#/model/{MODEL2}/3d"), f"rick {width}: another cover opens on 3D")
    await expect(tabs.locator("a[aria-current=page]")).to_have_text("3D", timeout=SLOW)
    for t, sub in [("3d", ""), ("pieces", "cut"), ("pieces", "flat"), ("pieces", "sizes"),
                   ("seams", ""), ("adjust", ""), ("compare", "drawing"),
                   ("compare", "reference"), ("compare", "ai"), ("history", "changes"),
                   ("history", "revisions"), ("history", "log"), ("pieces", "files"),
                   ("price", "")]:  # fmt: skip
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
        # a fresh page per tab: headless Chromium (software WebGL) stalled a capture of the
        # History tab reached from Check in the same page, while the page itself kept going
        await page.reload()
        card = page.locator(".d-card")
        await expect(card.get_by_role("navigation", name="Card")).to_be_visible(timeout=SLOW)
        cur = card.get_by_role("navigation", name="Card").locator("a[aria-current=page]")
        check(await cur.count() == 1, f"rick {width}: Desk card tab {t} is current")
        n[0] += 1
        await shot(page, width, f"{n[0]:02d}-desk-card-{t}")
    await page.goto(f"{URL}/#/work/desk/{ARR}")
    await page.reload()
    await expect(page.locator(".d-card")).to_be_visible(timeout=SLOW)
    n[0] += 1
    await shot(page, width, f"{n[0]:02d}-desk-card-arrangement")
    await covers_and_workshop(page, width, n)
    await search_and_theme(page, width, n)


async def price_and_shop(page: Page, width: int, n: list[int]) -> None:
    """A cover's Price & shop (ADR-126): the summary on top, prices per channel with the admin's
    fixed-price fields, the costing, the shop, B2B and orders; nothing is saved here."""
    await expect(page.get_by_test_id("cover-summary")).to_be_visible(timeout=SLOW)
    for part in ["cover-prices", "cover-shop", "cover-b2b", "cover-orders"]:
        await expect(page.get_by_test_id(part)).to_be_visible(timeout=SLOW)
    check(await page.get_by_test_id("cover-cost").count() == 1,
          f"rick {width}: Price & shop shows the costing")  # fmt: skip
    check(await page.get_by_role("button", name="Save in draft").count() == 2,
          f"rick {width}: an admin may set the B2C and B2B fixed price")  # fmt: skip
    n[0] += 1
    await shot(page, width, f"{n[0]:02d}-cover-price-and-shop")
    # All covers with the price columns; a price opens the cover's Price & shop
    await page.goto(f"{URL}/#/covers/all?prices=live")
    await expect(page.get_by_role("columnheader", name="B2C incl. VAT")).to_be_visible(timeout=SLOW)
    await expect(page.locator("td.price-cell a").first).to_be_visible(timeout=SLOW)
    n[0] += 1
    await shot(page, width, f"{n[0]:02d}-covers-with-prices")
    href = await page.locator("td.price-cell a").first.get_attribute("href")
    await page.locator("td.price-cell a").first.click()
    check(await landed(page, href or "-"), f"rick {width}: a price opens {href}")
    check((href or "").endswith("/price"), f"rick {width}: … the cover's Price & shop tab")


async def covers_and_workshop(page: Page, width: int, n: list[int]) -> None:
    """All covers: one filter row for Table and Cards, kept on the switch, selection in both."""
    await page.goto(f"{URL}/#/covers/all")
    filters = page.get_by_role("group", name="Filters")
    await expect(filters).to_be_visible(timeout=SLOW)
    for label in ["Search covers", "Category", "Cover", "Status", "Tag", "Sort",
                  "Select all shown"]:  # fmt: skip
        check(await filters.get_by_label(label, exact=True).count() == 1,
              f"rick {width}: All covers has the filter {label}")  # fmt: skip
    await expect(page.locator("table.list tbody tr").first).to_be_visible(timeout=SLOW)
    await filters.get_by_label("Search covers").fill(MODEL2.split("-")[-1])
    rows = await page.locator("table.list tbody tr").count()
    check(rows >= 1, f"rick {width}: the search narrows the table ({rows})")
    await page.get_by_role("link", name="Cards", exact=True).click()
    check(await landed(page, "#/covers/all?view=cards"), f"rick {width}: Cards in the address")
    check(
        await filters.get_by_label("Search covers").input_value() == MODEL2.split("-")[-1],
        f"rick {width}: the search stays when switching to Cards",
    )
    cards = page.locator(".gallery .product-wrap")
    check(await cards.count() == rows, f"rick {width}: Cards show what the Table showed")
    await cards.first.get_by_role("checkbox").check()
    await expect(page.locator(".selbar")).to_contain_text("1 selected", timeout=SLOW)
    n[0] += 1
    await shot(page, width, f"{n[0]:02d}-covers-cards-selected")
    await page.get_by_role("link", name="Table", exact=True).click()
    await expect(page.locator(".selbar")).to_contain_text("1 selected", timeout=SLOW)
    check(True, f"rick {width}: the selection stays when switching back to the Table")
    await page.get_by_role("button", name="Clear selection").click()
    # New cover: the three uploads; Learning: no upload
    await page.goto(f"{URL}/#/covers/new")
    for name in ["From a 3D file", "From a drawing", "Reference pairs"]:
        await expect(page.get_by_role("heading", name=re.compile(name))).to_be_visible(timeout=SLOW)
    check(await page.locator("input[type=file]").count() == 3,
          f"rick {width}: New cover has three uploads")  # fmt: skip
    await page.goto(f"{URL}/#/covers/learning")
    await expect(page.locator("h1.page-title")).to_have_text("Learning", timeout=SLOW)
    check(await page.locator("input[type=file]").count() == 0,
          f"rick {width}: Learning has no upload card")  # fmt: skip
    # the Workshop: read-only, and the cutting table's DXF only where the gate allows it
    await page.goto(f"{URL}/#/work/workshop")
    await expect(page.locator("h1.page-title")).to_have_text("Workshop", timeout=SLOW)
    await page.wait_for_load_state("networkidle")
    gate = await page.evaluate("""async () => {
      const w = await (await fetch('/api/workshop')).json();
      const links = [...document.querySelectorAll('tr[data-model] a[href$="cut.dxf"]')]
        .map(a => a.closest('tr').dataset.model);
      const ok = new Set(w.items.filter(i => i.dxf_ok).map(i => i.id));
      return {links: links.length, bad: links.filter(m => !ok.has(m)), items: w.items.length};
    }""")
    check(not gate["bad"], f"rick {width}: Workshop offers the DXF only past the gate {gate}")
    check(await page.locator("main button").count() == 0,
          f"rick {width}: the Workshop has no buttons (read-only)")  # fmt: skip


async def search_and_theme(page: Page, width: int, n: list[int]) -> None:
    box = page.get_by_role("searchbox", name=re.compile("Search covers, Desk codes"))
    await page.keyboard.press("Control+k")
    await expect(box).to_be_focused()
    await box.fill(MODEL.split("-")[-1])
    hits = page.get_by_role("listbox", name="Search results")
    await expect(hits.get_by_role("option").first).to_be_visible(timeout=SLOW)
    groups = [g.title() for g in await hits.locator(".hit-group").all_text_contents()]
    check("Covers" in groups and "Desk" in groups,
          f"rick {width}: the search finds covers and Desk codes {groups}")  # fmt: skip
    n[0] += 1
    await shot(page, width, f"{n[0]:02d}-search")
    await box.press("Enter")
    check(await landed(page, f"#/model/{MODEL}/3d"), f"rick {width}: Enter opens the first hit")
    await box.fill("71")
    await expect(hits.locator(".hit-group", has_text="Questions")).to_be_visible(timeout=SLOW)
    await box.press("Escape")
    # the theme button: auto → light → dark → auto, on <html>, remembered after a reload
    btn = page.locator("button.theme-toggle")
    seen = []
    for _ in range(3):
        await btn.click()
        seen.append(await page.evaluate("document.documentElement.dataset.theme || 'auto'"))
    check(seen == ["light", "dark", "auto"], f"rick {width}: the theme button cycles {seen}")
    await btn.click()
    await btn.click()  # dark
    await page.reload()
    th = await page.evaluate("document.documentElement.dataset.theme || 'auto'")
    check(th == "dark", f"rick {width}: the chosen theme is remembered ({th})")
    await btn.click()  # back to auto: the pass's own scheme


async def as_other(page: Page, user: str, width: int) -> None:
    await login(page, user)
    check(await landed(page, START[user]), f"{user} {width}: starts on {START[user]}")
    if user in MENU:
        await walk_menu(page, user, width, [0])
    # pages for other roles say so; nothing breaks
    for h in ["#/settings/users", "#/shop/orders"] + (
        ["#/prices/materials", "#/settings/costs"] if user == "vic" else []
    ):
        await page.goto(f"{URL}/{h}")
        await expect(page.get_by_text("Not for your account")).to_be_visible(timeout=SLOW)
    check(True, f"{user} {width}: pages for other roles say so")
    if user in ("eddy", "rens"):
        # editors: the price tabs of Settings only, read-only; a cover's prices without fields
        await page.goto(f"{URL}/#/prices/channels")
        check(await landed(page, "#/settings/pricing"), f"{user} {width}: old Prices address")
        tabs = page.get_by_role("navigation", name="Settings")
        await expect(tabs).to_be_visible(timeout=SLOW)
        got = [t.strip() for t in await tabs.locator("a").all_inner_texts()]
        check(got == SETTINGS_EDITOR, f"{user} {width}: Settings tabs {got}")
        await page.goto(f"{URL}/#/model/{MODEL}/price")
        await expect(page.get_by_test_id("cover-prices")).to_be_visible(timeout=SLOW)
        check(await page.get_by_role("button", name="Save in draft").count() == 0,
              f"{user} {width}: an editor sees the prices, no fields")  # fmt: skip
        check(await page.get_by_test_id("cover-orders").count() == 0,
              f"{user} {width}: orders on a cover are for admins")  # fmt: skip
    if user == "werkplaats":
        await as_workshop(page, width)
    if user == "vic":
        await page.goto(f"{URL}/#/model/{MODEL}/price")
        await expect(page.get_by_text("Prices and the shop are for editors and admins")
                     ).to_be_visible(timeout=SLOW)  # fmt: skip
        check(True, f"vic {width}: a viewer sees no prices on a cover")


async def as_workshop(page: Page, width: int) -> None:
    """The workshop login (ADR-128): Work only; the Desk card without Approve; the API agrees."""
    for h in ["#/covers/all", f"#/model/{MODEL}/3d", "#/settings/costs", "#/shop/b2b"]:
        await page.goto(f"{URL}/{h}")
        await expect(page.get_by_text("Not for your account")).to_be_visible(timeout=SLOW)
    check(True, f"werkplaats {width}: covers, prices, settings and the shop say so")
    await page.goto(f"{URL}/#/work/workshop")
    await expect(page.get_by_test_id("ws-orders")).to_be_visible(timeout=SLOW)
    check(await page.get_by_role("button", name="Send to production").count() == 0,
          f"werkplaats {width}: no Send to production for the workshop")  # fmt: skip
    await shot(page, width, "workshop-Workshop")
    await page.goto(f"{URL}/#/work/desk/{MODEL}")
    bar = page.locator(".d-actions")
    await expect(bar.get_by_role("button", name=re.compile("^Comment"))).to_be_visible(timeout=SLOW)
    check(await bar.get_by_role("button", name=re.compile("Approve")).count() == 0,
          f"werkplaats {width}: no Approve on a Desk card")  # fmt: skip
    check(await bar.get_by_role("button", name=re.compile("Reject")).count() == 0,
          f"werkplaats {width}: no Reject on a Desk card")  # fmt: skip
    check(await page.get_by_role("link", name=re.compile("Open cover")).count() == 0,
          f"werkplaats {width}: no link to the cover's page")  # fmt: skip
    await bar.get_by_test_id("after-sewing").click()
    await expect(bar.get_by_role("button", name="Fits", exact=True)).to_be_visible(timeout=SLOW)
    check(await bar.locator("label.d-check").count() == 0,
          f"werkplaats {width}: no Produced for the workshop")  # fmt: skip
    await shot(page, width, "workshop-Desk-card")
    codes = await page.evaluate(
        """async () => Promise.all(['/api/prices/list', '/api/admin/orders',
            '/api/admin/shop/settings', '/api/workshop'].map(async u => (await fetch(u)).status))"""
    )
    check(codes == [403, 403, 403, 200], f"werkplaats {width}: the API refuses {codes}")


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        for theme, (w, h) in [(t, s) for t in THEMES for s in WIDTHS]:
            THEME["now"] = theme
            for user in ["rick", "rens", "eddy", "vic", "werkplaats"]:
                ctx: Any = await browser.new_context(
                    viewport={"width": w, "height": h}, color_scheme=theme
                )
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
                    problems.append(f"{theme} {user} {w}: {type(exc).__name__}: {exc}"[:400])
                    try:
                        await page.screenshot(
                            path=f"{SHOTS}/fail-{user}-{w}-{theme}.png", timeout=60_000
                        )
                    except Exception:  # noqa: BLE001 - the failure is already recorded
                        pass
                await ctx.close()
        await browser.close()
    if low_contrast:
        print("\nUnder the contrast line (look at these):")
        for where, bad in low_contrast.items():
            print(f"  {where}: {bad}")
    print("\n".join(["", "PROBLEMS:", *problems]) if problems else "\nall good")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
