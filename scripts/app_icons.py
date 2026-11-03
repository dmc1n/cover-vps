"""The studio's home-screen icons (ADR-154): the s2dio mark on white, 180 px (iOS), 192 and 512 px
(the web app manifest; maskable: the mark inside the middle 60 %, the safe zone is 80 %).

Runs in the Playwright image (a real browser draws the SVG):

    docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/repo" \\
      mcr.microsoft.com/playwright/python:v1.63.0-noble \\
      bash -c "pip install -q --user playwright==1.63.0 && python /repo/scripts/app_icons.py"
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
MARK = ROOT / "apps" / "web" / "public" / "brand" / "s2dio-mark.svg"
OUT = ROOT / "apps" / "web" / "public" / "brand"
SIZES = {"apple-touch-icon.png": 180, "app-192.png": 192, "app-512.png": 512}
SHARE = 0.6  # the mark's width as a part of the icon


def main() -> None:
    svg = MARK.read_text(encoding="utf-8").replace("<svg ", '<svg width="100%" height="100%" ', 1)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for name, size in SIZES.items():
            page = browser.new_page(viewport={"width": size, "height": size})
            mark = round(size * SHARE)
            page.set_content(
                f"<html><body style='margin:0;width:{size}px;height:{size}px;background:#fff;"
                f"display:grid;place-items:center'><div style='width:{mark}px;height:{mark}px'>"
                f"{svg}</div></body></html>"
            )
            page.screenshot(path=str(OUT / name), omit_background=False)
            page.close()
            print(OUT / name, size)
        browser.close()


if __name__ == "__main__":
    main()
