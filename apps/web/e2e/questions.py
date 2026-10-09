"""Browser check of the Desk's Questions tab (ADR-109), the way Rens answers, in Chromium,
WebKit (Safari, iPad), Firefox and Microsoft Edge (with corporate policies), wide and on a
tablet.

Per browser and width, as Rens (an approver): the Desk shows the tabs, with the badge of open
questions; the Questions tab lists them, the topic filter narrows the list; a question shows its
covers (links to their Desk cards), its pictures and Wouter's answer. Keyboard: "2" chooses the
second option and brings the answer form into view, with its Pictures block on the screen (the
lesson of ADR-096); a question picture is marked in red, a file is uploaded and marked, a
comment typed, Ctrl+Enter sends (POST .../pictures, then the answer naming them); the answer
shows with its thumbnails, which load. "j" moves to the next question, "/" to the search.
Then, once: Vic (a viewer) sees no answer form; Rick (the owner) marks an answer final and the
question processed, and it moves to "Processed".

Run against a running studio with a scratch data copy (never the live data), users rens, rick,
vic with the password below, and the questions imported (scripts/questions.py import):

    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/questionstest:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:18191 \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/questions.py"

Edge: the image `desk-edge` (Playwright's image with `playwright install msedge`), with
COVER_E2E_BROWSERS=msedge and a policy file mounted at /etc/opt/edge/policies/managed/
(apps/web/e2e/edge-policies.json: no hardware acceleration, clipboard blocked, strict
tracking prevention, as a locked-down office PC).
"""

import asyncio
import os
import sys
from typing import Any

from playwright.async_api import Browser, Page, Playwright, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18191")
BROWSERS = os.environ.get("COVER_E2E_BROWSERS", "chromium,webkit,firefox").split(",")
WIDTHS = [
    tuple(int(x) for x in w.split("x"))
    for w in os.environ.get("COVER_E2E_SIZES", "1440x900,820x1180").split(",")
]
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
QUESTION = os.environ.get("COVER_E2E_QUESTION", "S45: de band in één stuk")
SLOW = 60_000


async def login(browser: Browser, user: str, size: tuple[int, ...]) -> tuple[Any, Page]:
    ctx = await browser.new_context(viewport={"width": size[0], "height": size[1]})
    page = await ctx.new_page()
    page.set_default_timeout(SLOW)
    await page.goto(URL)
    await page.get_by_label("User name").fill(user)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible()
    return ctx, page


async def pick(page: Page) -> None:
    """The test's question, under "All" (it has an answer, so it is no longer "Open")."""
    await page.get_by_role("group", name="Status").get_by_role("button", name="All").click()
    await page.locator(".q-list li a", has_text=QUESTION).click()


async def in_sight(page: Page, selector: str) -> bool:
    """On the screen and not covered (by the header or the list above it on a tablet)."""
    return bool(
        await page.evaluate(
            """(s) => { const el = document.querySelector(s);
                        const b = el?.getBoundingClientRect();
                        if (!b || b.top < 0 || b.bottom > innerHeight) return false;
                        const hit = document.elementFromPoint(b.left + 30, b.top + b.height / 2);
                        return !!hit && el.contains(hit); }""",
            selector,
        )
    )


async def mark(page: Page, shot: str | None = None) -> None:
    marker = page.get_by_role("dialog", name="Mark the picture")
    try:
        await expect(marker).to_be_visible()
    except AssertionError:
        notes = await page.locator(".d-pics-note").all_text_contents()
        raise AssertionError(f"no marking editor; the page says {notes}") from None
    canvas = marker.locator("canvas")
    await expect(canvas).to_be_visible()
    await page.wait_for_timeout(300)
    box = await canvas.bounding_box()
    assert box
    await marker.get_by_role("button", name="Circle").click()
    await page.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] * 0.3)
    await page.mouse.down()
    await page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.7, steps=8)
    await page.mouse.up()
    if shot:
        await page.screenshot(path=f"{SHOTS}/{shot}")
    await marker.get_by_role("button", name="Use this picture").click()
    await expect(marker).to_be_hidden()


