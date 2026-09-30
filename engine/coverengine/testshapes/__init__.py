"""Deterministic procedural test shapes with analytic reference dimensions.

Dimensions come from `testdata/shapes.yaml`. Analytic surfaces are single meshes; furniture
primitives are deliberately overlapping, un-merged boxes, i.e. triangle soups like real CAD
exports. Every shape is written as a binary STL plus a JSON sidecar of reference values.
"""

from __future__ import annotations

import json
import math
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from ruamel.yaml import YAML

from coverengine import __version__
from coverengine.params.registry import repo_root

FORMAT_VERSION = 1
HALF = 1 / 2  # half a unit / half a turn (geometry, not a parameter)
Array = NDArray[np.float64]
IntArray = NDArray[np.int64]


@dataclass
class Shape:
    name: str
    vertices: Array
    faces: IntArray
    # Analytic values `cover info` can measure exactly from the mesh (compared at 1e-6 mm):
    # name -> (value, measure), measure being a key of coverengine.io.info.MEASURES.
    exact: dict[str, tuple[float, str]] = field(default_factory=dict)
    # Analytic values of the continuous surface; the mesh approximates them (information only).
    reference: dict[str, float] = field(default_factory=dict)
    notes: dict[str, Any] = field(default_factory=dict)


def shapes_config_path() -> Path:
    return repo_root() / "testdata" / "shapes.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    data = YAML(typ="safe", pure=True).load((path or shapes_config_path()).read_text())
    return dict(data)


# ---------------------------------------------------------------------------------------------
# Mesh helpers


def _grid(nu: int, nv: int, fn: Callable[[Array, Array], Array]) -> tuple[Array, IntArray]:
    """Surface over a (nu+1) x (nv+1) parameter grid on [0,1]^2; returns vertices and faces."""
    u, v = np.meshgrid(np.linspace(0.0, 1.0, nu + 1), np.linspace(0.0, 1.0, nv + 1), indexing="ij")
    verts = fn(u.ravel(), v.ravel())
    idx = np.arange((nu + 1) * (nv + 1)).reshape(nu + 1, nv + 1)
    a, b = idx[:-1, :-1].ravel(), idx[1:, :-1].ravel()
    c, d = idx[1:, 1:].ravel(), idx[:-1, 1:].ravel()
    faces = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    return verts, faces.astype(np.int64)


def _periodic(nu: int, nv: int, fn: Callable[[Array, Array], Array]) -> tuple[Array, IntArray]:
    """Like _grid but u wraps around (u = k / nu for k in 0..nu-1): cylinders, cones."""
    u, v = np.meshgrid(np.arange(nu) / nu, np.linspace(0.0, 1.0, nv + 1), indexing="ij")
    verts = fn(u.ravel(), v.ravel())
    idx = np.arange(nu * (nv + 1)).reshape(nu, nv + 1)
    nxt = np.roll(idx, -1, axis=0)
    a, b = idx[:, :-1].ravel(), nxt[:, :-1].ravel()
    c, d = nxt[:, 1:].ravel(), idx[:, 1:].ravel()
    faces = np.concatenate([np.stack([a, b, c], 1), np.stack([a, c, d], 1)])
    return verts, faces.astype(np.int64)


def _cos_sin(turns: Array) -> tuple[Array, Array]:
    """cos and sin of 2*pi*turns, exact at quarter turns so extreme vertices are exact."""
    ang = 2.0 * math.pi * turns
    c, s = np.cos(ang), np.sin(ang)
    quarter = np.isclose((turns * 4.0) % 1.0, 0.0) | np.isclose((turns * 4.0) % 1.0, 1.0)
    c = np.where(quarter, np.round(c), c)
    s = np.where(quarter, np.round(s), s)
    return c, s


def _box(lo: Array | list[float], hi: Array | list[float]) -> tuple[Array, IntArray]:
    lo_, hi_ = np.asarray(lo, float), np.asarray(hi, float)
    corners = np.array(
        [[x, y, z] for x in (lo_[0], hi_[0]) for y in (lo_[1], hi_[1]) for z in (lo_[2], hi_[2])]
    )
    # corner index = 4*ix + 2*iy + iz; one quad per side, wound so normals point outward
    quads = []
    for axis in range(3):
        bit = 1 << (2 - axis)
        others = [1 << (2 - a) for a in range(3) if a != axis]
        for side in (0, 1):
            base = bit * side
            ring = [base, base + others[0], base + others[0] + others[1], base + others[1]]
            outward_first = (axis == 1) != (side == 1)
            quads.append(ring if outward_first else ring[::-1])
    faces = [(a, b, c) for a, b, c, d in quads] + [(a, c, d) for a, b, c, d in quads]
    return corners, np.array(faces, dtype=np.int64)


