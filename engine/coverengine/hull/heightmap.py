"""Height map of a triangle soup: the highest point of the model above each spot of the floor.

Grid cell centres lie on multiples of the resolution, so symmetric models give symmetric maps.
Every cell centre covered by a triangle's footprint gets that triangle's exact height there.
Triangles that cover no cell centre (thin or vertical ones) mark the cells nearest to their
vertices and to samples along their edges instead, so thin tubes and vertical boards are not
lost between samples. Cells nothing lies above hold -inf.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

# Work in chunks of this many (triangle, cell) candidate pairs to bound memory.
CHUNK_PAIRS = 4_000_000
# A cell centre on a triangle's edge counts as inside (relative barycentric tolerance).
EDGE_EPS = 1e-9


@dataclass
class HeightMap:
    """z[i, j] is the height above the cell centre (x0 + i*h, y0 + j*h); -inf where empty."""

    z: Array
    x0: float
    y0: float
    h: float

    @property
    def xs(self) -> Array:
        return self.x0 + self.h * np.arange(self.z.shape[0], dtype=np.float64)

    @property
    def ys(self) -> Array:
        return self.y0 + self.h * np.arange(self.z.shape[1], dtype=np.float64)

    @property
    def footprint(self) -> NDArray[np.bool_]:
        return np.isfinite(self.z)


def grid_for(lo: Array, hi: Array, h: float, margin_mm: float) -> tuple[float, float, int, int]:
    """Origin and size of a grid on multiples of h covering [lo, hi] plus margin in x and y."""
    x0 = math.floor((lo[0] - margin_mm) / h) * h
    y0 = math.floor((lo[1] - margin_mm) / h) * h
    nx = math.ceil((hi[0] + margin_mm - x0) / h) + 1
    ny = math.ceil((hi[1] + margin_mm - y0) / h) + 1
    return x0, y0, nx, ny


def rasterize(vertices: Array, faces: IntArray, h: float, margin_mm: float) -> HeightMap:
    v = np.asarray(vertices, dtype=np.float64)
    f = np.asarray(faces, dtype=np.int64)
    x0, y0, nx, ny = grid_for(v.min(axis=0), v.max(axis=0), h, margin_mm)
    z = np.full((nx, ny), -np.inf)
    tri = v[f]  # (m, 3, 3)
    a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
    e1, e2 = b - a, c - a
    det = e1[:, 0] * e2[:, 1] - e2[:, 0] * e1[:, 1]
    lo, hi = tri[:, :, :2].min(axis=1), tri[:, :, :2].max(axis=1)
    i0 = np.ceil((lo[:, 0] - x0) / h).astype(np.int64)
    i1 = np.floor((hi[:, 0] - x0) / h).astype(np.int64)
    j0 = np.ceil((lo[:, 1] - y0) / h).astype(np.int64)
    j1 = np.floor((hi[:, 1] - y0) / h).astype(np.int64)
    wi, wj = np.maximum(i1 - i0 + 1, 0), np.maximum(j1 - j0 + 1, 0)
    # triangles seen edge-on from above have no footprint; they are splatted below
    scale = np.linalg.norm(e1[:, :2], axis=1) * np.linalg.norm(e2[:, :2], axis=1)
    flat = np.abs(det) > EDGE_EPS * scale
    counts = np.where(flat, wi * wj, 0)
    hits = np.zeros(len(f), dtype=np.int64)

    order = np.flatnonzero(counts)
    if len(order):
        cumulative = np.cumsum(counts[order])
        cuts = np.searchsorted(
            cumulative, np.arange(CHUNK_PAIRS, cumulative[-1], CHUNK_PAIRS), side="right"
        )
    else:
        cuts = np.zeros(0, dtype=np.int64)
    for part in np.split(order, cuts):
        if len(part) == 0:
            continue
        n = counts[part]
        t = np.repeat(part, n)
        off = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
        ii = i0[t] + off // wj[t]
        jj = j0[t] + off % wj[t]
        px = x0 + ii * h - a[t, 0]
        py = y0 + jj * h - a[t, 1]
        d = det[t]
        u = (px * e2[t, 1] - e2[t, 0] * py) / d
        w = (e1[t, 0] * py - px * e1[t, 1]) / d
        inside = (u >= -EDGE_EPS) & (w >= -EDGE_EPS) & (u + w <= 1 + EDGE_EPS)
        zz = a[t, 2] + u * e1[t, 2] + w * e2[t, 2]
        np.maximum.at(z, (ii[inside], jj[inside]), zz[inside])
        hits += np.bincount(t[inside], minlength=len(f))

    missed = np.flatnonzero(hits == 0)
    if len(missed):
        _splat(z, tri[missed], x0, y0, h)
    return HeightMap(z, x0, y0, h)


def _splat(z: Array, tri: Array, x0: float, y0: float, h: float) -> None:
    """Mark the cells nearest to vertices and edge samples (spacing <= h/2) of triangles."""
    starts = tri
    ends = np.roll(tri, -1, axis=1)
    seg_a, seg_b = starts.reshape(-1, 3), ends.reshape(-1, 3)
    length = np.linalg.norm((seg_b - seg_a)[:, :2], axis=1)
    n = np.ceil(length / (h / 2)).astype(np.int64) + 1
    s = np.repeat(np.arange(len(n)), n)
    k = np.arange(n.sum()) - np.repeat(np.cumsum(n) - n, n)
    frac = (k / np.maximum(n[s] - 1, 1))[:, None]
    p = seg_a[s] + frac * (seg_b[s] - seg_a[s])
    ii = np.rint((p[:, 0] - x0) / h).astype(np.int64)
    jj = np.rint((p[:, 1] - y0) / h).astype(np.int64)
    np.maximum.at(z, (ii, jj), p[:, 2])
