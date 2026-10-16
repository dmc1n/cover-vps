"""Browser check of the vents' logo in the 3D view (ADR-146), in Chromium.

Per cover: the cover page's 3D tab and its Desk card. Show ▾ → Logo is on by default with the
vents; the canvas reports as many logos drawn as vents.json has (`data-vent-logos`), each one
on the screen inside its vent's opening, in its lower half; switching Logo off draws none,
on again draws them again. A cover exported before ADR-146 (finished.json without
logos_mm) shows "Logo position not computed yet: run again" and draws none.

Run against a running studio with a scratch data copy (never the live data) and a user:

    docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \\
      -v "$PWD:/repo:ro" -v "$PWD/out/ventlogo:/shots" \\
      -e COVER_E2E_URL=http://127.0.0.1:18461 -e COVER_E2E_MODELS=drawing-t1 \\
      -e COVER_E2E_OLD=drawing-c1 mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q --user playwright==1.63.0 && python /repo/apps/web/e2e/vent_logo.py"

Screenshots go to $COVER_E2E_SHOTS (default /shots).
"""

import asyncio
import os
import sys
from typing import Any

from playwright.async_api import Browser, Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18461")
MODELS = [m for m in os.environ.get("COVER_E2E_MODELS", "drawing-t1").split(",") if m]
OLD = [m for m in os.environ.get("COVER_E2E_OLD", "").split(",") if m]
USER = os.environ.get("COVER_E2E_USER", "tester")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
SLOW = 90_000  # software WebGL in the container


async def login(page: Page) -> None:
    await page.goto(URL)
    await page.get_by_label("User name").fill(USER)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible()


async def screen(page: Page, mm: list[float]) -> tuple[float, float]:
    xy = await page.evaluate("(p) => document.querySelector('.viewer canvas').coverToScreen(p)", mm)
    return float(xy[0]), float(xy[1])


async def vents_on(page: Page) -> None:
    """The Vents button pressed (it is remembered per browser; a fresh one starts off)."""
    vents = page.get_by_role("toolbar", name="3D view").get_by_role("button", name="Vents")
    if await vents.get_attribute("aria-pressed") != "true":
        await vents.click()


async def logo_toggle(page: Page, on: bool) -> None:
    await page.get_by_role("toolbar", name="3D view").get_by_label("Show", exact=True).click()
    box = page.get_by_test_id("vent-logo-toggle")
    await expect(box).to_be_visible()
    if await box.is_checked() != on:
        await box.click()
    await page.keyboard.press("Escape")


async def face(page: Page, vent: dict[str, Any]) -> None:
    """Turn the camera to look straight at a vent from outside, close (a test hook only)."""
    await page.evaluate(
        "(v) => document.querySelector('.viewer canvas').lookAtMm?.(v.centre_mm, v.normal)", vent
    )
    await page.wait_for_timeout(800)


async def check(page: Page, model: str, tag: str, problems: list[str]) -> None:
    canvas = page.locator(".viewer canvas")
    await expect(canvas).to_be_visible()
    await expect(page.locator(".viewer canvas[data-loaded]")).to_be_visible()
    await page.wait_for_timeout(2000)
    doc = await (await page.request.get(f"{URL}/api/models/{model}/files/vents.json")).json()
    vents = doc["vents"]
    await vents_on(page)
    await logo_toggle(page, True)  # the default; asserted on: checked
    await expect(canvas).to_have_attribute("data-vent-logos", str(len(vents)), timeout=SLOW)
    if doc.get("logo") != "placed":
        problems.append(f"{tag}: vents.json logo is {doc.get('logo')!r}, not 'placed'")
    checked = 0
    for v in vents:
        await face(page, v)  # straight at it from outside: its logo must be on the screen
        lg = v["logo"]
        lx, ly = zip(*[await screen(page, c) for c in lg["corners_mm"]], strict=True)
        ox, oy = zip(*[await screen(page, c) for c in v["corners_mm"]], strict=True)
        cx, cy = sum(lx) / 4, sum(ly) / 4
        checked += 1
        if not (min(ox) - 2 <= cx <= max(ox) + 2 and min(oy) - 2 <= cy <= max(oy) + 2):
            problems.append(f"{tag}: vent {v['number']}'s logo outside its opening")
            continue
        if abs(cx - sum(ox) / 4) > max(3.0, (max(ox) - min(ox)) * 0.05):
            problems.append(f"{tag}: vent {v['number']}'s logo not centred on it")
        if cy < sum(oy) / 4:  # y grows down the screen: the lower half has the larger y
            problems.append(f"{tag}: vent {v['number']}'s logo in the upper half")
    if checked != len(vents):
        problems.append(f"{tag}: {checked} of {len(vents)} logos checked on the screen")
    await face(page, next((v for v in vents if v["piece"] == "skirt-front"), vents[0]))
    await page.screenshot(path=f"{SHOTS}/{tag}-logo-on.png")
    await logo_toggle(page, False)
    await expect(canvas).to_have_attribute("data-vent-logos", "0")
    await page.screenshot(path=f"{SHOTS}/{tag}-logo-off.png")
    await logo_toggle(page, True)
    await expect(canvas).to_have_attribute("data-vent-logos", str(len(vents)))
    print(f"{tag}: {len(vents)} logos drawn, off and on again")


async def run(browser: Browser) -> list[str]:
    problems: list[str] = []
    ctx = await browser.new_context(viewport={"width": 1440, "height": 1000})
    page = await ctx.new_page()
    page.set_default_timeout(SLOW)
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
    await login(page)
    for model in MODELS:
        await page.goto(f"{URL}/#/model/{model}/3d")
        await check(page, model, f"cover-{model}", problems)
        await page.goto(f"{URL}/#/work/desk/{model}")
        await expect(page.locator(".d-card")).to_be_visible()
        await check(page, model, f"desk-{model}", problems)
    for model in OLD:
        await page.goto(f"{URL}/#/model/{model}/3d")
        await expect(page.locator(".viewer canvas[data-loaded]")).to_be_visible()
        await vents_on(page)
        await logo_toggle(page, True)
        note = page.get_by_test_id("vent-logo-missing")
        await expect(note).to_have_text("Logo position not computed yet: run again")
        await expect(page.locator(".viewer canvas")).to_have_attribute("data-vent-logos", "0")
        await page.screenshot(path=f"{SHOTS}/cover-{model}-logo-missing.png")
        print(f"{model}: 'logo position not computed yet' shown, no logo drawn")
    await ctx.close()
    return problems


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--use-gl=swiftshader", "--enable-webgl"])
        problems = await run(browser)
        await browser.close()
    for msg in problems:
        print("PROBLEM", msg)
    print("OK" if not problems else f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
