"""Browser check of measuring on the 3D cover (ADR-111), in Chromium, with a mouse and a finger.

Per cover: the studio's 3D view. "Vent sizes" lists every vent with the cutting file's numbers
(vents.json: opening, bottom edge above the hem, to the seam on each side), checked against the
file. "Measure": the two bottom corners of a vent that faces the camera (they snap to the vent's
corners) give the opening's width, straight and along the fabric; the two lower ends of the
front's corner seams give the front's length; Esc cancels a first point; one measurement is
removed, then all. On a phone-sized screen two taps make a measurement. Then the Desk card: the
check list (PDF) downloads, and a fit is saved with a measured value, which the history shows.

Run against a running studio with a scratch data copy (never the live data) and a user:

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/measuretest:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:18193 -e COVER_E2E_MODELS=suns-2-seater-kota,drawing-c1 \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/measure.py"

Screenshots go to $COVER_E2E_SHOTS (default /shots).
"""

import asyncio
import os
import sys
from typing import Any

from playwright.async_api import Browser, Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18193")
MODELS = os.environ.get("COVER_E2E_MODELS", "suns-2-seater-kota").split(",")
USER = os.environ.get("COVER_E2E_USER", "tester")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
PARTS = os.environ.get("COVER_E2E_PARTS", "studio,phone,desk").split(",")
SLOW = 90_000  # software WebGL in the container


def cm(mm: float) -> str:
    return f"{mm / 10:.1f} cm"


async def login(page: Page) -> None:
    await page.goto(URL)
    await page.get_by_label("User name").fill(USER)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible()


async def screen(page: Page, mm: list[float]) -> tuple[float, float]:
    xy = await page.evaluate("(p) => document.querySelector('.viewer canvas').coverToScreen(p)", mm)
    return float(xy[0]), float(xy[1])


async def ready(page: Page) -> None:
    """The 3D view drawn and the cover loaded (its pieces' file fetched, a moment to frame)."""
    await expect(page.locator(".viewer canvas")).to_be_visible()
    await expect(page.locator(".viewer canvas[data-loaded]")).to_be_visible()
    await page.wait_for_timeout(2500)
    await top(page)


async def top(page: Page) -> None:
    """The 3D view at the top of the window, its toolbar just above."""
    await page.evaluate(
        "() => { const t = document.querySelector('.viewer .layers');"
        " window.scrollTo(0, window.scrollY + t.getBoundingClientRect().top - 8); }"
    )
    await page.wait_for_timeout(300)


async def vent_sizes(page: Page, model: str, tag: str) -> list[dict[str, Any]]:
    doc = await (await page.request.get(f"{URL}/api/models/{model}/files/vents.json")).json()
    vents = doc["vents"]
    toggle = page.get_by_test_id("vent-sizes-toggle")
    if not await toggle.is_checked():
        await toggle.check()
    rows = page.get_by_test_id("vent-row")
    await expect(rows).to_have_count(len(vents))
    for k, v in enumerate(vents):
        row = rows.nth(k)
        w, h = v["size_mm"]
        await expect(row.get_by_test_id("vent-opening")).to_have_text(f"{cm(w)} × {cm(h)}")
        await expect(row.get_by_test_id("vent-above")).to_contain_text(cm(v["above_hem_mm"]))
        for side in ("left", "right"):
            s = v["sides"][side]
            await expect(row.get_by_test_id(f"vent-{side}")).to_contain_text(cm(s["mm"]))
            if s["name"]:
                await expect(row.get_by_test_id(f"vent-{side}")).to_contain_text(s["name"])
    await page.wait_for_timeout(800)
    await page.screenshot(path=f"{SHOTS}/{tag}-vent-sizes.png")
    print(f"{tag}: {len(vents)} vents listed as in vents.json")
    return list(vents)


async def click_at(page: Page, mm: list[float], touch: bool = False) -> None:
    x, y = await screen(page, mm)
    if touch:
        await page.touchscreen.tap(x, y)
    else:
        await page.mouse.move(x, y)
        await page.wait_for_timeout(150)
        await page.mouse.down()
        await page.mouse.up()
    await page.wait_for_timeout(250)


