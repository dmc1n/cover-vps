"""A cover proposal from a customer's rough sizes, for the webshop (ADR-061,
docs/plans/webshop-configurator.md).

The customer picks what to cover and gives the rough sizes. The proposal is built from the
shapes we already make from the owner's drawings (`drawn.py`) and the company rules:

- a fit allowance;
- the chair space and balloons of a table;
- one vent per full metre of every side;
- the bottom drawcord (and the middle one of a table);
- pieces no wider than the roll.

Every piece of these shapes is flat, so its size and area are exact: the proposal takes well
under a second. The price comes from the cost model `quote.*` in config/defaults.yaml (to
confirm by the owner). The definitive pattern is made after the order, with the full program.
"""

from __future__ import annotations

import json
import math
import secrets
from pathlib import Path
from typing import Any

import numpy as np
import shapely
import trimesh

from coverengine import drawn
from coverengine.errors import CoverError
from coverengine.params import EffectiveParams

MM_PER_CM = 10.0  # param-ok: unit conversion
MM_PER_M = 1000.0  # param-ok: unit conversion
MM2_PER_M2 = 1e6  # param-ok: unit conversion
MIN_PER_H = 60.0  # param-ok: unit conversion
PERCENT = 100.0  # param-ok: ratio to percent

# what a customer can cover: the fields (cm), their defaults and sensible ranges, in
# config/quote_products.json (the owner can change them there)
PRODUCTS_JSON = Path(__file__).resolve().parents[2] / "config" / "quote_products.json"
PRODUCTS: dict[str, dict[str, Any]] = {
    k: {"label": v["label"], "fields": {f: tuple(t) for f, t in v["fields"].items()}}
    for k, v in json.loads(PRODUCTS_JSON.read_text(encoding="utf-8")).items()
    if not k.startswith("_")
}


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


def colours(params: EffectiveParams) -> list[str]:
    return [c.strip() for c in str(params["quote.colours"]).split(",") if c.strip()]


def options(params: EffectiveParams) -> dict[str, Any]:
    """What the configurator shows: the products, their fields and the options."""
    return {
        "products": {
            k: {
                "label": v["label"],
                "fields": [
                    {
                        "key": f,
                        "default": d,
                        "min": lo,
                        "max": hi,
                        "unit": "cm" if f.endswith("_cm") else None,
                    }
                    for f, (d, lo, hi) in v["fields"].items()
                ],  # fmt: skip
            }
            for k, v in PRODUCTS.items()
        },
        "options": {
            "vents": True,
            "drawcord": True,
            "colours": colours(params),
        },
        "currency": "EUR",
    }


