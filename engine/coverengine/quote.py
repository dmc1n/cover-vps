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
confirm by the owner), or from the price set published on the admin page (ADR-098,
`costing.py`). The definitive pattern is made after the order, with the full program.
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

from coverengine import costing, drawn
from coverengine.errors import CoverError
from coverengine.params import EffectiveParams


def _join(meshes: Any) -> trimesh.Trimesh:
    m = trimesh.util.concatenate(list(meshes))
    assert isinstance(m, trimesh.Trimesh)
    return m


MM_PER_CM = 10.0  # param-ok: unit conversion
MM_PER_M = 1000.0  # param-ok: unit conversion
MM2_PER_M2 = 1e6  # param-ok: unit conversion

# what a customer can cover: the fields (cm), their defaults and sensible ranges, in
# config/quote_products.json (the owner can change them there)
PRODUCTS_JSON = Path(__file__).resolve().parents[2] / "config" / "quote_products.json"
PRODUCTS: dict[str, dict[str, Any]] = {
    k: {"label": v["label"],
        "fields": {f: tuple(t[:3]) for f, t in v["fields"].items()},
        # a size asked only when a yes/no is ticked (a lounger's headrest, owner 7 Oct 2026)
        "requires": {f: t[3] for f, t in v["fields"].items() if len(t) > 3}}  # noqa: PLR2004
    for k, v in json.loads(PRODUCTS_JSON.read_text(encoding="utf-8")).items()
    if not k.startswith("_")
}  # fmt: skip


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
                        "requires": v["requires"].get(f),
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
        if not v.get("headrest"):  # a flat lounger (owner, 7 Oct 2026): a low box
            return "box", {"length_cm": v["length_cm"] + 2 * ease,
                           "depth_cm": v["width_cm"] + 2 * ease,
                           "height_cm": v["height_cm"] + ease}, facts  # fmt: skip
        # a raised headrest: high over the head, a slope, low over the body (the head at the
        # back of the sloped box, the lounger's length its depth)
        head = max(v["headrest_height_cm"], v["height_cm"])
        slope = _p(params, "quote.lounger_slope_cm")
        depth = v["length_cm"] + 2 * ease
        back = min(v["headrest_length_cm"] + ease, depth - slope)
        low = v["height_cm"] + ease
        return "sloped box", {"length_cm": v["width_cm"] + 2 * ease, "depth_cm": depth,
                              "back_height_cm": head + ease, "front_height_cm": low,
                              "back_strip_cm": back,
                              "front_strip_cm": max(0.0, depth - back - slope)}, facts  # fmt: skip
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


