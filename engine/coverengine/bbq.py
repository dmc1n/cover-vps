# ruff: noqa: E501  (drawing proportions keep their "param-ok" note on the same line)
"""Barbecues in 3D from their published sizes, and the cover over them (ADR-119).

One builder per kind of barbecue, in mm, Z up, on the ground, the front towards -y, centred
in plan on its bounding box (like `furniture.build`):

- `kamado`: a ceramic egg (Big Green Egg, Kamado Joe, Monolith) with its front handle, back
  hinge and top vent, standing in a nest (steel legs and ring), optionally with side tables
  (EGG Mates, Kamado Joe's shelves) or a nest handler; or set into a table;
- `gas`: a gas grill on a cart: the cabinet, the hood (a rounded lid), the handle bar in
  front, side shelves;
- `pellet`: a pellet grill: a barrel lid on legs, the hopper on one side, a side shelf;
- `fire_table`: a fire table or plancha (OFYR and the like): a round plate on a cone, or a
  square table.

The same builders serve the shop's 3D preview (`furniture.build`, from the customer's sizes)
and the catalogue models of `scripts/bbq_models.py` (from the manufacturers' sizes).

`fit` puts the configurator's cover over such a barbecue: a round cover with a cone on top
(a kamado, a round fire table) or a box with a hipped roof (everything else). Both slope on
every point of the top, so water runs off (rule 12), and their sizes come from the barbecue's
own points plus the ease, so the hood, the dome, the handle and the shelves all fit under it.
A cover goes on a COLD barbecue: acrylic canvas is not heat-proof.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import trimesh

# proportions of the parts that are not in the published sizes (display and fit only)
EGG_WIDEST = 0.47  # param-ok: display: the egg's widest point as a share of its height
EGG_FOOT = 0.56  # param-ok: display: the egg's foot diameter as a share of its widest
VENT_D = 0.18  # param-ok: display: the top vent's diameter as a share of the egg's
VENT_H = 0.07  # param-ok: display: the top vent's height as a share of the egg's diameter
HANDLE_W = 0.42  # param-ok: display: the handle bar's width as a share of the egg's diameter
HINGE_W = 0.28  # param-ok: display: the hinge's width as a share of the egg's diameter
BAR = 30.0  # param-ok: display: mm, a bar's or a board's thickness
LEG = 35.0  # param-ok: display: mm, a nest's or a cart's leg
SEG = 48  # param-ok: display: segments round an egg or a plate


def _box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> trimesh.Trimesh:
    b = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    b.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    return b


def _join(parts: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    m = trimesh.util.concatenate(parts)
    assert isinstance(m, trimesh.Trimesh)
    lo, hi = m.bounds
    m.apply_translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
    return m


def _cyl(r: float, z0: float, z1: float, x: float = 0.0, y: float = 0.0) -> trimesh.Trimesh:
    c = trimesh.creation.cylinder(radius=r, height=z1 - z0, sections=SEG)
    c.apply_translation((x, y, (z0 + z1) / 2))
    return c


def egg_profile(d: float, h: float) -> np.ndarray:
    """The egg's half outline (radius, z) from its foot to its top, without the top vent."""
    R, zm = d / 2, EGG_WIDEST * h
    rf = EGG_FOOT * R
    a_low = zm / math.sqrt(1 - (rf / R) ** 2)
    zs = np.linspace(0, h, 41)  # param-ok: display: profile points
    r = np.where(
        zs <= zm,
        R * np.sqrt(np.clip(1 - ((zm - zs) / a_low) ** 2, 0, 1)),
        R * np.sqrt(np.clip(1 - ((zs - zm) / (h - zm)) ** 2, 0, 1)),
    )
    return np.column_stack([np.r_[0.0, r, 0.0], np.r_[0.0, zs, h]])


