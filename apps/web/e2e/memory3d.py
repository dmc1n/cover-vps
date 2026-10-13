"""The studio's 3D memory (ADR-129): open 20 covers' 3D views in a row on a scratch studio (never
live data) and check that nothing piles up. After each cover the page goes to a page without 3D;
there every WebGL renderer must be gone (window.__three, apps/web/src/dispose3d.ts), and the JS
heap after a garbage collection must stay flat (the 20th no more than the 5th plus a margin).

    docker run --rm --network host --user $(id -u):$(id -g) -e HOME=/tmp -v "$PWD:/repo:ro" \
      mcr.microsoft.com/playwright/python:v1.63.0-noble \
      bash -c "pip install -q --user playwright==1.63.0 && \
               python /repo/apps/web/e2e/memory3d.py http://127.0.0.1:18193"

Credentials: COVER_E2E_USER / COVER_E2E_PASSWORD (default tester / browser-test-password).
The scratch catalogue needs 20 covers with panels.glb. Read-only: it writes nothing.
"""

import asyncio
import os
import sys
from urllib.parse import quote

from playwright.async_api import async_playwright, expect

COVERS = 20
HEAP_MARGIN = 24 * 1024 * 1024  # bytes the heap may wander between the 5th and the 20th cover
COUNTERS = """() => {
    if (typeof gc === 'function') gc();
    return { ...(window.__three || {renderers: -1, geometries: -1, textures: -1}),
             heap: performance.memory ? performance.memory.usedJSHeapSize : -1 };
}"""


async def main(url: str) -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            args=[
                "--js-flags=--expose-gc",
                "--enable-precise-memory-info",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
            ]  # fmt: skip
        )
        page = await browser.new_page(viewport={"width": 1280, "height": 860})
        page.set_default_timeout(90_000)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(url)
        await page.get_by_label("User name").fill(os.getenv("COVER_E2E_USER", "tester"))
        await page.get_by_label("Password").fill(
            os.getenv("COVER_E2E_PASSWORD", "browser-test-password")
        )
        await page.get_by_role("button", name="Log in").click()
        await expect(page.get_by_role("button", name="Log out")).to_be_visible()
        models = await (await page.request.get(f"{url}/api/models")).json()
        ids: list[str] = []
        for m in models:
            detail = await page.request.get(f"{url}/api/models/{quote(m['id'], safe='')}")
            if detail.ok and "panels.glb" in (await detail.json())["files"]:
                ids.append(m["id"])
            if len(ids) == COVERS:
                break
        assert len(ids) == COVERS, f"the scratch catalogue has {len(ids)} covers with panels.glb"
        shown, away = [], []
        for model in ids:
            await page.goto(f"{url}/#/model/{quote(model, safe='')}/3d")
            await expect(page.locator(".viewer canvas")).to_have_count(1)
            # loaded: the renderer holds the cover's geometry
            await page.wait_for_function("window.__three && window.__three.geometries > 0")
            await page.wait_for_timeout(1500)
            shown.append(await page.evaluate(COUNTERS))
            await page.goto(f"{url}/#/covers/all")
            await expect(page.locator(".viewer canvas")).to_have_count(0)
            await page.wait_for_timeout(500)
            away.append(await page.evaluate(COUNTERS))
            print(model, "3D:", shown[-1], "away:", away[-1], flush=True)
        assert all(s["renderers"] == 1 for s in shown), shown  # one viewer at a time
        assert all(a["renderers"] == 0 for a in away), away  # every renderer let go
        heaps = [a["heap"] for a in away]
        if heaps[0] >= 0:
            print("heap MB away from 3D:", [round(h / 2**20, 1) for h in heaps])
            assert heaps[-1] <= heaps[4] + HEAP_MARGIN, heaps
        assert not errors, errors
        await browser.close()
        print(f"memory3d: OK, {COVERS} covers, renderers released, heap flat")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1].rstrip("/")))