def proposal(product: str, given: dict[str, Any], params: EffectiveParams,
             prices: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """The proposal and its price. `prices` is the published price set (ADR-098); without one,
    the defaults of config/defaults.yaml."""
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
    colour = given.get("colour") or colours(params)[0]
    cost = _cost({"piece": len(pieces), "fabric_m": roll_mm / MM_PER_M, "seam_m": seam_m,
                  "hem_m": hem_mm / MM_PER_M, "vent": vents, "cord_m": cord_m,
                  "roll_width_mm": _p(params, "roll.width_mm"), "fabric_m2": cut_area / MM2_PER_M2,
                  # the balloons are sold next to the cover (the shop's support), not in it
                  "balloon": 0},
                 prices or costing.default_price_set(params), colour)  # fmt: skip
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
        "hem_m": round(hem_mm / MM_PER_M, 1),
        "colour": colour,
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


def _cost(facts: dict[str, Any], prices: dict[str, Any], colour: str | None) -> dict[str, Any]:
    """The consumer price (and the full costing for our side; the customer never sees it)."""
    c = costing.costing(facts, prices, colour=colour)
    b2c, b2b = c["channels"]["b2c"], c["channels"]["b2b"]
    return {
        "fabric_eur": c["fabric_eur"],
        "labour_minutes": round(c["labour_minutes"]),
        "labour_eur": c["labour_eur"],
        "parts_eur": c["components_eur"],
        "cost_eur": c["cost_eur"],
        "extras_eur": b2c["extras_eur"],
        "sale_ex_vat_eur": b2c["net_eur"],
        "vat_eur": b2c["vat_eur"],
        "sale_eur": b2c["gross_eur"],
        "b2b_ex_vat_eur": b2b["net_eur"],
        "placeholder_prices": c["indicative"],
        "costing": c,
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
        if product == "lounger" and g.get("headrest"):
            dims[2] = max(dims[2], v["headrest_height_cm"])
    return sorted(dims[:2])[::-1] + [dims[2]]


def new_id() -> str:
    return secrets.token_hex(8)  # param-ok: 16 hex characters


__all__ = ["PRODUCTS", "options", "proposal", "preview_glb", "nearest", "new_id", "trimesh"]


# ---- the rain check and the upsell (ADR-062) ----------------------------------------------------

SUPPORTS = ("none", "balloons", "frame")
BALLOON_RGBA = (236, 238, 240, 255)  # param-ok: display colour of the balloons
SHOP_SUPPORTS = ("none", "balloons")  # what the shop offers now (the frame is off for now)


def full_sizes(product: str, given: dict[str, Any]) -> dict[str, Any]:
    """The customer's sizes with the product's defaults for what was left out."""
    if product not in PRODUCTS:
        raise CoverError(f"unknown product {product!r}")
    return {f: given.get(f, d) for f, (d, _, _) in PRODUCTS[product]["fields"].items()}


def cover_mesh(product: str, given: dict[str, Any], params: EffectiveParams,
               support: str = "none") -> trimesh.Trimesh:  # fmt: skip
    """The proposed cover as one mesh (mm, Z up, centred in plan like `furniture.build`).

    support:
    - none: the shape as drawn (a flat top on a table);
    - balloons: a hipped roof over the balloons; the fabric runs straight between them and
      slopes down all round (the owner, 2026-09-30);
    - frame: a gabled roof with a fixed slope.

    Only box covers (tables, loungers, items) get a roof; the other shapes keep their own."""
    shape, sizes, facts = _sizes(product, given, params)
    if shape == "round" and support != "none":  # a cone over the balloon (or a frame)
        key = "quote.balloon_rise_cm" if support == "balloons" else "quote.frame_rise_cm"
        m = _cone(sizes["diameter_cm"] * MM_PER_CM / 2, sizes["height_cm"] * MM_PER_CM,
                  _p(params, key) * MM_PER_CM)  # fmt: skip
    elif shape != "box" or support == "none":
        pieces = drawn.build(shape, sizes, math.inf)
        m = _join(list(drawn.scene(pieces).geometry.values()))
    else:
        L, W, H = (sizes[k] * MM_PER_CM for k in ("length_cm", "depth_cm", "height_cm"))
        rise = (
            _p(params, "quote.balloon_rise_cm" if support == "balloons" else "quote.frame_rise_cm")
            * MM_PER_CM
        )
        n = max(2, int(facts.get("balloons") or 1))
        reach = 0.0 if support == "frame" else (L / 2) * (1 - 1 / n)  # the outer balloons' x
        m = _roof(L, W, H, rise, reach, hip=support == "balloons")
    if product == "lounger" and shape == "sloped box":
        # the sloped box runs its depth along y; the lounger lies along x with its head at +x
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0, 0, 1)))
        hi = m.vertices[:, 2] > m.vertices[:, 2].max() - 1.0  # param-ok: mm, the head's top
        if m.vertices[hi, 0].mean() < m.vertices[:, 0].mean():
            m.apply_transform(trimesh.transformations.rotation_matrix(math.pi, (0, 0, 1)))
    c = (m.bounds[0] + m.bounds[1]) / 2
    m.apply_translation((-c[0], -c[1], 0.0))
    return m


