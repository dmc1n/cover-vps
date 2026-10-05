"""The owner's own reference for a model, against what the program made (ADR-070).

Per model the workshop can upload what it knows to be right: a 3D model of the cover (a surface
model: STEP, IGES, STL, OBJ, PLY, GLB) and/or a PDF (its drawing or its pattern). Each is
compared with the program's cover, so the differences can be seen and learned from:

- surface: the reference is imported like any model and laid over the program's cover surface
  (placed alike, then fitted with ICP); per point of the program's cover the distance to the
  reference, signed (+: ours is roomier, -: tighter): mean, 95 %, largest, and how much lies
  within the fit tolerance; and compare.glb, the program's cover coloured by that distance;
- drawing: every size written on the PDF is looked for among the program's lengths (the pieces'
  edges, their flat sizes, the cover's size); then an image-reading AI puts the PDF beside the
  program's pattern and lists the differences (pieces, seams, sizes, features), with lessons a
  person can accept.
"""

from __future__ import annotations

import base64
import json
import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from coverengine.errors import CoverError
from coverengine.params import EffectiveParams

TOL_MM, TOL_REL = 10.0, 0.006  # param-ok: a written size matches within 1 cm or 0.6 %
FIT_MM = 5.0  # param-ok: the fit tolerance of the success criterion (CLAUDE.md, ±5 mm)
SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mm|cm|in)\b", re.I)
TO_MM = {"mm": 1.0, "cm": 10.0, "in": 25.4}  # param-ok: units
PCT = 100.0  # param-ok: shares as percentages
DPI = 110  # param-ok: drawing pages as pictures for the AI


# ---- 3D against 3D -------------------------------------------------------------------------------
def surface(model_dir: Path, ref: Path, params: EffectiveParams) -> dict[str, Any]:
    from coverengine.io.model_io import load_model

    ours = load_model(model_dir / "hull.glb")
    theirs = _load_raw(ref, params)
    for m in (ours, theirs):
        if m.is_empty:
            raise CoverError("a surface without triangles")
    theirs = _same_frame(ours, theirs)
    # placed alike (both on the ground, centred in the top view), then fitted
    for m in (ours, theirs):
        if m.is_empty:
            raise CoverError("a surface without triangles")
    shift = _centre(ours) - _centre(theirs)
    theirs.apply_translation(shift)
    _turn(ours, theirs)
    _fit(ours, theirs)
    signed = _signed(ours.vertices, theirs)  # + : ours outside the reference (roomier)
    back = np.abs(_signed(theirs.vertices, ours))
    a = np.abs(signed)
    res = {
        "kind": "surface",
        "reference": ref.name,
        "mean_mm": round(float(a.mean()), 1),
        "p95_mm": round(float(np.percentile(a, 95)), 1),  # param-ok
        "max_mm": round(float(a.max()), 1),
        "within_fit_pct": round(float((a <= FIT_MM).mean() * PCT), 1),
        "roomier_pct": round(float((signed > FIT_MM).mean() * PCT), 1),
        "tighter_pct": round(float((signed < -FIT_MM).mean() * PCT), 1),
        "reference_covered_p95_mm": round(float(np.percentile(back, 95)), 1),  # param-ok
        "area_m2": {"ours": round(float(ours.area) / 1e6, 3),
                    "theirs": round(float(theirs.area) / 1e6, 3)},
        "size_mm": {"ours": [round(float(x)) for x in ours.extents],
                    "theirs": [round(float(x)) for x in theirs.extents]},
    }  # fmt: skip
    _deviation_glb(ours, signed, model_dir / "reference" / "compare.glb")
    return res


SAMPLES = 2500  # param-ok: points of the program's cover used to fit the reference
SCALES = (1.0, 10.0, 25.4, 1000.0, 0.001)  # param-ok: mm, cm, inch, m, a file in µm


def _load_raw(ref: Path, params: EffectiveParams) -> trimesh.Trimesh:
    """The reference as it is in its file (no turning to a front: the fit does that)."""
    if ref.suffix.lower() in (".step", ".stp", ".iges", ".igs"):
        from coverengine.io.cad import load_cad

        cad = load_cad(ref, float(params["import.deflection_mm"]),
                       float(params["import.angular_deflection_deg"]),
                       float(params["import.sew_tolerance_mm"]))  # fmt: skip
        parts = [trimesh.Trimesh(p.vertices, p.faces, process=False) for p in cad.parts]
        joined: Any = trimesh.util.concatenate(parts)
        return joined
    from coverengine.io.info import load_mesh

    return load_mesh(ref)