def egg(d: float, h: float, z0: float = 0.0, handle: float = 0.0, hinge: float = 0.0
        ) -> list[trimesh.Trimesh]:  # fmt: skip
    """A kamado: the egg (diameter d, height h with its top vent) on z0, the handle sticking
    out `handle` in front of the egg, the hinge `hinge` behind it (mm)."""
    vent_h = VENT_H * d
    body_h = h - vent_h
    body = trimesh.creation.revolve(egg_profile(d, body_h), sections=SEG)
    body.apply_translation((0, 0, z0))
    if body.volume < 0:
        body.invert()
    parts = [body, _cyl(VENT_D * d / 2, z0 + body_h - vent_h, z0 + h)]
    R, zm = d / 2, z0 + EGG_WIDEST * body_h
    lid = zm + 0.1 * body_h  # param-ok: display: just above the lid's seam
    if handle > 0:
        w = HANDLE_W * d / 2
        y_out = -(R + handle)
        parts += [_box(-w, y_out, lid, w, y_out + BAR, lid + BAR),
                  _box(-w, y_out, lid, -w + BAR, -R * 0.85, lid + BAR),  # param-ok: display
                  _box(w - BAR, y_out, lid, w, -R * 0.85, lid + BAR)]  # fmt: skip # param-ok: display
    if hinge > 0:
        w = HINGE_W * d / 2
        parts.append(_box(-w, R * 0.8, zm - 0.15 * body_h, w, R + hinge,  # param-ok: display
                          zm + 0.2 * body_h))  # fmt: skip # param-ok: display
    return parts


def kamado(egg_d: float, height: float, *, egg_h: float | None = None, depth: float | None = None,
           width: float | None = None, shelf_depth: float | None = None,
           handler: float = 0.0, stand: str = "nest", carrier: float = 0.0,
           egg_mesh: trimesh.Trimesh | None = None) -> trimesh.Trimesh:  # fmt: skip
    """A kamado in a nest (or on a low stand: stand "none"), mm.

    egg_d: the egg's widest diameter; height: the top of the top vent from the ground (lid
    closed); egg_h: the egg's own height (default from its diameter); depth: front of the handle
    to back of the hinge (default the egg plus a handle and a hinge); width: over the side tables
    (none when not wider than the egg); handler: a nest handler sticking out at the right;
    carrier: the width over a table-top egg's carrier handles (MiniMax); egg_mesh: a measured
    egg (its foot at z = 0, centred, the handle towards -y) in place of the drawn one."""
    eh = egg_h or 1.4 * egg_d  # param-ok: display: an egg is about 1.4 times as high as wide
    eh = min(eh, height)
    z0 = height - eh
    dep = depth or egg_d * 1.32  # param-ok: display: a handle and a hinge
    handle = max(0.0, 0.62 * (dep - egg_d))  # param-ok: display: most of it is the handle
    hinge = max(0.0, dep - egg_d - handle)
    # put the egg so the handle and the hinge give the depth asked
    if egg_mesh is not None:
        given = egg_mesh.copy()
        given.apply_translation((0, 0, z0))
        parts = [given]
    else:
        parts = egg(egg_d, eh, z0, handle, hinge)
    R = egg_d / 2
    if carrier > egg_d:  # a carrier's two handles at the egg's foot
        for sx in (-1, 1):
            x0, x1 = sx * 0.5 * R, sx * carrier / 2  # param-ok: display
            parts.append(_box(min(x0, x1), -2 * BAR, z0 + BAR, max(x0, x1), 2 * BAR, z0 + 2 * BAR))
    if stand == "nest" and z0 > BAR:
        ring_z = z0 + 0.18 * eh  # param-ok: display: the nest's ring round the egg's foot
        for a in (45, 135, 225, 315):  # param-ok: display: four legs
            x, y = (
                0.8 * R * math.cos(math.radians(a)),
                0.8 * R * math.sin(math.radians(a)),
            )  # param-ok: display
            parts.append(_box(x - LEG / 2, y - LEG / 2, 0, x + LEG / 2, y + LEG / 2, ring_z))
        ring = trimesh.creation.annulus(r_min=0.8 * R, r_max=0.8 * R + LEG, height=BAR,  # param-ok: display
                                        sections=SEG)  # fmt: skip
        ring.apply_translation((0, 0, ring_z - BAR / 2))
        low = trimesh.creation.annulus(r_min=0.8 * R, r_max=0.8 * R + LEG, height=BAR,  # param-ok: display
                                       sections=SEG)  # fmt: skip
        low.apply_translation((0, 0, z0 - BAR / 2))
        parts += [ring, low]
        if handler > 0:
            parts.append(
                _box(0.8 * R, -BAR, ring_z - BAR, 0.8 * R + handler, BAR, ring_z)
            )  # param-ok: display
    elif z0 > BAR:  # a plain stand
        parts.append(_cyl(0.6 * R, 0, z0))  # param-ok: display
    if width and width > egg_d + 2 * BAR:
        zs = z0 + EGG_WIDEST * (eh - VENT_H * egg_d)  # the lid's seam: where the tables are
        sd = shelf_depth or 0.75 * egg_d  # param-ok: display: an EGG Mate's depth
        for sx in (-1, 1):
            x0, x1 = sx * 0.9 * R, sx * width / 2  # param-ok: display: hooked onto the nest
            parts.append(_box(min(x0, x1), -sd / 2, zs - BAR, max(x0, x1), sd / 2, zs))
            if stand == "nest":  # its bracket down to the ring
                xb = sx * (0.8 * R + LEG)  # param-ok: display
                parts.append(
                    _box(min(xb, x0), -BAR, zs - 0.25 * eh, max(xb, x0), BAR, zs)
                )  # param-ok: display
    return _join(parts)


