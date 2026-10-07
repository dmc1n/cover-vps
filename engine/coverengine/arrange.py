"""Arrangements: furniture placed together, one cover over the whole (ADR-089).

The owner, 7 October 2026: "we first place the products in the arrangement we want, then we
produce a cover; so we can also make larger covers for fixed arrangements" (e.g. the SUNS
2-seater Portofino with the chaise lounge Portofino).

An arrangement is a list of members: an existing model's furniture (its own model.glb, never
its cover) with a place in the plan. Each member is first mirrored (optional, in x), then
turned about the vertical, then moved so its plan box's middle lands at (x_mm, y_mm). All
members stand on the ground. Joined, they become one new model, `arr-<name>`, which the
standard pipeline covers like any furniture: the drape hull bridges the gaps, the skirt runs
at one height, the pieces fit the roll.

`arrangement.json` in the new model keeps the members, their places and each member's
version, so the cover can be made again when a member changes.

Units mm, Z up, the front at -y (as every imported model).
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from coverengine.errors import CoverError

ARRANGEMENT_JSON = "arrangement.json"
SOURCE_GLB = "arrangement.glb"
M_TO_MM = 1000.0  # param-ok: unit
SIDES = ("left", "right", "front", "back")
SLUG_CHARS = 60  # param-ok: an arrangement's id at most this long
CLOSE_MM = 5.0  # param-ok: the footprint's slits closed and its outline smoothed by this
# The cover's plan over an arrangement (ADR-095), chosen on the page before the cover is built:
# follow the members (their rectangles joined, sharp inner corners), one rectangle round
# everything, or the smoothed box of the first version (slanted walls across an L's corner).
FOOTPRINTS = ("follow", "box", "smooth")


@dataclass
class Member:
    model_id: str
    x_mm: float = 0.0
    y_mm: float = 0.0
    rot_deg: float = 0.0
    mirror: bool = False

    @classmethod
    def of(cls, d: dict[str, Any]) -> Member:
        return cls(str(d["model_id"]), float(d.get("x_mm") or 0.0), float(d.get("y_mm") or 0.0),
                   float(d.get("rot_deg") or 0.0), bool(d.get("mirror")))  # fmt: skip


def furniture(models: Path, model_id: str) -> trimesh.Trimesh:
    """A model's own furniture in mm, Z up, its plan box centred on the origin, on the ground.
    model.glb is glTF: metres with Y up; the model's z is the file's y, its y the file's -z."""
    path = models / model_id / "model.glb"
    if not path.is_file():
        raise CoverError(f"{model_id}: no imported furniture (model.glb)")
    loaded = trimesh.load(path, force="mesh")
    if not isinstance(loaded, trimesh.Trimesh) or not len(loaded.faces):
        raise CoverError(f"{model_id}: its furniture is empty")
    v = np.asarray(loaded.vertices, dtype=np.float64) * M_TO_MM
    m = trimesh.Trimesh(np.column_stack([v[:, 0], -v[:, 2], v[:, 1]]), loaded.faces, process=False)
    lo, hi = m.bounds
    m.apply_translation((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, -lo[2]))
    return m


def placed(mesh: trimesh.Trimesh, m: Member) -> trimesh.Trimesh:
    """A member as it stands in the arrangement: mirrored, turned, moved (plan box middle at
    x_mm, y_mm), on the ground."""
    out = mesh.copy()
    if m.mirror:
        out.vertices[:, 0] *= -1
        out.invert()  # keep the faces facing out
    out.apply_transform(trimesh.transformations.rotation_matrix(math.radians(m.rot_deg),
                                                                (0, 0, 1)))  # fmt: skip
    lo, hi = out.bounds
    out.apply_translation((m.x_mm - (lo[0] + hi[0]) / 2, m.y_mm - (lo[1] + hi[1]) / 2, -lo[2]))
    return out


def plan_box(mesh: trimesh.Trimesh) -> tuple[float, float, float, float]:
    lo, hi = mesh.bounds
    return float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])


def snap(members: list[Member], meshes: dict[str, trimesh.Trimesh], i: int, j: int, side: str,
         align: str = "back", gap_mm: float = 0.0) -> Member:  # fmt: skip
    """Member i put against member j's `side` (left, right, front, back), `gap_mm` apart,
    aligned with it: for left and right at its back, front or middle; for front and back at its
    left, right or middle."""
    if side not in SIDES:
        raise CoverError(f"side: one of {', '.join(SIDES)}")
    a = placed(meshes[members[i].model_id], members[i])
    b = placed(meshes[members[j].model_id], members[j])
    ax0, ay0, ax1, ay1 = plan_box(a)
    bx0, by0, bx1, by1 = plan_box(b)
    w, d = ax1 - ax0, ay1 - ay0
    m = Member(**asdict(members[i]))
    if side in ("left", "right"):
        m.x_mm = bx0 - gap_mm - w / 2 if side == "left" else bx1 + gap_mm + w / 2
        m.y_mm = {"back": by1 - d / 2, "front": by0 + d / 2}.get(align, (by0 + by1) / 2)
    else:  # the front is at -y
        m.y_mm = by0 - gap_mm - d / 2 if side == "front" else by1 + gap_mm + d / 2
        m.x_mm = {"left": bx0 + w / 2, "right": bx1 - w / 2}.get(align, (bx0 + bx1) / 2)
    return m


