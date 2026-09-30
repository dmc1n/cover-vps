"""Parts of an imported model: splitting into bodies, size filter and name exclusions.

Every loader (STEP, IGES, mesh files) delivers a list of named triangle sets. Each set is split
into connected bodies, because one CAD part or one STL often holds many separate pieces (a
compound of screws, a whole chair in one file). Filtering then works per body.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

# Vertices closer than this are the same point when bodies are split (CAD faces share edges
# only up to rounding). Geometry, not a parameter.
MERGE_QUANTUM_MM = 1e-6

KEPT = "kept"
DROPPED_SMALL = "dropped_small"
EXCLUDED = "excluded"


@dataclass
class Part:
    """One connected body; `path` is unique in the model ("chair/seat", "chair/seat/2")."""

    path: str
    vertices: Array
    faces: IntArray
    status: str = KEPT
    rule: str | None = None  # the exclusion pattern that matched, if any

    @property
    def name(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def bounds(self) -> tuple[Array, Array]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    @property
    def size(self) -> Array:
        lo, hi = self.bounds
        return hi - lo

    @property
    def max_extent(self) -> float:
        return float(self.size.max())

    def volume(self) -> float | None:
        """Enclosed volume in mm3 if the body is closed (every edge used twice), else None."""
        f = self.faces
        edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
        _, counts = np.unique(edges, axis=0, return_counts=True)
        if len(counts) == 0 or not np.all(counts == 2):
            return None
        tri = self.vertices[f]
        return abs(
            float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()) / 6
        )

    def transformed(self, matrix: Array) -> Part:
        """Apply a 4x4 transform (rotation and translation, optionally uniform scale)."""
        v = self.vertices @ matrix[:3, :3].T + matrix[:3, 3]
        return Part(self.path, v, self.faces, self.status, self.rule)


def merge_vertices(vertices: Array, faces: IntArray) -> tuple[Array, IntArray]:
    """Weld coincident vertices; keeps the first occurrence, in first-occurrence order."""
    keys = np.round(vertices / MERGE_QUANTUM_MM).astype(np.int64)
    _, first, inverse = np.unique(keys, axis=0, return_index=True, return_inverse=True)
    order = np.argsort(first, kind="stable")  # unique ids in order of first appearance
    rank = np.empty_like(order)
    rank[order] = np.arange(len(order))
    return vertices[first[order]], rank[inverse.ravel()][faces]


def split_bodies(path: str, vertices: Array, faces: IntArray) -> list[Part]:
    """Split a triangle set into edge-connected bodies: one keeps `path`, several get /1, /2."""
    if len(faces) == 0:
        return []
    v, f = merge_vertices(np.asarray(vertices, dtype=np.float64), np.asarray(faces, np.int64))
    # faces are connected when they share an edge; bodies that only touch at a point (a leg
    # under a seat corner) stay separate. Graph nodes: faces first, then edges.
    nf = len(f)
    edges = np.sort(f[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), axis=1)
    _, edge_id = np.unique(edges, axis=0, return_inverse=True)
    rows = np.repeat(np.arange(nf), 3)
    cols = nf + edge_id.ravel()
    n = nf + int(edge_id.max()) + 1
    graph = coo_matrix((np.ones(len(rows), dtype=np.int8), (rows, cols)), shape=(n, n))
    count, labels = connected_components(graph, directed=False)
    count = len(np.unique(labels[:nf]))
    face_label = labels[:nf]
    if count == 1:
        return [Part(path, v, f)]
    # number bodies in order of their first face, so the numbering follows the file
    _, first_face = np.unique(face_label, return_index=True)
    parts = []
    for k, label in enumerate(np.argsort(first_face, kind="stable"), start=1):
        sel = f[face_label == label]
        used, local = np.unique(sel, return_inverse=True)
        parts.append(Part(f"{path}/{k}", v[used], local.reshape(sel.shape)))
    return parts


def unique_paths(paths: Iterable[str]) -> list[str]:
    """Make repeated names unique in order: "screw", "screw#2", "screw#3"."""
    seen: dict[str, int] = {}
    out = []
    for p in paths:
        seen[p] = seen.get(p, 0) + 1
        out.append(p if seen[p] == 1 else f"{p}#{seen[p]}")
    return out


def matching_rule(path: str, patterns: Sequence[str]) -> str | None:
    """First exclusion pattern matching the full path or any path segment (case-insensitive)."""
    low = path.lower()
    segments = low.split("/")
    for pattern in patterns:
        pat = pattern.lower()
        if fnmatch.fnmatchcase(low, pat) or any(fnmatch.fnmatchcase(s, pat) for s in segments):
            return pattern
    return None


def classify(parts: Sequence[Part], min_part_mm: float, exclude: Sequence[str]) -> None:
    """Set each part's status: excluded by name first, then dropped when too small."""
    for part in parts:
        rule = matching_rule(part.path, exclude)
        if rule is not None:
            part.status, part.rule = EXCLUDED, rule
        elif part.max_extent < min_part_mm:
            part.status, part.rule = DROPPED_SMALL, None
        else:
            part.status, part.rule = KEPT, None
