"""Browser check of the Cutting file view (ADR-147), in Chromium.

Per width (1440 desktop with a mouse; 820, an iPad, as a touch screen) and theme (light, dark):

- the cover page (Pieces → Cutting file) and the Desk card (Pieces): the drawing comes from the
  server (`cutview.svg`), its pieces counted as the meta says, the watermark exactly when the
  cover is not approved (and its words in the drawing itself);
- the layer toggles Cut, Pen, Texts and Names hide and show their layer;
- zoom in, fit, the wheel (desktop) or a two-finger pinch (iPad), a pan;
- a click (a tap) on a piece shows its box in cm and its edges;
- the measuring tool: two clicks give a distance;
- on the Desk card an older revision beside the current one, with what changed;
- rights: the workshop login sees an unapproved cover's cutting file refused and an approved
  one drawn; a viewer is refused; the DXF download stays locked before approval.

Run against a running studio with a scrubbed scratch copy of the data (never the live data):
mail, public URL, shop domain, Mollie and the link key cleared, `cover-users two-factor off`,
users e2e-admin (admin), e2e-viewer (viewer) and e2e-workshop (workshop). Then:

    docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \\
      -v "$PWD:/repo:ro" -v "$PWD/out/dxfview:/shots" -e COVER_E2E_URL=http://127.0.0.1:18471 \\
      -e COVER_E2E_APPROVED=drawing-t1 -e COVER_E2E_WAITING=blocchi-2seater-moon-right \\
      mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q --user playwright==1.63.0 && python /repo/apps/web/e2e/dxf_view.py"

COVER_E2E_BIG names a big cover to time (optional). Screenshots go to $COVER_E2E_SHOTS.
"""

import asyncio
import os
import sys
import time
from typing import Any

from playwright.async_api import Browser, Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18471")
APPROVED = os.environ.get("COVER_E2E_APPROVED", "drawing-t1")
WAITING = os.environ.get("COVER_E2E_WAITING", "blocchi-2seater-moon-right")
BIG = os.environ.get("COVER_E2E_BIG", "")
ADMIN = os.environ.get("COVER_E2E_USER", "e2e-admin")
VIEWER = os.environ.get("COVER_E2E_VIEWER", "e2e-viewer")
WORKSHOP = os.environ.get("COVER_E2E_WORKSHOP", "e2e-workshop")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
WIDTHS = [int(w) for w in os.environ.get("COVER_E2E_WIDTHS", "1440,820").split(",")]
TOUCH = {820}
SLOW = 60_000
WATERMARK = "PREVIEW – NOT FOR CUTTING"


async def login(page: Page, user: str) -> None:
    await page.goto(URL)
    await page.get_by_label("User name").fill(user)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible()


async def vb(view: Any) -> list[float]:
    stage = view.get_by_test_id(f"{await view.get_attribute('data-testid')}-stage")
    return [float(x) for x in (await stage.get_attribute("data-vb") or "0 0 1 1").split()]


async def to_screen(view: Any, xy: list[float]) -> tuple[float, float]:
    """A point of the drawing (mm, y down) on the screen, from the stage's view box."""
    tid = await view.get_attribute("data-testid")
    stage = view.get_by_test_id(f"{tid}-stage")
    box = await stage.bounding_box()
    x, y, w, h = await vb(view)
    return box["x"] + (xy[0] - x) / w * box["width"], box["y"] + (xy[1] - y) / h * box["height"]


async def centre(view: Any) -> None:
    """The stage in the middle of the window (the Desk card's action bar covers the bottom)."""
    tid = await view.get_attribute("data-testid")
    await view.get_by_test_id(f"{tid}-stage").evaluate("e => e.scrollIntoView({block: 'center'})")
    await view.page.wait_for_timeout(150)


async def tap(page: Page, touch: bool, x: float, y: float) -> None:
    if touch:
        await page.touchscreen.tap(x, y)
    else:
        await page.mouse.click(x, y)


