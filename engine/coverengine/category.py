"""Every model's category, with the names SUNS uses on hello-suns.com (ADR-050).

The owner, 2 October 2026: "categorise all models automatically: tables, chairs, lounge, coffee
tables, ...; look at hello-suns.com for the right names". The site's categories (Dining:
Tafels, Stoelen, Low dining tafels, Low dining stoelen, Barsets; Lounge: Sofasets,
Loungestoelen; Relax: Ligbedden, Daybeds; Styling: Bijzettafels, Poefs). Lounge (coffee)
tables, hockers and fire pits have no category of their own on the site (they are part of the
lounge sets): Loungetafels, Hockers and Vuurtafels are named the same way and marked as not on
the site; Barsets is split into Bartafels and Barstoelen.

The name of the model decides first (rules below, with the height for tables); what they cannot
place, the AI places from the name and the product photo, choosing only from CATEGORIES.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

from coverengine.params import EffectiveParams

# group, category, on the SUNS site
CATEGORIES: list[tuple[str, str, bool]] = [
    ("Dining", "Tafels", True),
    ("Dining", "Stoelen", True),
    ("Dining", "Low dining tafels", True),
    ("Dining", "Low dining stoelen", True),
    ("Dining", "Bartafels", True),
    ("Dining", "Barstoelen", True),
    ("Lounge", "Sofasets", True),
    ("Lounge", "Loungestoelen", True),
    ("Lounge", "Loungetafels", False),
    ("Lounge", "Hockers", False),
    ("Relax", "Ligbedden", True),
    ("Relax", "Daybeds", True),
    ("Styling", "Bijzettafels", True),
    ("Styling", "Poefs", True),
    ("Overig", "Vuurtafels", False),
]
NAMES = [f"{g} › {c}" for g, c, _ in CATEGORIES]
TABLES = {"Tafels", "Low dining tafels", "Bartafels", "Loungetafels", "Bijzettafels", "Vuurtafels"}
LOW_TABLE_MM = 550.0  # param-ok: a table lower than this is a lounge (coffee) table

# (pattern on the model's name, category); the first that matches decides
RULES: list[tuple[str, str]] = [
    (r"fire-?pit|vuur", "Vuurtafels"),
    (r"daybed", "Daybeds"),
    (r"sun-?lounger|lounger|ligbed|bed\b", "Ligbedden"),
    (r"low-?bar-?(chair|stool)|bar-?(chair|stool)|barstoel", "Barstoelen"),
    (r"low-?bar-?table|bar-?table|bartafel", "Bartafels"),
    (r"low-?dining-?(chair|stoel)", "Low dining stoelen"),
    (r"low-?dining", "Low dining tafels"),
    (r"side-?table|bijzettafel", "Bijzettafels"),
    (r"pouf|poef", "Poefs"),
    (r"hocker|footstool|ottoman", "Hockers"),
    (r"lounge-?table|loungetable|coffee|big-table|farzi|lounge-(conico|ronda)", "Loungetafels"),
    (r"dining-?chair|(^|-)chair-|armchair|stoel", "Stoelen"),
    (r"lounge-?chair|single-?seat|loungestoel|adirondack", "Loungestoelen"),
    (
        r"seater|sofa|corner|middle|chaise|longue|bench|element|l-part|bended|curved|part-|"
        r"moon|angled|extension|lounge-(blocchi|vento)$",
        "Sofasets",
    ),
    (r"chair", "Stoelen"),
    (r"dining-?table|picnic|table|tabel|dining-.*-dia-|dining-nova|dining-omis", "Tafels"),
]


def by_name(name: str, height_mm: float | None) -> str | None:
    n = name.lower()
    for pattern, cat in RULES:
        if re.search(pattern, n):
            if cat == "Tafels" and height_mm is not None and height_mm < LOW_TABLE_MM:
                return "Loungetafels"
            return cat
    return None


def full(cat: str) -> str:
    group = next(g for g, c, _ in CATEGORIES if c == cat)
    return f"{group} › {cat}"


AI_SYSTEM = """You sort outdoor furniture into the categories of SUNS (hello-suns.com). You get
the product's name (from its 3D model) and its photo when there is one. Choose exactly one of
these categories:
__CATS__
Answer with JSON only: {"category": "<one of the list, exactly as written>",
 "sure": true or false, "why": "one short sentence"}"""


def by_ai(model_dir: Path, name: str, params: EffectiveParams) -> dict[str, Any]:
    from coverengine.ai import ask_parts

    parts: list[dict[str, Any]] = [{"type": "text", "text": f"Product: {name}"}]
    for pic in ("product.jpg", "reference.png", "cover.png"):
        p = model_dir / pic
        if p.is_file():
            mime = "image/jpeg" if p.suffix == ".jpg" else "image/png"
            data = base64.b64encode(p.read_bytes()).decode()
            parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
            break
    ans = ask_parts(params, AI_SYSTEM.replace("__CATS__", "\n".join(NAMES)), parts)
    cat = str(ans.get("category", ""))
    if cat not in NAMES:
        return {"category": None, "why": f"the AI gave {cat!r}, not one of the list"}
    return {"category": cat, "sure": bool(ans.get("sure")), "why": str(ans.get("why", ""))}


# the furniture types read from the owner's drawings (scripts/drawings.py) -> categories
DRAWN = {
    "sofa": "Sofasets", "corner sofa": "Sofasets", "bench": "Sofasets", "daybed": "Daybeds",
    "lounge chair": "Loungestoelen", "chair": "Stoelen", "dining chair": "Stoelen",
    "lounger": "Ligbedden", "ottoman": "Hockers", "table": "Tafels", "round table": "Tafels",
    "fire pit": "Vuurtafels", "cushion": "Poefs",
}  # fmt: skip
DRAWINGS = Path(__file__).resolve().parents[2] / "out" / "drawings" / "covers-and-all"


def _from_drawing(model_dir: Path, height: float | None) -> str | None:
    """A model built from one of the owner's drawings: the furniture type read from it."""
    ref = model_dir / "reference.png"
    if not (model_dir.name.startswith("drawing-") and ref.is_file()):
        return None
    try:
        rows = json.loads((DRAWINGS / "drawings.json").read_text())
    except OSError:
        return None
    stem = model_dir.name.removeprefix("drawing-")
    for r in rows:
        code = re.sub(r"[^a-z0-9]+", "-", r["code"].lower()).strip("-")
        if code == stem:
            cat = DRAWN.get(str((r.get("ai") or {}).get("furniture")))
            if cat == "Tafels" and height is not None and height < LOW_TABLE_MM:
                return "Loungetafels"
            return cat
    return None


def categorise(model_dir: Path, params: EffectiveParams, use_ai: bool = True) -> dict[str, Any]:
    """The category for one model: {category, by: name | ai, why}."""
    from coverengine.params.registry import read_cover_definition

    cover = read_cover_definition(model_dir)
    product = (cover.get("notes") or "").split(": ", 1)[-1]
    name = f"{model_dir.name} {product}"
    height = None
    mj = model_dir / "model.json"
    if mj.is_file():
        height = float(json.loads(mj.read_text())["size_mm"][2])
    cat = by_name(model_dir.name, height) or _from_drawing(model_dir, height)
    if cat:
        return {"category": full(cat), "by": "name", "why": f"the name ({model_dir.name})"}
    if use_ai:
        got = by_ai(model_dir, name, params)
        if got.get("category"):
            return {"category": got["category"], "by": "ai", "why": got.get("why", ""),
                    "sure": got.get("sure", False)}  # fmt: skip
    return {"category": None, "by": None, "why": "no rule and no AI answer"}
