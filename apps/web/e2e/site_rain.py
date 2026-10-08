"""The rain on the scroll page keeps moving (ADR-106). The owner (8 Oct 2026): "the rain on the
scroll page stops moving".

In a real browser: scroll with the wheel (Lenis) down to the rain chapter, and check that the
picture there keeps changing, on its own, while nobody scrolls:

1. right after arriving;
2. after standing still for SITE_RAIN_WAIT seconds (default 8);
3. after scrolling up out of the chapter and back down;
4. after the tab was in the background (frozen) and came back;
5. on a phone (390 px);
and, with the device asking for less motion, that the chapter shows without errors (the rain
then stands still, by design).

The film grain over the pictures (CSS, not a canvas) does not count: only the canvases are read.
Against a local build (site_serve.mjs) or the preview:

    node apps/web/e2e/site_serve.mjs --port 18300 &
    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/sitepolish:/shots" \\
      -e SITE_URL=http://127.0.0.1:18300/ mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/site_rain.py"

Exit status 0 when the rain moves in every case. A frame strip of the rain is written to
/shots/rain-*.png.
"""

import asyncio
import os
import sys

from playwright.async_api import BrowserContext, Page, async_playwright

URL = os.environ.get("SITE_URL", "https://preview.s2dio.living/")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
WAIT = float(os.environ.get("SITE_RAIN_WAIT", "8"))
RAIN_AT = 0.93  # how far through the story's chapters the rain is well under way
MOVING = 0.002  # at least this share of the pixels changes between two looks 0.4 s apart

NO_GRAIN = ".st-scene::after { animation: none !important; opacity: 0 !important; }"

# What the visitor sees of the scene is drawn on the canvases in the pinned section (the rendered
# frames, and the rain over them). Each look keeps a small copy of every visible canvas; the
# answer is the share of pixels that changed clearly since the last look. Reading the canvases is
# cheap; a screenshot of a page that keeps moving takes very long in a software-drawn browser.
LOOK = """
() => {
  const now = [];
  for (const c of document.querySelectorAll(".st-pinned canvas")) {
    const s = getComputedStyle(c);
    const r = c.getBoundingClientRect();
    const hidden = s.display === "none" || s.visibility === "hidden" || +s.opacity === 0;
    if (!r.width || !r.height || hidden) continue;
    if (r.bottom <= 0 || r.top >= innerHeight) continue;
    const small = document.createElement("canvas");
    small.width = 480;
    small.height = Math.max(1, Math.round((480 * c.height) / Math.max(c.width, 1)));
    const x = small.getContext("2d");
    try {
      x.drawImage(c, 0, 0, small.width, small.height);
      now.push(x.getImageData(0, 0, small.width, small.height).data);
    } catch (e) {}
  }
  const before = window.__look || [];
  window.__look = now;
  let changed = 0, total = 0;
  now.forEach((A, k) => {
    const B = before[k];
    total += A.length / 4;
    if (!B || B.length !== A.length) return;
    for (let i = 0; i < A.length; i += 4) {
      const d = Math.abs(A[i] - B[i]) + Math.abs(A[i + 1] - B[i + 1]) +
        Math.abs(A[i + 2] - B[i + 2]) + Math.abs(A[i + 3] - B[i + 3]);
      if (d > 24) changed++;
    }
  });
  return total ? changed / total : 0;
}
"""


async def scroll_to(page: Page, share: float) -> None:
    """Wheel (as a visitor does, through Lenis) to `share` of the story's chapters."""
    target = await page.evaluate(
        """(s) => { const el = document.querySelector('.st-chapters');
        const top = el.getBoundingClientRect().top + window.scrollY;
        return top + s * (el.offsetHeight - window.innerHeight); }""",
        share,
    )
    for _ in range(200):
        y = await page.evaluate("window.scrollY")
        gap = target - y
        if abs(gap) < 40:
            break
        await page.mouse.wheel(0, max(-500, min(500, gap)))
        await page.wait_for_timeout(60)
    await page.wait_for_timeout(1200)  # the smooth scroll settles


