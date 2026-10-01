"""What an uploaded 3D file is (ADR-039): the furniture itself, or only the cover surface.

Some products come with a drawing of the cover surface instead of the furniture. Then the
program does not make a cover round it: the surface is the cover, and only the pieces are
drawn (`hull.top: given`). The program guesses which one it is and the owner confirms it.

The guess looks at three things a cover surface has and furniture does not:

- closed sides: horizontal lines of sight from outside towards the middle, low down, all hit
  the surface (a table or a sofa on legs lets most of them through between the legs);
- no floor: almost no flat area at the bottom (a cover is open there; a pouf or a planter has a
  bottom face);
- one skin: its area is about that of its own envelope (furniture has undersides, legs, cushions
  and inner faces, two to four times as much).

A closed block (a cover drawn as a solid, or a pouf) cannot be told apart by shape: then the file
name decides ("cover", "hoes", ...), marked as not sure. A cover drawn as a solid loses its
bottom in `hull.top: given`.

The guess and its numbers go to `kind.json`; `confirmed` stays false until the owner confirms.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import shapely
import trimesh
from scipy.spatial import ConvexHull

KIND_JSON = "kind.json"
PERCENT = 100.0  # param-ok: ratio to percent
PRODUCT, COVER = "product", "cover"
# Lines of sight: this many directions round the object, at these shares of its height.
SIGHT_DIRECTIONS = 72  # param-ok: sampling density
SIGHT_HEIGHTS = (0.1, 0.2, 0.3)  # param-ok: low down, where legs are
# A face is flat (floor) when its normal is within this cosine of straight down or up, and at
# most FLOOR_BAND of the height above the lowest point.
FLAT_NZ = 0.95  # param-ok: geometric constant
FLOOR_BAND = 0.02  # param-ok: share of the height
# The thresholds for a cover surface.
COVER_SIDES = 0.9  # share of the lines of sight that hit
COVER_FLOOR = 0.1  # param-ok: floor area as a share of the footprint
COVER_SKIN = 1.3  # area over envelope area
# Words in a file name that mean a cover (English, Dutch, German, French).
COVER_WORDS = ("cover", "hoes", "huelle", "hülle", "housse", "surface")


def measure(mesh: trimesh.Trimesh) -> dict[str, float]:
    v = np.asarray(mesh.vertices, np.float64)
    lo, hi = v.min(axis=0), v.max(axis=0)
    height = float(hi[2] - lo[2]) or 1.0
    hull = ConvexHull(v)
    tri = v[hull.simplices]
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    areas = np.linalg.norm(cross, axis=1) / 2
    down = hull.equations[:, 2] < -FLAT_NZ
    footprint = float(areas[down].sum()) or 1.0
    envelope = float(areas.sum()) - footprint
    skin = float(mesh.area) / max(envelope, 1.0)

    normals_z = mesh.face_normals[:, 2]
    low = mesh.triangles_center[:, 2] < lo[2] + FLOOR_BAND * height
    floor_area = float(mesh.area_faces[low & (np.abs(normals_z) > FLAT_NZ)].sum())
    floor = floor_area / footprint
    open_skin = (float(mesh.area) - floor_area) / max(envelope, 1.0)

    centre = (lo + hi) / 2
    radius = float(np.linalg.norm(hi[:2] - lo[:2]))
    hit = 0
    for share in SIGHT_HEIGHTS:
        z = lo[2] + share * height
        segments = trimesh.intersections.mesh_plane(mesh, [0.0, 0.0, 1.0], [0.0, 0.0, z])
        lines = shapely.MultiLineString([s[:, :2].tolist() for s in segments])
        for k in range(SIGHT_DIRECTIONS):
            a = 2 * math.pi * k / SIGHT_DIRECTIONS
            d = np.array([math.cos(a), math.sin(a)])
            sight = shapely.LineString([centre[:2] - d * radius, centre[:2]])
            hit += bool(len(segments)) and sight.intersects(lines)
    sides = hit / (len(SIGHT_HEIGHTS) * SIGHT_DIRECTIONS)
    return {
        "sides_closed": round(sides, 3),
        "floor_share": round(floor, 3),
        "skin_ratio": round(skin, 2),
        "skin_ratio_without_floor": round(open_skin, 2),
    }


def guess(mesh: trimesh.Trimesh, name: str = "") -> dict[str, Any]:
    """`name`: the uploaded file's name; it decides for a closed block (see below)."""
    m = measure(mesh)
    checks = {
        "sides_closed": m["sides_closed"] >= COVER_SIDES,
        "no_floor": m["floor_share"] <= COVER_FLOOR,
        "one_skin": m["skin_ratio"] <= COVER_SKIN,
    }
    votes = sum(checks.values())
    kind = COVER if votes == len(checks) else PRODUCT
    reasons = [
        (
            "closed all round low down"
            if checks["sides_closed"]
            else f"open low down: {round((1 - m['sides_closed']) * PERCENT)} % of the side "
            "views pass through (legs)"
        ),
        "open at the bottom" if checks["no_floor"] else "has a bottom face",
        (
            "a single skin, about as big as its envelope"
            if checks["one_skin"]
            else f"{m['skin_ratio']:g} times the area of its envelope (undersides, legs, cushions)"
        ),
    ]
    sure = votes in (0, len(checks))
    # A closed block (closed sides, a bottom, otherwise one skin) is either a cover drawn as a
    # solid or block-shaped furniture (a pouf): the file name decides, and it is never sure.
    block = (
        checks["sides_closed"]
        and not checks["no_floor"]
        and m["skin_ratio_without_floor"] <= COVER_SKIN
    )
    if block:
        named = any(w in name.lower() for w in COVER_WORDS)
        kind, sure = (COVER if named else PRODUCT), False
        reasons = [
            "a closed block: a cover drawn as a solid, or block-shaped furniture",
            (f"the file name ({name}) says cover" if named else "the file name does not say cover"),
        ]
    return {
        "format_version": 1,
        "guess": kind,
        "sure": sure,
        "measures": m,
        "reasons": reasons,
        "confirmed": False,
        "kind": None,
    }


def write_guess(model_dir: Path, mesh: trimesh.Trimesh, name: str = "") -> dict[str, Any]:
    """The guess after an import; a confirmed answer from before is kept."""
    old = read(model_dir)
    doc = guess(mesh, name)
    if old and old.get("confirmed"):
        doc["confirmed"], doc["kind"] = True, old["kind"]
    (model_dir / KIND_JSON).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


def read(model_dir: Path) -> dict[str, Any] | None:
    p = model_dir / KIND_JSON
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None


def confirm(model_dir: Path, kind: str) -> dict[str, Any]:
    """The owner's answer: a cover surface is used as the cover (`hull.top: given`)."""
    from coverengine.errors import CoverError
    from coverengine.params.registry import read_cover_definition

    if kind not in (PRODUCT, COVER):
        raise CoverError(f"kind must be {PRODUCT} or {COVER}")
    doc = read(model_dir) or {"format_version": 1, "guess": None, "sure": False}
    doc["confirmed"], doc["kind"] = True, kind
    (model_dir / KIND_JSON).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    cover = read_cover_definition(model_dir) or {"format_version": 1, "model_id": model_dir.name}
    hull = cover.setdefault("parameters", {}).setdefault("hull", {})
    if kind == COVER:
        hull["top"] = "given"
    elif hull.get("top") == "given":
        hull.pop("top")
    (model_dir / "cover.json").write_text(json.dumps(cover, indent=2) + "\n", encoding="utf-8")
    return doc
