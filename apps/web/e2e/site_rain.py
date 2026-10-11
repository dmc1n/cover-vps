"""The rain on the scroll page falls, always down, and never stands still (ADR-106, ADR-120).

The owner (8 Oct 2026): "the rain on the scroll page stops moving"; (9 Oct): "when scrolling we
still have the static rain". The story's pictures are scrubbed by the scroll, so a drop baked
into them stood still while reading and rose when scrolling up. Now the pictures carry only the
wet look and every falling drop is drawn by RainLayer in time.

In a real browser: scroll with the wheel (Lenis) down to the rain chapter and check

1. the rendered picture there holds no rain streaks of its own (a thin-bright-line detector on
   the frames' canvas, at three places in the chapter; the old pictures with baked rain score
   0.2-0.3 %, clean ones under 0.1 %);
2. the rain moves on its own, while nobody scrolls: right after arriving, after standing still
   for SITE_RAIN_WAIT seconds (default 8), after scrolling away and back, after the tab was in
   the background;
3. while the visitor scrolls up and while he scrolls down, the drops move down: on a clock the
   test steps 16 ms at a time, each short streak's lower end is looked for a frame later in its
   column; nearly all are found lower, almost none higher;
4. on a phone (390 px) it moves too;
5. with the device asking for less motion, the chapter shows without errors (no falling rain
   then, by design).

The film grain over the pictures (CSS, not a canvas) does not count: only the canvases are read.
Against a local build (site_serve.mjs, with --media for renders not yet on the website) or the
preview:

    node apps/web/e2e/site_serve.mjs --port 18300 [--media out/storyrender/media \\
        --settings '{"story_media": {...}}'] &
    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/storyrender:/shots" \\
      -e SITE_URL=http://127.0.0.1:18300/ mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q playwright==1.63.0 && python /repo/apps/web/e2e/site_rain.py"

Exit status 0 when every check holds. Pictures of the rain are written to /shots/rain-*.png.
"""

import asyncio
import os
import sys

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

URL = os.environ.get("SITE_URL", "https://preview.s2dio.living/")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
WAIT = float(os.environ.get("SITE_RAIN_WAIT", "8"))
RAIN_AT = 0.93  # how far through the story's chapters the rain is well under way
RAIN_SPAN = (0.88, 0.93, 0.985)  # where the pictures are checked for baked rain
MOVING = 0.002  # at least this share of the pixels changes between two looks 0.4 s apart
BAKED = 0.0015  # at most this share of a picture's pixels on thin bright streaks

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

# The rendered picture (the canvas that is not the rain layer): the share of its pixels on a
# thin bright streak, a pixel brighter by 10 than the pixels 2 to the left and right, the line
# going on down for 3 rows (upright or leaning a pixel). Rain baked into a picture shows as such
# streaks; stone, plaster and the cover's seams hardly do.
BAKED_JS = """
() => {
  const c = [...document.querySelectorAll(".st-pinned canvas")]
    .find((x) => !x.classList.contains("st-rainfall"));
  if (!c) return -1;
  const W = 480, H = Math.max(1, Math.round((480 * c.height) / Math.max(c.width, 1)));
  const s = document.createElement("canvas");
  s.width = W; s.height = H;
  const x = s.getContext("2d");
  x.drawImage(c, 0, 0, W, H);
  const d = x.getImageData(0, 0, W, H).data;
  const L = new Float32Array(W * H);
  for (let i = 0; i < W * H; i++) L[i] = 0.299 * d[4*i] + 0.587 * d[4*i+1] + 0.114 * d[4*i+2];
  const R = new Uint8Array(W * H);
  for (let y = 0; y < H; y++)
    for (let i = 2; i < W - 2; i++) {
      const k = y * W + i;
      R[k] = L[k] - Math.max(L[k - 2], L[k + 2]) > 10 ? 1 : 0;
    }
  const near = (y, i) => R[y * W + i - 1] || R[y * W + i] || R[y * W + i + 1];
  let n = 0;
  for (let y = 0; y < H - 2; y++)
    for (let i = 3; i < W - 3; i++)
      if (R[y * W + i] && near(y + 1, i) && near(y + 2, i)) n++;
  return n / ((H - 2) * (W - 6));
}
"""