def _cone(R: float, H: float, rise: float) -> trimesh.Trimesh:
    """A round cover with a cone-shaped top (the balloon in the middle) and its band."""
    nr, na = 16, 72  # param-ok: grid of the cone
    rs = np.linspace(0, R, nr)
    ang = np.linspace(0, 2 * np.pi, na, endpoint=False)
    v = [[0.0, 0.0, H + rise]]
    for r in rs[1:]:
        for a in ang:
            v.append([r * np.cos(a), r * np.sin(a), H + rise * (1 - r / R)])
    f = [[0, 1 + k, 1 + (k + 1) % na] for k in range(na)]
    for i in range(nr - 2):
        o0, o1 = 1 + i * na, 1 + (i + 1) * na
        for k in range(na):
            p0, p1 = o0 + k, o0 + (k + 1) % na
            q1, q0 = o1 + (k + 1) % na, o1 + k
            f += [[p0, q0, q1], [p0, q1, p1]]
    o = len(v)
    for a in ang:
        v.append([R * np.cos(a), R * np.sin(a), 0.0])
    rim = 1 + (nr - 2) * na
    for k in range(na):
        f += [[rim + k, o + k, o + (k + 1) % na], [rim + k, o + (k + 1) % na, rim + (k + 1) % na]]
    return trimesh.Trimesh(np.array(v), np.array(f), process=False)


def _roof(L: float, W: float, H: float, rise: float, reach: float, hip: bool) -> trimesh.Trimesh:
    """A box cover with a roof: walls to the ground, the top rising `rise` to a ridge along x
    (from -reach to +reach); hipped ends (balloons) or gable ends (frame)."""
    nx, ny = 61, 31  # param-ok: grid of the roof
    xs = np.linspace(-L / 2, L / 2, nx)
    ys = np.linspace(-W / 2, W / 2, ny)
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    across = 1 - np.abs(gy) / (W / 2)
    if hip:
        along = 1 - np.clip(np.abs(gx) - reach, 0, None) / max(L / 2 - reach, 1.0)
        z = H + rise * np.minimum(across, along)
    else:
        z = H + rise * across
    v = np.column_stack([gx.ravel(), gy.ravel(), z.ravel()])
    f = []
    for i in range(nx - 1):
        for j in range(ny - 1):
            a, b, c, d = i * ny + j, (i + 1) * ny + j, (i + 1) * ny + j + 1, i * ny + j + 1
            f += [[a, b, c], [a, c, d]]
    top = trimesh.Trimesh(v, np.array(f), process=False)
    # the walls: from the roof's edge down to the ground
    ring = ([(i, 0) for i in range(nx)] + [(nx - 1, j) for j in range(1, ny)]
            + [(i, ny - 1) for i in range(nx - 2, -1, -1)]
            + [(0, j) for j in range(ny - 2, 0, -1)])  # fmt: skip
    pts = np.array([[xs[i], ys[j], z[i, j]] for i, j in ring])
    wv: list[list[float]] = []
    wf: list[list[int]] = []
    for k in range(len(pts)):
        p, q = pts[k], pts[(k + 1) % len(pts)]
        o = len(wv)
        wv += [[p[0], p[1], 0.0], [q[0], q[1], 0.0], [q[0], q[1], q[2]], [p[0], p[1], p[2]]]
        wf += [[o, o + 1, o + 2], [o, o + 2, o + 3]]
    walls = trimesh.Trimesh(np.array(wv), np.array(wf), process=False)
    return _join([top, walls])


def under_cover(product: str, given: dict[str, Any], params: EffectiveParams) -> trimesh.Trimesh:
    """The customer's furniture as it stands under the cover: a table set's chairs pushed in,
    inside the cover that was made wider for them (the owner, 5 Oct 2026)."""
    from coverengine import furniture

    full = full_sizes(product, given)
    if product in ("dining_set", "round_set") and full.get("chairs"):
        shape, sizes, _ = _sizes(product, given, params)
        room = _p(params, "hull.chair_room_mm") / MM_PER_CM + _p(params, "quote.ease_cm")
        return furniture.build(product, full, room_cm=room, top_cm=float(sizes["height_cm"]))
    return furniture.build(product, full)