def _same_frame(ours: trimesh.Trimesh, theirs: trimesh.Trimesh) -> trimesh.Trimesh:
    """The reference in the program's units and up axis: of the usual units (mm, cm, inch, m)
    and the two usual up axes (Z, Y), the one whose size best matches the program's cover."""
    best, best_err = theirs, math.inf
    turn = trimesh.transformations.rotation_matrix(math.pi / 2, [1, 0, 0])  # Y up -> Z up
    for up in (None, turn):
        for k in SCALES:
            m = theirs.copy()
            if up is not None:
                m.apply_transform(up)
            m.apply_scale(k)
            err = float(
                np.abs(np.log(np.maximum(m.extents, 1e-6) / np.maximum(ours.extents, 1e-6))).sum()
            )
            if err < best_err:
                best, best_err = m, err
    lo = best.bounds[0]
    best.apply_translation([0, 0, -lo[2]])  # on the ground
    return best


def _signed(points: np.ndarray, mesh: trimesh.Trimesh) -> np.ndarray:
    """Distance from each point to the mesh, signed by the nearest face's outward normal."""
    import igl

    v, f = np.asarray(mesh.vertices, dtype=np.float64), np.asarray(mesh.faces, dtype=np.int64)
    sq, idx, close = igl.point_mesh_squared_distance(np.asarray(points, dtype=np.float64), v, f)
    side = np.einsum("ij,ij->i", points - close, mesh.face_normals[idx])
    return np.sqrt(sq) * np.where(side >= 0, 1.0, -1.0)


def _turn(ours: trimesh.Trimesh, theirs: trimesh.Trimesh) -> None:
    """Of the turns about the vertical (every 15°, and mirrored never), the one that lays the
    reference best over the program's cover; ICP then finishes the fit."""
    import igl

    rng = np.random.default_rng(3)
    pts = ours.vertices[
        rng.choice(len(ours.vertices), min(SAMPLES // 3, len(ours.vertices)), False)
    ]  # param-ok
    c = _centre(theirs)
    best, best_err = np.eye(4), math.inf
    for deg in range(0, 360, 15):  # param-ok: 15° steps
        rot = trimesh.transformations.rotation_matrix(math.radians(deg), [0, 0, 1], c)
        v = trimesh.transform_points(theirs.vertices, rot)
        v += _centre(ours) - _centre(trimesh.Trimesh(v, theirs.faces, process=False))
        sq, _, _ = igl.point_mesh_squared_distance(pts, v, np.asarray(theirs.faces, dtype=np.int64))
        if float(sq.mean()) < best_err:
            best_err = float(sq.mean())
            best = rot
    theirs.apply_transform(best)
    theirs.apply_translation(_centre(ours) - _centre(theirs))


def _fit(ours: trimesh.Trimesh, theirs: trimesh.Trimesh, rounds: int = 25) -> None:
    """ICP: the reference moved and turned (no scaling, no mirroring) onto the program's cover;
    only a small correction is kept (the placement on the ground is right already)."""
    import igl

    rng = np.random.default_rng(7)
    pts = ours.vertices[
        rng.choice(len(ours.vertices), min(SAMPLES, len(ours.vertices)), False)
    ]  # param-ok
    total = np.eye(4)
    v = np.asarray(theirs.vertices, dtype=np.float64).copy()
    f = np.asarray(theirs.faces, dtype=np.int64)
    for _ in range(rounds):
        _, _, close = igl.point_mesh_squared_distance(pts, v, f)
        a, b = close - close.mean(axis=0), pts - pts.mean(axis=0)
        u, _, vt = np.linalg.svd(a.T @ b)
        d = np.sign(np.linalg.det(vt.T @ u.T))
        rot = vt.T @ np.diag([1, 1, d]) @ u.T
        t = pts.mean(axis=0) - rot @ close.mean(axis=0)
        v = v @ rot.T + t
        step = np.eye(4)
        step[:3, :3], step[:3, 3] = rot, t
        total = step @ total
    moved = float(np.linalg.norm(total[:3, 3]))
    if moved < 0.15 * float(np.linalg.norm(ours.extents)):  # param-ok: only a small correction
        theirs.apply_transform(total)


def _centre(m: trimesh.Trimesh) -> np.ndarray:
    lo, hi = m.bounds
    return np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])


def _deviation_glb(m: trimesh.Trimesh, signed: np.ndarray, path: Path) -> None:
    """Sage within the fit, sand where ours is roomier, red where it is tighter."""
    from coverengine.io.model_io import glb_bytes, linear_colours

    t = np.clip(np.abs(signed) / (4 * FIT_MM), 0, 1)[:, None]  # param-ok: full colour at 2 cm
    sage = np.array([110, 119, 107, 255.0])
    room = np.array([180, 154, 114, 255.0])
    tight = np.array([178, 64, 44, 255.0])
    far = np.where((signed > 0)[:, None], room, tight)
    col = np.where((np.abs(signed) <= FIT_MM)[:, None], sage, sage * (1 - t) + far * t)
    out = trimesh.Trimesh(m.vertices, m.faces, vertex_colors=linear_colours(col.astype(np.uint8)),
                          process=False)  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(glb_bytes([("compare", out)]))


