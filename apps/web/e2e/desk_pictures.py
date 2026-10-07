"""Browser check of the Desk's pictures (ADR-096): Rens rejects a cover with a marked snapshot
of the 3D view, a marked page of the drawing, an uploaded file, a pasted and a dropped picture,
then comments with one picture, and sees them as thumbnails in the history.

Run against a running studio with a scratch data copy holding drawing-s45 and a user "rens":

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/desktest:/shots" \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/desk_pictures.py"
"""

import asyncio
import os
import sys

from playwright.async_api import Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18182")
MODEL = os.environ.get("COVER_E2E_MODEL", "drawing-s45")
USER = os.environ.get("COVER_E2E_USER", "rens")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
PICTURE = os.environ.get("COVER_E2E_PICTURE", f"{SHOTS}/upload-sample.jpg")  # a photo to upload
# a small red-and-white PNG, made here so the paste and the drop need no file
TINY = (
    "iVBORw0KGgoAAAANSUhEUgAAAKAAAAB4CAIAAAD6wG44AAAC6ElEQVR42u3dS0hUURyA8XPuXK+z"
    "yAe5CyezlBnNJ1qDjpnag6hBskSpwGgWUkLSIlwVEgVFRQtrZeAmcmrM8I1gubBBNKUwU6YHpqMp"
    "1iLJYlzc5rYwWrQxAmmU71udzb0Xzo8/nM3hyu8LU4LWbwpbADABTAATwAQwAUwAA0wAE8AEMAFM"
    "ABPAABPABDABTAATwAQwAQwwAUwAE8AEMAFMf6au3qsv19Wxv3/fxepqJpgAJoABJoAJYAKYACaA"
    "CWCACWACmAAmgAlgApgABpgAJoAJ4JUrcBShtZ6BdwP8T6n/8du1NVeGXgxYYuOEITytbi1MKzlU"
    "ajabh18+9w725e7Iy87YaQij+2lnnCVe0zTXiUp3873iAyURGyJMJrWrp3161g9h6AKrJnVmbqbr"
    "SUdmapZzf/Hit8Xu3s5Pn+fPnT7vHewryt974/bVyMioQsceT6vbYd/VcL/+qLOsf8g7/dEfHRVd"
    "Ue6qq78FYegCG8IY840KIUbHRw7uc968cy0tJSMpMTk83CyEePPOV3b42MBwv6fV/fuRxG3WmI0x"
    "y2stTFOkEjSCKIYqsGEYQWN5res/jpdWvPa96h/y2rNzhRBNbQ/iN2912PPTUzIftT38dWRQlIbG"
    "u7quSym3WOLRDelDlqIo1kSbECI1OX1i8n3sJsvo2Iiqhqkm1RxurjxZ5Z+Z8rQ0WhOShBBSSinl"
    "1PSH7bZUIYQ1wVaQx7ErtCdY1/UUW1p+TmFgKdDc7ln4+uXMqbNz87OBpYCu676341Wuaill77Me"
    "IcSkf6Ki3NXS1XzEWWrPygkGg487mvBbMbl6/y5c8XZhbc2VS9cvYLActwtprQEzvuscmAAmgAlg"
    "gAlgApgAJoAJYAKYAAaYACaACWACmAAmgAEmgAlgApgAJoAJYIAJYFq7reL1UWKCCWACmAAGmAAm"
    "gAlgApgAJoAJYIAJYAKYACaACWACGGACmAAmgAlgApgABpgAprXaTz0+wIR8eBCtAAAAAElFTkSu"
    "QmCC"
)


async def drag(page: Page, box: dict, a: tuple[float, float], b: tuple[float, float]) -> None:
    x0, y0 = box["x"] + box["width"] * a[0], box["y"] + box["height"] * a[1]
    x1, y1 = box["x"] + box["width"] * b[0], box["y"] + box["height"] * b[1]
    await page.mouse.move(x0, y0)
    await page.mouse.down()
    for k in range(1, 9):
        await page.mouse.move(x0 + (x1 - x0) * k / 8, y0 + (y1 - y0) * k / 8 + (k % 2) * 3)
    await page.mouse.up()