async def pinch(page: Page, view: Any, factor: float) -> None:
    """Two fingers apart (factor > 1 zooms in), as pointer events on the stage."""
    tid = await view.get_attribute("data-testid")
    await page.evaluate(
        """([tid, factor]) => {
          const el = document.querySelector(`[data-testid="${tid}-stage"]`);
          const r = el.getBoundingClientRect();
          const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
          const ev = (type, id, x) => el.dispatchEvent(new PointerEvent(type, {
            pointerId: id, pointerType: "touch", clientX: x, clientY: cy, bubbles: true,
            isPrimary: id === 11, button: 0, buttons: 1 }));
          ev("pointerdown", 11, cx - 40); ev("pointerdown", 12, cx + 40);
          for (let k = 1; k <= 10; k++) {
            const d = 40 * (1 + (factor - 1) * k / 10);
            ev("pointermove", 11, cx - d); ev("pointermove", 12, cx + d);
          }
          ev("pointerup", 11, cx - 40 * factor); ev("pointerup", 12, cx + 40 * factor);
        }""",
        [tid, factor],
    )


async def check_view(page: Page, view: Any, model: str, tag: str, touch: bool,
                     problems: list[str], approved: bool) -> None:  # fmt: skip
    await expect(view).to_have_attribute("data-ready", "1", timeout=SLOW)
    meta = await (await page.request.get(f"{URL}/api/models/{model}/cutview")).json()
    n = int(await view.get_attribute("data-pieces") or -1)
    if n != len(meta["pieces"]) or n == 0:
        problems.append(f"{tag}: {n} pieces drawn, the meta has {len(meta['pieces'])}")
    drawn = await view.locator(".cv-piece").count()
    if drawn != n:
        problems.append(f"{tag}: {drawn} piece paths for {n} pieces")
    wm = await view.get_attribute("data-watermark")
    if wm != ("0" if approved else "1"):
        problems.append(f"{tag}: watermark {wm!r} on an {'approved' if approved else 'unapproved'}")
    words = await view.locator(".cv-watermark").count()
    if approved == bool(words):
        problems.append(f"{tag}: the watermark's words {'present' if words else 'missing'}")
    # the layers: off hides, on again shows
    layers = (("pen", ".cv-pen", "display"), ("text", ".cv-text", "display"),
              ("names", ".cv-name", "display"), ("cut", ".cv-cut", "stroke-opacity"))  # fmt: skip
    for layer, sel, prop in layers:
        btn = view.locator(f'button[data-layer="{layer}"]')
        if await btn.get_attribute("aria-pressed") != "true":
            await btn.click()
        if not await view.locator(sel).count():
            if layer != "names":
                problems.append(f"{tag}: no {sel} in the drawing")
            continue
        await btn.click()
        await expect(btn).to_have_attribute("aria-pressed", "false")
        off = await view.locator(sel).first.evaluate(f"e => getComputedStyle(e)['{prop}']")
        if off not in ("none", "0"):
            problems.append(f"{tag}: {layer} off but {prop} is {off}")
        await page.screenshot(path=f"{SHOTS}/{tag}-no-{layer}.png") if layer == "pen" else None
        await btn.click()
        await expect(btn).to_have_attribute("aria-pressed", "true")
        on = await view.locator(sel).first.evaluate(f"e => getComputedStyle(e)['{prop}']")
        if on in ("none", "0"):
            problems.append(f"{tag}: {layer} on again but {prop} is {on}")
    await page.screenshot(path=f"{SHOTS}/{tag}.png")
    # zoom in, fit; the wheel or a pinch
    await centre(view)
    fit_w = (await vb(view))[2]
    await view.get_by_role("button", name="Zoom in").click()
    if not (await vb(view))[2] < fit_w * 0.8:
        problems.append(f"{tag}: Zoom in did not zoom")
    await view.get_by_role("button", name="Fit to screen").click()
    if abs((await vb(view))[2] - fit_w) > fit_w * 0.01:
        problems.append(f"{tag}: Fit did not go back to the whole sheet")
    if touch:
        await pinch(page, view, 2.0)
        if not (await vb(view))[2] < fit_w * 0.75:
            problems.append(
                f"{tag}: a pinch did not zoom ({(await vb(view))[2]:.0f} of {fit_w:.0f})"
            )
    else:
        sx, sy = await to_screen(view, meta["pieces"][0]["centre"])
        await page.mouse.move(sx, sy)
        await page.mouse.wheel(0, -400)
        await page.wait_for_timeout(200)
        if not (await vb(view))[2] < fit_w * 0.9:
            problems.append(f"{tag}: the wheel did not zoom")
        before = await vb(view)
        await page.mouse.move(sx, sy)
        await page.mouse.down()
        await page.mouse.move(sx + 120, sy + 60, steps=6)
        await page.mouse.up()
        after = await vb(view)
        if not after[0] < before[0]:
            problems.append(f"{tag}: dragging did not pan")
    await view.get_by_role("button", name="Fit to screen").click()
    # a click on a piece: its box and edges (the biggest piece, near its first edge)
    pc = max(meta["pieces"], key=lambda p: p["size_mm"][0] * p["size_mm"][1])
    e = pc["edges"][0]
    cx, cy = pc["centre"]
    target = [e["mid"][0] + (cx - e["mid"][0]) * 0.08, e["mid"][1] + (cy - e["mid"][1]) * 0.08]
    await centre(view)
    await tap(page, touch, *await to_screen(view, target))
    await expect(view).to_have_attribute("data-selected", str(pc["index"]))
    tid = await view.get_attribute("data-testid")
    size = f"{pc['size_mm'][0] / 10:.1f} cm × {pc['size_mm'][1] / 10:.1f} cm"
    await expect(view.get_by_test_id(f"{tid}-size")).to_have_text(size)
    labels = await view.locator(".cv-edge").count()
    if labels != len(pc["edges"]):
        problems.append(f"{tag}: {labels} edge labels for {len(pc['edges'])} edges")
    await page.screenshot(path=f"{SHOTS}/{tag}-piece.png")
    await view.get_by_role("button", name="Close the piece").click()
    # measuring: two corners of that piece
    await view.get_by_role("button", name="Measure a distance").click()
    a, b = e["a"], e["b"]
    await tap(page, touch, *await to_screen(view, a))
    await tap(page, touch, *await to_screen(view, b))
    readout = view.get_by_test_id(f"{tid}-distance")
    await expect(readout).to_be_visible()
    got = await readout.inner_text()
    want = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
    if f"{want / 10:.1f} cm" not in got:
        problems.append(f"{tag}: measured {got!r}, the corners are {want / 10:.1f} cm apart")
    await page.screenshot(path=f"{SHOTS}/{tag}-measure.png")
    await view.get_by_role("button", name="Measure a distance").click()
    print(f"{tag}: {n} pieces, watermark {wm}, layers, zoom, piece {pc['name']}, measure {got}")


