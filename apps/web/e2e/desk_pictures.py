"""Browser check of the Desk's pictures (ADR-096), the way Rens uses them, in Chromium, WebKit
(Safari, iPad) and Firefox, wide and narrow.

Per browser, width and cover: open the card, press Reject. The Pictures row must be on the
screen at once, without scrolling (8 Oct 2026: on live it was below the screen, so Rens never
saw it and no picture was ever sent). Then every source: Snapshot 3D, Snapshot drawing, Upload
(through the file chooser), paste and drop, each marked; Reject sends them (POST .../pictures,
then the reject naming them). Then "Correct this cover" with a marked snapshot. Finally the
pictures are thumbnails in the history and load.

Run against a running studio with a scratch data copy (never the live data) and a user:

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/desktest:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:18183 -e COVER_E2E_MODELS=drawing-c2,drawing-c18 \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/desk_pictures.py"

Pictures go to $COVER_E2E_SHOTS (default /shots), which must hold upload-sample.jpg.
"""

import asyncio
import json
import os
import sys
from typing import Any

from playwright.async_api import Browser, Page, Playwright, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18182")
MODELS = os.environ.get("COVER_E2E_MODELS", "drawing-s45").split(",")
BROWSERS = os.environ.get("COVER_E2E_BROWSERS", "chromium,webkit,firefox").split(",")
WIDTHS = [int(w) for w in os.environ.get("COVER_E2E_WIDTHS", "1440,820").split(",")]
USER = os.environ.get("COVER_E2E_USER", "rens")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
PICTURE = os.environ.get("COVER_E2E_PICTURE", f"{SHOTS}/upload-sample.jpg")
SLOW = 90_000  # software WebGL in the container: a snapshot of a big cover takes seconds
# a small PNG for the paste and the drop
TINY = (
    "iVBORw0KGgoAAAANSUhEUgAAAKAAAAB4CAIAAAD6wG44AAAC6ElEQVR42u3dS0hUURyA8XPuXK+zyAe5CyezlBnN"
    "J1qDjpnag6hBskSpwGgWUkLSIlwVEgVFRQtrZeAmcmrM8I1gubBBNKUwU6YHpqMp1iLJYlzc5rYwWrQxAmmU71ud"
    "zb0Xzo8/nM3hyu8LU4LWbwpbADABTAATwAQwAUwAA0wAE8AEMAFMABPAABPABDABTAATwAQwAQwwAUwAE8AEMAFM"
    "f6au3qsv19Wxv3/fxepqJpgAJoABJoAJYAKYACaACWCACWACmAAmgAlgApgABpgAJoAJ4JUrcBShtZ6BdwP8T6n/"
    "8du1NVeGXgxYYuOEITytbi1MKzlUajabh18+9w725e7Iy87YaQij+2lnnCVe0zTXiUp3873iAyURGyJMJrWrp316"
    "1g9h6AKrJnVmbqbrSUdmapZzf/Hit8Xu3s5Pn+fPnT7vHewryt974/bVyMioQsceT6vbYd/VcL/+qLOsf8g7/dEf"
    "HRVdUe6qq78FYegCG8IY840KIUbHRw7uc968cy0tJSMpMTk83CyEePPOV3b42MBwv6fV/fuRxG3WmI0xy2stTFOk"
    "EjSCKIYqsGEYQWN5res/jpdWvPa96h/y2rNzhRBNbQ/iN2912PPTUzIftT38dWRQlIbGu7quSym3WOLRDelDlqIo"
    "1kSbECI1OX1i8n3sJsvo2Iiqhqkm1RxurjxZ5Z+Z8rQ0WhOShBBSSinl1PSH7bZUIYQ1wVaQx7ErtCdY1/UUW1p+"
    "TmFgKdDc7ln4+uXMqbNz87OBpYCu676341Wuaill77MeIcSkf6Ki3NXS1XzEWWrPygkGg487mvBbMbl6/y5c8XZh"
    "bc2VS9cvYLActwtprQEzvuscmAAmgAlggAlgApgAJoAJYAKYAAaYACaACWACmAAmgAEmgAlgApgAJoAJYIAJYFq7"
    "reL1UWKCCWACmAAGmAAmgAlgApgAJoAJYIAJYAKYACaACWACGGACmAAmgAlgApgABpgAprXaTz0+wIR8eBCtAAAA"
    "AElFTkSuQmCC"
)
PUT_FILE = """([kind, b64]) => {
    const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
    const dt = new DataTransfer();
    dt.items.add(new File([bytes], kind + ".png", {type: "image/png"}));
    if (kind === "pasted") {
        const ev = new ClipboardEvent("paste", {clipboardData: dt});
        // Firefox gives a made-up paste an empty clipboard: give it what a real paste has
        Object.defineProperty(ev, "clipboardData", {value: dt});
        window.dispatchEvent(ev);
    } else {
        const zone = document.querySelector(".d-reject .d-pics");
        zone.dispatchEvent(new DragEvent("dragover", {dataTransfer: dt, bubbles: true}));
        zone.dispatchEvent(new DragEvent("drop", {dataTransfer: dt, bubbles: true}));
    }
}"""