async def mark(page: Page, shot: str, tools: list[str]) -> None:
    marker = page.get_by_role("dialog", name="Mark the picture")
    await expect(marker).to_be_visible()
    canvas = marker.locator("canvas")
    await page.wait_for_timeout(300)
    box = await canvas.bounding_box()
    assert box
    for tool in tools:
        await marker.get_by_role("button", name=tool).click()
        if "Arrow" in tool:
            await drag(page, box, (0.15, 0.15), (0.45, 0.45))
        elif "Circle" in tool:
            await drag(page, box, (0.5, 0.3), (0.8, 0.7))
        else:
            await drag(page, box, (0.2, 0.8), (0.7, 0.85))
    await page.screenshot(path=f"{SHOTS}/{shot}")
    await marker.get_by_role("button", name="Use this picture").click()
    await expect(marker).to_be_hidden()


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(URL)
        await page.get_by_label("User name").fill(USER)
        await page.get_by_label("Password").fill(PASSWORD)
        await page.get_by_role("button", name="Log in").click()
        await page.wait_for_timeout(1500)
        await page.goto(f"{URL}/#/desk/{MODEL}")
        card = page.locator(".d-card")
        await expect(card.locator(".d-3d canvas")).to_be_visible(timeout=30_000)
        await page.wait_for_timeout(4000)  # the 3D files load
        await page.screenshot(path=f"{SHOTS}/1-card.png")

        # reject: reason, words, then the pictures
        await page.get_by_role("button", name="✕ Reject").click()
        await page.locator(".d-reject .d-chips").get_by_role("button", name="shape").click()
        await page.locator(".d-reject textarea").fill("Front must be round, see the arrow")
        await page.get_by_role("button", name="Snapshot 3D").click()
        await mark(page, "2-marker-3d.png", ["➚ Arrow", "◯ Circle", "✎ Line"])
        await page.get_by_role("button", name="Snapshot drawing").click()
        await mark(page, "3-marker-drawing.png", ["◯ Circle", "➚ Arrow"])
        await page.set_input_files("input[aria-label='Upload a picture']", PICTURE)
        await mark(page, "4-marker-upload.png", ["✎ Line"])
        # paste (Ctrl+V) and drop: the same events a browser sends
        await page.evaluate(
            """(b64) => {
                const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                const f = new File([bytes], "pasted.png", {type: "image/png"});
                const dt = new DataTransfer(); dt.items.add(f);
                window.dispatchEvent(new ClipboardEvent("paste", {clipboardData: dt}));
            }""",
            TINY,
        )
        await mark(page, "5-marker-paste.png", ["◯ Circle"])
        await page.evaluate(
            """(b64) => {
                const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
                const f = new File([bytes], "dropped.png", {type: "image/png"});
                const dt = new DataTransfer(); dt.items.add(f);
                const zone = document.querySelector(".d-pics");
                zone.dispatchEvent(new DragEvent("dragover", {dataTransfer: dt, bubbles: true}));
                zone.dispatchEvent(new DragEvent("drop", {dataTransfer: dt, bubbles: true}));
            }""",
            TINY,
        )
        await mark(page, "6-marker-drop.png", [])
        await expect(page.locator(".d-pics-list li")).to_have_count(5)
        await page.locator(".d-actions").screenshot(path=f"{SHOTS}/7-reject-with-pictures.png")
        await page.locator(".d-reject").get_by_role("button", name="Reject").click()
        await expect(page.locator(".d-msg")).to_have_text("Rejected", timeout=15_000)

        # back to the card: the history shows the five pictures
        await page.goto(f"{URL}/#/desk/{MODEL}")
        await page.reload()
        thumbs = page.locator(".d-timeline .d-thumbs img")
        await expect(thumbs).to_have_count(5, timeout=15_000)
        # a comment with one picture
        await page.get_by_role("button", name="Comment").click()
        await page.locator(".d-reject textarea").fill("Seam at the back is 3 cm too low")
        await page.get_by_role("button", name="Snapshot 3D").click()
        await mark(page, "8-marker-comment.png", ["➚ Arrow"])
        await page.get_by_role("button", name="Save comment").click()
        await expect(page.locator(".d-msg")).to_have_text("Comment saved", timeout=15_000)
        await expect(thumbs).to_have_count(6, timeout=15_000)
        hist = page.locator(".d-panel", has_text="History")
        await hist.scroll_into_view_if_needed()
        await hist.screenshot(path=f"{SHOTS}/9-history.png")
        await thumbs.first.click()
        await expect(page.locator(".d-zoom img")).to_be_visible()
        await page.wait_for_timeout(500)
        await page.screenshot(path=f"{SHOTS}/10-zoom.png")
        await page.locator(".d-zoom").click()
        # each picture is a real image, served to the logged-in user
        sizes = await page.evaluate(
            """async () => Promise.all(
                [...document.querySelectorAll('.d-timeline .d-thumbs img')].map(async i => {
                    const r = await fetch(i.src);
                    return [r.status, (await r.blob()).size];
                }))"""
        )
        print("pictures:", sizes)
        assert all(s == 200 and n > 500 for s, n in sizes), sizes
        await browser.close()
        if errors:
            print("page errors:", errors)
            return 1
        print("desk pictures: ok")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
