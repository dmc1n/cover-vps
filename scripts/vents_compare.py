"""Before/after picture of a cover's air vents, next to the approver's marked pictures (ADR-101).

    uv run python scripts/vents_compare.py OUT.png --old DIR --new DIR [--pics A.png ...]

Each cover is drawn from the front-left, the front-right and the back (the pieces in soft grey,
shaded by the way they face), its vents as dark openings with their piece and height; the plan
from above shows every vent as an arrow out of the cover. For looking, not for the cutting table.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

MAX_FACES = 12000  # the picture needs no more triangles than this


def _mesh(model: Path) -> tuple[np.ndarray, np.ndarray]:
    d = np.load(model / "panels.npz")
    v, f = d["vertices"], d["faces"]
    if len(f) > MAX_FACES:  # fewer triangles, the same shape (libigl's edge collapse)
        import igl

        out = igl.decimate(np.asarray(v, np.float64), np.asarray(f, np.int64), MAX_FACES)
        if isinstance(out[0], bool | np.bool_):  # older libigl: (ok, V, F, J, I)
            out = out[1:]
        if len(out[1]):
            v, f = out[0], out[1]
    return v, f


def _vents(model: Path) -> list[dict]:
    p = model / "vents.json"
    return json.loads(p.read_text())["vents"] if p.is_file() else []


def _view(ax, model: Path, az: float, title: str) -> None:  # type: ignore[no-untyped-def]
    v, f = _mesh(model)
    tri = v[f]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9
    light = np.array([0.3, -0.5, 0.8])
    shade = 0.55 + 0.4 * np.abs(n @ (light / np.linalg.norm(light)))
    col = np.stack([shade * 0.86, shade * 0.84, shade * 0.78, np.ones_like(shade)], axis=1)
    ax.add_collection3d(Poly3DCollection(tri, facecolors=col, edgecolors="none"))
    for x in _vents(model):
        c = np.asarray(x["corners_mm"]) + np.asarray(x["normal"]) * 40.0
        ax.add_collection3d(
            Poly3DCollection([c], facecolors="#d03020", edgecolors="#000000", linewidths=1.5)
        )
    lo, hi = v.min(axis=0), v.max(axis=0)
    mid, span = (lo + hi) / 2, (hi - lo).max() / 2
    ax.set_xlim(mid[0] - span, mid[0] + span)
    ax.set_ylim(mid[1] - span, mid[1] + span)
    ax.set_zlim(0, 2 * span)
    ax.view_init(elev=22, azim=az)
    ax.set_box_aspect((1, 1, 1))
    ax.set_axis_off()
    ax.set_title(title, fontsize=8)


def _plan(ax, model: Path, title: str) -> None:  # type: ignore[no-untyped-def]
    v, f = _mesh(model)
    tri = v[f][:, :, :2]
    from matplotlib.collections import PolyCollection

    ax.add_collection(PolyCollection(tri, facecolors="#e4e0d6", edgecolors="none"))
    lo, hi = v[:, :2].min(axis=0) - 700, v[:, :2].max(axis=0) + 700
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    for x in _vents(model):
        c, nrm = np.asarray(x["centre_mm"]), np.asarray(x["normal"])
        z = [q[2] for q in x["corners_mm"]]
        ax.annotate("", xy=(c[0] + nrm[0] * 300, c[1] + nrm[1] * 300), xytext=(c[0], c[1]),
                    arrowprops={"arrowstyle": "->", "color": "#d03020"})  # fmt: skip
        ax.plot(c[0], c[1], "s", color="#202020", ms=5)
        ax.text(c[0] + nrm[0] * 380, c[1] + nrm[1] * 380,
                f"{x['piece'].removeprefix('skirt-')}\n{min(z) / 10:.0f}-{max(z) / 10:.0f}cm",
                fontsize=5, ha="center", va="center")  # fmt: skip
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.set_title(title + " (from above, front at the bottom)", fontsize=8)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--old", type=Path, required=True)
    ap.add_argument("--new", type=Path, required=True)
    ap.add_argument("--pics", type=Path, nargs="*", default=[])
    a = ap.parse_args()
    import matplotlib.image as mpimg

    rows = 3 if a.pics else 2
    fig = Figure(figsize=(16, 4.2 * rows), dpi=90)
    for i, (label, m) in enumerate((("before", a.old), ("after", a.new))):
        n = len(_vents(m))
        for j, az in enumerate((-125, -55, 90)):
            ax = fig.add_subplot(rows, 4, i * 4 + j + 1, projection="3d")
            side = {-125: "front-left", -55: "front-right", 90: "back"}[az]
            _view(ax, m, az, f"{label}: {n} vents, {side}")
        _plan(fig.add_subplot(rows, 4, i * 4 + 4), m, f"{label}: {n} vents")
    for k, p in enumerate(a.pics[:4]):
        ax = fig.add_subplot(rows, 4, 8 + k + 1)
        ax.imshow(mpimg.imread(p))
        ax.set_axis_off()
        ax.set_title(f"marked: {p.name}", fontsize=8)
    fig.suptitle(a.new.name, fontsize=11)
    fig.tight_layout()
    a.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(a.out)


if __name__ == "__main__":
    main()