def kamado_table(egg_d: float, height: float, table_l: float, table_w: float, table_h: float,
                 egg_h: float | None = None) -> trimesh.Trimesh:  # fmt: skip
    """A kamado set into a table (the EGG table, a modular nest frame), mm. The egg stands in
    the middle, its foot on the table's lower shelf."""
    eh = min(egg_h or 1.33 * egg_d, height)  # param-ok: display
    z0 = height - eh
    parts = egg(egg_d, eh, z0, handle=0.25 * egg_d, hinge=0.12 * egg_d)  # param-ok: display
    top = 40.0  # param-ok: display: mm, a table top
    parts.append(_box(-table_l / 2, -table_w / 2, table_h - top, table_l / 2, table_w / 2, table_h))
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * (table_l / 2 - 2 * LEG), sy * (table_w / 2 - 2 * LEG)
            parts.append(_box(x - LEG, y - LEG, 0, x + LEG, y + LEG, table_h - top))
    shelf = max(BAR, min(z0, table_h - top - BAR))
    parts.append(_box(-table_l / 2 + LEG, -table_w / 2 + LEG, shelf - BAR, table_l / 2 - LEG,
                      table_w / 2 - LEG, shelf))  # fmt: skip
    return _join(parts)


def _hood(width: float, y0: float, y1: float, z0: float, z1: float) -> trimesh.Trimesh:
    """A rounded lid over y0..y1 (front to back) from z0 up to z1, extruded along x."""
    import shapely

    t = np.linspace(0, math.pi, 25)  # param-ok: display: the lid's arc
    yc, a = (y0 + y1) / 2, (y1 - y0) / 2
    b = z1 - z0
    arc = [(yc - a * math.cos(s), z0 + b * math.sin(s) ** 0.6) for s in t]  # param-ok: display
    poly = shapely.Polygon([(y0, z0)] + arc + [(y1, z0)]).buffer(0)
    m = trimesh.creation.extrude_polygon(poly, width)
    # the polygon is in (y, z); the extrusion runs along its own z: turn it to x
    m.apply_transform(np.array([[0, 0, 1, -width / 2], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]],
                               dtype=float))  # fmt: skip
    return m