async def run_width(browser: Browser, width: int, scheme: str, problems: list[str]) -> None:
    touch = width in TOUCH
    ctx = await browser.new_context(
        viewport={"width": width, "height": 1180 if touch else 1000},
        has_touch=touch,
        is_mobile=False,
        color_scheme=scheme,  # fmt: skip
    )
    page = await ctx.new_page()
    page.set_default_timeout(SLOW)
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
    await login(page, ADMIN)
    for model, approved in ((APPROVED, True), (WAITING, False)):
        tag = f"{width}-{scheme}-cover-{model}"
        await page.goto(f"{URL}/#/model/{model}/pieces/cutfile")
        await check_view(page, page.get_by_test_id("cutview"), model, tag, touch, problems,
                         approved)  # fmt: skip
        if not approved:  # the download stays locked while the drawing shows
            r = await page.request.get(f"{URL}/api/models/{model}/files/cut.dxf")
            if r.status != 403:
                problems.append(f"{tag}: the unapproved DXF answered {r.status}")
    # the Desk card, and an older revision beside the current one
    tag = f"{width}-{scheme}-desk-{APPROVED}"
    await page.goto(f"{URL}/#/work/desk/{APPROVED}/pieces")
    await expect(page.locator(".d-card")).to_be_visible()
    await check_view(page, page.get_by_test_id("cutview"), APPROVED, tag, touch, problems, True)
    pick = page.get_by_test_id("cutfile-compare")
    options = await pick.locator("option").all_inner_texts()
    if len(options) > 2:
        await pick.select_option(index=2)  # the newest revision but one
        await expect(page.get_by_test_id("cutview-old")).to_have_attribute("data-ready", "1")
        await expect(page.get_by_test_id("cutfile-diff")).not_to_contain_text("Comparing")
        rows = await page.locator(".cutfile-changes tbody tr").count()
        summary = await page.get_by_test_id("cutfile-diff").inner_text()
        await page.get_by_test_id("cutting-file").screenshot(path=f"{SHOTS}/{tag}-compare.png")
        if rows:
            await page.locator(".cutfile-changes tbody tr button").first.click()
            await page.wait_for_timeout(400)
            await page.get_by_test_id("cutting-file").screenshot(
                path=f"{SHOTS}/{tag}-compare-piece.png"
            )
        print(f"{tag}: compared with {options[2]!r}: {rows} changed pieces; "
              f"{summary.splitlines()[0] if summary else ''}")  # fmt: skip
    else:
        problems.append(f"{tag}: no older revision to compare with")
    if BIG and width == WIDTHS[0] and scheme == "light":
        start = time.perf_counter()
        await page.goto(f"{URL}/#/model/{BIG}/pieces/cutfile")
        await expect(page.get_by_test_id("cutview")).to_have_attribute("data-ready", "1")
        first = time.perf_counter() - start
        await page.reload()
        start = time.perf_counter()
        await expect(page.get_by_test_id("cutview")).to_have_attribute("data-ready", "1")
        again = time.perf_counter() - start
        await page.screenshot(path=f"{SHOTS}/{width}-{scheme}-big-{BIG}.png")
        print(f"big cover {BIG}: drawn in {first:.1f} s, again (cached) {again:.1f} s")
    await ctx.close()


