"""The configurator's "photo or link" box in a real browser (ADR-112): Chromium, WebKit and
Firefox at 1440, 1024, 820 and 390 px. The box is opened, a photo chosen, the suggestion asked
(answered by a fake: no paid call); while it waits and after the answer: no sideways scrolling,
and the box, its fields, its button and the answer lie inside the panel and the screen.

Against this build served locally (no studio, no live data):

    node apps/web/e2e/site_serve.mjs --port 18341 &
    docker run --rm --network host -v "$PWD:/repo:ro" -v "$PWD/out/suggestfix:/shots" \
      -e COVER_E2E_URL=http://127.0.0.1:18341 -e COVER_E2E_TAG=after \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q playwright==1.63.0 && (Xvfb :99 &) && sleep 1 && \
               DISPLAY=:99 python /repo/apps/web/e2e/suggest_layout.py"

(Firefox runs in a window on Xvfb: headless it makes no WebGL here; xvfb-run hangs in Docker.)
"""

import asyncio
import json
import os
import sys
from typing import Any

from playwright.async_api import Page, Route, async_playwright

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18341")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
TAG = os.environ.get("COVER_E2E_TAG", "after")
WIDTHS = (1440, 1024, 820, 390)
PHOTO = bytes.fromhex(  # a 1x1 PNG: the field shows "1 photo"
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d4944415478da63f8ffff3f0005fe02fea7d6a9c80000000049454e44ae426082"
)

LONG = (
    "https://www.example-tuinmeubelen-webshop.nl/collections/outdoor-lounge/products/"
    "suns-marolo-daybed-rond-rope-sand-camel-cushion-2026-collectie?variant=4711471147114711"
)
FAKE = {  # an answer like the API's, with the longest links a shop can give
    "product": "sofa", "label": "Sofa", "sizes": {"length": 180},
    "flags": {"length": ["estimate"]}, "check": ["length"],
    "summary": "Een ronde daybed met touw rondom; meet de lengte na.",
    "source": {"url": None, "title": None, "photos": 1},
    "recognised": {"url": LONG, "title": LONG, "name": "SUNS Marolo daybed", "brand": "SUNS"},
    "comparable": {"url": LONG, "title": None}, "match": None,
}  # fmt: skip

MEASURE = """() => {
  const r = (s) => { const e = document.querySelector(s); if (!e) return null;
    const b = e.getBoundingClientRect(); return [b.left, b.right, b.top, b.bottom]; };
  const panel = document.querySelector('.s-config-panel');
  return { vw: document.documentElement.clientWidth, sw: document.documentElement.scrollWidth,
    panel_sideways: panel ? panel.scrollWidth > panel.clientWidth + 1 : null,
    panel: r('.s-config-panel'), box: r('.s-suggest'), photo: r('.s-suggest-photo'),
    link: r('.s-suggest-url'), go: r('.s-suggest .s-btn'), card: r('.s-suggest-card') };
}"""


def inside(a: list[float] | None, b: list[float] | None, slack: float = 0.5) -> bool:
    return bool(a and b) and a[0] >= b[0] - slack and a[1] <= b[1] + slack  # type: ignore[index]


def judge(m: dict[str, Any], card: bool) -> dict[str, bool]:
    screen = [0, m["vw"]]
    ok = {
        "no_sideways_scroll": m["sw"] <= m["vw"] + 1 and not m["panel_sideways"],
        "box_in_panel": inside(m["box"], m["panel"]),
        "box_on_screen": inside(m["box"], screen),
        "photo_in_box": inside(m["photo"], m["box"]),
        "link_in_box": inside(m["link"], m["box"]),
        "button_in_box": inside(m["go"], m["box"]),
    }
    if card:
        ok["card_in_box"] = inside(m["card"], m["box"])
    return ok


async def check(page: Page, name: str) -> dict[str, object]:
    """Three moments: a photo chosen, the 30-60 s wait ("We zoeken je meubel op… (dit kan een
    minuut duren)" on the button: it stuck out of the panel, owner 9 Oct 2026), the answer."""
    await page.goto(f"{URL}/configure", wait_until="load")
    await page.wait_for_selector(".s-suggest-open", timeout=20000)
    await page.click(".s-suggest-open")
    await page.set_input_files(".s-suggest-photo input",
                               files=[{"name": "sofa.png", "mimeType": "image/png",
                                       "buffer": PHOTO}])  # fmt: skip
    await page.wait_for_timeout(300)
    box = await page.query_selector(".s-suggest")
    rows: dict[str, Any] = {"name": name}
    rows["chosen"] = judge(await page.evaluate(MEASURE), False)
    answer = asyncio.Event()

    async def held(route: Route) -> None:  # the answer waits until the wait is measured
        await answer.wait()
        await route.fulfill(json=FAKE)

    await page.route("**/api/shop/suggest", held)
    await page.click(".s-suggest .s-btn")
    await page.wait_for_timeout(400)
    m = await page.evaluate(MEASURE)
    rows["waiting"] = judge(m, False)
    if box:
        await box.scroll_into_view_if_needed()
    await page.screenshot(path=f"{SHOTS}/{TAG}-{name}-waiting.png")
    answer.set()
    await page.wait_for_selector(".s-suggest-card", timeout=10000)
    await page.wait_for_timeout(300)
    m = await page.evaluate(MEASURE)
    rows["answer"] = judge(m, True)
    rows["measured"] = m
    if box:
        await box.scroll_into_view_if_needed()
    await page.screenshot(path=f"{SHOTS}/{TAG}-{name}.png")
    return rows


async def main() -> int:
    report, bad = [], 0
    async with async_playwright() as p:
        for engine in ("chromium", "webkit", "firefox"):
            # headless Firefox makes no WebGL here, and the configurator needs it: Firefox runs
            # in a window under xvfb-run
            ff = engine == "firefox"
            b = await getattr(p, engine).launch(
                headless=not (ff and os.environ.get("DISPLAY")),
                firefox_user_prefs={"webgl.force-enabled": True} if ff else None,
            )
            for w in WIDTHS:
                ctx = await b.new_context(viewport={"width": w, "height": 900}, locale="nl-NL")
                page = await ctx.new_page()
                row = await check(page, f"{engine}-{w}")
                fails = [
                    f"{when}: {k}"
                    for when in ("chosen", "waiting", "answer")
                    for k, v in row[when].items()
                    if not v
                ]  # type: ignore[attr-defined]
                bad += bool(fails)
                print(f"{row['name']:16s} {'ok' if not fails else 'FAIL ' + ', '.join(fails)}")
                report.append(row)
                await ctx.close()
            await b.close()
    with open(f"{SHOTS}/{TAG}-report.json", "w") as f:
        json.dump(report, f, indent=1)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