def gas(width: float, depth: float, height: float, shelf_h: float, hood_w: float | None = None,
        handle: float = 80.0) -> trimesh.Trimesh:  # fmt: skip  # param-ok: display: mm
    """A gas grill on a cart, mm: width over the side shelves, depth with the handle, height to
    the top of the closed hood, the shelves' height, the hood's (and cart's) width."""
    hw = min(hood_w or 0.6 * width, width)  # param-ok: display
    d = depth - handle
    y0, y1 = -depth / 2 + handle, depth / 2
    box_top = shelf_h + 0.12 * (height - shelf_h)  # param-ok: display: the firebox's rim
    parts = [
        _box(-hw / 2, y0, 2 * LEG, hw / 2, y1, box_top),  # the cabinet and firebox
        _hood(hw, y0, y1, box_top, height),
    ]
    for sx in (-1, 1):  # side shelves
        if width > hw + BAR:
            x0, x1 = sx * hw / 2, sx * width / 2
            parts.append(_box(min(x0, x1), y0 + 0.05 * d, shelf_h - BAR, max(x0, x1),  # param-ok: display
                              y1 - 0.05 * d, shelf_h))  # fmt: skip # param-ok: display
        for sy in (y0 + LEG, y1 - LEG):  # castors
            parts.append(_cyl(LEG, 0, 2 * LEG, sx * (hw / 2 - LEG), sy))
    hz = box_top + 0.55 * (height - box_top)  # param-ok: display: the handle bar's height
    bar = trimesh.creation.cylinder(
        radius=BAR / 2, height=0.8 * hw, sections=16
    )  # param-ok: display
    bar.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0, 1, 0)))
    bar.apply_translation((0, -depth / 2 + BAR / 2, hz))
    parts.append(bar)
    for sx in (-1, 1):
        parts.append(_box(sx * 0.4 * hw - BAR / 2, -depth / 2, hz - BAR / 2, sx * 0.4 * hw + BAR / 2,  # param-ok: display
                          y0 + BAR, hz + BAR / 2))  # fmt: skip
    return _join(parts)


def pellet(width: float, depth: float, height: float, barrel_l: float | None = None,
           hopper_w: float = 330.0, handle: float = 80.0) -> trimesh.Trimesh:  # fmt: skip  # param-ok: display: mm
    """A pellet grill, mm: width over the hopper and the side shelf, depth with the handle,
    height to the top of the lid; the barrel's length (the lid)."""
    bl = min(barrel_l or 0.62 * width, width - hopper_w)  # param-ok: display
    r = min((depth - handle) / 2, 0.3 * height)  # param-ok: display
    zc = height - r
    barrel = trimesh.creation.cylinder(radius=r, height=bl, sections=SEG)
    barrel.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0, 1, 0)))
    barrel.apply_translation((0, 0, zc))
    x0 = -bl / 2
    parts = [barrel, _box(x0, -r, zc - r - BAR, -x0, r, zc)]
    for sx in (-1, 1):  # legs and a bottom shelf
        for sy in (-1, 1):
            parts.append(_box(sx * bl / 2 - LEG * (sx > 0), sy * r * 0.8 - LEG / 2, 0,  # param-ok: display
                              sx * bl / 2 + LEG * (sx < 0), sy * r * 0.8 + LEG / 2, zc - r))  # fmt: skip # param-ok: display
    parts.append(_box(x0, -0.8 * r, 0.25 * zc, -x0, 0.8 * r, 0.25 * zc + BAR))  # param-ok: display
    # the hopper at the right, a little lower than the lid
    ht = height - 0.04 * height  # param-ok: display
    parts.append(
        _box(bl / 2, -0.6 * r, zc - r - 0.15 * height, bl / 2 + hopper_w, 0.6 * r, ht)
    )  # param-ok: display
    side = width - bl - hopper_w
    if side > BAR:  # a side shelf at the left
        parts.append(_box(x0 - side, -0.8 * r, zc - BAR, x0, 0.8 * r, zc))  # param-ok: display
    bar = trimesh.creation.cylinder(
        radius=BAR / 2, height=0.8 * bl, sections=16
    )  # param-ok: display
    bar.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0, 1, 0)))
    bar.apply_translation((0, -r - handle + BAR / 2, zc + 0.2 * r))  # param-ok: display
    parts.append(bar)
    for sx in (-1, 1):
        parts.append(_box(sx * 0.4 * bl - BAR / 2, -r - handle, zc + 0.2 * r - BAR / 2,  # param-ok: display
                          sx * 0.4 * bl + BAR / 2, -0.9 * r, zc + 0.2 * r + BAR / 2))  # fmt: skip # param-ok: display
    return _join(parts)


