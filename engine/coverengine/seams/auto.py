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
from typing import Any

import igl
import numpy as np
import shapely
import trimesh
from numpy.typing import NDArray

from coverengine.errors import CoverError
from coverengine.seams.cut import CutMesh, Seam

Array = NDArray[np.float64]
Mask = NDArray[np.bool_]
IntArray = NDArray[np.int64]

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


def split_positions(
    line: Outline, corner_s: list[float], max_panel_mm: float, min_panel_mm: float = 0.0
) -> list[float]:
    """Vertical seam positions: corners plus equal splits of long stretches. Corners closer
    together than `min_panel_mm` get one seam (no strips a few cm wide)."""
    cuts = sorted(corner_s)
    while len(cuts) > 1:
        gaps = [(cuts[(i + 1) % len(cuts)] - cuts[i]) % line.length for i in range(len(cuts))]
        i = int(np.argmin(gaps))
        if gaps[i] >= min_panel_mm:
            break
        j = (i + 1) % len(cuts)
        mid = (cuts[i] + gaps[i] / 2) % line.length  # one seam half way between the two
        cuts = sorted([c for k, c in enumerate(cuts) if k not in (i, j)] + [mid])
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


# A corner seam cuts the skirt up to this many corner windows from its point on the outline.
CORNER_REACH = 3.0  # param-ok: geometric reach

# Rim profile: sampled along the outline this often, from points this far inside the rim (mm).
RIM_STEP_MM = 10.0  # param-ok: sampling
RIM_BAND_MM = 50.0  # param-ok: geometric reach
# Wall seam: cut this far past a wall's end, and only on the upright cover within this plan
# distance of the outline (mm).
WALL_END_MM = 30.0  # param-ok: geometric reach past a wall's end
# Past a wall's end the wall field rises this much per mm along the outline (a steep end).
WALL_END_SLOPE = 1.0  # param-ok: geometric shape of the wall ends
# A wall all round is left open over this length at its lowest point (mm).
WALL_GAP_MM = 50.0  # param-ok: geometric
# The wall field counts everything this far below the top edge line as wall (mm).
WALL_MASK_MM = 5.0  # param-ok: geometric tolerance
WALL_ZONE_MM = 10.0  # param-ok: geometric reach


def skirt_seam(z_mm: float) -> Seam:
    """The seam between skirt and top: a level line at height `z_mm` all round. A level line is
    smooth wherever the surface is not flat, so the skirt panels get straight edges."""
    return Seam(
        id="skirt",
        kind="skirt",
        field=lambda p: p[:, 2] - z_mm,
        faces=lambda cut: np.ones(len(cut.mesh.faces), dtype=bool),
    )


@dataclass
class RimProfile:
    """Height of the top edge along the outline: `height[i]` at arc length `at[i]`, a lower
    envelope smoothed over the smoothing length, so it never lies above the real edge."""

    at: Array
    height: Array
    length: float

    def __call__(self, xy: Array, ext: Any) -> Array:
        t = np.asarray(shapely.line_locate_point(ext, shapely.points(xy)))
        return np.asarray(np.interp(t, self.at, self.height, period=self.length))


def _wrap(a: Array, w: int) -> Array:
    return np.concatenate([a[-w:], a, a[:w]]) if w else a


def rim_profile(mesh: Any, line: Outline, inset_mm: float, smoothing_mm: float) -> RimProfile:
    """Along the outline (every RIM_STEP_MM), the top of the upright part: the highest point of
    the cover less than `inset_mm` inside the outline seen from above, where the top starts to
    round over.
    A running median over the smoothing length (outliers go, kinks stay), a short average, and
    lowered where that runs above the edge: a smooth line at or below the edge."""
    v = np.asarray(mesh.vertices)
    upright = line.inside_distance(v[:, :2]) < inset_mm  # still at the outline
    e = np.asarray(mesh.edges_unique)
    border = np.zeros(len(v), dtype=bool)  # upright points next to the rounding: the edge line
    cross = upright[e[:, 0]] != upright[e[:, 1]]
    border[e[cross].ravel()] = True
    border &= upright
    ext = line.polygon.exterior
    n = max(int(line.length / RIM_STEP_MM), 8)  # param-ok: fewest samples
    step = line.length / n
    s = np.asarray(shapely.line_locate_point(ext, shapely.points(v[border, :2])))
    bins = np.minimum((s / step).astype(np.int64), n - 1)
    z = v[border, 2]
    low = np.full(n, np.nan)
    order = np.argsort(bins, kind="stable")
    groups = np.split(order, np.flatnonzero(np.diff(bins[order])) + 1)
    for g in groups:
        if len(g):
            low[bins[g[0]]] = float(np.median(z[g]))
    ok = np.isfinite(low)
    if not ok.any():
        low[:] = float(v[:, 2].max())
        ok[:] = True
    idx = np.arange(n)
    low = np.interp(idx, idx[ok], low[ok], period=n)
    w = max(int(smoothing_mm / 2 / step), 1)
    wa = max(w // 2, 1)
    kernel = np.ones(2 * wa + 1) / (2 * wa + 1)

    def average(a: Array) -> Array:
        out: Array = np.convolve(_wrap(a, wa), kernel, mode="valid").astype(np.float64)
        return out

    def running(a: Array, fn: Any) -> Array:
        padded = _wrap(a, w)
        return np.array([fn(padded[i : i + 2 * w + 1]) for i in range(n)], dtype=np.float64)

    # the running median removes single low points (the wall a millimetre out of plumb) but
    # keeps real kinks of the edge; a short average then smooths the line, and where that runs
    # above the edge it is lowered by the largest overshoot nearby, itself averaged
    smooth = average(running(low, np.median))
    smooth = smooth - average(running(np.maximum(smooth - low, 0.0), np.max))
    height: Array = np.maximum(np.array(smooth, dtype=np.float64), float(v[:, 2].min()))
    at: Array = np.asarray((idx + 0.5) * step, dtype=np.float64)  # param-ok: bin centres
    return RimProfile(at, height, line.length)


def rim_seam(line: Outline, rim: RimProfile, below_mm: float) -> Seam:
    """The seam between skirt and top `below_mm` under the top edge (follow_rim)."""
    ext = line.polygon.exterior
    return Seam(
        id="skirt",
        kind="skirt",
        field=lambda p: p[:, 2] - (rim(p[:, :2], ext) - below_mm),
        faces=lambda cut: np.ones(len(cut.mesh.faces), dtype=bool),
    )


def wall_ranges(
    rim: RimProfile, level_z: float, wall_min_mm: float, min_length_mm: float
) -> list[tuple[float, float]]:
    """Arc-length ranges where the top edge stands more than `wall_min_mm` above the skirt seam
    over at least `min_length_mm`: there the upright part is a wall panel. An end may pass the
    outline's length; a wall all round is left open at its lowest point."""
    n = len(rim.at)
    step = rim.length / n
    tall = rim.height - level_z > wall_min_mm
    if tall.all():
        low = int(np.argmin(rim.height))
        gap = max(int(WALL_GAP_MM / step / 2), 1)
        tall[[(low + k) % n for k in range(-gap, gap + 1)]] = False
    if not tall.any():
        return []
    start = int(np.flatnonzero(~tall)[0])  # walk from a low point, so no range is split
    out, i = [], 0
    while i < n:
        if tall[(start + i) % n]:
            k = i
            while k < n and tall[(start + k) % n]:
                k += 1
            a = ((start + i) % n) * step
            if (k - i) * step >= min_length_mm:
                out.append((a, a + (k - i) * step))
            i = k
        else:
            i += 1
    return out


def _outside(t: Array, ranges: list[tuple[float, float]], length: float) -> Array:
    """Distance along the outline from t to the nearest range (0 inside one)."""
    best = np.full(len(t), np.inf)
    for a, b in ranges:
        d = (t - a) % length  # position after the range start
        span = b - a
        inside = d <= span
        gap = np.where(inside, 0.0, np.minimum(d - span, length - d))
        best = np.minimum(best, gap)
    return best


def wall_field(
    line: Outline, rim: RimProfile, inset_mm: float, ranges: list[tuple[float, float]]
) -> Any:
    """Positive on the top, negative on a wall. Along a wall's range, the wall is the upright
    part (less than `inset_mm` inside the outline, where the top edge rounds over) together with
    everything clearly below the top edge line, so a wall a millimetre out of plumb gives no
    zig-zag, and the top never reaches down onto the upright part (that would stop it lying
    flat). Past a range's end the field rises steeply, so the wall ends in a short upright
    line."""
    ext = line.polygon.exterior

    def field(p: Array) -> Array:
        t = np.asarray(shapely.line_locate_point(ext, shapely.points(p[:, :2])))
        edge = rim(p[:, :2], ext) - WALL_MASK_MM
        base = np.minimum(line.inside_distance(p[:, :2]) - inset_mm, p[:, 2] - edge)
        out: Array = base + _outside(t, ranges, line.length) * WALL_END_SLOPE
        return out

    return field


def wall_seam(
    line: Outline,
    rim: RimProfile,
    inset_mm: float,
    ranges: list[tuple[float, float]],
    top_region: int,
) -> Seam:
    """The seam between the top and the walls."""
    ext = line.polygon.exterior
    padded = [(a - WALL_END_MM, b + WALL_END_MM) for a, b in ranges]

    def faces(cut: CutMesh) -> Mask:
        c = np.asarray(cut.mesh.triangles_center)
        t = np.asarray(shapely.line_locate_point(ext, shapely.points(c[:, :2])))
        near = line.inside_distance(c[:, :2]) < WALL_ZONE_MM
        within = _outside(t, padded, line.length) == 0
        return near & (cut.region == top_region) & within

    return Seam(id="wall", kind="wall", field=wall_field(line, rim, inset_mm, ranges), faces=faces)


def corner_seam(line: Outline, s: float, index: int, skirt_region: int, reach_mm: float) -> Seam:
    """A vertical seam across the skirt at arc length s: the skirt faces on its plane, up to
    CORNER_REACH times `reach_mm` from the outline point (where the skirt climbs over a low,
    rounded corner it reaches further in than the window)."""
    p0, _ = line.at(s)
    # the direction of the outline across the corner (before to after), so at a sharp corner
    # the seam runs diagonally across it instead of along one side
    before, _ = line.at(s - reach_mm / 2)
    after, _ = line.at(s + reach_mm / 2)
    t = (after - before) / (float(np.linalg.norm(after - before)) or 1.0)

    def faces(cut: CutMesh) -> Mask:
        c = np.asarray(cut.mesh.triangles_center)
        near = np.linalg.norm(c[:, :2] - p0, axis=1) < reach_mm * CORNER_REACH
        on_plane = np.abs((c[:, :2] - p0) @ t) < reach_mm
        return near & on_plane & (cut.region == skirt_region)

    return Seam(
        id=f"corner-{index + 1}",
        kind="corner",
        field=lambda q: (q[:, :2] - p0) @ t,
        faces=faces,
    )