def _soup(parts: list[tuple[Array, IntArray]]) -> tuple[Array, IntArray]:
    verts, faces, offset = [], [], 0
    for v, f in parts:
        verts.append(v)
        faces.append(f + offset)
        offset += len(v)
    return np.concatenate(verts), np.concatenate(faces)


def _rot_x(deg: float) -> Array:
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, -s], [0.0, s, c]])


def _bbox_exact(v: Array) -> dict[str, dict[str, Any]]:
    """Bounding box of the float64 construction (not of the stored float32 values)."""
    lo, hi = v.min(axis=0), v.max(axis=0)
    out: dict[str, dict[str, Any]] = {}
    for i, axis in enumerate("xyz"):
        out[f"bbox_min_{axis}_mm"] = {"value": float(lo[i]), "measure": f"bbox_min_{axis}"}
        out[f"bbox_max_{axis}_mm"] = {"value": float(hi[i]), "measure": f"bbox_max_{axis}"}
    return out


# ---------------------------------------------------------------------------------------------
# Analytic shapes


def plate(c: Mapping[str, Any]) -> Shape:
    sx, sy = float(c["size_x"]), float(c["size_y"])
    v, f = _grid(
        c["div_x"],
        c["div_y"],
        lambda u, w: np.stack([(u - HALF) * sx, (w - HALF) * sy, np.zeros_like(u)], 1),
    )
    return Shape("plate", v, f, reference={"area_mm2": sx * sy})


def cylinder(c: Mapping[str, Any]) -> Shape:
    r, h = float(c["radius"]), float(c["height"])

    def fn(u: Array, w: Array) -> Array:
        cs, sn = _cos_sin(u)
        return np.stack([r * cs, r * sn, w * h], 1)

    v, f = _periodic(c["segments"], c["rings"], fn)
    return Shape(
        "cylinder",
        v,
        f,
        exact={"radius_mm": (r, "half_size_x"), "height_mm": (h, "size_z")},
        reference={"area_mm2": 2 * math.pi * r * h},
    )


def cone(c: Mapping[str, Any]) -> Shape:
    r, h = float(c["radius"]), float(c["height"])
    segments, rings = c["segments"], c["rings"]

    def fn(u: Array, w: Array) -> Array:
        cs, sn = _cos_sin(u)
        rr = r * (1.0 - w)
        return np.stack([rr * cs, rr * sn, w * h], 1)

    v, f = _periodic(segments, rings, fn)
    # the top ring collapses to the apex: merge it into one vertex
    top = np.arange(segments) * (rings + 1) + rings
    apex = top[0]
    f = np.where(np.isin(f, top), apex, f)
    f = f[(f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])]
    v, f = _compact(v, f)
    slant = math.hypot(r, h)
    return Shape(
        "cone",
        v,
        f,
        exact={"radius_mm": (r, "half_size_x"), "height_mm": (h, "size_z")},
        reference={"area_mm2": math.pi * r * slant, "slant_mm": slant},
    )


def _compact(v: Array, f: IntArray) -> tuple[Array, IntArray]:
    used = np.unique(f)
    remap = np.full(len(v), -1, dtype=np.int64)
    remap[used] = np.arange(len(used))
    return v[used], remap[f]


def _uv_sphere_patch(
    r: float, nu: int, nv: int, lon: tuple[float, float], colat: tuple[float, float]
) -> tuple[Array, IntArray]:
    def fn(u: Array, w: Array) -> Array:
        turns = lon[0] + (lon[1] - lon[0]) * u
        cs, sn = _cos_sin(turns)
        # colatitude in half-turns: 0 = north pole, HALF = south pole (in units of full turns)
        ct = colat[0] + (colat[1] - colat[0]) * w
        cz, sz = _cos_sin(ct)
        return np.stack([r * sz * cs, r * sz * sn, r * cz], 1)

    return _grid(nu, nv, fn)


def _weld(v: Array, f: IntArray) -> tuple[Array, IntArray]:
    """Merge coincident vertices (poles, seams) and drop degenerate faces."""
    key = np.round(v, 9)
    _, first, inverse = np.unique(key, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first)
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    v2 = v[first[order]]
    f2 = rank[inverse.ravel()][f]
    f2 = f2[(f2[:, 0] != f2[:, 1]) & (f2[:, 1] != f2[:, 2]) & (f2[:, 0] != f2[:, 2])]
    return v2, f2


