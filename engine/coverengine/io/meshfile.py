"""STL, OBJ, PLY and glTF/GLB import through trimesh.

Named objects in the file become parts; each is split into connected bodies, so a single STL
holding a whole chair with its screws still gets per-body filtering. Coordinates stay in the
file's units; only glTF defines one (metres, Y up).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import trimesh

from coverengine.errors import CoverError
from coverengine.io.parts import Part, split_bodies, unique_paths

MESH_SUFFIXES = (".stl", ".obj", ".ply", ".glb", ".gltf")
GLTF_SUFFIXES = (".glb", ".gltf")


@dataclass
class MeshModel:
    parts: list[Part]
    units_declared: str | None  # "m" for glTF, None for formats without units


def natural_key(text: str) -> list[object]:
    """Sort "part/2" before "part/10"."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def load_mesh_parts(path: Path) -> MeshModel:
    suffix = path.suffix.lower()
    if suffix not in MESH_SUFFIXES:
        raise CoverError(f"{path}: unsupported file type {suffix}")
    try:
        scene = trimesh.load(path, force="scene", process=False)
    except Exception as exc:  # trimesh raises many types for broken files
        raise CoverError(f"{path}: could not read the mesh ({exc})") from exc
    if not isinstance(scene, trimesh.Scene):
        raise CoverError(f"{path}: no triangles found")
    nodes = sorted(scene.graph.nodes_geometry, key=natural_key)
    named: list[tuple[str, np.ndarray, np.ndarray]] = []
    for node in nodes:
        transform, geom_name = scene.graph[node]
        geom = scene.geometry.get(geom_name)
        if not isinstance(geom, trimesh.Trimesh) or len(geom.faces) == 0:
            continue
        v = np.asarray(geom.vertices, dtype=np.float64) @ transform[:3, :3].T + transform[:3, 3]
        name = path.stem if str(node) == path.name else str(node)  # trimesh names STLs by file
        named.append((name, v, np.asarray(geom.faces, dtype=np.int64)))
    if not named:
        raise CoverError(f"{path}: no triangles found")
    parts: list[Part] = []
    for part_path, (_, v, f) in zip(unique_paths(n for n, _, _ in named), named, strict=True):
        parts.extend(split_bodies(part_path, v, f))
    return MeshModel(parts, "m" if suffix in GLTF_SUFFIXES else None)