async def measure(page: Page, a: list[float], b: list[float], touch: bool = False) -> Any:
    before = await page.get_by_test_id("measurement").count()
    await click_at(page, a, touch)
    await click_at(page, b, touch)
    item = page.get_by_test_id("measurement").nth(before)
    await expect(item).to_be_visible()
    await expect(item.get_by_test_id("surface")).not_to_have_text("…")
    return item


async def facing(page: Page, vents: list[dict[str, Any]]) -> dict[str, Any]:
    """The vent seen biggest on the screen, from the front (its corners run bottom left, bottom
    right, top right, top left as seen from outside: clockwise on screen, y down)."""

    async def area(v: dict[str, Any]) -> float:
        p = [await screen(page, c) for c in v["corners_mm"]]
        return sum(p[k][0] * p[k - 1][1] - p[k - 1][0] * p[k][1] for k in range(4)) / 2

    sizes = [await area(v) for v in vents]
    return vents[max(range(len(vents)), key=lambda k: sizes[k])]


async def studio(browser: Browser, model: str, problems: list[str]) -> None:
    tag = f"studio-{model}"
    ctx = await browser.new_context(viewport={"width": 1440, "height": 1000})
    page = await ctx.new_page()
    page.set_default_timeout(SLOW)
    page.on("pageerror", lambda e: problems.append(f"{tag}: {e}"))
    await login(page)
    await page.goto(f"{URL}/#/model/{model}")
    await ready(page)
    vents = await vent_sizes(page, model, tag)
    await page.get_by_test_id("measure-toggle").click()
    await expect(page.locator("[data-testid=measure][data-ready='1']")).to_be_visible()
    # a vent's opening, corner to corner (they snap to the vent's corners)
    v = await facing(page, vents)
    bl, br = v["corners_mm"][0], v["corners_mm"][1]
    item = await measure(page, bl, br)
    print(f"{tag}: {await item.inner_text()}".replace("\n", " "))
    width = cm(v["size_mm"][0])
    await expect(item.get_by_test_id("straight")).to_have_text(width)
    await expect(item.get_by_test_id("surface")).to_have_text(width)
    await expect(item).to_contain_text("vent")
    print(f"{tag}: V{v['number']} corner to corner {width}, straight and along the fabric")
    # the front: the lower ends of its two corner seams
    snaps = await (await page.request.get(f"{URL}/api/models/{model}/measure.json")).json()
    low = snaps["lower_edge_z_mm"]
    ends = [p for s in snaps["seams"] for p in (s["points_mm"][0], s["points_mm"][-1])
            if p[2] <= low + 1]  # fmt: skip
    lo_y = min(p[1] for p in ends)
    front = sorted((p for p in ends if p[1] <= lo_y + 1), key=lambda p: p[0])
    if len(front) >= 2:
        a, b = front[0], front[-1]
        item = await measure(page, a, b)
        want = cm(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)
        await expect(item.get_by_test_id("straight")).to_have_text(want)
        print(f"{tag}: front, seam end to seam end: {want}")
    # hovering near a seam names it
    s = snaps["seams"][0]["points_mm"]
    x, y = await screen(page, s[len(s) // 2])
    await page.mouse.move(x + 4, y + 3)
    await page.wait_for_timeout(400)
    print(f"{tag}: hover shows: {await page.get_by_test_id('measure-snap').inner_text()}")
    await page.screenshot(path=f"{SHOTS}/{tag}-measure.png")
    # turned and zoomed, the measurements stay where they were (they are in the scene)
    canvas = page.locator(".viewer canvas")
    box = await canvas.bounding_box()
    assert box
    await page.mouse.move(box["x"] + box["width"] * 0.8, box["y"] + box["height"] * 0.5)
    await page.mouse.down()
    await page.mouse.move(box["x"] + box["width"] * 0.55, box["y"] + box["height"] * 0.45, steps=8)
    await page.mouse.up()
    await page.mouse.wheel(0, -300)
    await page.wait_for_timeout(1200)
    await page.screenshot(path=f"{SHOTS}/{tag}-measure-turned.png")
    count = await page.get_by_test_id("measurement").count()
    assert count >= 1, "a turn of the view made a measurement"
    # Esc cancels a first point
    await click_at(page, bl)
    await expect(page.get_by_test_id("measure")).to_contain_text("second point")
    await page.keyboard.press("Escape")
    await expect(page.get_by_test_id("measure")).not_to_contain_text("second point")
    # remove one, then all
    await page.get_by_role("button", name="Remove measurement 1").click()
    await expect(page.get_by_test_id("measurement")).to_have_count(count - 1)
    if count > 1:
        await page.get_by_role("button", name="Clear all").click()
        await expect(page.get_by_test_id("measurement")).to_have_count(0)
    await ctx.close()


async def phone(browser: Browser, model: str, problems: list[str]) -> None:
    tag = f"phone-{model}"
    ctx = await browser.new_context(
        viewport={"width": 390, "height": 844}, has_touch=True, is_mobile=True
    )
    page = await ctx.new_page()
    page.set_default_timeout(SLOW)
    page.on("pageerror", lambda e: problems.append(f"{tag}: {e}"))
    await login(page)
    await page.goto(f"{URL}/#/model/{model}")
    await ready(page)
    doc = await (await page.request.get(f"{URL}/api/models/{model}/files/vents.json")).json()
    await page.get_by_test_id("measure-toggle").tap()
    await expect(page.locator("[data-testid=measure][data-ready='1']")).to_be_visible()
    v = await facing(page, doc["vents"])
    await page.locator(".viewer canvas").scroll_into_view_if_needed()
    item = await measure(page, v["corners_mm"][0], v["corners_mm"][1], touch=True)
    await expect(item.get_by_test_id("straight")).to_have_text(cm(v["size_mm"][0]))
    await page.screenshot(path=f"{SHOTS}/{tag}-measure.png", full_page=True)
    print(f"{tag}: two taps measure the vent: {cm(v['size_mm'][0])}")
    await ctx.close()


async def desk(browser: Browser, model: str, problems: list[str]) -> None:
    tag = f"desk-{model}"
    ctx = await browser.new_context(viewport={"width": 1440, "height": 1000})
    page = await ctx.new_page()
    page.set_default_timeout(SLOW)
    page.on("pageerror", lambda e: problems.append(f"{tag}: {e}"))
    await login(page)
    await page.goto(f"{URL}/#/desk/{model}")
    link = page.locator(".d-3d figcaption a", has_text="Check list")
    await expect(link).to_be_visible()
    r = await page.request.get(URL + (await link.get_attribute("href") or ""))
    assert r.ok and (await r.body()).startswith(b"%PDF"), "the check list is a PDF"
    pts = await (await page.request.get(f"{URL}/api/models/{model}/checkpoints")).json()
    key = next(p for p in pts["points"] if p["key"].endswith(".above_hem"))
    await page.get_by_test_id("measured-toggle").click()
    form = page.get_by_test_id("measured-form")
    await expect(form).to_be_visible()
    await form.locator(f"input[data-key='{key['key']}']").fill(f"{(key['mm'] + 8) / 10:.1f}")
    await expect(form).to_contain_text("+0.8")
    await page.screenshot(path=f"{SHOTS}/{tag}-measured.png", full_page=True)
    await page.get_by_role("button", name="Does not fit").click()
    # the card reloads after the action: the new history comes with it
    await page.wait_for_timeout(3000)
    await expect(page.locator(".d-timeline")).to_contain_text("measured 1 size")
    await page.locator(".d-timeline").screenshot(path=f"{SHOTS}/{tag}-history.png")
    print(f"{tag}: check list downloads; a fit with 1 measured size is in the history")
    await ctx.close()


async def main() -> int:
    problems: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        if "studio" in PARTS:
            for model in MODELS:
                await studio(browser, model, problems)
        if "phone" in PARTS:
            await phone(browser, MODELS[0], problems)
        if "desk" in PARTS:
            await desk(browser, MODELS[-1], problems)
        await browser.close()
    for pr in problems:
        print("PAGE ERROR", pr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
