"""Hull masks from the model's CoverDefinition (`cover.json`, key `hull_masks`).

    {"type": "box", "min": [x, y, z], "max": [x, y, z], "mode": "exclude"}  furniture inside is
                                                                            ignored (a pole)
    {"type": "box", "min": [...], "max": [...], "mode": "solid"}            the box is added as
                                                                            if it were furniture
Coordinates are canonical model coordinates in mm (as in model.glb).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray

from coverengine.errors import CoverError

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]
MODES = ("exclude", "solid")


def load_masks(model_dir: Path) -> list[dict[str, Any]]:
    path = model_dir / "cover.json"
    if not path.is_file():
        return []
    masks = json.loads(path.read_text(encoding="utf-8")).get("hull_masks", []) or []
    for i, m in enumerate(masks):
        if m.get("type") != "box" or m.get("mode") not in MODES:
            raise CoverError(f"{path}: hull_masks[{i}] must be a box with mode exclude or solid")
        if len(m.get("min", [])) != 3 or len(m.get("max", [])) != 3:
            raise CoverError(f"{path}: hull_masks[{i}] needs min and max as [x, y, z] in mm")
    return list(masks)


def _box(lo: Array, hi: Array) -> tuple[Array, IntArray]:
    box = trimesh.creation.box(bounds=np.array([lo, hi], dtype=np.float64))
    return np.asarray(box.vertices, dtype=np.float64), np.asarray(box.faces, dtype=np.int64)


def apply(
    vertices: Array, faces: IntArray, masks: Sequence[dict[str, Any]]
) -> tuple[Array, IntArray]:
    """The model triangles the hull is built from, after masks."""
    v, f = np.asarray(vertices, dtype=np.float64), np.asarray(faces, dtype=np.int64)
    for m in masks:
        lo, hi = np.minimum(m["min"], m["max"]), np.maximum(m["min"], m["max"])
        if m["mode"] == "exclude":
            centre = v[f].mean(axis=1)
            inside = np.all((centre >= lo) & (centre <= hi), axis=1)
            f = f[~inside]
        else:
            bv, bf = _box(np.asarray(lo, float), np.asarray(hi, float))
            f = np.vstack([f, bf + len(v)])
            v = np.vstack([v, bv])
    if len(f) == 0:
        raise CoverError("the hull masks exclude the whole model")
    return v, f
