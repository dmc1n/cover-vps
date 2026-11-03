"""Browser check of the studio on an iPad (ADR-154), in Chromium as an iPad Pro 11 (touch, a
mobile viewport, 2 device pixels per CSS pixel) and, to compare, at 1440 px with a mouse:

- typing without zoom: on the iPad every visible text field, select and textarea is at least
  16px (the login, the Desk, the Desk's reject remark, a cover page); with a mouse the reject
  remark keeps its 14px and the small fields stay small;
- explanations on touch: holding a control with a title for half a second shows its title in a
  card, and does not press it; a short tap presses it and shows nothing; a swipe shows nothing;
  the next touch hides the card; with a mouse, nothing of this happens;
- the home-screen app: the manifest and icons load before a login, the page names them, there
  is no service worker, and the session cookie is a lasting one (a home-screen app starts again
  from cold and must still be logged in);
- 3D: three.js is not loaded by the login page nor by a page without 3D, and is loaded by the
  first 3D view; the renderer draws at most 1.5 pixels per CSS pixel on the iPad (1 at 1440 px
  with 1 device pixel); a lost WebGL context shows "Reload 3D" instead of an empty box, and the
  button (and the browser giving the context back) builds the view anew, one renderer alive.

Screenshots of the Desk, the cover page with 3D, the reject dialog, a touch explanation and the
lost-context view go to $COVER_E2E_SHOTS (default /shots).

Run against a running studio with a scrubbed scratch copy of the data (never the live data): mail
and link keys cleared, `cover-users two-factor off`, an admin e2e-admin who approves. Then:

    docker run --rm --network host --user "$(id -u):$(id -g)" -e HOME=/tmp \\
      -v "$PWD:/repo:ro" -v "$PWD/out/ipad:/shots" -e COVER_E2E_URL=http://127.0.0.1:18491 \\
      mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q --user playwright==1.63.0 && python /repo/apps/web/e2e/ipad.py"

COVER_E2E_MODEL names the cover to open (default: the first built one on the Desk).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

from playwright.async_api import Page, async_playwright, expect

URL = os.environ.get("COVER_E2E_URL", "http://127.0.0.1:18491")
USER = os.environ.get("COVER_E2E_USER", "e2e-admin")
PASSWORD = os.environ.get("COVER_E2E_PASSWORD", "browser-test-password")
SHOTS = os.environ.get("COVER_E2E_SHOTS", "/shots")
MODEL = os.environ.get("COVER_E2E_MODEL", "")
SLOW = 90_000  # software WebGL in the container
HOLD_MS = 500  # touchTips.ts

problems: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("ok   " if ok else "FAIL ") + what, flush=True)
    if not ok:
        problems.append(what)


async def shot(page: Page, name: str) -> None:
    os.makedirs(SHOTS, exist_ok=True)
    await page.screenshot(path=f"{SHOTS}/{name}.png")


async def login(page: Page) -> None:
    await page.goto(f"{URL}/#/")
    await page.get_by_label("User name").fill(USER)
    await page.get_by_label("Password").fill(PASSWORD)
    await page.get_by_role("button", name="Log in").click()
    await expect(page.get_by_role("button", name="Log out")).to_be_visible(timeout=30_000)


SMALL_FIELDS = """() => [...document.querySelectorAll('input, select, textarea')]
  .filter(e => !['checkbox', 'radio', 'range', 'color', 'file', 'button', 'submit',
                 'reset', 'image', 'hidden'].includes(e.type))
  .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; })
  .map(e => [e.tagName.toLowerCase() + (e.className ? '.' + String(e.className).split(' ')[0] : '')
             + (e.getAttribute('aria-label') ? '[' + e.getAttribute('aria-label') + ']' : ''),
             parseFloat(getComputedStyle(e).fontSize)])"""


async def fields(page: Page, where: str, touch: bool) -> list[tuple[str, float]]:
    got = [(str(n), float(s)) for n, s in await page.evaluate(SMALL_FIELDS)]
    if touch:
        small = [(n, s) for n, s in got if s < 16]
        check(bool(got) and not small, f"iPad {where}: {len(got)} fields all >= 16px {small[:4]}")
    return got


async def touch(cdp: Any, kind: str, x: float, y: float) -> None:
    pts = [] if kind == "touchEnd" else [{"x": x, "y": y, "id": 1}]
    await cdp.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": pts})


async def hold(page: Page, cdp: Any, x: float, y: float, ms: int) -> None:
    await touch(cdp, "touchStart", x, y)
    await page.wait_for_timeout(ms)
    await touch(cdp, "touchEnd", x, y)


async def center(page: Page, selector: str) -> tuple[float, float]:
    # the middle of the screen: the Desk's action bar sits over the bottom edge
    await page.locator(selector).first.evaluate("e => e.scrollIntoView({block: 'center'})")
    await page.wait_for_timeout(300)
    box = await page.locator(selector).first.bounding_box()
    assert box, selector
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


async def touch_tips(page: Page, cdp: Any) -> None:
    """The one mechanism, on a control of our own (pressing it changes nothing) and then on a
    real one of the Desk for the screenshot."""
    await page.evaluate(
        """() => { const b = document.createElement('button');
          b.id = 'e2e-tip'; b.title = 'e2e: what this control does';
          b.textContent = 'tip'; b.style.cssText = 'position:fixed;left:300px;top:420px;z-index:5';
          window.__taps = 0; b.addEventListener('click', () => window.__taps++);
          document.body.appendChild(b); }"""
    )
    tip = page.locator("[data-testid=touch-tip]")
    x, y = await center(page, "#e2e-tip")
    await hold(page, cdp, x, y, HOLD_MS + 300)
    await expect(tip).to_be_visible(timeout=3000)
    check(
        await tip.inner_text() == "e2e: what this control does",
        "a long press shows the title in a card",
    )
    await page.wait_for_timeout(300)
    check(await page.evaluate("window.__taps") == 0, "a long press does not press the control")
    # the next touch hides it; a short tap presses and shows nothing
    await touch(cdp, "touchStart", x, y)
    await page.wait_for_timeout(80)
    await touch(cdp, "touchEnd", x, y)
    await page.wait_for_timeout(HOLD_MS + 200)
    check(await tip.count() == 0, "the next touch hides the card; a short tap shows none")
    check(await page.evaluate("window.__taps") == 1, "a short tap still presses the control")
    # a swipe that starts on it is a scroll, not a hold
    await touch(cdp, "touchStart", x, y)
    for k in range(1, 6):
        await touch(cdp, "touchMove", x, y - 8 * k)
        await page.wait_for_timeout(60)
    await page.wait_for_timeout(HOLD_MS)
    await touch(cdp, "touchEnd", x, y - 40)
    await page.wait_for_timeout(200)
    check(await tip.count() == 0, "a swipe shows no card")
    await page.evaluate("document.getElementById('e2e-tip').remove()")


async def gl_info(page: Page) -> dict[str, Any]:
    return dict(
        await page.evaluate(
            """() => { const c = document.querySelector('.viewer .canvas canvas');
              return { canvas: !!c, ratio: c ? c.width / c.clientWidth : 0,
                       renderers: window.__three ? window.__three.renderers : -1,
                       lost: !!document.querySelector('[data-testid=gl-lost]') }; }"""
        )
    )


async def lose(page: Page, restore: bool) -> None:
    await page.evaluate(
        """(restore) => { const c = document.querySelector('.viewer .canvas canvas');
          const gl = c.getContext('webgl2') || c.getContext('webgl');
          const ext = gl.getExtension('WEBGL_lose_context');
          ext.loseContext(); if (restore) setTimeout(() => ext.restoreContext(), 300); }""",
        restore,
    )


async def first_model(page: Page) -> str:
    if MODEL:
        return MODEL
    r = await page.request.get(f"{URL}/api/desk")
    items = (await r.json())["items"]
    built = [i for i in items if i["built"] and i["status"] != "approved"]
    assert built, "no built cover on the Desk"
    return str(built[0]["id"])


async def ipad(pw: Any) -> None:
    device = dict(pw.devices["iPad Pro 11"])
    browser = await pw.chromium.launch(args=["--enable-unsafe-swiftshader"])
    ctx = await browser.new_context(**device)
    page = await ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(f"page error: {e}"))
    scripts: list[str] = []
    page.on("request", lambda r: scripts.append(r.url) if r.resource_type == "script" else None)
    check(await page.evaluate("1") == 1, "iPad context")
    await page.goto(f"{URL}/#/")
    await page.get_by_label("User name").wait_for()
    check(
        await page.evaluate("matchMedia('(pointer: coarse)').matches"),
        "iPad: the browser reports a coarse pointer (a finger)",
    )
    await fields(page, "login", True)
    three = lambda: [u for u in scripts if "/assets/three-" in u]  # noqa: E731
    check(not three(), "the login page does not load three.js")
    # the home-screen app
    tags = await page.evaluate(
        """() => ({ manifest: document.querySelector('link[rel=manifest]')?.getAttribute('href'),
          cred: document.querySelector('link[rel=manifest]')?.crossOrigin,
          touch: document.querySelector('link[rel=apple-touch-icon]')?.getAttribute('href'),
          capable: document.querySelector('meta[name=apple-mobile-web-app-capable]')?.content,
          theme: document.querySelector('meta[name=theme-color]')?.content,
          sw: navigator.serviceWorker ? navigator.serviceWorker.controller : null })"""
    )
    check(
        tags["manifest"] == "/manifest.webmanifest" and tags["cred"] == "use-credentials",
        f"the page names its manifest, with credentials {tags}",
    )
    check(tags["touch"] == "/brand/apple-touch-icon.png" and tags["capable"] == "yes", "iOS tags")
    check(tags["sw"] is None, "no service worker controls the page")
    r = await page.request.get(f"{URL}/manifest.webmanifest")
    doc = await r.json()
    check(
        r.ok and doc["display"] == "standalone" and doc["name"] == "Cover Studio",
        "the manifest loads before a login",
    )
    for icon in doc["icons"]:
        ri = await page.request.get(URL + icon["src"])
        check(ri.ok and ri.headers["content-type"] == "image/png", f"icon {icon['src']}")

    await login(page)
    cookies = [c for c in await ctx.cookies() if c.get("httpOnly")]
    lasting = [c for c in cookies if c.get("expires", -1) > time.time() + 86400]
    check(bool(lasting), "the session cookie lasts beyond closing the app (not a session cookie)")
    # a page without 3D: no three.js
    scripts.clear()
    await page.goto(f"{URL}/#/work/questions")
    await page.wait_for_load_state("networkidle")
    check(not three(), "a page without 3D (Questions, loaded fresh) does not load three.js")

    # the Desk
    mid = await first_model(page)
    await page.goto(f"{URL}/#/work/desk/{mid}")
    await page.locator(".d-card-head h2").wait_for(timeout=SLOW)
    await page.locator(".viewer .canvas canvas").wait_for(timeout=SLOW)
    check(bool(three()), "the Desk card's 3D view loads three.js")
    await page.wait_for_timeout(1500)
    await fields(page, "Desk card", True)
    await shot(page, "ipad-desk")
    cdp = await ctx.new_cdp_session(page)
    await touch_tips(page, cdp)
    # a real control of the 3D view: the Show menu's explanation
    x, y = await center(page, ".viewer summary[title]")
    title = await page.locator(".viewer summary[title]").first.get_attribute("title")
    await hold(page, cdp, x, y, HOLD_MS + 300)
    tip = page.locator("[data-testid=touch-tip]")
    await expect(tip).to_have_text(title or "", timeout=3000)
    opened = await page.locator(".viewer details.menu").first.get_attribute("open")
    check(opened is None, "holding Show explains it and does not open the menu")
    await shot(page, "ipad-touch-tip")
    await page.keyboard.press("Escape")
    check(await tip.count() == 0, "Escape hides the card")
    # the reject dialog: its remark is 16px here (14px with a mouse)
    await page.locator("[data-testid=desk-reject]").tap()
    remark = page.locator(".d-reject textarea")
    await remark.wait_for()
    await remark.tap()
    size = float(await remark.evaluate("e => parseFloat(getComputedStyle(e).fontSize)"))
    check(size >= 16, f"iPad: the reject remark is {size}px (no zoom from 16px)")
    await fields(page, "reject dialog", True)
    await remark.fill("e2e: typing on the iPad (not sent)")
    await shot(page, "ipad-reject-dialog")

    # the cover page with 3D
    await page.goto(f"{URL}/#/model/{mid}/3d")
    await page.locator(".viewer .canvas canvas").wait_for(timeout=SLOW)
    await page.wait_for_timeout(2500)
    info = await gl_info(page)
    check(
        abs(info["ratio"] - 1.5) < 0.05,
        f"iPad (2 device pixels): the 3D draws {info['ratio']:.2f} pixels per CSS pixel",
    )
    await fields(page, "cover page", True)
    await shot(page, "ipad-cover-3d")
    # the device takes the context: Reload 3D, then one renderer again
    await lose(page, restore=False)
    lost = page.locator("[data-testid=gl-lost]")
    await expect(lost).to_be_visible(timeout=5000)
    check(True, "a lost context shows the Reload 3D card instead of an empty box")
    await shot(page, "ipad-gl-lost")
    await lost.get_by_role("button", name="Reload 3D").tap()
    await expect(lost).to_have_count(0, timeout=SLOW)
    await page.wait_for_timeout(2000)
    info = await gl_info(page)
    check(info["canvas"] and info["renderers"] == 1, f"Reload 3D builds the view anew {info}")
    # the browser gives it back by itself: built anew without a tap
    await lose(page, restore=True)
    await expect(lost).to_have_count(0, timeout=SLOW)
    await page.wait_for_timeout(2000)
    info = await gl_info(page)
    check(info["canvas"] and info["renderers"] == 1, f"a restored context rebuilds {info}")
    await shot(page, "ipad-cover-3d-after")

    other = [e for e in errors if "WebGL" not in e]
    check(not other, f"iPad: no page errors {other[:3]}")
    await browser.close()


async def desktop(pw: Any) -> None:
    browser = await pw.chromium.launch(args=["--enable-unsafe-swiftshader"])
    ctx = await browser.new_context(viewport={"width": 1440, "height": 900})
    page = await ctx.new_page()
    await page.goto(f"{URL}/#/")
    await page.get_by_label("User name").wait_for()
    check(
        not await page.evaluate("matchMedia('(pointer: coarse)').matches"),
        "1440: a mouse (fine pointer)",
    )
    await login(page)
    mid = await first_model(page)
    await page.goto(f"{URL}/#/work/desk/{mid}")
    await page.locator(".viewer .canvas canvas").wait_for(timeout=SLOW)
    got = await fields(page, "Desk card", False)
    await page.locator("[data-testid=desk-reject]").click()
    remark = page.locator(".d-reject textarea")
    await remark.wait_for()
    size = float(await remark.evaluate("e => parseFloat(getComputedStyle(e).fontSize)"))
    check(size == 14, f"1440: the reject remark keeps its 14px ({size})")
    got = await fields(page, "Desk card", False)
    check(any(s < 16 for _, s in got), "1440: the small fields keep their size")
    # a mouse press on a titled control is a plain click, no card
    await page.locator(".viewer summary[title]").first.click()
    await page.wait_for_timeout(HOLD_MS + 200)
    check(await page.locator("[data-testid=touch-tip]").count() == 0, "1440: no touch card")
    info = await gl_info(page)
    check(abs(info["ratio"] - 1) < 0.05, f"1440 (1 device pixel): 3D at {info['ratio']:.2f}")
    await shot(page, "desktop-reject-dialog")
    await browser.close()


async def main() -> int:
    async with async_playwright() as pw:
        for run in (ipad, desktop):
            try:
                await run(pw)
            except Exception as exc:  # noqa: BLE001 - say what failed, run the other one
                problems.append(f"{run.__name__}: {type(exc).__name__}: {str(exc)[:400]}")
                print(f"FAIL {run.__name__}: {exc}", flush=True)
    print(f"\n{len(problems)} problem(s)" + "".join(f"\n  - {p}" for p in problems))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
