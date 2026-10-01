"""`cover audit`: a fixed check of a calculated cover, and a second opinion from the AI (ADR-042).

The program measures, for each model:

- complete: every step's files are there and newer than the cover surface (a step that failed
  leaves older files behind, which must not count);
- furniture inside: points spread over the furniture above the hem all lie inside the cover;
- balloons: a table has at least one balloon under its cover;
- symmetric: a mirror-symmetric piece of furniture has a mirror-symmetric cover;
- water: the cover sheds water;
- pieces: the grade (stretch, seams, roll width) and no scrap pieces.

Then, with `--ai`, the AI gets three straight views (front, side, top: the furniture in grey,
the cover in see-through blue, furniture outside the cover in red), the product photo and the
measured facts, and gives its own verdict. Both go into `audit.json`; the views into
`audit.png`.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray

from coverengine.catalogue import grade, info
from coverengine.io.model_io import load_model
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
AUDIT_JSON, AUDIT_PNG = "audit.json", "audit.png"
SAMPLES = 20000  # param-ok: points spread over the furniture
OUTSIDE_MM = 3.0  # param-ok: a furniture point further than this outside the cover is outside
MIRROR_MM = 15.0  # param-ok: a symmetric cover mirrored lies within this of itself (95 %)
MIRROR_PCT = 95  # param-ok: share of points
SCRAP_M2 = 0.02  # param-ok: a piece smaller than this is scrap
STEP_FILES = ("panels.json", "pattern.json", "finished.json", "cut.dxf")
VIEW_IN = (9.0, 3.2)  # param-ok: picture size (inches)
VIEW_DPI = 110  # param-ok: picture resolution
MM_PER_CM = 10.0  # param-ok: unit conversion
TITLE_PT = 8  # param-ok: display
PERCENT = 100.0  # param-ok: ratio to percent
GREY, BLUE, RED = "#8a8f98", "#2f78dc", "#e0302a"  # param-ok: display colours


def _check(name: str, ok: bool, detail: str) -> dict[str, Any]:
    return {"check": name, "ok": bool(ok), "detail": detail}


def _furniture_above(model_dir: Path, hem: float) -> trimesh.Trimesh:
    m = load_model(model_dir)
    return trimesh.intersections.slice_mesh_plane(
        m, plane_normal=[0.0, 0.0, 1.0], plane_origin=[0.0, 0.0, hem], cap=False
    )


def outside(furniture: trimesh.Trimesh, cover: trimesh.Trimesh) -> tuple[Array, Array]:
    """Points on the furniture and how far each lies outside the cover (mm; <= 0 inside)."""
    import igl

    pts, _ = trimesh.sample.sample_surface(furniture, SAMPLES, seed=0)
    pts = np.vstack([pts, furniture.vertices])
    d2, face, near = igl.point_mesh_squared_distance(
        np.asarray(pts, np.float64),
        np.asarray(cover.vertices, np.float64),
        np.asarray(cover.faces, np.int32),
    )
    side = np.einsum("ij,ij->i", pts - near, cover.face_normals[face])
    return pts, np.where(side > 0, np.sqrt(d2), -np.sqrt(d2))


def mirror_gap(cover: trimesh.Trimesh, axis: int, mid: float) -> float:
    """How far (95 %) the mirrored cover lies from the cover itself (mm)."""
    import igl

    v = np.asarray(cover.vertices, np.float64).copy()
    v[:, axis] = 2 * mid - v[:, axis]
    d2, _, _ = igl.point_mesh_squared_distance(
        v, np.asarray(cover.vertices, np.float64), np.asarray(cover.faces, np.int32)
    )
    return float(np.percentile(np.sqrt(d2), MIRROR_PCT))


def views(furniture: trimesh.Trimesh, cover: trimesh.Trimesh, bad: Array, out: Path) -> Path:
    """Front, side and top views: furniture grey, cover see-through blue, outside points red."""
    from matplotlib.collections import PolyCollection
    from matplotlib.figure import Figure

    fig = Figure(figsize=VIEW_IN, dpi=VIEW_DPI)
    for k, (title, a, b) in enumerate(
        (("front (from the front)", 0, 2), ("side (from the right)", 1, 2), ("top", 0, 1))
    ):
        ax = fig.add_subplot(1, 3, k + 1)
        for mesh, colour, alpha in ((furniture, GREY, 1.0), (cover, BLUE, 0.3)):
            tri = mesh.vertices[mesh.faces][:, :, [a, b]]
            ax.add_collection(
                PolyCollection(list(tri), facecolors=colour, edgecolors="none", alpha=alpha)
            )
        if len(bad):
            ax.scatter(bad[:, a], bad[:, b], s=2, c=RED)
        allv = np.vstack([furniture.vertices, cover.vertices])
        ax.set_xlim(allv[:, a].min(), allv[:, a].max())
        ax.set_ylim(allv[:, b].min(), allv[:, b].max())
        ax.set_aspect("equal")
        ax.set_title(title, fontsize=TITLE_PT)
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(out, dpi=VIEW_DPI, metadata={"Software": None})
    return out


def measure(model_dir: Path, params: EffectiveParams) -> dict[str, Any]:
    """The program's checks for one model."""
    from coverengine.hull.box import Box

    checks = []
    hull_glb, hull_json = model_dir / "hull.glb", model_dir / "hull.json"
    if not hull_glb.is_file():
        return {"checks": [_check("complete", False, "no cover surface calculated")]}
    hull = json.loads(hull_json.read_text(encoding="utf-8"))
    t0 = hull_json.stat().st_mtime
    stale = [f for f in STEP_FILES if not (model_dir / f).is_file()]
    stale += [
        f for f in STEP_FILES if (model_dir / f).is_file() and (model_dir / f).stat().st_mtime < t0
    ]
    checks.append(
        _check(
            "complete",
            not stale,
            "all steps done after the cover surface"
            if not stale
            else f"missing or older than the cover surface: {', '.join(sorted(set(stale)))}",
        )
    )
    hem = float(params["hull.hem_height_mm"])  # type: ignore[arg-type]
    furniture = _furniture_above(model_dir, hem)
    cover = load_model(hull_glb)
    pts, dist = outside(furniture, cover)
    bad = pts[dist > OUTSIDE_MM]
    worst = float(dist.max())
    where = pts[int(np.argmax(dist))]
    checks.append(
        _check(
            "furniture inside",
            not len(bad),
            "all of the furniture above the hem is inside the cover"
            if not len(bad)
            else f"{len(bad) / len(pts) * PERCENT:.1f} % of the furniture is outside the cover, up "
            f"to {worst / MM_PER_CM:.1f} cm, near x {where[0] / MM_PER_CM:.0f}, "
            f"y {where[1] / MM_PER_CM:.0f}, z {where[2] / MM_PER_CM:.0f} cm",
        )
    )
    if info(model_dir)["family"] == "table":
        sup = hull.get("support") or {}
        n = int(sup.get("balloons", 0)) if sup.get("kind") == "balloons" else 0
        checks.append(
            _check(
                "balloons",
                n >= 1,
                f"{n} balloon(s) under the cover ({sup.get('chosen_by', '')})"
                if n
                else "a table without balloons under its cover",
            )
        )
    axes = Box._symmetry(np.asarray(furniture.vertices, np.float64))
    for axis, mid in axes:
        gap = mirror_gap(cover, axis, mid)
        side = "left-right" if axis == 0 else "front-back"
        checks.append(
            _check(
                f"symmetric {side}",
                gap < MIRROR_MM,
                f"the furniture is {side} symmetric; the cover mirrored lies within "
                f"{gap / MM_PER_CM:.1f} cm of itself",
            )
        )
    drains = bool((hull.get("drainage") or {}).get("drains", False))
    checks.append(_check("water", drains, "runs off" if drains else "water would stay on top"))
    g = grade(model_dir)
    pieces: list[dict[str, Any]] = []
    if (model_dir / "panels.json").is_file():
        pieces = json.loads((model_dir / "panels.json").read_text(encoding="utf-8"))["panels"]
    scrap = [p["name"] for p in pieces if p["area_m2"] < SCRAP_M2]
    checks.append(
        _check(
            "pieces",
            g["grade"] == "ready" and not scrap,
            f"{len(pieces)} pieces, {g['grade']}"
            + (f"; scrap pieces: {', '.join(scrap)}" if scrap else "")
            + (f"; {'; '.join(g.get('reasons', []))}" if g.get("reasons") else ""),
        )
    )
    views(furniture, cover, bad, model_dir / AUDIT_PNG)
    return {
        "checks": checks,
        "pieces": len(pieces),
        "cover": hull.get("top"),
        "size_cm": [round(v / MM_PER_CM) for v in np.ptp(cover.vertices, axis=0)],
        "furniture_size_cm": [round(v / MM_PER_CM) for v in np.ptp(furniture.vertices, axis=0)],
    }