async def as_rens(browser: Browser, name: str, size: tuple[int, ...]) -> list[str]:
    tag = f"{name}-{size[0]}"
    ctx, page = await login(browser, "rens", size)
    errors: list[str] = []
    posts: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"{tag}: {e}"))
    page.on(
        "request",
        lambda r: (
            posts.append(r.url.split("/api/")[1])
            if r.method == "POST" and "/api/questions/" in r.url
            else None
        ),
    )

    # the Desk's tabs, the badge on Questions
    await page.goto(f"{URL}/#/desk")
    tabs = page.get_by_role("navigation", name="Desk")
    badge = tabs.locator(".d-badge")
    await expect(badge).to_be_visible()
    open_n = int(await badge.inner_text())
    assert open_n > 0, f"{tag}: badge {open_n}"
    await tabs.screenshot(path=f"{SHOTS}/{tag}-1-tabs.png")
    await tabs.get_by_role("link", name="Questions").click()
    await expect(page.get_by_role("heading", name="Questions", exact=True)).to_be_visible()
    rows = page.locator(".q-list li a")
    await expect(rows.first).to_be_visible()
    assert await rows.count() == open_n, f"{tag}: {await rows.count()} rows, badge {open_n}"
    await page.screenshot(path=f"{SHOTS}/{tag}-2-list.png")

    # the topic filter
    await page.get_by_role("group", name="Topic").get_by_role("button", name="vents").click()
    await expect(rows.first).to_be_visible()
    subs = await page.locator(".q-list .d-row-sub").all_inner_texts()
    assert subs and all("vents" in s for s in subs), f"{tag}: vents filter shows {subs}"
    await page.get_by_role("group", name="Topic").get_by_role("button", name="vents").click()

    # one question: covers, pictures, Wouter's answer
    await pick(page)
    card = page.locator(".q-card")
    await expect(card.get_by_role("heading", level=2)).to_contain_text(QUESTION)
    await expect(card.locator(".q-covers a").first).to_have_attribute("href", "#/desk/drawing-s45")
    await expect(card.locator(".q-answers li", has_text="Wouter")).to_be_visible()
    await page.screenshot(path=f"{SHOTS}/{tag}-3-question.png", full_page=True)

    # keyboard: "2" chooses, the form comes into view with its Pictures block on the screen
    await page.locator("body").click(position={"x": 5, "y": 5})
    await page.keyboard.press("2")
    radios = card.locator(".q-options input[type=radio]")
    await expect(radios.nth(1)).to_be_checked()
    await page.wait_for_timeout(600)
    assert await in_sight(page, ".q-form .d-pics-bar"), f"{tag}: Pictures row off the screen"
    form = card.locator(".q-form")
    marks = form.get_by_role("button", name="Mark S45")
    if await marks.count():
        await marks.click()
        await mark(page, f"{tag}-4-marker.png")
    async with page.expect_file_chooser() as chooser:
        await form.get_by_role("button", name="Upload…").click()
    await (await chooser.value).set_files(
        files=[{"name": "photo.png", "mimeType": "image/png", "buffer": _png()}]
    )
    await mark(page)
    want = 2 if await marks.count() else 1
    await expect(form.locator(".d-pics-list li")).to_have_count(want)
    comment = form.get_by_label("Comment")
    await comment.fill(f"browser check {tag}")
    await page.screenshot(path=f"{SHOTS}/{tag}-5-ready.png")
    await comment.press("Control+Enter")
    await expect(form.locator(".d-msg")).to_contain_text("your answer is saved")
    assert any(p.endswith("/pictures") for p in posts), f"{tag}: no picture upload {posts}"
    assert any(p.endswith("/answer") for p in posts), f"{tag}: no answer sent {posts}"
    mine = card.locator(".q-answers li", has_text="Rens")
    await expect(mine).to_contain_text("b)")
    await expect(mine.locator(".d-thumbs img")).to_have_count(want)
    sizes = await page.evaluate(
        """async () => Promise.all(
            [...document.querySelectorAll('.q-answers .d-thumbs img')].map(async i => {
                const r = await fetch(i.src); return [r.status, (await r.blob()).size]; }))"""
    )
    assert all(s == 200 and n > 100 for s, n in sizes), f"{tag}: thumbnails {sizes}"
    await card.locator(".q-answers").screenshot(path=f"{SHOTS}/{tag}-6-answered.png")

    # j: the next question; /: the search
    before = page.url
    await page.locator("body").click(position={"x": 5, "y": 5})
    await page.keyboard.press("j")
    await expect(page).not_to_have_url(before)
    await page.keyboard.press("/")
    assert await page.evaluate("document.activeElement?.type") == "search", f"{tag}: / no search"
    await ctx.close()
    print(f"{tag}: ok ({len(posts)} posts, {len(sizes)} thumbnails)", flush=True)
    return errors