def balloons_mesh(product: str, given: dict[str, Any], params: EffectiveParams
                  ) -> trimesh.Trimesh | None:  # fmt: skip
    """The balloons under the cover, where `cover_mesh` lifts it: resting on the table top and
    touching the top of the roof (a table set only)."""
    shape, sizes, facts = _sizes(product, given, params)
    full = full_sizes(product, given)
    if "table_height_cm" not in full or shape not in ("box", "round"):
        return None
    table = float(full["table_height_cm"]) * MM_PER_CM
    rise = _p(params, "quote.balloon_rise_cm") * MM_PER_CM
    top = float(sizes["height_cm"]) * MM_PER_CM + rise
    r = max((top - table) / 2, 1.0)
    if shape == "round":
        xs = [0.0]
    else:
        L = float(sizes["length_cm"]) * MM_PER_CM
        n_roof = max(2, int(facts.get("balloons") or 1))
        reach = (L / 2) * (1 - 1 / n_roof)
        n = max(1, int(facts.get("balloons") or 1))
        xs = [0.0] if n == 1 else [float(x) for x in np.linspace(-reach, reach, n)]
    balls = []
    for x in xs:
        b = trimesh.creation.icosphere(subdivisions=3, radius=r)
        b.apply_translation((x, 0.0, table + r))
        balls.append(b)
    return _join(balls)


def rain_check(product: str, given: dict[str, Any], params: EffectiveParams,
               prices: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
    """Where rain stays on the proposed cover without support, with balloons and with a frame,
    and what the shop advises (the upsell). Box covers only; the other shapes are checked
    as they are."""
    import tempfile

    from coverengine import rain
    from coverengine.io.model_io import glb_bytes

    shape, sizes, facts = _sizes(product, given, params)
    under = under_cover(product, given, params)
    # the frame is off the shop for now (the owner, 5 Oct 2026): no balloons or nothing
    options = SHOP_SUPPORTS if shape in ("box", "round") else ("none",)
    out: dict[str, Any] = {}
    for support in options:
        cover = cover_mesh(product, given, params, support)
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "model.glb").write_bytes(glb_bytes([("furniture", under)]))
            (d / "hull.glb").write_bytes(glb_bytes([("cover", cover)]))
            (d / "model.json").write_text(
                json.dumps({"size_mm": list(np.ptp(under.vertices, axis=0))})
            )
            r = rain.simulate(d, params, use_ai=False)
            wet = d / "rain.glb"  # ponds and flat parts in blue, for the 3D view
            water = wet.read_bytes() if wet.is_file() else None
        # dry enough: no water stays and at most a narrow flat line (the straight ridge between
        # balloons sheds sideways)
        dry = r["pond_volume_l"] == 0 and r["flat_area_m2"] <= _p(params, "quote.flat_ok_m2")
        out[support] = {
            "ponds": len(r["ponds"]),
            "water_l": r["pond_volume_l"],
            "flat_m2": r["flat_area_m2"],
            "dry": dry,
            "_water_glb": water,
        }
    ps = prices or costing.default_price_set(params)
    advice = None
    if "balloons" in out and not out["none"]["dry"]:
        n = max(1, int(facts.get("balloons") or 1))
        if out["balloons"]["dry"]:
            advice = {"support": "balloons", "count": n,
                      "price_eur": round(
                          n * costing.accessory_price(ps, "balloon", "b2c")["gross_eur"], 2),
                      "why": f"without support {out['none']['flat_m2']} m2 of the top is flat: "
                             "water stays. "
                             f"With {n} balloon(s) under the cover it runs off."}  # fmt: skip
        elif "frame" in out and out["frame"]["dry"]:
            advice = {"support": "frame", "count": 1,
                      "price_eur": costing.accessory_price(ps, "frame", "b2c")["gross_eur"],
                      "why": "a frame gives the top a fixed slope: water runs off."}  # fmt: skip
    return {"options": out, "advice": advice}


def scene_glb(product: str, given: dict[str, Any], params: EffectiveParams, support: str = "none",
              colour_rgb: tuple[int, int, int] | None = None) -> bytes:  # fmt: skip
    """The furniture and the cover over it, for the shop's configurator."""
    from coverengine.hull.build import _coloured
    from coverengine.io.model_io import glb_bytes

    cover = cover_mesh(product, given, params, support)
    under = under_cover(product, given, params)
    rgb = colour_rgb or (80, 84, 74)  # param-ok: charcoal-ish
    parts = [
        ("furniture", _coloured(under, (182, 160, 128, 255))),  # param-ok: wood display colour
        ("cover", _coloured(cover, (*rgb, 255))),
    ]  # fmt: skip
    if support == "balloons":
        balls = balloons_mesh(product, given, params)
        if balls is not None:
            parts.insert(1, ("balloons", _coloured(balls, BALLOON_RGBA)))
    return glb_bytes(parts)
