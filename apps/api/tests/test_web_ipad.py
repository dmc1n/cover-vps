"""The studio on an iPad (ADR-154): typing without zoom, explanations on touch, the home-screen
app without a service worker, and 3D that is capped, recoverable and loaded only where shown.
The browser half is apps/web/e2e/ipad.py."""

import json
import re
import shutil
from pathlib import Path

from coverapi.main import create_app
from fastapi.testclient import TestClient
from PIL import Image

WEB = Path(__file__).resolve().parents[3] / "apps" / "web"
SRC = WEB / "src"


def _css() -> str:
    return re.sub(r"/\*.*?\*/", "", (SRC / "studio.css").read_text(encoding="utf-8"), flags=re.S)


def _blocks(css: str, at: str) -> list[str]:
    """The bodies of every `@media <at>` block."""
    out = []
    for m in re.finditer(re.escape(at) + r"\s*\{", css):
        depth, i = 1, m.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        out.append(css[m.end() : i - 1])
    return out


def test_fields_are_16px_on_touch_only() -> None:
    """iPad Safari zooms into a field under 16px: on a touch screen every text field, select and
    textarea is at least 16px, over every component's own size (!important); the desktop keeps
    the sizes it had (the Desk's remark stays 14px there)."""
    css = _css()
    rule = re.compile(
        r"input:not\([^{]*\),\s*select,\s*textarea\s*\{\s*font-size:\s*max\(16px,\s*1em\)\s*"
        r"!important;"
    )
    assert any(rule.search(b) for b in _blocks(css, "@media (pointer: coarse)"))
    # never a rule that zooms on the desktop: no field rule of 16px outside the touch block
    outside = css
    for b in _blocks(css, "@media (pointer: coarse)"):
        outside = outside.replace(b, "")
    assert "max(16px, 1em)" not in outside
    assert re.search(r"\.d-reject textarea\s*\{[^}]*font-size:\s*14px", css)


def test_viewport_keeps_pinch_zoom() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    viewport = re.search(r'<meta name="viewport" content="([^"]+)"', html)
    assert viewport
    assert "maximum-scale" not in viewport[1] and "user-scalable" not in viewport[1]