def rect(width: float, depth: float, m: Member) -> list[list[float]]:
    """A member's plan rectangle as it stands (its furniture's plan box, turned, its middle at
    x_mm, y_mm): four corners, counter-clockwise. Mirroring does not change a rectangle."""
    a = math.radians(m.rot_deg)
    c, s = math.cos(a), math.sin(a)
    half = ((-width / 2, -depth / 2), (width / 2, -depth / 2), (width / 2, depth / 2),
            (-width / 2, depth / 2))  # fmt: skip
    return [[m.x_mm + x * c - y * s, m.y_mm + x * s + y * c] for x, y in half]


def combine(models: Path, members: list[Member]) -> trimesh.Trimesh:
    """Every member placed, as one mesh, its plan box centred on the origin."""
    return combined(models, members)[0]


def combined(
    models: Path, members: list[Member]
) -> tuple[trimesh.Trimesh, list[list[list[float]]]]:
    """The joined mesh (its plan box centred on the origin) and every member's plan rectangle
    in that same frame."""
    if not members:
        raise CoverError("an arrangement needs at least one member")
    cache: dict[str, trimesh.Trimesh] = {}
    parts = []
    rects = []
    for m in members:
        if m.model_id not in cache:
            cache[m.model_id] = furniture(models, m.model_id)
        parts.append(placed(cache[m.model_id], m))
        w, d = cache[m.model_id].extents[:2]
        rects.append(rect(float(w), float(d), m))
    whole = trimesh.util.concatenate(parts)
    assert isinstance(whole, trimesh.Trimesh)
    lo, hi = whole.bounds
    sx, sy = -(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2
    whole.apply_translation((sx, sy, 0.0))
    moved = [[[round(float(x + sx), 3), round(float(y + sy), 3)] for x, y in r] for r in rects]
    return whole, moved


def version(models: Path, model_id: str) -> dict[str, Any]:
    """What a member was when it was placed: its file's hash and its latest revision."""
    d = models / model_id
    model = json.loads((d / "model.json").read_text()) if (d / "model.json").is_file() else {}
    rev = None
    index = d / "revisions" / "index.json"
    if index.is_file():
        revs = json.loads(index.read_text())
        rev = revs[-1].get("number") if revs else None
    glb = d / "model.glb"
    digest = hashlib.sha256(glb.read_bytes()).hexdigest()[:16] if glb.is_file() else None
    return {"model_glb": digest, "revision": rev,
            "size_mm": model.get("size_mm")}  # fmt: skip


def slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return "arr-" + (s or "arrangement")[:SLUG_CHARS]


def write(models: Path, model_id: str, name: str, members: list[Member],
          gap_mm: float = 0.0, footprint: str = "follow") -> Path:  # fmt: skip
    """The arrangement's furniture as one GLB (mm, Z up) and its arrangement.json in the new
    model's folder; the caller imports the GLB (`cover import --units mm --up z`).
    `footprint` is the cover's plan chosen on the page (ADR-095): follow, box or smooth."""
    if footprint not in FOOTPRINTS:
        raise CoverError(f"footprint: one of {', '.join(FOOTPRINTS)}")
    out = models / model_id
    out.mkdir(parents=True, exist_ok=True)
    whole, rects = combined(models, members)
    src = out / SOURCE_GLB
    whole.export(src)
    doc = {"format_version": 1, "id": model_id, "name": name, "gap_mm": gap_mm,
           "footprint": footprint,
           "members": [{**asdict(m), "version": version(models, m.model_id), "plan_mm": r}
                       for m, r in zip(members, rects, strict=True)],
           "size_mm": [round(float(x), 1) for x in whole.extents],
           "time": time.time()}  # fmt: skip
    tmp = out / (ARRANGEMENT_JSON + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n")
    tmp.replace(out / ARRANGEMENT_JSON)
    from coverengine.io import kind

    kind.confirm(out, kind.PRODUCT)  # furniture by construction: no "what is this file?" check
    return src


def read(model_dir: Path) -> dict[str, Any]:
    path = model_dir / ARRANGEMENT_JSON
    if not path.is_file():
        raise CoverError(f"{model_dir.name}: not an arrangement")
    doc: dict[str, Any] = json.loads(path.read_text())
    return doc


def plan_rects(doc: dict[str, Any]) -> list[list[list[float]]]:
    """Every member's plan rectangle in the arrangement's frame (as in arrangement.glb). Older
    arrangement.json files have no plan_mm: the rectangles from the members' sizes, centred
    as `combined` centres the whole (exact for members turned in steps of 90 degrees)."""
    members = doc.get("members") or []
    if members and all(m.get("plan_mm") for m in members):
        return [m["plan_mm"] for m in members]
    rects = []
    for m in members:
        size = (m.get("version") or {}).get("size_mm")
        if not size:
            raise CoverError(f"{m.get('model_id')}: its size is not recorded; build it again")
        rects.append(rect(float(size[0]), float(size[1]), Member.of(m)))
    pts = np.asarray([p for r in rects for p in r], dtype=np.float64)
    shift = -(pts.min(axis=0) + pts.max(axis=0)) / 2
    return [[[float(x + shift[0]), float(y + shift[1])] for x, y in r] for r in rects]


def footprint_of(doc: dict[str, Any], params: Any) -> str:
    """The plan chosen for the arrangement's cover, else the company default."""
    chosen = str(doc.get("footprint") or params["arrange.footprint"])
    return chosen if chosen in FOOTPRINTS else str(params["arrange.footprint"])


def footprints(
    models: Path, members: list[Member], gap_mm: float, params: Any
) -> list[dict[str, Any]]:
    """The plans the page offers before the cover is built (ADR-095): for each, its outline
    seen from above at the hem (mm), its size and how much floor it covers that no member
    stands on."""
    import shapely

    from coverengine.hull import plan as hp
    from coverengine.hull.box import Box, drain

    whole, rects = combined(models, members)
    c = float(params["hull.clearance_mm"])
    hem = float(params["hull.hem_height_mm"])
    polys = hp.aligned([shapely.Polygon(r) for r in rects], [hp.rect_angle(r) for r in rects],
                       float(params["arrange.align_mm"]))  # fmt: skip
    own = shapely.union_all(polys).buffer(c, join_style=hp.MITRE)
    close = gap_mm + float(params["arrange.close_mm"])
    out = []
    for name in FOOTPRINTS:
        if name == "smooth":
            above = trimesh.intersections.slice_mesh_plane(
                whole, plane_normal=[0.0, 0.0, 1.0], plane_origin=[0.0, 0.0, hem], cap=False
            )
            box = Box(np.asarray(above.vertices, np.float64), hem, c)
            sets = box.grow(int(params["hull.box_max_pieces"]))
            want = int(params["arrange.box_pieces"])
            planes = min(sets, key=lambda s: abs(len(s) - 1 - want))
            solid = box.solid(drain(box, planes, float(params["hull.min_slope_deg"])))
            pts = solid.points if solid is not None else above.vertices
            shape = shapely.MultiPoint(np.asarray(pts)[:, :2]).convex_hull
        else:
            shape, _ = hp.outline(polys, name, close, c)
        x0, y0, x1, y1 = shape.bounds
        out.append({
            "footprint": name,
            "outline_mm": [[round(float(x), 1), round(float(y), 1)]
                           for x, y in shape.exterior.coords],
            "size_mm": [round(x1 - x0, 1), round(y1 - y0, 1)],
            "area_m2": round(shape.area / 1e6, 3),
            "empty_m2": round(shape.difference(own).area / 1e6, 3),
            "rects_mm": [[[round(x, 1), round(y, 1)] for x, y in r] for r in rects],
        })  # fmt: skip
    return out


def stale(models: Path, doc: dict[str, Any]) -> list[str]:
    """The members that changed since the arrangement was made (its cover should be rebuilt)."""
    out = []
    for m in doc.get("members", []):
        now = version(models, m["model_id"])
        then = m.get("version") or {}
        if now.get("model_glb") != then.get("model_glb"):
            out.append(m["model_id"])
    return out


def outline(models: Path, model_id: str) -> dict[str, Any]:
    """A member's footprint seen from above (mm, centred like `furniture`): for the page."""
    import shapely

    m = furniture(models, model_id)
    tri = m.vertices[m.faces][:, :, :2]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    big = np.abs(e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]) > 1.0  # param-ok: mm², not edge-on
    foot = shapely.union_all([shapely.Polygon(t) for t in tri[big]])
    foot = foot.buffer(CLOSE_MM).buffer(-CLOSE_MM).simplify(CLOSE_MM)
    polys = list(getattr(foot, "geoms", [foot]))
    rings = [[[round(float(x), 1), round(float(y), 1)] for x, y in p.exterior.coords]
             for p in polys if p.area > 1]  # fmt: skip
    return {"model_id": model_id, "size_mm": [round(float(x), 1) for x in m.extents],
            "outline_mm": rings}  # fmt: skip