def sphere(c: Mapping[str, Any]) -> Shape:
    r = float(c["radius"])
    v, f = _uv_sphere_patch(r, c["segments"], c["rings"], (0.0, 1.0), (0.0, HALF))
    v, f = _weld(v, f)
    v = v + np.array([0.0, 0.0, r])
    return Shape(
        "sphere",
        v,
        f,
        exact={"radius_mm": (r, "half_size_z")},
        reference={"area_mm2": 4 * math.pi * r * r},
    )


def sphere_octant(c: Mapping[str, Any]) -> Shape:
    r = float(c["radius"])
    n = c["divisions"]
    v, f = _uv_sphere_patch(r, n, n, (0.0, 0.25), (0.0, 0.25))
    v, f = _weld(v, f)
    return Shape(
        "sphere_octant",
        v,
        f,
        exact={"radius_mm": (r, "size_x")},
        reference={"area_mm2": math.pi * r * r / 2},
    )


def saddle(c: Mapping[str, Any]) -> Shape:
    s, rc, n = float(c["size"]), float(c["curvature_radius"]), c["divisions"]
    lift = (s / 2) ** 2 / (2 * rc)

    def fn(u: Array, w: Array) -> Array:
        x, y = (u - HALF) * s, (w - HALF) * s
        return np.stack([x, y, (x * x - y * y) / (2 * rc) + lift], 1)

    v, f = _grid(n, n, fn)
    return Shape(
        "saddle",
        v,
        f,
        exact={"height_mm": (2 * lift, "size_z")},
        notes={"surface": "z = (x^2 - y^2) / (2 R) + lift", "lift_mm": lift, "R_mm": rc},
    )


def torus_segment(c: Mapping[str, Any]) -> Shape:
    big, small = float(c["major_radius"]), float(c["minor_radius"])
    turns = float(c["angle_deg"]) / 360.0

    def fn(u: Array, w: Array) -> Array:
        cu, su = _cos_sin(u * turns)
        cw, sw = _cos_sin(w)
        rr = big + small * cw
        return np.stack([rr * cu, rr * su, small * sw + small], 1)

    v, f = _grid(c["segments"], c["tube_segments"], fn)
    v, f = _weld(v, f)
    return Shape(
        "torus_segment",
        v,
        f,
        exact={"height_mm": (2 * small, "size_z")},
        reference={"area_mm2": 4 * math.pi**2 * big * small * turns},
    )


# ---------------------------------------------------------------------------------------------
# Furniture primitives (triangle soups of overlapping boxes, front toward -y)


def box_with_legs(c: Mapping[str, Any]) -> Shape:
    bx, by, bz = map(float, c["body"])
    lx, ly, lz = map(float, c["leg"])
    parts = [_box([-bx / 2, -by / 2, lz], [bx / 2, by / 2, lz + bz])]
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0 = sx * bx / 2 - (lx if sx > 0 else 0.0)
            y0 = sy * by / 2 - (ly if sy > 0 else 0.0)
            parts.append(_box([x0, y0, 0.0], [x0 + lx, y0 + ly, lz]))
    v, f = _soup(parts)
    return Shape(
        "box_with_legs", v, f, exact={"height_mm": (lz + bz, "size_z")}, notes={"parts": len(parts)}
    )


def slatted_table(c: Mapping[str, Any]) -> Shape:
    length, w, t, gap, n = (
        float(c["length"]),
        float(c["slat_width"]),
        float(c["slat_thickness"]),
        float(c["slat_gap"]),
        int(c["slats"]),
    )
    height = float(c["height"])
    depth = n * w + (n - 1) * gap
    lx, ly = map(float, c["leg"])
    inset = float(c["leg_inset"])
    rail_w, rail_h = map(float, c["rail"])
    parts, slats_y = [], []
    for i in range(n):
        y0 = -depth / 2 + i * (w + gap)
        slats_y.append([y0, y0 + w])
        parts.append(_box([-length / 2, y0, height - t], [length / 2, y0 + w, height]))
    rail_top = height - t
    for sx in (-1, 1):
        x_leg = sx * (length / 2 - inset) - (lx if sx > 0 else 0.0)
        parts.append(
            _box([x_leg, -depth / 2, rail_top - rail_h], [x_leg + rail_w, depth / 2, rail_top])
        )
        for sy in (-1, 1):
            y_leg = sy * (depth / 2 - inset) - (ly if sy > 0 else 0.0)
            parts.append(_box([x_leg, y_leg, 0.0], [x_leg + lx, y_leg + ly, rail_top]))
    v, f = _soup(parts)
    return Shape(
        "slatted_table",
        v,
        f,
        exact={
            "height_mm": (height, "size_z"),
            "depth_mm": (depth, "size_y"),
            "length_mm": (length, "size_x"),
        },
        notes={"slat_gap_mm": gap, "slats_y_mm": slats_y, "parts": len(parts)},
    )


