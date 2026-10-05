"""The website's scroll story (docs/plans/scroll-site.md, ADR-067): one catalogue model's cover
as three shapes of the same points, so the page can morph between them while scrolling:

- `design`: the cover surface as the studio designed it, cut into its pieces;
- `flat`: every piece unfolded to its flat pattern (true lengths), laid out on a roll;
- `drape`: the sewn cover as it falls over the furniture (Style3D, drape.bin).

Each point belongs to one piece (seams are split, so pieces can part and unfold). Units are
metres in the viewer's frame (Y up: engine x, z, −y). Binary layout, little endian:
design f32[n*3], flat f32[n*3], drape f32[n*3], piece u8[n], faces u32[m*3].
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from coverengine import drape as dr
from coverengine.params import EffectiveParams

MM_PER_M = 1000.0  # param-ok: units
FLOOR_M = 0.002  # param-ok: the flat pattern lies just above the floor (no flicker)
GAP_MM = 60.0  # param-ok: room between pieces on the roll
QMAX = 65535  # param-ok: drape.bin holds 16-bit numbers


def _view(xyz_mm: Any) -> Any:
    """Engine (mm, Z up) to the viewer (m, Y up)."""
    p = np.asarray(xyz_mm, dtype=np.float64) / MM_PER_M
    return np.column_stack([p[:, 0], p[:, 2], -p[:, 1]])


def _layout(flat: dict[int, Any], roll_mm: float) -> tuple[dict[int, Any], list[float]]:
    """Every piece turned with its long side along the roll, placed in rows across the roll's
    width like a simple marker; returns the placed points (mm) and the roll's size (mm)."""
    placed, x, y, row_h, length = {}, 0.0, 0.0, 0.0, 0.0
    order = sorted(flat, key=lambda k: -float(np.ptp(flat[k][:, 1]) * np.ptp(flat[k][:, 0])))
    for k in order:
        p = flat[k] - flat[k].mean(axis=0)
        u, _, vt = np.linalg.svd(p, full_matrices=False)
        p = p @ vt.T  # the long side along x
        if np.ptp(p[:, 1]) > roll_mm:
            p = p[:, ::-1]
        w, h = float(np.ptp(p[:, 0])), float(np.ptp(p[:, 1]))
        if y + h > roll_mm:  # a new row along the roll
            x, y, row_h = length + GAP_MM, 0.0, 0.0
        p = p - p.min(axis=0) + (x, y)
        placed[k] = p
        y += h + GAP_MM
        row_h = max(row_h, w)
        length = max(length, x + row_h)
    return placed, [length, roll_mm]


def build(model_dir: Path, params: EffectiveParams) -> tuple[dict[str, Any], bytes]:
    c = dr.cloth(model_dir, params)
    if c.flat is None:
        raise ValueError("no flat pieces")
    faces, piece, flat = c.faces, c.piece, c.flat
    final = c.x
    doc_path = model_dir / dr.DRAPE_JSON
    if doc_path.is_file():
        doc = json.loads(doc_path.read_text())
        if np.array_equal(np.asarray(doc["faces"]), faces):
            n = int(doc["points_per_frame"])
            lo, hi = (np.array(v) for v in doc["frame_box_mm"])
            raw = np.frombuffer((model_dir / dr.DRAPE_BIN).read_bytes(), dtype=np.uint16)
            final = raw.reshape(-1, n, 3)[-1].astype(np.float64) / QMAX * (hi - lo) + lo
    # one point per (welded point, piece): seams split, so pieces part and unfold
    keys = np.stack([faces.ravel(), np.repeat(piece, 3)], axis=1)  # param-ok: three corners
    uniq, idx = np.unique(keys, axis=0, return_inverse=True)
    idx = idx.reshape(-1, 3)  # param-ok: three corners
    corner_uv = flat.reshape(-1, 2)
    uv = np.zeros((len(uniq), 2))
    uv[idx.ravel()] = corner_uv
    pieces = sorted(set(piece.tolist()))
    per = {k: uv[uniq[:, 1] == k] for k in pieces}
    placed, roll = _layout(per, float(params["roll.usable_width_mm"]))
    flat_mm = np.zeros((len(uniq), 3))
    for k in pieces:
        flat_mm[uniq[:, 1] == k, :2] = placed[k]
    # the roll in front of the furniture, its long side along the furniture's length
    flat_mm[:, 0] -= roll[0] / 2
    flat_mm[:, 1] -= roll[1] / 2
    design = _view(c.x[uniq[:, 0]])
    draped = _view(final[uniq[:, 0]])
    on_floor = _view(flat_mm)
    on_floor[:, 1] = FLOOR_M
    meta = {
        "points": int(len(uniq)),
        "triangles": int(len(faces)),
        "pieces": [{"name": c.names[k], "index": int(k)} for k in pieces],
        "roll_m": [roll[0] / MM_PER_M, roll[1] / MM_PER_M],
        "size_m": (design.max(axis=0) - design.min(axis=0)).round(3).tolist(),
        "draped": final is not c.x,
    }
    blob = b"".join([
        design.astype("<f4").tobytes(), on_floor.astype("<f4").tobytes(),
        draped.astype("<f4").tobytes(), uniq[:, 1].astype(np.uint8).tobytes(),
        idx.astype("<u4").tobytes(),
    ])  # fmt: skip
    return meta, blob


def furniture_glb(model_dir: Path) -> bytes:
    """The furniture as one mesh (a model often has a thousand parts), coloured from its photo's
    look: a dark plinth under light upholstery."""
    scene = trimesh.load(model_dir / "model.glb")
    mesh: Any = scene.to_geometry() if isinstance(scene, trimesh.Scene) else scene
    v = np.asarray(mesh.vertices)
    low = v[:, 1] < v[:, 1].min() + 0.11  # param-ok: the plinth (m)
    plinth, cushion = [40, 42, 40, 255], [205, 207, 202, 255]  # param-ok: colours (RGBA)
    col = np.where(low[:, None], plinth, cushion).astype(np.uint8)
    out = trimesh.Trimesh(v, mesh.faces, vertex_colors=col, process=False)
    data: Any = out.export(file_type="glb")
    return bytes(data)