async def in_sight(page: Page, selector: str) -> bool:
    return bool(
        await page.evaluate(
            """(s) => { const b = document.querySelector(s)?.getBoundingClientRect();
                        return !!b && b.top >= 0 && b.bottom <= innerHeight; }""",
            selector,
        )
    )


async def mark(page: Page, tools: list[str], shot: str | None = None) -> None:
    marker = page.get_by_role("dialog", name="Mark the picture")
    try:
        await expect(marker).to_be_visible(timeout=SLOW)
    except AssertionError:
        notes = await page.locator(".d-pics-note").all_text_contents()
        raise AssertionError(f"no marking editor for {tools}; the page says {notes}") from None
    canvas = marker.locator("canvas")
    await expect(canvas).to_be_visible(timeout=SLOW)
    await page.wait_for_timeout(300)
    box = await canvas.bounding_box()
    assert box
    spots = {"Arrow": ((0.15, 0.15), (0.45, 0.45)), "Circle": ((0.5, 0.3), (0.8, 0.7)),
             "Line": ((0.2, 0.8), (0.7, 0.85))}  # fmt: skip
    for tool in tools:
        await marker.get_by_role("button", name=tool).click()
        (ax, ay), (bx, by) = spots[tool]
        await page.mouse.move(box["x"] + box["width"] * ax, box["y"] + box["height"] * ay)
        await page.mouse.down()
        await page.mouse.move(box["x"] + box["width"] * bx, box["y"] + box["height"] * by, steps=8)
        await page.mouse.up()
    if shot:
        await page.screenshot(path=f"{SHOTS}/{shot}")
    await marker.get_by_role("button", name="Use this picture").click()
    await expect(marker).to_be_hidden(timeout=SLOW)


async def one(browser: Browser, name: str, width: int, model: str) -> list[str]:
    tag = f"{name}-{width}-{model}"
    ctx = await browser.new_context(viewport={"width": width, "height": 900})
    page = await ctx.new_page()
    page.set_default_timeout(SLOW)
    errors: list[str] = []
    posts: list[tuple[str, Any]] = []
    page.on("pageerror", lambda e: errors.append(f"{tag}: {e}"))

    def on_request(r: Any) -> None:
        if r.method == "POST" and "/api/desk/" in r.url:
            body = None
            if "json" in (r.headers.get("content-type") or ""):
                body = json.loads(r.post_data or "{}")
            posts.append((r.url.split("/api/desk/")[1], body))

    page.on("request", on_request)
    await page.goto(URL)
    await page.get_by_label("User name").fill(USER)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible()
    await page.goto(f"{URL}/#/desk/{model}")
    actions = page.locator(".d-actions")
    # the 3D view, or (no WebGL, as Firefox in this container) its message: the card stays
    await expect(
        page.locator(".d-card .d-3d canvas, .d-card .d-3d .gl-error").first
    ).to_be_visible()
    gl = await page.locator(".d-card .d-3d canvas").count() > 0
    await page.wait_for_timeout(5000)  # the 3D files load

    # the reject dialog, and its Pictures row in sight without scrolling
    await actions.get_by_role("button", name="✕ Reject").click()
    await page.wait_for_timeout(1200)  # the dialog scrolls itself into view
    await page.screenshot(path=f"{SHOTS}/{tag}-1-reject.png")
    assert await in_sight(page, ".d-reject .d-pics-bar"), f"{tag}: Pictures row off the screen"
    reject = page.locator(".d-reject")
    tray = reject.locator(".d-pics-list li")
    await reject.get_by_role("button", name="Snapshot 3D").click()
    if gl:
        await mark(page, ["Arrow", "Circle", "Line"], f"{tag}-2-marker-3d.png")
    else:  # said in the Pictures block, not silent
        await expect(reject.locator(".d-pics-note").last).to_contain_text("WebGL")
    await reject.get_by_role("button", name="Snapshot drawing").click()
    await mark(page, ["Circle"])
    async with page.expect_file_chooser() as chooser:
        await reject.get_by_role("button", name="Upload…").click()
    await (await chooser.value).set_files(PICTURE)
    await mark(page, ["Line"])
    await page.evaluate(PUT_FILE, ["pasted", TINY])
    await mark(page, ["Circle"])
    await page.evaluate(PUT_FILE, ["dropped", TINY])
    await mark(page, [])
    want = 5 if gl else 4
    await expect(tray).to_have_count(want)
    await reject.locator(".d-chips").get_by_role("button", name="shape").click()
    await reject.locator("textarea").fill(f"browser check {tag}")
    await page.screenshot(path=f"{SHOTS}/{tag}-3-ready.png")
    await reject.get_by_role("button", name="Reject", exact=True).click()
    await expect(page.locator(".d-msg")).to_have_text("Rejected")
    uploads = [p for p in posts if p[0].endswith("/pictures")]
    assert uploads, f"{tag}: no POST .../pictures"
    act = [b for u, b in posts if u == model and b and b.get("action") == "reject"][-1]
    assert len(act["pictures"]) == want, f"{tag}: the reject names {act['pictures']}"

    # a correction with a picture
    await page.goto(f"{URL}/#/desk/{model}")
    await page.reload()
    fix = page.locator(".dc")
    await expect(fix).to_be_visible()
    await fix.get_by_role("button", name="Shape", exact=True).click()
    await fix.get_by_role("button", name="round front").click()
    await fix.get_by_role("button", name="Snapshot drawing").click()
    await mark(page, ["Arrow"])
    await expect(fix.locator(".d-pics-list li")).to_have_count(1)
    await fix.get_by_role("button", name="Save", exact=True).click()
    await expect(fix.locator(".dc-msg")).to_contain_text("Shape noted")
    corr = [b for u, b in posts if u == f"{model}/correct" and b][-1]
    assert len(corr["pictures"]) == 1, f"{tag}: the correction names {corr['pictures']}"

    # the history: thumbnails that load
    thumbs = page.locator(".d-timeline .d-thumbs img")
    await expect(thumbs.nth(want)).to_be_attached()  # the reject's, and 1 with the correction
    sizes = await page.evaluate(
        """async () => Promise.all(
            [...document.querySelectorAll('.d-timeline .d-thumbs img')].map(async i => {
                const r = await fetch(i.src);
                return [r.status, (await r.blob()).size];
            }))"""
    )
    assert len(sizes) >= want + 1 and all(s == 200 and n > 500 for s, n in sizes), f"{tag}: {sizes}"
    await page.locator(".d-panel", has_text="History").screenshot(
        path=f"{SHOTS}/{tag}-4-history.png"
    )
    await ctx.close()
    print(f"{tag}: ok ({len(uploads)} uploads, {len(sizes)} thumbnails, WebGL {gl})", flush=True)
    return errors