def _sizes(
    product: str, given: dict[str, Any], params: EffectiveParams
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """The shape and its sizes (cm) for drawn.build, and facts for the proposal."""
    if product not in PRODUCTS:
        raise CoverError(f"unknown product {product!r}")
    spec = PRODUCTS[product]["fields"]
    v: dict[str, Any] = {}
    for f, (d, lo, hi) in spec.items():
        x = given.get(f, d)
        if lo is not None:
            try:
                x = float(x)
            except (TypeError, ValueError):
                raise CoverError(f"{f}: a number please") from None
            if not lo <= x <= hi:
                raise CoverError(f"{f}: between {lo} and {hi} cm")
        v[f] = x
    ease = _p(params, "quote.ease_cm")  # room on every side, so the cover goes on easily
    chair = _p(params, "hull.chair_room_mm") / MM_PER_CM
    facts: dict[str, Any] = {"balloons": 0, "middle_cord": False}
    if product == "dining_set":
        chairs = bool(v["chairs"])
        width = v["table_width_cm"] + (2 * chair if chairs else 0) + 2 * ease
        height = (_p(params, "hull.chair_height_dining_mm") / MM_PER_CM
                  if chairs else v["table_height_cm"]) + ease  # fmt: skip
        sizes = {"length_cm": v["table_length_cm"] + 2 * ease, "depth_cm": width,
                 "height_cm": height}  # fmt: skip
        facts.update(
            balloons=max(1, math.ceil(v["table_length_cm"] * MM_PER_CM
                                      / _p(params, "hull.balloon_spacing_mm"))),  # fmt: skip
            middle_cord=True, chair_space=chairs,
        )  # fmt: skip
        return "box", sizes, facts
    if product == "round_set":
        chairs = bool(v["chairs"])
        dia = v["table_diameter_cm"] + (2 * chair if chairs else 0) + 2 * ease
        height = (_p(params, "hull.chair_height_dining_mm") / MM_PER_CM
                  if chairs else v["table_height_cm"]) + ease  # fmt: skip
        facts.update(balloons=1, middle_cord=True, chair_space=chairs)
        return "round", {"diameter_cm": dia, "height_cm": height, "band_pieces": 2}, facts
    strip = _p(params, "quote.back_strip_cm")
    if product == "sofa":
        return "sloped box", {
            "length_cm": v["length_cm"] + 2 * ease, "depth_cm": v["depth_cm"] + 2 * ease,
            "back_height_cm": v["back_height_cm"] + ease,
            "front_height_cm": min(v["front_height_cm"], v["back_height_cm"]) + ease,
            "back_strip_cm": strip, "front_strip_cm": 0,
        }, facts  # fmt: skip
    if product == "corner_sofa":
        d = v["depth_cm"] + 2 * ease
        return "L shape", {
            "x_length_cm": v["long_side_cm"] + 2 * ease,
            "y_length_cm": v["short_side_cm"] + 2 * ease,
            "x_arm_depth_cm": d, "y_arm_depth_cm": d,
            "x_back_strip_cm": strip, "y_back_strip_cm": strip,
            "back_height_cm": v["back_height_cm"] + ease,
            "front_height_cm": min(v["front_height_cm"], v["back_height_cm"]) + ease,
            "strip_corner": "mitre",
        }, facts  # fmt: skip
    if product == "lounger":
        return "box", {"length_cm": v["length_cm"] + 2 * ease, "depth_cm": v["width_cm"] + 2 * ease,
                       "height_cm": v["height_cm"] + ease}, facts  # fmt: skip
    return "box", {"length_cm": v["length_cm"] + 2 * ease, "depth_cm": v["width_cm"] + 2 * ease,
                   "height_cm": v["height_cm"] + ease}, facts  # fmt: skip


def _flat(piece: drawn.Piece) -> shapely.Geometry:
    """A flat piece laid out in its own plane (all drawn pieces are planar, or a band)."""
    pts = np.vstack([np.array(f) for f in piece.faces])
    c = pts.mean(axis=0)
    _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
    polys = []
    for f in piece.faces:
        q = (np.array(f) - c) @ vt[:2].T
        polys.append(shapely.Polygon(q).buffer(0))
    return shapely.union_all(polys)


def _band_length(piece: drawn.Piece) -> tuple[float, float] | None:
    """A round band (many upright quads): its unrolled length and height."""
    if len(piece.faces) < 4:  # param-ok: a band has many faces
        return None
    pts = [np.array(f) for f in piece.faces]
    length = sum(float(np.linalg.norm(f[1][:2] - f[0][:2])) for f in pts)
    height = float(max(f[:, 2].max() for f in pts) - min(f[:, 2].min() for f in pts))
    return length, height


def _shelf(rects: list[tuple[float, float]], width: float) -> float:
    """The roll length (mm) the cut rectangles take, laid in rows across the roll (a simple,
    honest estimate; the cutting table nests better)."""
    rows: list[list[float]] = []  # [used width, row height]
    for w, h in sorted(rects, key=lambda r: -r[1]):
        for row in rows:
            if row[0] + w <= width:
                row[0] += w
                break
        else:
            rows.append([w, h])
    return float(sum(r[1] for r in rows))


def proposal(product: str, given: dict[str, Any], params: EffectiveParams) -> dict[str, Any]:
    shape, sizes, facts = _sizes(product, given, params)
    allowance = _p(params, "stitching.allowance_mm")
    roll_usable = _p(params, "roll.usable_width_mm")
    pieces = drawn.build(shape, sizes, roll_usable - 2 * allowance)
    out_pieces, rects, cut_area, area3d = [], [], 0.0, 0.0
    hem_mm = 0.0
    for p in pieces:
        band = _band_length(p) if p.name.startswith("band") else None
        if band:
            w, h = band
            area = w * h
        else:
            poly = _flat(p)
            box = np.asarray(shapely.minimum_rotated_rectangle(poly).exterior.coords)[:4]
            a, b = np.linalg.norm(box[1] - box[0]), np.linalg.norm(box[2] - box[1])
            w, h = max(a, b), min(a, b)
            area = float(poly.area)
        pts = np.vstack([np.array(f) for f in p.faces])
        on_floor = float(pts[:, 2].min()) < 1.0
        if on_floor:  # the hem runs along this piece's bottom
            bottom = pts[pts[:, 2] < 1.0]
            hem_mm += float(np.ptp(bottom[:, 0]) + np.ptp(bottom[:, 1])) if not band else w
        hem = _p(params, "hem.allowance_mm") if on_floor else 0.0
        cw, ch = w + 2 * allowance, h + 2 * allowance + hem
        if cw > roll_usable and ch <= roll_usable:
            cw, ch = ch, cw
        rects.append((min(cw, ch), max(cw, ch)) if max(cw, ch) <= roll_usable else (cw, ch))
        cut_area += cw * ch
        area3d += area
        out_pieces.append({"name": p.name, "width_cm": round(w / MM_PER_CM, 1),
                           "height_cm": round(h / MM_PER_CM, 1),
                           "cut_width_cm": round(cw / MM_PER_CM, 1),
                           "cut_height_cm": round(ch / MM_PER_CM, 1)})  # fmt: skip
    roll_mm = _shelf([(min(r), max(r)) if max(r) <= roll_usable else r for r in rects], roll_usable)
    # vents: one per full metre of every side, at least one per side (owner, 1 Oct 2026)
    from coverengine.finish.finish import vent_count

    sides = _sides(shape, sizes)
    vents = sum(vent_count(s * MM_PER_CM, params) for s in sides) if given.get("vents", True) else 0
    cord_m = (hem_mm / MM_PER_M + _p(params, "quote.cord_extra_m")) * (
        2 if facts.get("middle_cord") else 1)  # fmt: skip
    seam_m = _seam_length(pieces) / MM_PER_M
    cost = _cost(roll_mm / MM_PER_M, len(pieces), seam_m, vents, cord_m, facts["balloons"], params)
    return {
        "product": product,
        "shape": shape,
        "sizes_cm": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in sizes.items()},
        "pieces": out_pieces,
        "cover_area_m2": round(area3d / MM2_PER_M2, 2),
        "fabric_m2": round(cut_area / MM2_PER_M2, 2),
        "roll_m": round(roll_mm / MM_PER_M, 2),
        "roll_width_cm": round(_p(params, "roll.width_mm") / MM_PER_CM),
        "seams_m": round(seam_m, 1),
        "vents": vents,
        "drawcord_m": round(cord_m, 1),
        "balloons": facts["balloons"],
        "chair_space": facts.get("chair_space", False),
        "colour": given.get("colour") or colours(params)[0],
        "price": cost,
        "note": "a proposal from rough sizes; the definitive pattern is made after the order",
    }


