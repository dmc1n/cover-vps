"""`cover info`: basic facts about a mesh file, compared to its analytic sidecar if present."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import trimesh

from coverengine.errors import CoverError

Bounds = tuple[np.ndarray, np.ndarray]


def _measure(kind: str, i: int) -> Callable[[Bounds], float]:
    def fn(b: Bounds) -> float:
        lo, hi = float(b[0][i]), float(b[1][i])
        return {"bbox_min": lo, "bbox_max": hi, "size": hi - lo, "half_size": (hi - lo) / 2}[kind]

    return fn


MEASURES: dict[str, Callable[[Bounds], float]] = {
    f"{kind}_{axis}": _measure(kind, i)
    for kind in ("bbox_min", "bbox_max", "size", "half_size")
    for i, axis in enumerate("xyz")
}


@dataclass
class Comparison:
    name: str
    analytic: float
    measured: float

    @property
    def diff(self) -> float:
        return self.measured - self.analytic


@dataclass
class MeshInfo:
    path: Path
    vertices: int
    faces: int
    bounds: Bounds
    area_mm2: float
    components: int
    watertight: bool
    comparisons: list[Comparison]
    references: list[tuple[str, float, float | None]]

    @property
    def max_abs_diff(self) -> float:
        return max((abs(c.diff) for c in self.comparisons), default=0.0)


def load_mesh(path: Path) -> trimesh.Trimesh:
    if not path.is_file():
        raise CoverError(f"no such file: {path}")
    mesh = trimesh.load(path, force="mesh", process=True)
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise CoverError(f"{path}: no triangles found")
    return mesh


def mesh_info(path: Path) -> MeshInfo:
    mesh = load_mesh(path)
    v = np.asarray(mesh.vertices, dtype=np.float64)
    bounds: Bounds = (v.min(axis=0), v.max(axis=0))
    area = float(mesh.area)
    comparisons: list[Comparison] = []
    references: list[tuple[str, float, float | None]] = []
    side = path.with_suffix(".json")
    if side.is_file():
        doc: dict[str, Any] = json.loads(side.read_text(encoding="utf-8"))
        for name, entry in doc.get("exact", {}).items():
            measure = MEASURES.get(entry["measure"])
            if measure is None:
                raise CoverError(f"{side}: unknown measure {entry['measure']!r}")
            comparisons.append(Comparison(name, float(entry["value"]), measure(bounds)))
        for name, value in doc.get("reference", {}).items():
            measured = area if name == "area_mm2" else None
            references.append((name, float(value), measured))
    return MeshInfo(
        path=path,
        vertices=len(mesh.vertices),
        faces=len(mesh.faces),
        bounds=bounds,
        area_mm2=area,
        components=len(mesh.split(only_watertight=False)),
        watertight=bool(mesh.is_watertight),
        comparisons=comparisons,
        references=references,
    )


def format_info(info: MeshInfo) -> str:
    lo, hi = info.bounds
    size = hi - lo
    lines = [
        f"file        {info.path}",
        f"vertices    {info.vertices}",
        f"triangles   {info.faces}",
        f"parts       {info.components} connected component(s)",
        f"watertight  {'yes' if info.watertight else 'no'}",
        f"bbox min    {lo[0]:.6f} {lo[1]:.6f} {lo[2]:.6f} mm",
        f"bbox max    {hi[0]:.6f} {hi[1]:.6f} {hi[2]:.6f} mm",
        f"size        {size[0]:.6f} x {size[1]:.6f} x {size[2]:.6f} mm",
        f"area        {info.area_mm2 / 1e6:.6f} m2",
    ]
    if info.comparisons:
        w = max(len(c.name) for c in info.comparisons)
        lines += ["", f"{'analytic check':<{w}}  {'analytic':>14}  {'measured':>14}  {'diff':>10}"]
        for c in info.comparisons:
            lines.append(f"{c.name:<{w}}  {c.analytic:14.6f}  {c.measured:14.6f}  {c.diff:10.2e}")
        lines.append(f"max |diff|  {info.max_abs_diff:.2e} mm")
    if info.references:
        lines += ["", "reference (continuous surface; the mesh approximates it)"]
        for name, value, measured in info.references:
            extra = ""
            if measured is not None and value:
                extra = f"  mesh {measured:.3f}  ({(measured - value) / value:+.3%})"
            lines.append(f"  {name} {value:.3f}{extra}")
    return "\n".join(lines)


def is_model(path: Path) -> bool:
    """A model directory (or its model.glb) written by `cover import`."""
    from coverengine.io.model_io import MODEL_JSON

    folder = path if path.is_dir() else path.parent
    return (folder / MODEL_JSON).is_file() and (path.is_dir() or path.suffix.lower() == ".glb")


def format_model_info(path: Path) -> str:
    """Summary of an imported model; stable text, used for the golden files."""
    from coverengine.io.model_io import load_model, read_model_json

    folder = path if path.is_dir() else path.parent
    doc = read_model_json(folder)
    mesh = load_model(folder)
    v = np.asarray(mesh.vertices, dtype=np.float64)
    lo, hi = v.min(axis=0), v.max(axis=0)
    size = hi - lo
    src, place, parts = doc["source"], doc["placement"], doc["parts"]
    lines = [
        f"model       {doc['id']}",
        f"source      {src['file']} ({src['format']}), sha256 {src['sha256'][:12]}",
        f"units       {src['units_used']} (file declares {src['units_detected'] or 'no unit'})",
        f"placement   up {place['up_axis']}, front {place['front']}, "
        f"raised by {place['ground_offset_mm']:.3f} mm",
        f"parts       {parts['kept']} kept, {parts['dropped_small']} dropped as smaller than "
        f"{parts['min_part_mm']:g} mm, {parts['excluded']} excluded by name",
        f"exclude     {', '.join(parts['exclude']) or 'none'}",
        f"vertices    {len(mesh.vertices)}",
        f"triangles   {len(mesh.faces)}",
        f"bbox min    {lo[0]:.3f} {lo[1]:.3f} {lo[2]:.3f} mm",
        f"bbox max    {hi[0]:.3f} {hi[1]:.3f} {hi[2]:.3f} mm",
        f"size        {size[0]:.3f} x {size[1]:.3f} x {size[2]:.3f} mm",
        f"area        {float(mesh.area) / 1e6:.6f} m2",
    ]
    lines += [f"warning     {w}" for w in doc["warnings"]] or ["warnings    none"]
    return "\n".join(lines)