AI_SYSTEM = """You check outdoor furniture covers for a workshop, as a second opinion next to the
program's own measurements. Image 1 shows three straight views of the furniture (grey) with the
calculated cover over it (see-through blue): from the front, from the right side, and from
above. Red dots are furniture outside the cover. Image 2 is the product photo. A good cover:
covers all of the furniture down to just above the floor; is roughly the furniture's shape (a box
over box-like furniture is intended); sheds water (no flat or hollow top; tables have balloons
under the cover); is symmetric when the furniture is; has few pieces with straight seams. You
also get the program's measured checks. Judge the pictures yourself, then compare with the
checks. Answer with JSON only:
{"verdict": "good | doubt | wrong", "problems": ["short plain sentences"],
 "disagree_with_program": ["checks where your view differs, with why"]}"""


def _image(path: Path) -> dict[str, Any]:
    mime = "image/png" if path.suffix == ".png" else "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}}


def second_opinion(model_dir: Path, params: EffectiveParams, facts: dict[str, Any]) -> Any:
    from coverengine.ai import ask_parts, lessons_text

    parts: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(facts)}]
    parts.append(_image(model_dir / AUDIT_PNG))
    if (model_dir / "product.jpg").is_file():
        parts.append(_image(model_dir / "product.jpg"))
    return ask_parts(params, AI_SYSTEM + lessons_text("all"), parts)


def audit(model_dir: Path, params: EffectiveParams, use_ai: bool) -> dict[str, Any]:
    doc = measure(model_dir, params)
    doc["model_id"] = model_dir.name
    doc["time"] = round(time.time())
    doc["ok"] = all(c["ok"] for c in doc["checks"])
    if use_ai and (model_dir / AUDIT_PNG).is_file():
        cover = info(model_dir)
        facts = {
            "product": (cover.get("notes") or model_dir.name).split(": ", 1)[-1],
            "family": cover.get("family"),
            **{k: doc.get(k) for k in ("cover", "pieces", "size_cm", "furniture_size_cm")},
            "checks": doc["checks"],
        }
        try:
            answer = second_opinion(model_dir, params, facts)
            doc["ai"] = {
                "model": str(params["ai.model"]),
                "verdict": str(answer.get("verdict", "")),
                "problems": [str(p) for p in answer.get("problems", [])],
                "disagree": [str(p) for p in answer.get("disagree_with_program", [])],
            }
        except Exception as exc:  # noqa: BLE001 - the AI is a second opinion, not required
            doc["ai"] = {"model": str(params["ai.model"]), "error": str(exc)}
    (model_dir / AUDIT_JSON).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc
