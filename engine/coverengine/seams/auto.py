"""Automatic seams for a tensioned cover (ADR-026).

- skirt seam: all round, where the vertical skirt meets the top: the level set of the inward
  distance to the outline (the hem seen from above) at `seams.skirt_seam_inset_mm`;
- corner seams: vertical, wherever the outline turns by more than `seams.corner_angle_deg`
  within `seams.corner_window_mm`, plus equal splits of stretches longer than
  `seams.max_skirt_panel_mm`; a skirt without corners gets one seam at the back.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import igl
import numpy as np
import shapely
import trimesh
from numpy.typing import NDArray

from coverengine.errors import CoverError
from coverengine.seams.cut import CutMesh, Seam

Array = NDArray[np.float64]
Mask = NDArray[np.bool_]

# Outline sampling step for corner detection (mm).
OUTLINE_STEP_MM = 5.0  # param-ok: sampling step
# Fewest samples of an outline.
MIN_SAMPLES = 8  # param-ok: sampling


@dataclass
class Outline:
    polygon: shapely.Polygon
    points: Array  # closed, resampled every OUTLINE_STEP_MM, counter-clockwise, no repeat
    length: float

    def inside_distance(self, xy: Array) -> Array:
        """Distance to the outline, positive inside."""
        pts = shapely.points(xy)
        d = shapely.distance(self.polygon.exterior, pts)
        return np.where(shapely.contains(self.polygon, pts), d, -d)

    def at(self, s: float) -> tuple[Array, Array]:
        """Point and unit tangent at arc length s."""
        p = np.asarray(self.polygon.exterior.interpolate(s % self.length).coords[0])
        q = np.asarray(
            self.polygon.exterior.interpolate((s + OUTLINE_STEP_MM) % self.length).coords[0]
        )
        t = q - p
        return p, t / np.linalg.norm(t)


def outline(mesh: trimesh.Trimesh) -> Outline:
    loop = igl.boundary_loop(np.asarray(mesh.faces, dtype=np.int64))
    if len(loop) < 3:
        raise CoverError("the cover has no hem (open bottom) to take the outline from")
    xy = np.asarray(mesh.vertices)[loop][:, :2]
    poly = shapely.Polygon(xy)
    if not poly.is_valid:
        poly = shapely.make_valid(poly)
        if poly.geom_type != "Polygon":
            poly = max(poly.geoms, key=lambda g: g.area)
    poly = shapely.geometry.polygon.orient(poly, 1.0)
    length = poly.exterior.length
    n = max(int(length / OUTLINE_STEP_MM), MIN_SAMPLES)
    s = np.linspace(0.0, length, n, endpoint=False)
    pts = np.array([poly.exterior.interpolate(x).coords[0] for x in s])
    return Outline(poly, pts, length)


def corners(line: Outline, angle_deg: float, window_mm: float) -> list[float]:
    """Arc-length positions where the outline turns sharply.

    Notches narrower than half the window (slat gaps reaching the edge of a table) are smoothed
    out first; the corners found are then placed on the real outline.
    """
    r = window_mm / 4
    smooth = line.polygon.buffer(r, join_style="round").buffer(-r, join_style="round")
    smooth = smooth.buffer(-r, join_style="round").buffer(r, join_style="round")
    if smooth.is_empty or smooth.geom_type != "Polygon":
        smooth = line.polygon
    smooth = shapely.geometry.polygon.orient(
        smooth, 1.0
    )  # counter-clockwise, as the heading assumes
    n0 = max(int(smooth.exterior.length / OUTLINE_STEP_MM), MIN_SAMPLES)
    p = np.array(
        [
            smooth.exterior.interpolate(x).coords[0]
            for x in np.linspace(0, smooth.exterior.length, n0, endpoint=False)
        ]
    )
    found_xy = _turns(p, angle_deg, window_mm, smooth.exterior.length)
    ext = line.polygon.exterior
    return sorted(float(ext.project(shapely.Point(q))) for q in found_xy)


def _turns(p: Array, angle_deg: float, window_mm: float, length: float) -> list[Array]:
    """Points of a closed polyline (sampled evenly) where it turns sharply."""
    n = len(p)
    t = np.roll(p, -1, axis=0) - p
    heading = np.unwrap(np.arctan2(t[:, 1], t[:, 0]))
    k = max(int(round(window_mm / 2 / OUTLINE_STEP_MM)), 1)
    # turning over the window centred on each sample (heading wraps by 2 pi around the loop)
    ext = np.concatenate([heading[-k:] - 2 * math.pi, heading, heading[:k] + 2 * math.pi])
    turn = np.abs(ext[2 * k :] - ext[:n])
    limit = math.radians(angle_deg)
    found: list[Array] = []
    order = np.argsort(-turn, kind="stable")
    taken = np.zeros(n, dtype=bool)
    for i in order:
        if turn[i] < limit:
            break
        if taken[i]:
            continue
        # the corner is the middle of the bend: where half of the turning over the window is
        # done (robust to small wiggles, and exactly symmetric for mirrored corners)
        seg = np.arange(i - k, i + k + 1)
        hd = ext[seg + k]  # unwrapped heading over the window
        cum = np.concatenate([[0.0], np.cumsum(np.diff(hd))])
        half = cum[-1] / 2
        j = int(np.clip(np.searchsorted(cum if half >= 0 else -cum, abs(half)), 1, len(cum) - 1))
        step = cum[j] - cum[j - 1]
        frac = (half - cum[j - 1]) / step if step != 0 else 0.0
        # the heading at sample m belongs to the segment from p[m] to p[m + 1]; its middle
        a = (p[seg[j - 1] % n] + p[(seg[j - 1] + 1) % n]) / 2
        b = (p[seg[j] % n] + p[(seg[j] + 1) % n]) / 2
        found.append(a + float(np.clip(frac, 0.0, 1.0)) * (b - a))
        taken[np.arange(i - 2 * k, i + 2 * k + 1) % n] = True
    del length
    return found


def split_positions(line: Outline, corner_s: list[float], max_panel_mm: float) -> list[float]:
    """Vertical seam positions: corners plus equal splits of long stretches."""
    cuts = list(corner_s)
    if not cuts:
        back = int(np.argmax(line.points[:, 1]))  # the rear of the cover
        cuts = [float(back * line.length / len(line.points))]
    cuts = sorted(cuts)
    out: list[float] = []
    for a, b in zip(cuts, cuts[1:] + [cuts[0] + line.length], strict=True):
        span = b - a
        parts = max(math.ceil(span / max_panel_mm), 1)
        out += [a + span * i / parts for i in range(parts)]
    return sorted(s % line.length for s in out)


def skirt_seam(line: Outline, inset_mm: float) -> Seam:
    """The seam between skirt and top: the level `inset_mm` inside the outline."""
    return Seam(
        id="skirt",
        kind="skirt",
        field=lambda p: line.inside_distance(p[:, :2]) - inset_mm,
        faces=lambda cut: np.ones(len(cut.mesh.faces), dtype=bool),
    )


def corner_seam(line: Outline, s: float, index: int, skirt_region: int, reach_mm: float) -> Seam:
    p0, t = line.at(s)

    def faces(cut: CutMesh) -> Mask:
        c = np.asarray(cut.mesh.triangles_center)
        near = np.linalg.norm(c[:, :2] - p0, axis=1) < reach_mm
        return near & (cut.region == skirt_region)

    return Seam(
        id=f"corner-{index + 1}",
        kind="corner",
        field=lambda q: (q[:, :2] - p0) @ t,
        faces=faces,
    )
