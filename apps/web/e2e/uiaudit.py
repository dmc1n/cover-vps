"""UI audit of the studio (docs/plans/studio-ui.md): every page, tab and sub-tab screenshotted at
two widths, with a count of what is on each screen (buttons, fields, checkboxes, headings, links,
page height, words), so the clutter can be measured before and after a redesign.

Nothing is changed: the script only opens pages and clicks tabs (never a button that saves,
approves, sends, runs or spends). Run it against a running studio with a scratch data copy
(never the live data) and the users rick (admin, approves), rens (editor, approves) and vic
(viewer), password below:

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/uiaudit/before:/shots" \\
      -e COVER_E2E_URL=http://127.0.0.1:18240 \\
      mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/uiaudit.py"

Screenshots go to $COVER_E2E_SHOTS/<width>/NN-name.png; the counts to $COVER_E2E_SHOTS/counts.json.
COVER_E2E_MODEL (a drawing cover), COVER_E2E_MODEL3D (a model with drape and rain) and
COVER_E2E_ARR (an arrangement) choose the examples.
"""

import asyncio
import json
import os
from typing import Any

from playwright.async_api import Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18240")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
MODEL = os.environ.get("COVER_E2E_MODEL", "drawing-s45")
MODEL3D = os.environ.get("COVER_E2E_MODEL3D", "suns-2-seater-kota")
ARR = os.environ.get("COVER_E2E_ARR", "arr-portofino-2-c")
SIZES = os.environ.get("COVER_E2E_SIZES", "1440x900,820x1180")
WIDTHS = [(int(w), int(h)) for w, h in (x.split("x") for x in SIZES.split(","))]

MODEL_TABS = ["3D", "Your drawing", "Your reference", "Seams", "AI advice", "Patterns",
              "Size drawing", "Cut pieces", "Settings", "Revisions", "Downloads",
              "Warnings and log"]  # fmt: skip
ADMIN_TABS = ["Users", "Orders", "B2B customers", "Matches", "Shop settings", "Photo test",
              "Prices & costing", "Website (AI)", "Requests", "Mail and address", "Logged in",
              "Audit log", "System"]  # fmt: skip
PRICE_TABS = ["Materials", "Labour", "Exchange rate", "Channels & price lists", "Costing",
              "Versions"]  # fmt: skip

COUNT_JS = """
() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const n = (sel) => [...document.querySelectorAll(sel)].filter(vis).length;
  const main = document.querySelector('main') || document.body;
  return {
    buttons: n('button'),
    fields: n('input:not([type=checkbox]):not([type=radio]):not([type=file]), textarea, select'),
    checkboxes: n('input[type=checkbox], input[type=radio]'),
    links: n('main a, .desk a'),
    headings: n('h1, h2, h3, h4, legend, summary'),
    tabs: n('nav.tabs button, .d-tabs a'),
    height: document.documentElement.scrollHeight,
    words: (main.innerText || '').split(/\\s+/).filter(Boolean).length,
  };
}
"""


async def login(page: Page, user: str) -> None:
    await page.goto(URL)
    await page.get_by_label("User name").fill(user)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible()


class Audit:
    def __init__(self, page: Page, width: int) -> None:
        self.page = page
        self.width = width
        self.n = 0
        self.counts: dict[str, Any] = {}
        os.makedirs(f"{SHOTS}/{width}", exist_ok=True)

    async def shot(self, name: str, wait_ms: int = 1200) -> None:
        await self.page.wait_for_timeout(wait_ms)
        self.n += 1
        key = f"{self.n:02d}-{name}"
        try:
            self.counts[key] = await self.page.evaluate(COUNT_JS)
        except Exception as e:  # noqa: BLE001 - a count is a nicety
            self.counts[key] = {"error": str(e)}
        path = f"{SHOTS}/{self.width}/{key}.png"
        try:
            await self.page.screenshot(path=path, full_page=True, timeout=90_000)
        except Exception:  # noqa: BLE001 - a very long page in software WebGL: the screen only
            try:
                await self.page.screenshot(path=path, timeout=90_000)
            except Exception as e:  # noqa: BLE001 - noted, the audit goes on
                self.counts[key]["shot_error"] = str(e).splitlines()[0]
                print("no shot", key)
        print(self.width, key, self.counts[key])

    async def go(self, name: str, hash_: str, wait_ms: int = 1500) -> None:
        await self.page.goto(f"{URL}/{hash_}")
        await self.page.wait_for_load_state("networkidle")
        await self.shot(name, wait_ms)

    async def tab(
        self, name: str, label: str, scope: str = "nav.tabs", wait_ms: int = 1200
    ) -> None:
        loc = self.page.locator(scope).get_by_role("button", name=label, exact=True)
        if not await loc.count():
            print("no tab", label)
            return
        await loc.first.click()
        await self.shot(name, wait_ms)