def fire_table(width: float, height: float, depth: float | None = None, round_: bool = True
               ) -> trimesh.Trimesh:  # fmt: skip
    """A fire table or plancha, mm: a round plate (diameter `width`) on a cone that narrows
    downwards (OFYR Classic), or a square or oblong table (OFYR Island) with the round plate set
    into its top."""
    plate = 20.0  # param-ok: display: mm
    if round_:
        R = width / 2
        prof = np.array([[0, 0], [0.32 * R, 0], [0.62 * R, height - plate],  # param-ok: display
                         [R, height - plate], [R, height], [0, height]])  # fmt: skip
        m = trimesh.creation.revolve(prof, sections=SEG * 2)
        if m.volume < 0:
            m.invert()
        return _join([m])
    d = depth or width
    parts = [_box(-width / 2, -d / 2, height - 3 * plate, width / 2, d / 2, height - plate),
             _box(-width / 2 + LEG, -d / 2 + LEG, 0, width / 2 - LEG, d / 2 - LEG, height - plate),
             _cyl(0.4 * min(width, d), height - plate, height)]  # fmt: skip # param-ok: display
    return _join(parts)


# ---- the configurator's cover over a barbecue ----------------------------------------------


def fit(mesh: trimesh.Trimesh, shape: str, ease: float, slope_min_deg: float,
        slope_max_deg: float, wall_min: float) -> dict[str, float]:  # fmt: skip
    """The cover over a barbecue (mm): a cone on a round band ("cone round") or a hipped roof on
    a box ("hip box"). Every point of the barbecue stays `ease` inside the walls and under the
    roof; of the roof slopes from `slope_min_deg` to `slope_max_deg` the one with the least
    fabric is taken, keeping the walls at least `wall_min` high (room for the vents)."""
    v = np.asarray(mesh.vertices, dtype=np.float64)
    lo, hi = v.min(axis=0), v.max(axis=0)
    c = (lo + hi) / 2
    x, y, z = v[:, 0] - c[0], v[:, 1] - c[1], v[:, 2]
    if shape == "cone round":
        r = np.hypot(x, y)
        R = float(r.max()) + ease
        dist, half = r, R
        plan, rim = math.pi * R * R, 2 * math.pi * R
    else:
        a, b = float(np.abs(x).max()) + ease, float(np.abs(y).max()) + ease
        if b > a:  # the ridge runs along the longer side
            a, b, x, y = b, a, y, x
        reach = a - b
        dist = np.maximum(np.abs(y), np.abs(x) - reach)
        half = b
        plan, rim = 4 * a * b, 4 * (a + b)
    best: dict[str, float] | None = None
    deg = slope_min_deg
    while deg <= slope_max_deg + 1e-9:
        s = math.tan(math.radians(deg))
        top = float((z + ease + s * dist).max())
        wall = top - s * half
        if wall >= wall_min:
            area = rim * wall + plan / math.cos(math.radians(deg))
            if best is None or area < best["area_mm2"]:
                best = {"wall_mm": wall, "rise_mm": top - wall, "slope_deg": deg,
                        "area_mm2": area}  # fmt: skip
        deg += 1.0
    if best is None:  # a very low barbecue: the steepest roof, the walls as asked
        s = math.tan(math.radians(slope_max_deg))
        top = max(float((z + ease + s * dist).max()), wall_min + s * half)
        best = {"wall_mm": top - s * half, "rise_mm": s * half, "slope_deg": slope_max_deg,
                "area_mm2": 0.0}  # fmt: skip
    if shape == "cone round":
        best["diameter_mm"] = 2 * half
    else:
        best["length_mm"], best["depth_mm"] = 2 * (half + reach), 2 * half
    return best