def test_home_screen_app_tags_and_manifest() -> None:
    html = (WEB / "index.html").read_text(encoding="utf-8")
    # behind a login the manifest is fetched with the session cookie
    assert re.search(
        r'<link rel="manifest" href="/manifest.webmanifest" crossorigin="use-credentials"', html
    )
    assert '<link rel="apple-touch-icon" href="/brand/apple-touch-icon.png"' in html
    assert '<meta name="apple-mobile-web-app-capable" content="yes"' in html
    assert re.search(r'<meta name="theme-color" content="#[0-9a-f]{6}"', html)
    doc = json.loads((WEB / "public" / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert doc["name"] == "Cover Studio" and doc["display"] == "standalone"
    assert doc["start_url"] == "/" and doc["scope"] == "/"
    sizes = set()
    for icon in [*doc["icons"], {"src": "/brand/apple-touch-icon.png", "sizes": "180x180"}]:
        path = WEB / "public" / icon["src"].lstrip("/")
        w, h = (int(n) for n in icon["sizes"].split("x"))
        with Image.open(path) as im:
            assert im.size == (w, h), icon
            assert im.mode in ("RGB", "RGBA")
            # iOS paints a transparent corner black: the icon is opaque
            assert im.convert("RGBA").getextrema()[3][0] == 255, icon
        sizes.add(w)
    assert {180, 192, 512} <= sizes


def test_no_service_worker() -> None:
    """Data is always live: no service worker that could answer from a cache (owner, 3 Nov)."""
    for f in [
        *SRC.rglob("*.ts"),
        *SRC.rglob("*.tsx"),
        WEB / "index.html",
        *(WEB / "public").rglob("*.js"),
    ]:
        text = f.read_text(encoding="utf-8")
        assert "serviceWorker" not in text and "registerSW" not in text, f
    assert not list((WEB / "public").glob("sw*.js")) and not list(
        (WEB / "public").glob("*worker*.js")
    )


def test_manifest_and_icons_load_without_login(tmp_path: Path) -> None:
    """The home screen asks for the manifest and icons before anyone logs in."""
    web = tmp_path / "dist"
    shutil.copytree(WEB / "public", web)
    shutil.copy(WEB / "index.html", web / "index.html")
    client = TestClient(create_app(tmp_path / "data", web, login_required=True))
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    assert r.json()["name"] == "Cover Studio"
    for icon in ("apple-touch-icon.png", "app-192.png", "app-512.png"):
        r = client.get(f"/brand/{icon}")
        assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get("/api/desk").status_code == 401  # the data itself still needs a login


def test_pixel_ratio_capped_everywhere() -> None:
    """No 3D view draws at the device's full pixel ratio (an iPad's 2x, a phone's 3x)."""
    for f in [*SRC.rglob("*.ts"), *SRC.rglob("*.tsx")]:
        for m in re.finditer(r"setPixelRatio\(([^;]*)\)", f.read_text(encoding="utf-8")):
            assert m[1].strip() != "window.devicePixelRatio", f"{f.name}: uncapped"
    gl = (SRC / "gl.tsx").read_text(encoding="utf-8")
    assert re.search(r"Math\.min\(window\.devicePixelRatio \|\| 1, coarse\(\) \? 1\.5 : 2\)", gl)


def test_studio_views_handle_a_lost_context() -> None:
    for name in ("Viewer.tsx", "Configure.tsx"):
        text = (SRC / name).read_text(encoding="utf-8")
        assert "watchContext(" in text and "<GlLost" in text and "pixelRatio()" in text, name
    gl = (SRC / "gl.tsx").read_text(encoding="utf-8")
    assert "webglcontextlost" in gl and "webglcontextrestored" in gl and "preventDefault" in gl


_IMPORT = re.compile(r"^\s*import\s+(?!type\b)(?:[^;]*?\sfrom\s+)?[\"']([^\"']+)[\"']", re.M)


def _static_graph(entry: Path) -> set[str]:
    """Every module the entry loads before its first paint: static imports only (a lazy
    `import()` and `import type` load nothing up front)."""
    seen: set[str] = set()
    todo = [entry]
    while todo:
        f = todo.pop()
        if str(f) in seen:
            continue
        seen.add(str(f))
        if f.suffix not in (".ts", ".tsx") or not f.is_file():
            continue
        for spec in _IMPORT.findall(f.read_text(encoding="utf-8")):
            if not spec.startswith("."):
                seen.add(spec)
                continue
            base = (f.parent / spec).resolve()
            for cand in (
                base,
                base.with_suffix(".tsx"),
                base.with_suffix(".ts"),
                base / "index.tsx",
                base / "index.ts",
            ):
                if cand.is_file():
                    todo.append(cand)
                    break
    return seen


def test_three_is_not_in_the_studios_first_load() -> None:
    """three.js (614 kB) loads with the first 3D view, not with the studio (lazy3d.tsx)."""
    graph = _static_graph(SRC / "main.tsx")
    three = sorted(s for s in graph if s == "three" or s.startswith("three/"))
    assert not three, f"the studio's first load pulls in {three}"
    for name in ("Viewer.tsx", "Configure.tsx", "Unfold.tsx", "Measure.tsx", "dispose3d.ts"):
        assert str((SRC / name).resolve()) not in graph, name
    # the 3D views still exist behind the lazy wrapper
    assert "three" in _static_graph(SRC / "Viewer.tsx")


def test_touch_tips_installed_once() -> None:
    main = (SRC / "main.tsx").read_text(encoding="utf-8")
    assert main.count("installTouchTips()") == 1
    tips = (SRC / "touchTips.ts").read_text(encoding="utf-8")
    assert "export const HOLD_MS = 500" in tips
    # scrolling stays the browser's: only the end of a hold that showed a card is cancelled
    assert re.search(r'"touchstart", onStart, passive\)', tips)
    assert re.search(r'"touchmove", onMove, passive\)', tips)