async def run_admin(browser: Any, width: int, height: int) -> dict[str, Any]:
    ctx = await browser.new_context(viewport={"width": width, "height": height})
    page = await ctx.new_page()
    await login(page, "rick")
    a = Audit(page, width)
    await a.go("models", "#/")
    await a.go("catalogue", "#/catalogue")
    await a.go("desk", "#/desk", 4000)
    await a.go("desk-card", f"#/desk/{MODEL}", 6000)
    # the reject dialog (opened, never sent)
    rej = page.get_by_role("button", name="Reject")
    if await rej.count():
        await rej.first.click()
        await a.shot("desk-card-reject-open", 800)
    await a.go("desk-arr", f"#/desk/{ARR}", 6000)
    await a.go("questions", "#/questions", 2000)
    await a.go("arrangements", "#/arrangements", 2000)
    await a.go("arrangement-open", f"#/arrangements/{ARR}", 6000)
    await a.go("learning", "#/learning")
    await a.go("prices", "#/prices", 2500)
    for t in PRICE_TABS[1:]:
        await a.tab(f"prices-{t.split()[0].lower()}", t, ".prices nav.tabs", 1500)
    await a.go("website", "#/website")
    await a.go("guide", "#/guide")
    await a.go("account", "#/account")
    await a.go("admin", "#/admin", 1500)
    for t in ADMIN_TABS[1:]:
        await a.tab(f"admin-{t.split()[0].lower().replace('&', '')}", t, "nav.tabs >> nth=0", 2000)
    await a.go("model", f"#/model/{MODEL}", 5000)
    for t in MODEL_TABS[1:]:
        await a.tab(f"model-{t.split()[-1].lower()}", t, "nav.tabs", 2500)
    # the model page keeps the tab of the model before (it is not in the address): back to 3D
    await page.goto(f"{URL}/#/model/{MODEL3D}")
    await page.locator("nav.tabs").get_by_role("button", name="3D", exact=True).click()
    await a.shot("model3d", 7000)
    drape = page.get_by_role("button", name="Drape", exact=True)
    if await drape.count():
        await drape.click()
        await a.shot("model3d-drape", 8000)
    await ctx.close()
    return a.counts


async def run_model3d(browser: Any, width: int, height: int) -> dict[str, Any]:
    """Only the 3D view with every simulation (COVER_E2E_ONLY=model3d)."""
    ctx = await browser.new_context(viewport={"width": width, "height": height})
    page = await ctx.new_page()
    await login(page, "rick")
    a = Audit(page, width)
    a.n = 43
    await page.goto(f"{URL}/#/model/{MODEL3D}")
    await a.shot("model3d", 9000)
    drape = page.get_by_role("button", name="Drape", exact=True)
    if await drape.count():
        await drape.click()
        await a.shot("model3d-drape", 9000)
    await ctx.close()
    return a.counts


async def run_role(browser: Any, user: str, width: int, height: int) -> dict[str, Any]:
    ctx = await browser.new_context(viewport={"width": width, "height": height})
    page = await ctx.new_page()
    await login(page, user)
    a = Audit(page, width)
    a.n = 80 if user == "rens" else 90
    await a.go(f"{user}-home", "#/")
    await a.go(f"{user}-desk", f"#/desk/{MODEL}", 6000)
    await ctx.close()
    return a.counts


async def main() -> None:
    os.makedirs(SHOTS, exist_ok=True)
    counts: dict[str, Any] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        for w, h in WIDTHS:
            if os.environ.get("COVER_E2E_ONLY") == "model3d":
                counts[str(w)] = await run_model3d(browser, w, h)
                continue
            counts[str(w)] = await run_admin(browser, w, h)
            for user in ("rens", "vic"):
                counts[str(w)].update(await run_role(browser, user, w, h))
        await browser.close()
    try:  # keep the other widths' counts from an earlier run
        with open(f"{SHOTS}/counts.json") as f:
            old = json.load(f)
        counts = {**old, **{w: {**old.get(w, {}), **c} for w, c in counts.items()}}
    except (OSError, ValueError):
        pass
    with open(f"{SHOTS}/counts.json", "w") as f:
        json.dump(counts, f, indent=1)


if __name__ == "__main__":
    asyncio.run(main())
