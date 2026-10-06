"""The air vents on the cover in 3D, to show them in the viewer (ADR-073).

The vents are placed on the flat skirt panels (`finish.place_vents`, in the coordinates of
`pattern.json`). To find where one sits on the cover, the panel is flattened again exactly as
`cover flatten` did (the same mesh, solver and settings, so the same flat panel; checked
against the stored outline) and each corner of the opening is carried back to 3D through the
flat triangle it lies in. Written by `cover export` as `vents.json`:

    {"vents": [{"piece": "skirt-front", "centre_mm": [x, y, z], "corners_mm": [[x, y, z] x 4],
                "normal": [x, y, z], "size_mm": [w, h]}], "warnings": [...]}

Corners run bottom left, bottom right, top right, top left (as seen from outside); the normal
points out of the cover.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.spatial import cKDTree

from coverengine.finish.finish import place_vents
from coverengine.flatten.pattern import _panel_mesh, compensation
from coverengine.flatten.solve import flatten
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
VENTS_JSON = "vents.json"
SAME_OUTLINE_MM = 1.0  # param-ok: the re-flattened panel must match the stored outline


def _barycentric(uv: Array, faces: NDArray[np.int64], p: Array) -> tuple[int, Array]:
    """The flat triangle `p` lies in (or the nearest one) and its barycentric weights."""
    a, b, c = uv[faces[:, 0]], uv[faces[:, 1]], uv[faces[:, 2]]
    v0, v1, v2 = b - a, c - a, p - a
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    den = np.where(np.abs(den) < 1e-12, 1e-12, den)  # param-ok: no division by zero
    w1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
    w2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
    w0 = 1 - w1 - w2
    worst = np.minimum(np.minimum(w0, w1), w2)  # >= 0 inside
    i = int(np.argmax(worst))
    w = np.clip(np.array([w0[i], w1[i], w2[i]]), 0.0, None)
    return i, w / w.sum()


def _to_3d(v: Array, f: NDArray[np.int64], uv: Array, p: Array) -> tuple[Array, Array]:
    i, w = _barycentric(uv, f, p)
    tri = v[f[i]]
    n = np.cross(tri[1] - tri[0], tri[2] - tri[0])
    return w @ tri, n / (np.linalg.norm(n) or 1.0)


def vents_3d(model_dir: Path, doc: dict[str, Any], params: EffectiveParams) -> dict[str, Any]:
    """Every vent of the cover in 3D (see the module's docstring)."""
    vents, _ = place_vents(doc["panels"], params)
    out: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not vents:
        return {"vents": out, "warnings": warnings}
    data = np.load(model_dir / "panels.npz")
    names = [p["name"] for p in json.loads((model_dir / "panels.json").read_text())["panels"]]
    vertices, faces, labels = data["vertices"], data["faces"], data["labels"]
    middle = (vertices.min(axis=0) + vertices.max(axis=0)) / 2
    outline_of = {p["name"]: np.asarray(p["outline_mm"], dtype=np.float64) for p in doc["panels"]}
    scale = compensation(params)
    for name, rects in vents.items():
        if name not in names:
            warnings.append(f"{name}: not in panels.json")
            continue
        mesh, _ = _panel_mesh(vertices, faces[labels == names.index(name)])
        flat = flatten(
            mesh,
            str(params["flatten.solver"]),
            int(params["flatten.iterations"]),
            float(params["flatten.slim_tolerance"]),  # type: ignore[arg-type]
            int(params["flatten.max_triangles"]),
        )
        uv = flat.uv * scale
        gap, _ = cKDTree(uv).query(outline_of[name])
        if float(gap.max()) > SAME_OUTLINE_MM:
            warnings.append(f"{name}: the flat panel differs from pattern.json (run cover flatten)")
            continue
        v, f = np.asarray(flat.vertices), np.asarray(flat.faces, dtype=np.int64)
        for rect in rects:
            corners = [_to_3d(v, f, uv, np.asarray(q, dtype=np.float64))[0] for q in rect]
            centre, normal = _to_3d(v, f, uv, np.asarray(rect, dtype=np.float64).mean(axis=0))
            away = centre - middle
            away[2] = 0.0
            if float(normal @ away) < 0:  # out of the cover, not into it
                normal = -normal
            # seen from outside the corners run bottom left to top left
            if float(np.cross(corners[1] - corners[0], corners[3] - corners[0]) @ normal) < 0:
                corners = [corners[1], corners[0], corners[3], corners[2]]
            w = float(np.linalg.norm(np.asarray(rect[1]) - np.asarray(rect[0])))
            h = float(np.linalg.norm(np.asarray(rect[3]) - np.asarray(rect[0])))
            out.append(
                {
                    "piece": name,
                    "centre_mm": [round(float(x), 1) for x in centre],
                    "corners_mm": [[round(float(x), 1) for x in c] for c in corners],
                    "normal": [round(float(x), 4) for x in normal],
                    "size_mm": [round(w, 1), round(h, 1)],
                }
            )
    return {"vents": out, "warnings": warnings}


def ensure_vents(model_dir: Path) -> Path | None:
    """vents.json, made when the viewer asks for it (ADR-080): export no longer flattens every
    skirt piece a second time. Made again when it is older than finished.json. None when the
    cover is not exported yet."""
    import json

    finished = model_dir / "finished.json"
    pattern = model_dir / "pattern.json"
    out = model_dir / VENTS_JSON
    if not (finished.is_file() and pattern.is_file()):
        return None
    if out.is_file() and out.stat().st_mtime >= finished.stat().st_mtime:
        return out
    from coverengine.params.registry import Registry, resolve_model

    params = resolve_model(model_dir, {}, Registry.load(None), None)
    doc = json.loads(pattern.read_text(encoding="utf-8"))
    try:
        vents = vents_3d(model_dir, doc, params)
    except (OSError, KeyError, ValueError) as exc:
        vents = {"vents": [], "warnings": [f"vents not placed in 3D: {exc}"]}
    out.write_text(json.dumps(vents, indent=1) + "\n", encoding="utf-8")
    return out