def chair(c: Mapping[str, Any]) -> Shape:
    sx, sy, sz = map(float, c["seat"])
    seat_top = float(c["seat_height"])
    bx, bt, bl = map(float, c["back"])
    tilt = float(c["back_tilt_deg"])
    lx, ly = map(float, c["leg"])
    parts = [_box([-sx / 2, -sy / 2, seat_top - sz], [sx / 2, sy / 2, seat_top])]
    # back: slab standing on the rear edge of the seat, tilted backwards about its bottom edge
    bv, bf = _box([-bx / 2, 0.0, 0.0], [bx / 2, bt, bl])
    bv = bv @ _rot_x(-tilt).T + np.array([0.0, sy / 2 - bt, seat_top])
    parts.append((bv, bf))
    for px in (-1, 1):
        for py in (-1, 1):
            x0 = px * sx / 2 - (lx if px > 0 else 0.0)
            y0 = py * sy / 2 - (ly if py > 0 else 0.0)
            parts.append(_box([x0, y0, 0.0], [x0 + lx, y0 + ly, seat_top - sz]))
    v, f = _soup(parts)
    return Shape("chair", v, f, notes={"parts": len(parts), "seat_height_mm": seat_top})


def l_lounge(c: Mapping[str, Any]) -> Shape:
    mx, my, mz = map(float, c["main"])
    wx, wy, wz = map(float, c["wing"])
    parts = [
        _box([-mx / 2, -my / 2, 0.0], [mx / 2, my / 2, mz]),
        _box([mx / 2 - wx, -my / 2, 0.0], [mx / 2, -my / 2 + wy, wz]),
    ]
    v, f = _soup(parts)
    return Shape("l_lounge", v, f, notes={"parts": len(parts)})


BUILDERS: dict[str, Callable[[Mapping[str, Any]], Shape]] = {
    "plate": plate,
    "cylinder": cylinder,
    "cone": cone,
    "sphere": sphere,
    "sphere_octant": sphere_octant,
    "saddle": saddle,
    "torus_segment": torus_segment,
    "box_with_legs": box_with_legs,
    "slatted_table": slatted_table,
    "chair": chair,
    "l_lounge": l_lounge,
}


def build_all(config: Mapping[str, Any] | None = None) -> list[Shape]:
    cfg = config or load_config()
    specs = {**cfg["analytic"], **cfg["furniture"]}
    unknown = set(specs) - set(BUILDERS)
    if unknown:
        raise ValueError(f"shapes.yaml: no builder for {sorted(unknown)}")
    return [BUILDERS[name](specs[name]) for name in BUILDERS if name in specs]


# ---------------------------------------------------------------------------------------------
# Output


def write_stl(path: Path, vertices: Array, faces: IntArray, name: str) -> None:
    """Binary STL with a fixed header so output is byte-identical across runs."""
    tri = vertices[faces].astype(np.float64)
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    lengths = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, lengths, out=np.zeros_like(normals), where=lengths > 0)
    record = np.zeros(len(faces), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("attr", "<u2")])
    record["n"] = normals
    record["v"] = tri
    header = f"coverengine testshape {name}".encode("ascii").ljust(80, b" ")[:80]
    with path.open("wb") as fh:
        fh.write(header)
        fh.write(struct.pack("<I", len(faces)))
        fh.write(record.tobytes())


def sidecar(shape: Shape) -> dict[str, Any]:
    exact = _bbox_exact(shape.vertices)
    for key, (value, measure) in shape.exact.items():
        exact[key] = {"value": float(value), "measure": measure}
    return {
        "format_version": FORMAT_VERSION,
        "engine_version": __version__,
        "name": shape.name,
        "units": "mm",
        "exact": exact,
        "reference": shape.reference,
        "notes": shape.notes,
        "mesh": {"vertices": len(shape.vertices), "faces": len(shape.faces)},
    }


def write_all(out_dir: Path, config: Mapping[str, Any] | None = None) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for shape in build_all(config):
        stl = out_dir / f"{shape.name}.stl"
        write_stl(stl, shape.vertices, shape.faces, shape.name)
        (out_dir / f"{shape.name}.json").write_text(
            json.dumps(sidecar(shape), indent=2, sort_keys=True) + "\n"
        )
        written.append(stl)
    from coverengine.testshapes.assembly import write_assemblies, write_faceted_all

    written += write_assemblies(out_dir, config)
    written += write_faceted_all(out_dir, config)
    return written
