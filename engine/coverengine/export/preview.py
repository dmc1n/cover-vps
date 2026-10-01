"""A 3D picture of the finished cover (`cover.png`) for the catalogue: the panels in the
house-style colours (palette.py), shaded, seams in dark lines, seen from the front right and
above."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.figure import Figure

from coverengine.export.drawing import _edge_visibility, _projected, _views, load_cover
from coverengine.palette import PIECES
from coverengine.params import EffectiveParams

PREVIEW_PNG = "cover.png"
SIZE_IN = (4.0, 3.0)  # param-ok: picture size (inches)
DPI = 150  # param-ok: picture resolution
PALETTE = PIECES  # the house-style piece colours
SHADE_MIN = 0.72  # param-ok: display (light shading: the house colours stay recognisable)


def write_preview(model_dir: Path, doc: dict[str, Any], params: EffectiveParams, out: Path) -> Path:
    cover = load_cover(model_dir, doc, params)
    view = _views()["iso"]
    n = cover.normals
    facing = n @ view.eye > 0
    faces = cover.welded[facing]
    depth = (cover.points[faces] @ view.eye).mean(axis=1)
    order = np.argsort(depth, kind="stable")
    light = view.eye + 0.6 * view.up - 0.3 * view.right  # param-ok: light from above left
    light /= np.linalg.norm(light)
    shade = SHADE_MIN + (1 - SHADE_MIN) * np.clip(n[facing] @ light, 0, 1)
    base = np.array(PALETTE)[cover.labels[facing] % len(PALETTE)]
    rgb = np.clip(base * shade[:, None], 0, 1)
    p2 = _projected(cover, view, cover.points)
    fig = Figure(figsize=SIZE_IN, dpi=DPI)
    ax = fig.add_axes((0.02, 0.02, 0.96, 0.96))
    ax.add_collection(
        PolyCollection(
            list(p2[faces[order]]), facecolors=rgb[order], edgecolors=rgb[order], linewidths=0.2
        )
    )
    visible = _edge_visibility(cover, facing)
    seams = cover.seam_edges[visible[: len(cover.seam_edges)]]
    ax.add_collection(LineCollection(list(p2[seams]), colors="#2a2f3a", linewidths=0.6))
    lo, hi = p2.min(axis=0), p2.max(axis=0)
    pad = 0.04 * float(np.ptp(p2, axis=0).max())  # param-ok: display margin
    ax.set_xlim(lo[0] - pad, hi[0] + pad)
    ax.set_ylim(lo[1] - pad, hi[1] + pad)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.savefig(out, dpi=DPI, transparent=True, metadata={"Software": None})
    return out