async def blocked(browser: Browser, model: str) -> None:
    """A browser that will not read a canvas back (privacy settings, policies): the Pictures
    block says so, and a failing snapshot says so too; nothing fails silently."""
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    await ctx.add_init_script(
        """HTMLCanvasElement.prototype.toBlob = function (cb) { cb(null); };
           HTMLCanvasElement.prototype.toDataURL = function () {
               throw new DOMException("The operation is insecure.", "SecurityError"); };"""
    )
    page = await ctx.new_page()
    await page.goto(URL)
    await page.get_by_label("User name").fill(USER)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible()
    await page.goto(f"{URL}/#/desk/{model}")
    await expect(
        page.locator(".d-card .d-3d canvas, .d-card .d-3d .gl-error").first
    ).to_be_visible()
    await page.wait_for_timeout(3000)
    await page.locator(".d-actions").get_by_role("button", name="✕ Reject").click()
    reject = page.locator(".d-reject")
    await expect(reject.locator(".d-pics-note").first).to_contain_text("Pictures need Chrome")
    await reject.get_by_role("button", name="Snapshot 3D").click()
    await expect(reject.locator(".d-pics-note").last).to_contain_text("3D")
    await page.screenshot(path=f"{SHOTS}/blocked-canvas.png")
    await ctx.close()
    print("blocked canvas: the Pictures block says so", flush=True)


async def launch(p: Playwright, name: str) -> Browser:
    if name == "chromium":
        return await p.chromium.launch(args=["--enable-unsafe-swiftshader"])
    if name == "msedge":  # real Microsoft Edge: `playwright install msedge` in the image first
        return await p.chromium.launch(channel="msedge", args=["--enable-unsafe-swiftshader"])
    return await getattr(p, name).launch()


async def main() -> int:
    expect.set_options(timeout=SLOW)
    errors: list[str] = []
    failed: list[str] = []
    async with async_playwright() as p:
        for name in BROWSERS:
            browser = await launch(p, name)
            if name == BROWSERS[0]:
                try:
                    await blocked(browser, MODELS[0])
                except Exception as exc:  # noqa: BLE001
                    failed.append(f"blocked canvas: {str(exc)[:600]}")
                    print(f"blocked canvas: FAILED {str(exc)[:600]}", flush=True)
            for width in WIDTHS:
                for model in MODELS:
                    try:
                        errors += await one(browser, name, width, model)
                    except Exception as exc:  # noqa: BLE001 - report every combination
                        failed.append(f"{name}-{width}-{model}: {str(exc)[:600]}")
                        print(f"{name}-{width}-{model}: FAILED {str(exc)[:600]}", flush=True)
            await browser.close()
    if errors:
        print("page errors:", errors)
    if failed or errors:
        return 1
    print("desk pictures: ok")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