async def as_vic_and_rick(browser: Browser, name: str) -> None:
    ctx, page = await login(browser, "vic", (1440, 900))
    await page.goto(f"{URL}/#/questions")
    await pick(page)
    await expect(page.locator(".q-card .q-answers")).to_be_visible()
    assert await page.locator(".q-form").count() == 0, "a viewer sees an answer form"
    await ctx.close()

    ctx, page = await login(browser, "rick", (1440, 900))
    await page.goto(f"{URL}/#/questions")
    await pick(page)
    card = page.locator(".q-card")
    rens = card.locator(".q-answers li", has_text="Rens")
    await rens.get_by_role("button", name="Mark final").click()
    await expect(rens.locator(".q-final")).to_be_visible()
    await card.get_by_label("What was done").fill(
        "S45: de band in één stuk gemaakt (browser check)"
    )
    await card.get_by_role("button", name="Mark processed").click()
    await expect(card.locator(".q-note-done")).to_contain_text("in één stuk")
    await page.screenshot(path=f"{SHOTS}/{name}-7-owner.png", full_page=True)
    await page.get_by_role("group", name="Status").get_by_role("button", name="Processed").click()
    await expect(page.locator(".q-list li a", has_text=QUESTION)).to_be_visible()
    await card.get_by_role("button", name="Reopen").click()  # for the next browser
    await expect(card.locator(".q-note-done")).to_have_count(0)
    await ctx.close()
    print(f"{name}: viewer read-only, owner final + processed: ok", flush=True)


def _png(w: int = 160, h: int = 120) -> bytes:
    """A small sand-coloured PNG, made here (no Pillow in the browser image)."""
    import struct
    import zlib

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(b"\x00" + bytes((196, 176, 142)) * w for _ in range(h))
    head = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head)
    return png + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


async def launch(p: Playwright, name: str) -> Browser:
    if name == "chromium":
        return await p.chromium.launch()
    if name == "msedge":
        return await p.chromium.launch(channel="msedge")
    return await getattr(p, name).launch()


async def edge_policies(browser: Browser) -> None:
    """The policies Edge applied, as edge://policy shows them (a screenshot for the record)."""
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    try:
        await page.goto("edge://policy")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{SHOTS}/msedge-0-policies.png", full_page=True)
        text = await page.locator("body").inner_text()
        print("edge policies applied:", "HardwareAccelerationModeEnabled" in text, flush=True)
    except Exception as exc:  # noqa: BLE001 - a record, not a check
        print(f"edge://policy not shown: {str(exc)[:200]}", flush=True)
    await ctx.close()


async def main() -> int:
    expect.set_options(timeout=SLOW)
    errors: list[str] = []
    failed: list[str] = []
    async with async_playwright() as p:
        for name in BROWSERS:
            browser = await launch(p, name)
            if name == "msedge":
                await edge_policies(browser)
            for size in WIDTHS:
                try:
                    errors += await as_rens(browser, name, size)
                except Exception as exc:  # noqa: BLE001 - report every combination
                    failed.append(f"{name}-{size[0]}: {str(exc)[:600]}")
                    print(f"{name}-{size[0]}: FAILED {str(exc)[:600]}", flush=True)
            try:
                await as_vic_and_rick(browser, name)
            except Exception as exc:  # noqa: BLE001
                failed.append(f"{name} owner: {str(exc)[:600]}")
                print(f"{name} owner: FAILED {str(exc)[:600]}", flush=True)
            await browser.close()
    if errors:
        print("page errors:", errors)
    if failed or errors:
        return 1
    print("questions: ok")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