# ---- a PDF against the pattern ------------------------------------------------------------------
def written_mm(pdf: Path) -> list[float]:
    """The sizes on the PDF in mm (metric when it has any, else its inches)."""
    import pymupdf

    doc = pymupdf.open(pdf)
    text = " ".join(doc[i].get_text() for i in range(doc.page_count))
    found = [(float(m.group(1).replace(",", ".")), m.group(2).lower()) for m in SIZE.finditer(text)]
    metric = [v * TO_MM[u] for v, u in found if u != "in"]
    vals = metric or [v * TO_MM[u] for v, u in found]
    return sorted({round(v, 1) for v in vals if 10 <= v <= 20000})  # param-ok: 1 cm .. 20 m


def our_lengths(model_dir: Path) -> dict[str, float]:
    """Every length the program's pattern has (mm), by name, to find a written size in."""
    out: dict[str, float] = {}
    pat = model_dir / "pattern.json"
    if pat.is_file():
        for p in json.loads(pat.read_text())["panels"]:
            out[f"{p['name']}: flat length"] = float(p["flat_length_mm"])
            out[f"{p['name']}: flat width"] = float(p["flat_width_mm"])
            for i, e in enumerate(p["edges"]):
                out[f"{p['name']}: edge {i + 1} ({e.get('kind')})"] = float(e["length_3d_mm"])
    hull = model_dir / "hull.json"
    if hull.is_file():
        lo, hi = (np.array(v) for v in json.loads(hull.read_text())["bbox_mm"])
        for k, v in zip(("length", "depth", "height"), hi - lo, strict=False):
            out[f"cover {k}"] = float(v)
    return out


def drawing(
    model_dir: Path, pdf: Path, params: EffectiveParams, use_ai: bool = True
) -> dict[str, Any]:
    written = written_mm(pdf)
    ours = our_lengths(model_dir)
    matched, missing = [], []
    for w in written:
        if not ours:
            missing.append(w)
            continue
        name, v = min(ours.items(), key=lambda kv: abs(kv[1] - w))
        if abs(v - w) <= max(TOL_MM, TOL_REL * w):
            matched.append({"written_mm": w, "ours": name, "ours_mm": round(v, 1)})
        else:
            missing.append(w)
    res: dict[str, Any] = {"kind": "drawing", "reference": pdf.name, "written_mm": written,
                           "matched": matched, "missing_mm": missing}  # fmt: skip
    if use_ai:
        try:
            res["ai"] = _ai_compare(model_dir, pdf, params, missing)
        except CoverError as exc:
            res["ai_error"] = str(exc)
    return res


AI_SYSTEM = """You compare a cover workshop's own drawing or pattern of a cover (the reference,
which is right) with the cover its program made: the program's size drawing (pieces with sizes)
and a picture of its cover. List every real difference: the number or shape of the pieces, where the
seams run, sizes, the slope of the top, ends, hem, vents, air pockets, drawstrings, anything a
sewer would notice. Then say what the program should learn: general rules (for all covers of
this kind, not for this model only), each with a check that would catch it. Be specific, with
the numbers. Answer with JSON only:
{"summary": "one or two sentences", "differences": [{"what": "...", "reference": "...",
 "program": "...", "matters": "high | medium | low"}],
 "lessons": [{"rule": "...", "check": "...", "applies_to": "box | tensioned | drawn | all"}]}"""


def _ai_compare(model_dir: Path, pdf: Path, params: EffectiveParams,
                missing: list[float]) -> dict[str, Any]:  # fmt: skip
    import pymupdf

    from coverengine.ai import ask_parts
    from coverengine.params import Registry

    vision = Registry.load(None).resolve(trial={
        "ai.provider": str(params["ai.vision_provider"]),
        "ai.model": str(params["ai.vision_model"]),
        "ai.base_url": str(params["ai.vision_base_url"]), "ai.timeout_s": 600})  # fmt: skip

    def pages(path: Path, limit: int = 4) -> list[str]:
        doc = pymupdf.open(path)
        return [base64.b64encode(doc[i].get_pixmap(dpi=DPI).tobytes("png")).decode()
                for i in range(min(limit, doc.page_count))]  # fmt: skip

    parts: list[dict[str, Any]] = [{"type": "text", "text":
        "The reference (the workshop's own, right) follows first, then the program's size drawing"
        f" and its cover. Sizes on the reference not found in the program's pattern (mm): "
        f"{missing}"}]  # fmt: skip
    parts += [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{i}"}}
        for i in pages(pdf)
    ]
    if (model_dir / "sizes.pdf").is_file():
        parts += [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{i}"}}
                  for i in pages(model_dir / "sizes.pdf", 3)]  # fmt: skip
    if (model_dir / "cover.png").is_file():
        png = base64.b64encode((model_dir / "cover.png").read_bytes()).decode()
        parts.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png}"}})
    ans = ask_parts(vision, AI_SYSTEM, parts)
    ans.pop("_usage", None)
    return ans
