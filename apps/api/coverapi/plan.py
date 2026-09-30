"""The plan view for the seam editor: a top-view picture of the cover (height shading with
contour lines, so folds show), the outline, and the seams as lines, all in the model's plan
coordinates (mm), the same as `seams.json`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from coverengine.io.model_io import load_model
from coverengine.seams import auto
from coverengine.seams.panels import _ordered

PLAN_PNG = "plan.png"
PLAN_PX = 1600  # longest side of the picture
CONTOURS = 24  # contour lines over the cover's height
PAD_MM = 40.0  # room round the cover in the picture


def _extent(v: np.ndarray) -> list[float]:
    lo, hi = v[:, :2].min(axis=0) - PAD_MM, v[:, :2].max(axis=0) + PAD_MM
    return [float(lo[0]), float(lo[1]), float(hi[0]), float(hi[1])]


def render_png(model_dir: Path) -> list[float]:
    """Write plan.png (top view of hull.glb) and return its extent [xmin, ymin, xmax, ymax]."""
    from matplotlib.figure import Figure
    from matplotlib.tri import Triangulation

    hull = load_model(model_dir / "hull.glb")
    v, f = np.asarray(hull.vertices), np.asarray(hull.faces)
    ext = _extent(v)
    w, h = ext[2] - ext[0], ext[3] - ext[1]
    scale = PLAN_PX / max(w, h)
    fig = Figure(figsize=(w * scale / 100, h * scale / 100), dpi=100)
    ax = fig.add_axes((0, 0, 1, 1))
    # faces seen from above only (the top), drawn low to high
    n = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    up = f[n[:, 2] > 0]
    tri = Triangulation(v[:, 0], v[:, 1], up)
    z = v[:, 2]
    ax.tripcolor(tri, z, cmap="Greys_r", shading="gouraud", alpha=0.9)
    levels = np.linspace(float(z.min()), float(z.max()), CONTOURS)
    ax.tricontour(tri, z, levels=levels, colors="#5a6b9a", linewidths=0.4)
    ax.set_xlim(ext[0], ext[2])
    ax.set_ylim(ext[1], ext[3])
    ax.set_aspect("auto")
    ax.axis("off")
    fig.savefig(model_dir / PLAN_PNG, dpi=100)
    return ext


def plan(model_dir: Path) -> dict[str, Any]:
    hull_path = model_dir / "hull.glb"
    if not hull_path.is_file():
        raise FileNotFoundError("no cover surface yet")
    png = model_dir / PLAN_PNG
    hull = load_model(hull_path)
    v = np.asarray(hull.vertices)
    if not png.is_file() or png.stat().st_mtime < hull_path.stat().st_mtime:
        ext = render_png(model_dir)
    else:
        ext = _extent(v)
    import trimesh

    line = auto.outline(trimesh.Trimesh(hull.vertices, hull.faces, process=True))
    outline = [[round(x, 1), round(y, 1)] for x, y in line.polygon.exterior.coords]
    out: dict[str, Any] = {
        "extent": [round(e, 1) for e in ext],
        "outline": outline,
        "seams": [],
        "panels": [],
        "manual": _read(model_dir / "seams.json"),
        "auto": _read(model_dir / "seams.auto.json"),
        "image": PLAN_PNG,
        "proposals": (_read(model_dir / "pattern.json") or {}).get("proposals", []),
    }
    npz, report = model_dir / "panels.npz", _read(model_dir / "panels.json")
    if npz.is_file() and report:
        data = np.load(npz)
        original = data["original_vertex"]
        points = np.zeros((int(original.max()) + 1, 3))
        points[original] = data["vertices"]
        for i, s in enumerate(report["seams"]):
            edges = data["seam_edges"][data["seam_index"] == i]
            if not len(edges):
                continue
            # a seam may come in several parts: walk each
            remaining = {tuple(e) for e in edges.tolist()}
            while remaining:
                part = _connected(remaining)
                order = _ordered(np.array(sorted(part)))
                xy = points[order][:, :2]
                out["seams"].append(
                    {
                        "id": s["id"],
                        "kind": s["kind"],
                        "points": [[round(float(x), 1), round(float(y), 1)] for x, y in xy],
                    }
                )
        faces, labels = data["faces"], data["labels"]
        verts = data["vertices"]
        for k, p in enumerate(report["panels"]):
            mine = faces[labels == k]
            c = verts[mine].mean(axis=1)
            top = c[:, 2] >= np.percentile(c[:, 2], 50) if p["region"] != "top" else slice(None)
            at = c[top][:, :2].mean(axis=0)
            out["panels"].append(
                {"name": p["name"], "region": p["region"], "at": [round(float(a), 1) for a in at]}
            )
    return out


def _connected(edges: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Take one connected run of edges out of the set."""
    start = next(iter(edges))
    part, frontier = {start}, {start[0], start[1]}
    edges.discard(start)
    grew = True
    while grew:
        grew = False
        for e in list(edges):
            if e[0] in frontier or e[1] in frontier:
                part.add(e)
                edges.discard(e)
                frontier.update(e)
                grew = True
    return part


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def save_seams(model_dir: Path, doc: dict[str, Any] | None) -> None:
    """Write the hand-placed seams to seams.json (None: back to the automatic seams)."""
    path = model_dir / "seams.json"
    if doc is None:
        path.unlink(missing_ok=True)
        return
    out: dict[str, Any] = {"format_version": 1, "note": "placed in the web app"}
    if doc.get("skirt_seams") is not None:
        out["skirt_seams"] = [[float(x), float(y)] for x, y in doc["skirt_seams"]]
    if doc.get("top_seams") is not None:
        lines = [[[float(x), float(y)] for x, y in line] for line in doc["top_seams"]]
        out["top_seams"] = [line for line in lines if len(line) >= 2]
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