def _sides(shape: str, s: dict[str, Any]) -> list[float]:
    """The sides of the cover (cm) for the vent rule."""
    if shape == "round":
        return [math.pi * s["diameter_cm"]]
    if shape == "L shape":
        x, y, d = s["x_length_cm"], s["y_length_cm"], s["x_arm_depth_cm"]
        return [x, y, x - d, y - d, d, d]
    return [s["length_cm"], s["length_cm"], s["depth_cm"], s["depth_cm"]]


def _seam_length(pieces: list[drawn.Piece]) -> float:
    """The seams: polygon edges two pieces share (mm)."""
    owner: dict[str, set[int]] = {}
    ends: dict[str, tuple[Any, Any]] = {}
    for i, p in enumerate(pieces):
        for f in p.faces:
            for a, b in zip(f, f[1:] + f[:1], strict=True):
                pa, pb = sorted((tuple(np.round(a, 1)), tuple(np.round(b, 1))))
                k = f"{pa}{pb}"
                owner.setdefault(k, set()).add(i)
                ends[k] = (pa, pb)
    return float(
        sum(np.linalg.norm(np.subtract(*ends[k])) for k, who in owner.items() if len(who) > 1)
    )


def _cost(roll_m: float, pieces: int, seam_m: float, vents: int, cord_m: float, balloons: int,
          params: EffectiveParams) -> dict[str, Any]:  # fmt: skip
    waste = 1 + _p(params, "quote.waste_pct") / PERCENT
    fabric = roll_m * waste * _p(params, "quote.fabric_eur_per_m")
    minutes = (_p(params, "quote.minutes_base") + pieces * _p(params, "quote.minutes_per_piece")
               + seam_m * _p(params, "quote.minutes_per_seam_m")
               + vents * _p(params, "quote.minutes_per_vent"))  # fmt: skip
    labour = minutes / MIN_PER_H * _p(params, "quote.labour_eur_per_hour")
    parts = (vents * _p(params, "quote.vent_eur") + cord_m * _p(params, "quote.cord_eur_per_m")
             + balloons * _p(params, "quote.balloon_eur"))  # fmt: skip
    cost = fabric + labour + parts
    sale = cost * (1 + _p(params, "quote.markup_pct") / PERCENT)
    vat = sale * _p(params, "quote.vat_pct") / PERCENT
    return {
        "fabric_eur": round(fabric, 2),
        "labour_minutes": round(minutes),
        "labour_eur": round(labour, 2),
        "parts_eur": round(parts, 2),
        "cost_eur": round(cost, 2),
        "sale_ex_vat_eur": round(sale, 2),
        "vat_eur": round(vat, 2),
        "sale_eur": round(sale + vat, 2),
        "placeholder_prices": bool(params["quote.prices_are_placeholders"]),
    }