# The rain layer one frame apart while the page scrolls: where each streak's lower end (its
# head) was, and where the nearest head in the same column is a frame later. A drop that falls
# is found lower; a drop that rose would be found higher. The page runs on a clock the test
# steps (16 ms, a frame of a 60 Hz screen), so a drop moves less than the gap to the next one.
# Returns [heads found lower, heads found higher].
GRAB_JS = """
() => {
  const c = document.querySelector(".st-pinned canvas.st-rainfall");
  if (!c) return null;
  const W = c.width, H = c.height;
  const d = c.getContext("2d").getImageData(0, 0, W, H).data;
  const alpha = (x, y) => d[4 * (y * W + x) + 3];
  const heads = [];  // [x, y of the lower end, length of the streak above it]
  for (let x = 0; x < W; x++)
    for (let y = 1; y < H - 1; y++)
      if (alpha(x, y) > 14 && alpha(x, y + 1) < 5) {
        let top = y;
        while (top > 0 && alpha(x, top - 1) > 4) top--;
        heads.push([x, y, y - top]);
      }
  const prev = window.__rain;
  window.__rain = heads;
  if (!prev) return null;
  const at = new Map();
  for (const [x, y] of heads) {
    if (!at.has(x)) at.set(x, []);
    at.get(x).push(y);
  }
  // only the short (far) streaks, whole on screen: one moves less than its own length in a
  // frame, so the nearest head within that length in its column is itself
  let down = 0, up = 0;
  for (const [x, y, len] of prev) {
    if (len < 6 || len > 70 || y - len <= 0) continue;
    let best = null;
    for (const xx of [x - 1, x, x + 1])
      for (const yy of at.get(xx) || []) {
        const dy = yy - y;
        if (Math.abs(dy) <= len && (best === null || Math.abs(dy) < Math.abs(best))) best = dy;
      }
    if (best === null || Math.abs(best) < 2) continue;
    if (best > 0) down++;
    else up++;
  }
  return [down, up];
}
"""


async def chapter_y(page: Page, share: float) -> float:
    return await page.evaluate(
        """(s) => { const el = document.querySelector('.st-chapters');
        const top = el.getBoundingClientRect().top + window.scrollY;
        return top + s * (el.offsetHeight - window.innerHeight); }""",
        share,
    )


async def scroll_to(page: Page, share: float) -> None:
    """Wheel (as a visitor does, through Lenis) to `share` of the story's chapters."""
    target = await chapter_y(page, share)
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


async def falling_while_scrolling(page: Page, down: bool) -> list[int]:
    """Wheel through the rain chapter (up or down) on the stepped clock and count the heads that
    were found lower and higher, frame by frame: [lower, higher]."""
    step = 60 if down else -60
    total = [0, 0]
    await page.evaluate("window.__rain = null")
    for _ in range(8):
        await page.mouse.wheel(0, step)
        for _ in range(3):  # Lenis turns the wheel into a smooth scroll over these frames
            await page.clock.run_for(16)
            counts = await page.evaluate(GRAB_JS)
            if counts:
                total = [total[0] + counts[0], total[1] + counts[1]]
    return total


async def stepped_fall(browser: Browser, errors: list[str]) -> tuple[list[int], list[int]]:
    """The scroll test on a page whose clock the test steps."""
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.clock.install()
    await page.goto(URL)
    await page.clock.run_for(3000)
    await page.clock.pause_at(10**12)  # from here on the clock moves only when stepped
    await page.wait_for_selector(".st-chapters", timeout=30000)
    target = await chapter_y(page, 0.95)
    await page.evaluate(f"window.scrollTo(0, {target})")
    for _ in range(60):  # the scroll settles, the frames load
        await page.clock.run_for(50)
        await page.wait_for_timeout(20)
    up = await falling_while_scrolling(page, False)
    down = await falling_while_scrolling(page, True)
    await ctx.close()
    return up, down


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
    results: list[tuple[str, bool]] = []

    def check(name: str, value: float, want_moving: bool = True) -> None:
        ok = value >= MOVING if want_moving else True
        results.append((name, ok))
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {value * 100:.2f} % of the pixels change")

    def check_baked(where: float, share: float) -> None:
        ok = 0 <= share <= BAKED
        results.append((f"no baked rain at {where:.2f}", ok))
        print(f"{'ok  ' if ok else 'FAIL'} no rain baked into the picture at {where:.2f}: "
              f"{share * 100:.3f} % streak pixels (at most {BAKED * 100:.2f} %)")  # fmt: skip

    def check_fall(name: str, counts: list[int]) -> None:
        down, up = counts
        # a few heads meet a neighbour's (up to 15 %); a rising rain would turn the numbers round
        ok = down >= 80 and up <= 0.2 * down
        results.append((name, ok))
        print(f"{'ok  ' if ok else 'FAIL'} {name}: {down} drops found lower a frame later, "
              f"{up} higher")  # fmt: skip

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"]
        )
        ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await open_story(ctx, errors)
        for where in RAIN_SPAN:
            await scroll_to(page, where)
            await page.wait_for_timeout(1500)  # the frames nearby load
            check_baked(where, await page.evaluate(BAKED_JS))
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
        up, down = await stepped_fall(browser, errors)
        check_fall("scrolling up, the drops fall", up)
        check_fall("scrolling down, the drops fall", down)

        phone = await browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=2,
            is_mobile=True,
            has_touch=True,
        )
        page = await open_story(phone, errors)
        # a phone scrolls by touch; the page scrolls itself there
        target = await chapter_y(page, RAIN_AT)
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
        target = await chapter_y(page, RAIN_AT)
        await page.evaluate(f"window.scrollTo(0, {target})")
        await page.wait_for_timeout(1500)
        check("less motion asked (shown, may stand still)", await motion(page, "7-calm"), False)
        await calm.close()
        await browser.close()

    for e in errors:
        print("page error:", e)
    failed = [r for r in results if not r[1]]
    return 1 if failed or errors else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
