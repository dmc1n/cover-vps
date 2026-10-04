"""The drape simulation: the sewn cover falling over the furniture (ADR-056,
docs/plans/drape-simulation.md).

The owner, 2 October 2026: "a simulation where the cover really falls over the product ...
lifelike, where you also see folds where there is too much fabric".

The cut pieces keep their flat shapes: every triangle's rest shape comes from the flat pattern,
not from the designed 3D surface. The pieces are sewn along their seams, start where they lie
in the designed cover, and then the support is gone. Gravity, the fabric's stretch and bending
stiffness, and contact with the furniture, the balloons and the ground decide where the fabric
goes. Too much fabric folds; too little pulls tight.

Solver: projective dynamics (Bouaziz et al. 2014). Each step is a few rounds of a local step
(every triangle's stretch projected onto the allowed range, vectorised) and a global step
(one sparse linear solve with a matrix factorised once). Bending is the quadratic energy of
the flat rest shape (cotangent Laplacian), within each piece; a seam is a free hinge.
Contact projects points out of the furniture's distance field. Deterministic.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import igl
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla
import trimesh
from numpy.typing import NDArray

from coverengine.errors import CoverError
from coverengine.flatten.solve import flatten
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
IntArray = NDArray[np.int64]

DRAPE_JSON = "drape.json"
DRAPE_GLB = "drape.glb"
DRAPE_BIN = "drape.bin"  # the fall, frame by frame, for the 3D view
DRAPE_PNG = "drape.png"  # the cover as it lies next to the design, for the AI and the report
G = 9810.0  # param-ok: gravity, mm/s2
GRAMS_PER_KG = 1000.0  # param-ok: unit conversion
MM2_PER_M2 = 1e6  # param-ok: unit conversion
PERCENT = 100.0  # param-ok: ratio to percent
D3 = 3  # param-ok: three coordinates, three corners of a triangle
MM_PER_CM = 10.0  # param-ok: unit conversion
SETTLE_SHARE = 4  # param-ok: the cover may only rest after the first quarter of the time


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


@dataclass
class Cloth:
    x: Array  # start positions (n, 3)
    faces: IntArray  # (m, 3), welded over the seams
    piece: IntArray  # (m,) piece of every triangle
    rest_inv: Array  # (m, 2, 2) inverse of the rest edge matrix
    rest_area: Array  # (m,)
    names: list[str]
    bending: sp.csr_matrix  # (n, n) quadratic bending of the flat rest shape
    flat: Array | None = None  # (m, 3, 2) every triangle's corners in its flat piece (mm)


def cloth(model_dir: Path, params: EffectiveParams) -> Cloth:
    """The cut pieces as one sewn cloth: the pieces of `panels.npz` (cover cut), each with its
    flat shape as rest shape, the two sides of every seam welded into one."""
    npz = model_dir / "panels.npz"
    if not npz.is_file():
        raise CoverError(f"no pieces in {model_dir} (run cover cut first)")
    d = np.load(npz)
    v3, faces, labels, orig = d["vertices"], d["faces"], d["labels"], d["original_vertex"]
    names = [p["name"] for p in json.loads((model_dir / "panels.json").read_text())["panels"]]
    ids, weld = np.unique(orig, return_inverse=True)  # the seam's two sides: one point
    n = len(ids)
    x = np.zeros((n, D3))
    np.add.at(x, weld, v3)
    x /= np.bincount(weld, minlength=n)[:, None]
    all_faces, all_piece, inv, area, flats = [], [], [], [], []
    rows, cols, vals = [], [], []
    solver = str(params["flatten.solver"])
    iterations = int(params["flatten.iterations"])
    tolerance = _p(params, "flatten.slim_tolerance")
    for k in range(len(names)):
        f = faces[labels == k]
        used, local = np.unique(f, return_inverse=True)
        local = local.reshape(f.shape)
        mesh = trimesh.Trimesh(v3[used], local, process=False)
        flat = flatten(mesh, solver, iterations, tolerance)  # same vertices, same order
        uv = flat.uv
        e1 = uv[local[:, 1]] - uv[local[:, 0]]
        e2 = uv[local[:, 2]] - uv[local[:, 0]]
        dm = np.stack([e1, e2], axis=2)  # (t, 2, 2): columns are the rest edges
        det = dm[:, 0, 0] * dm[:, 1, 1] - dm[:, 0, 1] * dm[:, 1, 0]
        good = np.abs(det) > 1e-9  # param-ok: degenerate triangles carry no stretch
        inv.append(np.linalg.inv(dm[good]))
        area.append(np.abs(det[good]) / 2)
        all_faces.append(weld[used[local[good]]])
        all_piece.append(np.full(int(good.sum()), k))
        flats.append(uv[local[good]])
        # bending: the cotangent Laplacian of the flat piece, its inner points only
        lap = igl.cotmatrix(np.column_stack([uv, np.zeros(len(uv))]), local.astype(np.int32))
        mass = igl.massmatrix(
            np.column_stack([uv, np.zeros(len(uv))]),
            local.astype(np.int32),
            igl.MASSMATRIX_TYPE_VORONOI,
        )
        boundary = np.zeros(len(uv), bool)
        e = np.sort(np.concatenate([local[:, [0, 1]], local[:, [1, 2]], local[:, [2, 0]]]), axis=1)
        e, count = np.unique(e, axis=0, return_counts=True)
        boundary[e[count == 1].ravel()] = True  # an edge of one triangle only: the piece's edge
        inner = np.flatnonzero(~boundary)
        if len(inner):
            lap = sp.csr_matrix(lap)[inner]
            minv = sp.diags(1.0 / np.maximum(mass.diagonal()[inner], 1e-9))
            q = (lap.T @ minv @ lap).tocoo()
            g = weld[used]
            rows.append(g[q.row])
            cols.append(g[q.col])
            vals.append(q.data)
    bending = (
        sp.csr_matrix(
            (np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)
        )
        if vals
        else sp.csr_matrix((n, n))
    )
    return Cloth(
        x, np.vstack(all_faces), np.concatenate(all_piece), np.vstack(inv),
        np.concatenate(area), names, bending, np.vstack(flats),
    )  # fmt: skip


def sheet(x: Array, faces: IntArray, uv: Array) -> Cloth:
    """One piece as cloth: its 3D start, its triangles and its flat shape (for tests and for a
    single loose piece)."""
    e1, e2 = uv[faces[:, 1]] - uv[faces[:, 0]], uv[faces[:, 2]] - uv[faces[:, 0]]
    dm = np.stack([e1, e2], axis=2)
    det = dm[:, 0, 0] * dm[:, 1, 1] - dm[:, 0, 1] * dm[:, 1, 0]
    flat = np.column_stack([uv, np.zeros(len(uv))])
    lap = sp.csr_matrix(igl.cotmatrix(flat, faces.astype(np.int32)))
    mass = igl.massmatrix(flat, faces.astype(np.int32), igl.MASSMATRIX_TYPE_VORONOI)
    e = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    e, count = np.unique(e, axis=0, return_counts=True)
    inner = np.setdiff1d(np.arange(len(uv)), e[count == 1].ravel())
    minv = sp.diags(1.0 / np.maximum(mass.diagonal()[inner], 1e-9))  # param-ok: no zero area
    bending = (lap[inner].T @ minv @ lap[inner]).tocsr()
    return Cloth(x.copy(), faces, np.zeros(len(faces), np.int64), np.linalg.inv(dm),
                 np.abs(det) / 2, ["sheet"], bending, uv[faces])  # fmt: skip


TIGHTEST_PCT = 99  # param-ok: the measures leave out the odd 1 % (single triangles)
NEAR_EVERY = 8  # param-ok: steps between full checks of which points are near the furniture
NEAR_MM = 80.0  # param-ok: a point further than this cannot reach it within those steps
REFACTOR_SHARE = 0.002  # param-ok: the matrix is renewed when this share of the held points changed


def limit_stretch(f: Array, limit: float) -> Array:
    """Every triangle's deformation gradient (t, 3, 2) with its stretches held within 1 ± limit:
    F V diag(clamped / stretch) V^T, from the closed form of the 2 x 2 matrix F^T F (much faster
    than an SVD of every triangle)."""
    a = np.einsum("ti,ti->t", f[:, :, 0], f[:, :, 0])
    b = np.einsum("ti,ti->t", f[:, :, 0], f[:, :, 1])
    d = np.einsum("ti,ti->t", f[:, :, 1], f[:, :, 1])
    mid, rad = (a + d) / 2, np.sqrt(((a - d) / 2) ** 2 + b**2)
    s1 = np.sqrt(np.maximum(mid + rad, 0.0))
    s2 = np.sqrt(np.maximum(mid - rad, 0.0))
    theta = np.arctan2(2 * b, a - d) / 2
    c, s = np.cos(theta), np.sin(theta)
    floor = 1e-6  # param-ok: a collapsed triangle keeps its direction
    r1 = np.clip(s1, 1 - limit, 1 + limit) / np.maximum(s1, floor)
    r2 = np.clip(s2, 1 - limit, 1 + limit) / np.maximum(s2, floor)
    m = np.empty((len(f), 2, 2))
    m[:, 0, 0] = r1 * c * c + r2 * s * s
    m[:, 0, 1] = m[:, 1, 0] = (r1 - r2) * c * s
    m[:, 1, 1] = r1 * s * s + r2 * c * c
    return f @ m


def hem_points(c: Cloth, band_mm: float) -> NDArray[np.int64]:
    """The points of the open bottom edge: on an edge of one triangle only, and within band_mm
    of the lowest point. A tightened drawcord (and the elastics at the corners) hold them
    (ADR-060)."""
    e = np.sort(np.concatenate([c.faces[:, [0, 1]], c.faces[:, [1, 2]], c.faces[:, [2, 0]]]), 1)
    e, count = np.unique(e, axis=0, return_counts=True)
    edge = np.unique(e[count == 1].ravel())
    low = c.x[:, 2].min()
    return edge[c.x[edge, 2] < low + band_mm]


class Contact:
    """The furniture and the balloons as one surface. A point that has come closer than the
    fabric's thickness, or has gone through, is put back on the side it came from: the
    closest point on the surface plus the thickness towards where the point was before the
    step. Exact (closest points, no grid), so thin parts are not crossed."""

    def __init__(self, meshes: list[trimesh.Trimesh]):
        m = trimesh.util.concatenate(meshes)
        assert isinstance(m, trimesh.Trimesh)
        self.v = np.asarray(m.vertices, np.float64)
        self.f = np.asarray(m.faces, np.int32)
        self.tree = igl.AABB()  # built once, asked many times
        self.tree.init(self.v, self.f)

    def closest(self, p: Array) -> tuple[Array, Array]:
        d2, _, c = self.tree.squared_distance(self.v, self.f, np.asarray(p, np.float64))
        return np.sqrt(np.asarray(d2)), np.asarray(c)

    def project(
        self, y: Array, before: Array, thick: float, only: NDArray[np.bool_] | None = None
    ) -> tuple[Array, NDArray[np.bool_]]:
        if only is not None:  # only the points that can be near
            idx = np.flatnonzero(only)
            out_y, out_hit = y.copy(), np.zeros(len(y), bool)
            if len(idx):
                py, ph = self.project(y[idx], before[idx], thick)
                out_y[idx], out_hit[idx] = py, ph
            return out_y, out_hit
        dist, c = self.closest(y)
        out = before - c  # towards the side the point came from
        length = np.linalg.norm(out, axis=1)
        safe = length > 1e-9  # param-ok: a point exactly on the surface keeps its own side
        out[safe] /= length[safe, None]
        side = np.einsum("ij,ij->i", y - c, out)  # < 0: it went through
        hit = safe & (side < thick)
        y = y.copy()
        y[hit] = c[hit] + out[hit] * thick
        return y, hit


def _colliders(model_dir: Path) -> list[trimesh.Trimesh]:
    from coverengine.hull.build import balloon_meshes, chair_meshes
    from coverengine.io.model_io import load_model

    m = load_model(model_dir)
    out = [trimesh.Trimesh(m.vertices, m.faces, process=False)]
    hull = json.loads((model_dir / "hull.json").read_text(encoding="utf-8"))
    out += balloon_meshes(model_dir, hull)  # the balloons under a table cover hold it up too
    out += chair_meshes(hull)  # and the dining chairs beside it (the chair space)
    return out


def simulate(
    model_dir: Path, params: EffectiveParams, log: Any = print, use_ai: bool = True
) -> dict[str, Any]:
    t0 = time.time()
    c = cloth(model_dir, params)
    meshes = _colliders(model_dir)
    contact = Contact(meshes)
    if str(params["drape.engine"]) == "style3d":  # Newton's garment solver (ADR-058)
        from coverengine import drape_style3d

        frames, extra = drape_style3d.run(c, meshes, params, log)
        report = measures(c, frames[-1].astype(np.float64), contact, params)
        report.update(extra, points=len(c.x), triangles=int(len(c.faces)), frames=len(frames))
    else:
        frames, report = run(c, contact, params, log)
        report["engine"] = "own"
    report["run_s"] = round(time.time() - t0, 1)
    write(model_dir, c, frames, report)
    picture(model_dir, c, frames[-1])
    # then the rain on the cover as it lies (ADR-057): where water would collect
    from coverengine import rain

    log("rain on the draped cover ...")
    wet = rain.simulate(model_dir, params, use_ai=use_ai, surface="drape")
    report["wet"] = wet_summary(wet)
    if use_ai:
        report["ai"] = verdict(model_dir, report, params)
    doc = json.loads((model_dir / DRAPE_JSON).read_text(encoding="utf-8"))
    doc.update({k: report[k] for k in ("wet", "ai") if k in report})
    (model_dir / DRAPE_JSON).write_text(json.dumps(doc) + "\n", encoding="utf-8")
    return report


def wet_summary(wet: dict[str, Any]) -> dict[str, Any]:
    """The rain on the draped cover, in short (for drape.json, the audit and the AI)."""
    return {
        "ponds": len(wet["ponds"]),
        "pond_volume_l": wet["pond_volume_l"],
        "pond_area_m2": wet["pond_area_m2"],
        "deepest_mm": max((p["max_depth_mm"] for p in wet["ponds"]), default=0.0),
        "flat_area_m2": wet["flat_area_m2"],
        "growing_ponds": wet["growing_ponds"],
        "dry": wet["dry"],
        **wet.get("heat", {}),
        "ai": (wet.get("ai") or {}).get("verdict"),
    }


def run(
    c: Cloth, contact: Contact, params: EffectiveParams, log: Any = print
) -> tuple[list[Any], dict[str, Any]]:
    """The fall itself: the frames (positions) and the measures of where the cloth lies."""
    n = len(c.x)
    h = 1.0 / _p(params, "drape.steps_per_second")
    seconds = _p(params, "drape.seconds")
    rounds = int(params["drape.iterations"])
    stretch_w = _p(params, "drape.stretch_stiffness")
    bend_w = _p(params, "drape.bending_stiffness")
    limit = _p(params, "drape.max_stretch_pct") / PERCENT
    thick = _p(params, "drape.thickness_mm")
    friction = _p(params, "drape.friction")
    damping = _p(params, "drape.damping")
    weight = _p(params, "drape.fabric_g_m2") / GRAMS_PER_KG / MM2_PER_M2  # kg/mm2
    frames_wanted = int(params["drape.frames"])
    rest_speed = _p(params, "drape.rest_mm_s")

    # lumped masses
    mass = np.zeros(n)
    np.add.at(mass, c.faces.ravel(), np.repeat(c.rest_area * weight / D3, D3))
    mass = np.maximum(mass, 1e-12)  # param-ok: no zero masses
    # the global matrix: M/h^2 + stretch + bending
    cu = np.zeros((len(c.faces), D3, 2))  # how each corner enters the deformation gradient
    cu[:, 1] = c.rest_inv[:, 0, :]
    cu[:, 2] = c.rest_inv[:, 1, :]
    cu[:, 0] = -(cu[:, 1] + cu[:, 2])
    wa = stretch_w * c.rest_area
    r = np.repeat(c.faces, D3, axis=1).ravel()
    cc = np.tile(c.faces, (1, D3)).ravel()
    k = np.einsum("tad,tbd->tab", cu, cu) * wa[:, None, None]
    lhs = sp.csr_matrix((k.ravel(), (r, cc)), shape=(n, n))
    base = (lhs + sp.diags(mass / h**2) + bend_w * c.bending).tocsr()
    hold_w = _p(params, "drape.contact_stiffness")
    solve = spla.splu(base.tocsc()).solve  # x, y and z in one call
    factored_for = np.zeros(len(c.x), bool)  # the held points the factorisation is for
    near = np.ones(len(c.x), bool)

    x = c.x.copy()
    # start just outside the designed surface: the cover slipped on
    normals = trimesh.Trimesh(x, c.faces, process=False).vertex_normals
    x += normals * thick
    held_hem = np.zeros(n, bool)  # the drawcord pulled tight: the hem stays (ADR-060)
    if str(params["drape.hem"]) == "held":
        held_hem[hem_points(c, _p(params, "drape.hem_band_mm"))] = True
    hem_at = x.copy()
    v = np.zeros_like(x)
    gravity = np.array([0.0, 0.0, -G])
    steps = int(seconds / h)
    every = max(1, steps // frames_wanted)
    frames = [x.astype(np.float32)]
    log(f"{n} points, {len(c.faces)} triangles, {steps} steps")
    for step in range(steps):
        s = x + h * v + h * h * gravity
        y = s.copy()
        held = np.zeros(n, bool)  # points held by the furniture or the ground this step
        target = x.copy()  # a held point that is not touching this step stays where it was
        for k in range(rounds):
            # contact: where a point would go through or come too close, it is held on the
            # surface, on the side it came from (a constraint in the solve, not a push after)
            if k == 0 and step % NEAR_EVERY == 0:  # which points are near anything at all
                far, _ = contact.closest(y)
                near = far < NEAR_MM
            if k == 0 or k == rounds - 1:  # contacts at the start and the end of the rounds
                t, hit = contact.project(y, x, thick, near)
                low = t[:, 2] < thick
                t[low, 2] = thick
                hit |= low
                t[held_hem] = hem_at[held_hem]
                hit |= held_hem
            if k == 0:  # the held points, once a step; the matrix only when they changed
                changed = int((hit != factored_for).sum())
                if changed > REFACTOR_SHARE * n:
                    solve = spla.splu((base + sp.diags(np.where(hit, hold_w, 0.0))).tocsc()).solve
                    factored_for = hit.copy()
            target[factored_for & hit] = t[factored_for & hit]
            # local: every triangle's deformation gradient, its stretch limited
            ds = np.stack([y[c.faces[:, 1]] - y[c.faces[:, 0]],
                           y[c.faces[:, 2]] - y[c.faces[:, 0]]], axis=2)  # fmt: skip
            f = ds @ c.rest_inv  # (t, 3, 2)
            p = limit_stretch(f, limit)  # (t, 3, 2)
            rhs = (mass / h**2)[:, None] * s + np.where(factored_for, hold_w, 0.0)[:, None] * target
            contrib = np.einsum("tid,tad->tai", p, cu) * wa[:, None, None]  # (t, 3 corners, 3)
            np.add.at(rhs, c.faces.ravel(), contrib.reshape(-1, D3))
            y = solve(rhs)
        # what still lies too deep after the rounds is put on the surface
        y, hit = contact.project(y, x, thick, near)
        y[held_hem] = hem_at[held_hem]
        y[:, 2] = np.maximum(y[:, 2], thick)
        touching = held | hit
        # a point held by the furniture this step but pulled away by the fabric is released
        # next step (the hold is renewed only where the point still presses on the surface)
        nv = (y - x) / h
        nv[touching] *= 1 - friction  # friction where it lies on something
        nv *= 1 - damping
        x, v = y, nv
        if (step + 1) % every == 0:
            frames.append(x.astype(np.float32))
        speed = float(np.percentile(np.linalg.norm(v, axis=1), 99))  # param-ok: the fastest 1 %
        if step % 20 == 0:  # param-ok: progress line every 20 steps
            log(f"  step {step + 1}/{steps}: 99 % of the cloth slower than {speed:.0f} mm/s")
        if step > steps // SETTLE_SHARE and speed < rest_speed:  # it lies still
            frames.append(x.astype(np.float32))
            break
    report = measures(c, x, contact, params)
    report.update(
        seconds_simulated=round((step + 1) * h, 2), steps=step + 1, points=n,
        triangles=int(len(c.faces)), frames=len(frames),
    )  # fmt: skip
    return frames, report


def measures(c: Cloth, x: Array, contact: Contact, params: EffectiveParams) -> dict[str, Any]:
    """Folds (where the fabric bends sharply: too much fabric), tension (where it is stretched
    to its limit: too little), the sag below the designed surface and the gap to the furniture."""
    mesh = trimesh.Trimesh(x, c.faces, process=False)
    # folds: the bending of every point, from the angle between neighbouring triangles
    angles = mesh.face_adjacency_angles
    same_piece = c.piece[mesh.face_adjacency[:, 0]] == c.piece[mesh.face_adjacency[:, 1]]
    fold_v = np.zeros(len(x))
    edges = mesh.face_adjacency_edges[same_piece]
    np.maximum.at(fold_v, edges[:, 0], angles[same_piece])
    np.maximum.at(fold_v, edges[:, 1], angles[same_piece])
    fold_deg = np.degrees(fold_v)
    folds = fold_deg > _p(params, "drape.fold_deg")
    # tension: the stretch of every triangle
    ds = np.stack([x[c.faces[:, 1]] - x[c.faces[:, 0]], x[c.faces[:, 2]] - x[c.faces[:, 0]]], 2)
    sig = np.linalg.svd(ds @ c.rest_inv, compute_uv=False)
    stretch = (sig[:, 0] - 1) * PERCENT
    sag = c.x[:, 2] - x[:, 2]
    dist, _ = contact.closest(x)
    area = mesh.area_faces
    fold_area = float(area[folds[c.faces].any(axis=1)].sum()) / MM2_PER_M2
    return {
        "fold_area_m2": round(fold_area, 3),  # param-ok: decimals
        "fold_share_pct": round(PERCENT * fold_area * MM2_PER_M2 / float(area.sum()), 1),
        "max_fold_deg": round(float(np.percentile(fold_deg, TIGHTEST_PCT)), 1),
        "max_stretch_pct": round(
            float(np.percentile(stretch, TIGHTEST_PCT)), 2
        ),  # the tightest 1 %
        "tight_share_pct": round(
            PERCENT
            * float(area[stretch > 0.8 * _p(params, "drape.max_stretch_pct")].sum())
            / float(area.sum()),
            1,
        ),  # fmt: skip
        "max_sag_mm": round(float(sag.max()), 1),
        "touching_share_pct": round(
            PERCENT * float((dist < 2 * _p(params, "drape.thickness_mm")).mean()), 1
        ),
        "_fold_deg": fold_deg,
        "_stretch_pct": stretch,
    }


def write(model_dir: Path, c: Cloth, frames: list[Any], report: dict[str, Any]) -> None:
    fold = report.pop("_fold_deg")
    report.pop("_stretch_pct")
    final = frames[-1].astype(np.float64)
    # the cover as it lies, coloured by its folds (sand where it folds, grey-green elsewhere)
    t = np.clip(fold / 60.0, 0, 1)[:, None]  # param-ok: 60 degrees is a full fold colour
    base = np.array([133, 136, 111, 255.0])  # param-ok: house sage
    hot = np.array([178, 64, 44, 255.0])  # param-ok: house red
    colours = (base * (1 - t) + hot * t).astype(np.uint8)
    from coverengine.io.model_io import glb_bytes, linear_colours

    m = trimesh.Trimesh(final, c.faces, vertex_colors=linear_colours(colours), process=False)
    (model_dir / DRAPE_GLB).write_bytes(glb_bytes([("drape", m)]))
    # the fall: every frame's points as 16-bit numbers inside the box of all frames
    allp = np.stack(frames)
    lo, hi = allp.min(axis=(0, 1)), allp.max(axis=(0, 1))
    q = np.round((allp - lo) / np.maximum(hi - lo, 1e-6) * 65535).astype(np.uint16)  # param-ok
    (model_dir / DRAPE_BIN).write_bytes(q.tobytes())
    doc = {
        **report,
        "faces": c.faces.astype(int).tolist(),
        "frame_box_mm": [lo.round(2).tolist(), hi.round(2).tolist()],
        "points_per_frame": int(len(final)),
    }
    (model_dir / DRAPE_JSON).write_text(json.dumps(doc) + "\n", encoding="utf-8")


PICTURE_IN = (15.0, 5.4)  # param-ok: picture size (inches)
FRONT_AZ = -60  # param-ok: the camera's turn for the front view (degrees)


def picture(model_dir: Path, c: Cloth, final: Any) -> Path:
    """drape.png: the cover as it lies (folds in red) from two sides, next to the design."""
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    from coverengine.io.model_io import load_model

    x = np.asarray(final, np.float64)
    designed = load_model(model_dir / "hull.glb")
    light = np.array([0.3, -0.6, 0.75]) / np.linalg.norm([0.3, -0.6, 0.75])
    fold = measures_fold(c, x)
    lo, hi = x.min(axis=0), x.max(axis=0)
    mid, r = (lo + hi) / 2, float((hi - lo).max()) / 2
    fig = Figure(figsize=PICTURE_IN)
    views = [("draped, from the front", x, c.faces, fold, FRONT_AZ),
             ("designed", None, None, None, FRONT_AZ),
             ("draped, from the back", x, c.faces, fold, FRONT_AZ + 180)]  # fmt: skip
    for i, (title, v, f, hot, az) in enumerate(views):
        ax = fig.add_subplot(1, 3, i + 1, projection="3d")
        if v is None or f is None:
            v, f = np.asarray(designed.vertices), np.asarray(designed.faces)
        tri = v[f]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-9  # param-ok
        shade = (0.35 + 0.65 * np.abs(n @ light))[:, None]  # param-ok: lighting
        base = np.tile([0.52, 0.53, 0.44], (len(f), 1))  # param-ok: house sage
        if hot is not None:
            t = np.clip(hot[f].max(axis=1) / 60.0, 0, 1)[:, None]  # param-ok: full red at 60 deg
            base = base * (1 - t) + np.array([0.70, 0.25, 0.17]) * t  # param-ok: house red
        ax.add_collection3d(Poly3DCollection(tri, facecolors=np.clip(base * shade, 0, 1),
                                             edgecolor="none"))  # fmt: skip
        ax.set_xlim(mid[0] - r, mid[0] + r)
        ax.set_ylim(mid[1] - r, mid[1] + r)
        ax.set_zlim(0, 2 * r)
        ax.view_init(22, az)  # param-ok: view
        ax.set_axis_off()
        ax.set_title(title)
    fig.tight_layout()
    out = model_dir / DRAPE_PNG
    fig.savefig(out, dpi=80)  # param-ok: picture resolution
    return out


def measures_fold(c: Cloth, x: Array) -> Array:
    """How sharply the cloth bends at every point (degrees), within the pieces."""
    mesh = trimesh.Trimesh(x, c.faces, process=False)
    same = c.piece[mesh.face_adjacency[:, 0]] == c.piece[mesh.face_adjacency[:, 1]]
    fold = np.zeros(len(x))
    edges = mesh.face_adjacency_edges[same]
    np.maximum.at(fold, edges[:, 0], mesh.face_adjacency_angles[same])
    np.maximum.at(fold, edges[:, 1], mesh.face_adjacency_angles[same])
    return np.degrees(fold)


AI_SYSTEM = """You judge a simulated outdoor furniture cover for a workshop. The cut pieces were
sewn virtually and dropped over the furniture under gravity: the picture shows the cover as it
lies (red where the fabric folds sharply), from the front and from the back, next to the designed
shape. You also get the numbers: the share of the cover in folds, the tightest stretch, how far
the top sags below the design (where nothing holds it), and how much of it lies on the
furniture. A good cover lies smooth and taut, with few folds; folds mean a piece has more
fabric than the shape needs; a deep sag on top means water may stand there (water must always
run off). The fabric values are estimates, so judge places and shapes more than exact sizes.
Answer with JSON only:
{"verdict": "good" | "doubt" | "wrong", "summary": "one or two plain sentences",
 "problems": ["where, what and why, short"], "advice": ["what to change in the pattern"]}"""


def verdict(model_dir: Path, report: dict[str, Any], params: EffectiveParams) -> dict[str, Any]:
    """DeepSeek's opinion on the drape: the picture and the numbers."""
    import base64

    from coverengine.ai import ask_parts, lessons_text

    facts = {k: v for k, v in report.items() if not k.startswith("_") and k != "ai"}
    png = base64.b64encode((model_dir / DRAPE_PNG).read_bytes()).decode()
    parts: list[dict[str, Any]] = [
        {"type": "text", "text": json.dumps(facts)},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png}"}},
    ]
    try:
        ans = ask_parts(params, AI_SYSTEM + lessons_text("all"), parts)
    except Exception as exc:  # noqa: BLE001 - the AI is a second opinion
        return {"error": str(exc)}
    return {
        "model": str(params["ai.model"]),
        "verdict": str(ans.get("verdict", "")),
        "summary": str(ans.get("summary", "")),
        "problems": [str(p) for p in ans.get("problems", [])],
        "advice": [str(a) for a in ans.get("advice", [])],
    }


def summary(report: dict[str, Any]) -> str:
    w = report.get("wet") or {}
    rain = (
        f"; rain: {w['ponds']} pond(s), {w['pond_volume_l']} l, {w['flat_area_m2']} m2 flat"
        if w
        else ""
    )
    return rain_free(report) + rain


def rain_free(report: dict[str, Any]) -> str:
    return (
        f"{report['points']} points, {report['seconds_simulated']} s simulated in "
        f"{report['run_s']} s; folds on {report['fold_area_m2']} m2 "
        f"({report['fold_share_pct']} %), max stretch {report['max_stretch_pct']} %, "
        f"sag up to {report['max_sag_mm'] / MM_PER_CM:.1f} cm, "
        f"touching {report['touching_share_pct']} %"
    )