def preview_glb(product: str, given: dict[str, Any], params: EffectiveParams) -> bytes:
    """The proposal in 3D (glTF, for the configurator or the webshop's own viewer)."""
    from coverengine.hull.build import _coloured
    from coverengine.io.model_io import glb_bytes
    from coverengine.palette import piece

    shape, sizes, _ = _sizes(product, given, params)
    allowance = _p(params, "stitching.allowance_mm")
    pieces = drawn.build(shape, sizes, _p(params, "roll.usable_width_mm") - 2 * allowance)
    sc = drawn.scene(pieces)
    parts = []
    for i, (name, g) in enumerate(sc.geometry.items()):
        r, gg, b = piece(i)
        rgba = (int(r * 255), int(gg * 255), int(b * 255), 255)  # param-ok: 8-bit colour
        parts.append((name, _coloured(g, rgba)))
    return glb_bytes(parts)


def nearest(
    product: str, given: dict[str, Any], models: Path, top: int = 3
) -> list[dict[str, Any]]:
    """The SUNS models nearest in kind and size: their covers are made and tested."""
    want = {"dining_set": "Tafels", "round_set": "Tafels", "sofa": "Sofasets",
            "corner_sofa": "Sofasets", "lounger": "Ligbedden", "item": None}[product]  # fmt: skip
    target = _bbox_cm(product, given)
    out = []
    for d in models.glob("suns-*"):
        try:
            cover = json.loads((d / "cover.json").read_text())
            size = json.loads((d / "model.json").read_text())["size_mm"]
        except (OSError, ValueError, KeyError):
            continue
        cat = str(cover.get("category") or "").split(" › ")[-1]
        if want and cat != want:
            continue
        s = sorted([size[0] / MM_PER_CM, size[1] / MM_PER_CM])[::-1] + [size[2] / MM_PER_CM]
        dist = float(np.abs(np.subtract(s, target)).sum())
        drape = d / "drape.json"
        tested = None
        if drape.is_file():
            dj = json.loads(drape.read_text())
            tested = {"engine": dj.get("engine"), "folds_pct": dj.get("fold_share_pct"),
                      "sag_cm": round(float(dj.get("max_sag_mm", 0)) / MM_PER_CM, 1)}  # fmt: skip
        out.append({"model_id": d.name, "name": (cover.get("notes") or d.name).split(": ")[-1],
                    "size_cm": [round(x) for x in s], "difference_cm": round(dist),
                    "drape": tested})  # fmt: skip
    out.sort(key=lambda r: float(str(r["difference_cm"])))
    return out[:top]


def _bbox_cm(product: str, g: dict[str, Any]) -> list[float]:
    f = PRODUCTS[product]["fields"]
    v = {k: float(g.get(k, d)) for k, (d, lo, _) in f.items() if lo is not None}
    if product == "dining_set":
        dims = [v["table_length_cm"], v["table_width_cm"], v["table_height_cm"]]
    elif product == "round_set":
        dims = [v["table_diameter_cm"], v["table_diameter_cm"], v["table_height_cm"]]
    elif product == "corner_sofa":
        dims = [v["long_side_cm"], v["short_side_cm"], v["back_height_cm"]]
    elif product == "sofa":
        dims = [v["length_cm"], v["depth_cm"], v["back_height_cm"]]
    else:
        dims = [v["length_cm"], v["width_cm"], v["height_cm"]]
    return sorted(dims[:2])[::-1] + [dims[2]]


def new_id() -> str:
    return secrets.token_hex(8)  # param-ok: 16 hex characters


__all__ = ["PRODUCTS", "options", "proposal", "preview_glb", "nearest", "new_id", "trimesh"]