async def motion(page: Page, name: str, looks: int = 4) -> float:
    """The smallest change between successive looks at the pinned scene, 0.4 s apart."""
    await page.evaluate("window.__look = null")
    await page.evaluate(LOOK)
    changes = []
    for _ in range(looks - 1):
        await page.wait_for_timeout(400)
        changes.append(await page.evaluate(LOOK))
    try:  # a picture for the strip; may be slow while the page keeps moving
        await page.screenshot(path=f"{SHOTS}/rain-{name}.png", timeout=90000)
    except Exception as e:  # noqa: BLE001 - the picture is a courtesy, the numbers are the test
        print(f"  (no picture for {name}: {str(e)[:60]})")
    return min(changes)


async def open_story(ctx: BrowserContext, errors: list[str]) -> Page:
    page = await ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.goto(URL)
    await page.wait_for_selector(".st-chapters", timeout=30000)
    await page.add_style_tag(content=NO_GRAIN)
    await page.wait_for_timeout(1500)
    return page


async def main() -> int:
    errors: list[str] = []
    results: list[tuple[str, float, bool]] = []

    def check(name: str, value: float, want_moving: bool = True) -> None:
        ok = value >= MOVING if want_moving else True
        results.append((name, value, ok))
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {value * 100:.2f} % of the pixels change")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"]
        )
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await open_story(ctx, errors)
        await scroll_to(page, RAIN_AT)
        check("arrived in the rain", await motion(page, "1-arrived"))
        await page.wait_for_timeout(WAIT * 1000)
        check(f"after {WAIT:.0f} s standing still", await motion(page, "2-standing"))
        await scroll_to(page, 0.45)
        await scroll_to(page, RAIN_AT)
        check("scrolled up and back down", await motion(page, "3-back"))
        # the tab in the background: frozen as browsers do, then another tab in front
        cdp = await ctx.new_cdp_session(page)
        await cdp.send("Page.setWebLifecycleState", {"state": "frozen"})
        await asyncio.sleep(3)
        await cdp.send("Page.setWebLifecycleState", {"state": "active"})
        other = await ctx.new_page()
        await other.goto("about:blank")
        await other.bring_to_front()
        await asyncio.sleep(2)
        await other.close()
        await page.bring_to_front()
        await page.wait_for_timeout(800)
        check("back from a background tab", await motion(page, "4-tab"))
        await ctx.close()

        phone = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        )
        page = await open_story(phone, errors)
        # a phone scrolls by touch; the page scrolls itself there
        target = await page.evaluate(
            """(s) => { const el = document.querySelector('.st-chapters');
            return el.getBoundingClientRect().top + window.scrollY
              + s * (el.offsetHeight - window.innerHeight); }""",
            RAIN_AT,
        )
        for k in range(1, 21):
            await page.evaluate(f"window.scrollTo(0, {target * k / 20})")
            await page.wait_for_timeout(50)
        await page.wait_for_timeout(1500)
        check("on a phone", await motion(page, "5-phone"))
        await page.wait_for_timeout(WAIT * 1000)
        check(f"on a phone after {WAIT:.0f} s", await motion(page, "6-phone-standing"))
        await phone.close()

        calm = await browser.new_context(
            viewport={"width": 1440, "height": 900}, reduced_motion="reduce"
        )
        page = await open_story(calm, errors)
        target = await page.evaluate(
            """(s) => { const el = document.querySelector('.st-chapters');
            return el.getBoundingClientRect().top + window.scrollY
              + s * (el.offsetHeight - window.innerHeight); }""",
            RAIN_AT,
        )
        await page.evaluate(f"window.scrollTo(0, {target})")
        await page.wait_for_timeout(1500)
        check("less motion asked (shown, may stand still)", await motion(page, "7-calm"), False)
        await calm.close()
        await browser.close()

    for e in errors:
        print("page error:", e)
    failed = [r for r in results if not r[2]]
    return 1 if failed or errors else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