def build(product: str, v: dict[str, Any]) -> trimesh.Trimesh:
    """The configurator's barbecue from the customer's sizes (cm), as a mesh in mm, its longer
    side along x under a hipped cover (as its ridge runs)."""
    m = _build(product, v)
    ext = m.bounds[1] - m.bounds[0]
    if ext[1] > ext[0] + 1e-6 and cover_shape(product, v) == "hip box":
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi / 2, (0, 0, 1)))
    return m


def _build(product: str, v: dict[str, Any]) -> trimesh.Trimesh:
    cm = 10.0  # param-ok: unit conversion
    f = {k: float(x) * cm for k, x in v.items() if k.endswith("_cm")}
    if product == "bbq_kamado":
        shelves = bool(v.get("side_tables"))
        return kamado(f["egg_diameter_cm"], f["closed_height_cm"],
                      depth=max(f["handle_depth_cm"], f["egg_diameter_cm"]),
                      width=f["tables_width_cm"] if shelves else None)  # fmt: skip
    if product == "bbq_kamado_table":
        return kamado_table(f["egg_diameter_cm"], max(f["closed_height_cm"], f["table_height_cm"]),
                            f["table_length_cm"], f["table_width_cm"],
                            f["table_height_cm"])  # fmt: skip
    if product == "bbq_gas":
        return gas(f["width_cm"], f["depth_cm"], f["closed_height_cm"],
                   min(f["shelf_height_cm"], f["closed_height_cm"]), f["hood_width_cm"])  # fmt: skip
    if product == "bbq_pellet":
        return pellet(f["width_cm"], f["depth_cm"], f["closed_height_cm"], f["lid_length_cm"])
    if product == "bbq_fire_table":
        square = bool(v.get("square"))
        return fire_table(f["fire_width_cm"], f["height_cm"], f["depth_cm"] if square else None,
                          round_=not square)  # fmt: skip
    raise ValueError(f"no barbecue builder for {product!r}")


def cover_shape(product: str, v: dict[str, Any]) -> str:
    """Round with a cone for a kamado alone or a round fire table; a hipped box otherwise."""
    if product == "bbq_kamado" and not v.get("side_tables"):
        return "cone round"
    if product == "bbq_fire_table" and not v.get("square"):
        return "cone round"
    return "hip box"


def plan_cm(product: str, v: dict[str, Any]) -> list[float]:
    """The barbecue's size as the catalogue cards have it: length ≥ width, then height (cm).
    Built from the barbecue itself, so the customer's sizes and a catalogue model's bounding
    box are measured the same way (handles, hinges and shelves included)."""
    m = build(product, v)
    s = (m.bounds[1] - m.bounds[0]) / 10.0  # param-ok: mm to cm
    return [round(float(x), 1) for x in [max(s[0], s[1]), min(s[0], s[1]), s[2]]]


def fields(product: str, size_cm: list[float]) -> dict[str, Any]:
    """A catalogue barbecue's size card as the configurator's fields (to price its cover)."""
    length, width, height = size_cm
    if product == "bbq_kamado":
        if length > width * 1.6:  # param-ok: far wider than deep: side tables
            return {"egg_diameter_cm": width / 1.32, "handle_depth_cm": width,  # param-ok: handle
                    "closed_height_cm": height, "tables_width_cm": length,
                    "side_tables": True}  # fmt: skip
        return {"egg_diameter_cm": width, "handle_depth_cm": length, "closed_height_cm": height,
                "side_tables": False}  # fmt: skip
    if product == "bbq_kamado_table":
        return {"table_length_cm": length, "table_width_cm": width, "closed_height_cm": height}
    if product == "bbq_fire_table":
        return {"fire_width_cm": length, "depth_cm": width, "height_cm": height,
                "square": length - width > 1.0}  # fmt: skip
    return {"width_cm": length, "depth_cm": width, "closed_height_cm": height}