async def run_roles(browser: Browser, problems: list[str]) -> None:
    ctx = await browser.new_context(viewport={"width": 1024, "height": 900}, has_touch=True)
    page = await ctx.new_page()
    page.set_default_timeout(SLOW)
    await login(page, WORKSHOP)
    await page.goto(f"{URL}/#/work/desk/{WAITING}/pieces")
    view = page.get_by_test_id("cutview")
    await expect(view).to_contain_text("once the Desk approved it")
    await view.evaluate("e => e.scrollIntoView({block: 'center'})")
    await page.screenshot(path=f"{SHOTS}/workshop-waiting.png")
    await page.goto(f"{URL}/#/work/desk/{APPROVED}/pieces")
    await expect(view).to_have_attribute("data-ready", "1")
    await expect(view).to_have_attribute("data-watermark", "0")
    await page.screenshot(path=f"{SHOTS}/workshop-approved.png")
    print("workshop: the unapproved cover refused, the approved one drawn")
    await ctx.close()
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    page.set_default_timeout(SLOW)
    await login(page, VIEWER)
    await page.goto(f"{URL}/#/model/{APPROVED}/pieces/cutfile")
    await expect(page.get_by_test_id("cutview")).to_contain_text("editors, approvers and admins")
    r = await page.request.get(f"{URL}/api/models/{APPROVED}/cutview.svg")
    if r.status != 403:
        problems.append(f"viewer: cutview.svg answered {r.status}")
    print("viewer: refused")
    await ctx.close()


async def main() -> int:
    problems: list[str] = []
    os.makedirs(SHOTS, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for width in WIDTHS:
            for scheme in ("light", "dark"):
                await run_width(browser, width, scheme, problems)
        await run_roles(browser, problems)
        await browser.close()
    for line in problems:
        print("PROBLEM:", line)
    print("all good" if not problems else f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
