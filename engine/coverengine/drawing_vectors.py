"""The drawing read by the program itself, from its own lines (ADR-072).

The workshop's PDFs come out of CAD: every view is drawn as vector lines. A plan view of a free
shape (a kidney, a lens) is one closed path, so its outline is there exactly, point by point;
nothing has to be guessed from a picture. This module finds those closed outlines and the sizes
written next to them (height, length, circumference), and scales the outline from them. When
two written sizes disagree it says so instead of choosing quietly. The AI only checks the result
afterwards (scripts/drawing_outline.py), it does not decide the shape.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np

IN_CM = 2.54
NUM = r"(\d+(?:[.,]\d+)?)"
MIN_SEGMENTS = 20  # param-ok: a free outline has many; title boxes and arrows have few
TITLE_BLOCK = 0.88  # param-ok: below this share of the page height sits the order table
BEZIER_STEPS = 8  # param-ok: points per curve piece
AGREE = 0.03  # param-ok: two written sizes of the same thing agree within 3 %
CM2_PER_M2 = 1e4  # param-ok: unit
BEZIER = slice(1, 5)  # param-ok: a curve item's four points


def _bezier(p0: Any, p1: Any, p2: Any, p3: Any) -> list[tuple[float, float]]:
    out = []
    for k in range(1, BEZIER_STEPS + 1):
        t = k / BEZIER_STEPS
        a, b, c, d = (1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t**2, t**3
        out.append((a * p0.x + b * p1.x + c * p2.x + d * p3.x,
                    a * p0.y + b * p1.y + c * p2.y + d * p3.y))  # fmt: skip
    return out


def closed_outlines(pdf: Path) -> list[dict[str, Any]]:
    """Every closed path with many segments above the order table: [{page, points (pt)}]."""
    import pymupdf

    found = []
    for pn, page in enumerate(pymupdf.open(pdf).pages()):
        limit = page.rect.height * TITLE_BLOCK
        for d in page.get_drawings():
            items = d["items"]
            if len(items) < MIN_SEGMENTS or d["rect"].y1 > limit:
                continue
            pts: list[tuple[float, float]] = [(items[0][1].x, items[0][1].y)]
            for it in items:
                if it[0] == "l":
                    pts.append((it[2].x, it[2].y))
                elif it[0] == "c":
                    pts += _bezier(*it[BEZIER])
                else:  # a rectangle or a quad: not a free outline
                    pts = []
                    break
            if len(pts) < MIN_SEGMENTS or math.dist(pts[0], pts[-1]) > 0.5:  # param-ok: pt
                continue
            arr = np.array(pts[:-1])
            arr[:, 1] = -arr[:, 1]  # the page's y runs down; the plan's y (to the back) up
            found.append({"page": pn, "points": arr})
    return found


def _cm(value: str, unit: str) -> float:
    v = float(value.replace(",", "."))
    return v * IN_CM if unit.lower().startswith("in") else v


def written(pdf: Path) -> dict[str, list[float]]:
    """Sizes written with a word that says what they are, in cm: per word (height, length,
    circumference, diameter, width), every value found in the same text block. A value with
    its unit counts; a bare number is cm (the drawings write "45.0cm 17.7in" or "152.4")."""
    import pymupdf

    words = ("height", "length", "circumference", "diameter", "width", "depth")
    out: dict[str, list[float]] = {}
    for page in pymupdf.open(pdf).pages():
        for b in page.get_text("blocks"):
            text = b[4]
            low = text.lower()
            for w in words:
                if w not in low:
                    continue
                vals = [_cm(v, u) for v, u in re.findall(NUM + r"\s*(cm|in)\b", text, re.I)]
                # a bare number (no unit): cm, as the drawings write the metric value plainly
                bare = re.findall(NUM + r"(?![\d.,])(?!\s*(?:cm|in\b))", text, re.I)
                vals += [float(v.replace(",", ".")) for v in bare]
                if vals:
                    out.setdefault(w, []).extend(round(v, 1) for v in vals)
    return out


def _perimeter(p: np.ndarray) -> float:
    return float(np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1).sum())


def _longest(p: np.ndarray) -> float:
    from scipy.spatial.distance import pdist

    return float(pdist(p).max())


def outline_shape(pdf: Path) -> dict[str, Any] | None:
    """The plan outline in cm and the height, with how the scale was found and any written
    size that disagrees. None when the drawing has no closed free outline."""
    shapes = closed_outlines(pdf)
    if not shapes:
        return None
    best = max(shapes, key=lambda s: len(s["points"]))
    pts = best["points"]
    sizes = written(pdf)
    per_pt, long_pt = _perimeter(pts), _longest(pts)
    # every written size that could set the scale, and what it gives
    options = []
    for c in sizes.get("circumference", []):
        options.append(("circumference", c, c / per_pt))
    for c in sizes.get("length", []) + sizes.get("diameter", []):
        options.append(("length", c, c / long_pt))
    if not options:
        return {"error": "no written circumference or length to scale the outline",
                "sizes": sizes}  # fmt: skip
    # the labelled circumference first (its unit is written), then the length
    options.sort(key=lambda o: o[0] != "circumference")
    used = options[0]
    scale = used[2]
    conflicts = [
        {"size": name, "written_cm": v, "outline_gives_cm": round(v / s * scale, 1)}
        for name, v, s in options[1:]
        if abs(s / scale - 1) > AGREE
    ]
    heights = sizes.get("height", [])
    if not heights:
        return {"error": "no written height", "sizes": sizes}
    outline = pts * scale
    return {
        "shape": {"outline_cm": [[round(x, 2), round(y, 2)] for x, y in outline],
                  "height_cm": max(heights)},
        "page": best["page"],
        "scaled_by": {"size": used[0], "written_cm": used[1]},
        "conflicts": conflicts,
        "sizes": sizes,
        "plan_cm": {
            "circumference": round(_perimeter(outline), 1),
            "longest": round(_longest(outline), 1),
            "area_m2": round(float(abs(np.dot(outline[:, 0], np.roll(outline[:, 1], -1))
                                       - np.dot(np.roll(outline[:, 0], -1), outline[:, 1])) / 2)
                             / CM2_PER_M2, 3),
        },
    }  # fmt: skip
