# ruff: noqa: E501  (the page template has long CSS and HTML lines)
"""A self-contained catalogue page (one HTML file) of the models and their covers: product photo,
cover picture, grade and key numbers, with search, filters and sorting. For sharing a snapshot
of the catalogue outside the web app.

    uv run --with pillow python scripts/catalogue_page.py --models models --tag suns \\
        --title "SUNS Cover Catalogue" --out out/suns/catalogue.html
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import sys
from pathlib import Path

from coverengine.catalogue import grade

THUMB_PX = 240  # longest side of the embedded pictures
QUALITY = 72


def thumb(path: Path) -> str | None:
    if not path.is_file():
        return None
    from PIL import Image

    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        ground = Image.new("RGBA", im.size, (255, 255, 255, 255))
        ground.alpha_composite(im)
        im = ground
    im = im.convert("RGB")
    im.thumbnail((THUMB_PX, THUMB_PX))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=QUALITY, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def name(model_id: str, prefix: str) -> str:
    words = model_id.removeprefix(prefix).split("-")
    return " ".join(w if w.isdigit() else w.capitalize() for w in words if w)


def rows(models: Path, tag: str | None, prefix: str) -> list[dict[str, object]]:
    out = []
    for d in sorted(models.iterdir()):
        if not (d / "model.json").is_file():
            continue
        g = grade(d)
        if tag and tag not in g.get("tags", []):
            continue
        out.append(
            {
                "id": d.name,
                "name": name(d.name, prefix),
                "grade": g["grade"],
                "reasons": g.get("reasons", []),
                "family": g.get("family") or "",
                "size": [round(v / 10) for v in (g.get("size_mm") or [])],
                "panels": g.get("panels"),
                "stretch": g.get("max_stretch_pct"),
                "roll": round((g.get("roll_length_mm") or 0) / 1000, 1) or None,
                "photo": thumb(d / "product.jpg"),
                "cover": thumb(d / "cover.png"),
            }
        )
    return out


PAGE = """<title>__TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600&family=Source+Sans+3:wght@400;600&family=IBM+Plex+Mono:wght@400&display=swap">
<style>
/* Layout: a sticky filter bar over a wrapping grid of product cards (photo + cover side by side) */
:root {
  --bg: #eef1f0; --card: #ffffff; --ink: #1c2422; --muted: #5d6a67; --line: #d5dcda;
  --accent: #1f6f6a; --ready: #1d7a3e; --check: #9a5b00; --failed: #b3261e;
  --ready-bg: #dff2e5; --check-bg: #fbecd2; --failed-bg: #f9dcd9; --pic: #f5f7f6;
  --display: "Barlow Condensed", "Arial Narrow", sans-serif;
  --body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #121817; --card: #1b2321; --ink: #e4ebe9; --muted: #9aa8a4; --line: #2c3835;
  --accent: #5cbcb3; --ready: #7fd49a; --check: #f0b75e; --failed: #f08a82;
  --ready-bg: #1f3a29; --check-bg: #3d2f16; --failed-bg: #402020; --pic: #232d2b; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #121817; --card: #1b2321; --ink: #e4ebe9; --muted: #9aa8a4; --line: #2c3835;
  --accent: #5cbcb3; --ready: #7fd49a; --check: #f0b75e; --failed: #f08a82;
  --ready-bg: #1f3a29; --check-bg: #3d2f16; --failed-bg: #402020; --pic: #232d2b; color-scheme: dark }
body { background: var(--bg); color: var(--ink); font-family: var(--body); font-size: 15px; }
.wrap { max-width: 1320px; margin: 0 auto; padding-inline: 16px; padding-block: 24px 48px; }
h1 { font-family: var(--display); font-weight: 600; font-size: clamp(28px, 4vw, 40px); letter-spacing: 0.01em; margin: 0; text-wrap: balance; }
.sub { color: var(--muted); margin: 6px 0 0; max-width: 70ch; }
.tally { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0 0; }
.tally button { font: 600 14px var(--body); border: 1px solid var(--line); background: var(--card); color: var(--ink); border-radius: 999px; padding: 6px 12px; cursor: pointer; font-variant-numeric: tabular-nums; }
.tally button[aria-pressed="true"] { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.bar { position: sticky; top: env(safe-area-inset-top, 0px); z-index: 2; background: var(--bg); display: flex; flex-wrap: wrap; gap: 8px; padding-block: 12px; border-bottom: 1px solid var(--line); margin-bottom: 16px; }
.bar input, .bar select { font: 15px var(--body); color: var(--ink); background: var(--card); border: 1px solid var(--line); border-radius: 6px; padding: 7px 10px; }
.bar input { flex: 1 1 220px; min-width: 0; }
.bar .count { align-self: center; color: var(--muted); font-size: 13px; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 14px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 10px; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.pics { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.pics figure { margin: 0; }
.pics img, .pics .none { width: 100%; max-width: 100%; aspect-ratio: 4 / 3; object-fit: contain; background: var(--pic); border-radius: 5px; display: block; }
.pics .none { display: flex; align-items: center; justify-content: center; color: var(--muted); font-size: 12px; }
.pics figcaption { font-family: var(--display); font-size: 12px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); margin-top: 3px; }
.name { font-weight: 600; font-size: 16px; line-height: 1.25; }
.facts { display: flex; flex-wrap: wrap; gap: 4px 12px; font-family: var(--mono); font-size: 12.5px; color: var(--muted); font-variant-numeric: tabular-nums; }
.pill { font: 600 12px var(--body); border-radius: 999px; padding: 2px 9px; }
.pill.ready { background: var(--ready-bg); color: var(--ready); }
.pill.check { background: var(--check-bg); color: var(--check); }
.pill.failed { background: var(--failed-bg); color: var(--failed); }
.top { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.fam { font-size: 12px; color: var(--muted); }
.why { font-size: 13px; color: var(--muted); margin: 0; }
.over { color: var(--failed); } .under { color: var(--ready); }
.empty { color: var(--muted); padding: 32px 0; }
</style>
<div class="wrap">
  <h1>__TITLE__</h1>
  <p class="sub">__SUB__</p>
  <div class="tally" id="tally"></div>
  <div class="bar">
    <input id="q" type="search" placeholder="Search a product, e.g. Blocchi or dining table" aria-label="Search">
    <select id="fam" aria-label="Family"></select>
    <select id="sort" aria-label="Sort">
      <option value="name">Name</option>
      <option value="grade">Ready first</option>
      <option value="stretch">Least stretch first</option>
      <option value="size">Largest first</option>
    </select>
    <span class="count" id="count"></span>
  </div>
  <div class="grid" id="grid"></div>
  <p class="empty" id="empty" hidden>No product matches. Clear the search or pick another filter.</p>
</div>
<script>
const DATA = __DATA__;
const LIMIT = __LIMIT__;
const label = { ready: "Ready", check: "To check", failed: "Failed" };
const state = { grade: "", q: "", fam: "", sort: "name" };
const el = (id) => document.getElementById(id);
function tally() {
  const n = (g) => DATA.filter((d) => !g || d.grade === g).length;
  el("tally").innerHTML = [["", "All " + n("")], ["ready", "Ready " + n("ready")], ["check", "To check " + n("check")], ["failed", "Failed " + n("failed")]]
    .map(([g, t]) => `<button type="button" data-g="${g}" aria-pressed="${state.grade === g}">${t}</button>`).join("");
  el("tally").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => { state.grade = b.dataset.g; tally(); draw(); }));
}
function card(d) {
  const pic = (src, cap) => `<figure>${src ? `<img src="${src}" alt="${cap} of ${d.name}" loading="lazy">` : `<div class="none">no ${cap.toLowerCase()}</div>`}<figcaption>${cap}</figcaption></figure>`;
  const st = d.stretch == null ? "" : `<span class="${d.stretch > LIMIT ? "over" : "under"}">${d.stretch.toFixed(1)} % stretch</span>`;
  return `<article class="card"><div class="pics">${pic(d.photo, "Product")}${pic(d.cover, "Cover")}</div>
    <div class="top"><span class="name">${d.name}</span><span class="pill ${d.grade}">${label[d.grade]}</span></div>
    ${d.family ? `<span class="fam">Family: ${d.family}</span>` : ""}
    <div class="facts">${d.size.length ? `<span>${d.size.join(" × ")} cm</span>` : ""}${d.panels ? `<span>${d.panels} panels</span>` : ""}${st}${d.roll ? `<span>${d.roll} m fabric</span>` : ""}</div>
    ${d.reasons.length ? `<p class="why">${d.reasons.join("; ")}</p>` : ""}</article>`;
}
function draw() {
  const q = state.q.toLowerCase();
  const order = { ready: 0, check: 1, failed: 2 };
  const vol = (d) => d.size.reduce((a, b) => a * b, d.size.length ? 1 : 0);
  const list = DATA.filter((d) => (!state.grade || d.grade === state.grade) && (!state.fam || d.family === state.fam) && (!q || d.name.toLowerCase().includes(q)));
  list.sort((a, b) => state.sort === "grade" ? order[a.grade] - order[b.grade] || a.name.localeCompare(b.name)
    : state.sort === "stretch" ? (a.stretch ?? 1e9) - (b.stretch ?? 1e9)
    : state.sort === "size" ? vol(b) - vol(a) : a.name.localeCompare(b.name));
  el("grid").innerHTML = list.map(card).join("");
  el("count").textContent = `${list.length} of ${DATA.length} shown`;
  el("empty").hidden = list.length > 0;
}
const fams = [...new Set(DATA.map((d) => d.family).filter(Boolean))].sort();
el("fam").innerHTML = `<option value="">All families</option>` + fams.map((f) => `<option>${f}</option>`).join("");
el("q").addEventListener("input", (e) => { state.q = e.target.value; draw(); });
el("fam").addEventListener("change", (e) => { state.fam = e.target.value; draw(); });
el("sort").addEventListener("change", (e) => { state.sort = e.target.value; draw(); });
tally(); draw();
</script>
"""


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", type=Path, default=Path("models"))
    ap.add_argument("--tag")
    ap.add_argument("--prefix", default="suns-")
    ap.add_argument("--title", default="Cover Catalogue")
    ap.add_argument("--sub", default="")
    ap.add_argument("--limit", type=float, default=2.0, help="stretch limit (%)")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)
    data = rows(a.models, a.tag, a.prefix)
    page = (
        PAGE.replace("__TITLE__", html.escape(a.title))
        .replace("__SUB__", html.escape(a.sub))
        .replace("__LIMIT__", str(a.limit))
        .replace("__DATA__", json.dumps(data, separators=(",", ":")).replace("</", "<\\/"))
    )
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(page, encoding="utf-8")
    print(f"{len(data)} products -> {a.out} ({a.out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
