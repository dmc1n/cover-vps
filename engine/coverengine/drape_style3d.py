"""The drape with Newton's Style3D cloth solver (ADR-058, docs/plans/realistic-drape-engine.md).

Newton (NVIDIA, Disney Research, Google DeepMind; Linux Foundation, Apache 2.0) has a garment
solver, Style3D, that takes what `cover cut` and `cover flatten` give: the cover in 3D, sewn,
and every triangle's shape in its flat piece. Its fabric has stretch and bending per direction
(weft, warp, shear), so a woven fabric like Coverlast (the weft about half as strong as the warp)
behaves as such. The grain is not known before nesting; the long side of every piece is taken
along the warp (the roll's length), as the cutting table lays long pieces.

Same input and output as the own solver (`drape.run`): the frames of the fall (mm, Z up) and the
measures, so the playback, the rain, the heatmap and the audit stay as they are.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import trimesh
from numpy.typing import NDArray

from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
MM_PER_M = 1000.0  # param-ok: unit conversion
G_PER_KG = 1000.0  # param-ok: unit conversion
G = 9.81  # param-ok: gravity, m/s2


def _p(params: EffectiveParams, key: str) -> float:
    return float(params[key])  # type: ignore[arg-type]


def _mm(arr: Any, n: int) -> Any:
    """A Warp array of the first n particles, in mm."""
    assert arr is not None
    return arr.numpy()[:n].astype(np.float32) * MM_PER_M


def grain(flat: Array, piece: NDArray[np.int64], corners3d: Array) -> Array:
    """Every piece's flat corners turned so the warp (flat +y) runs along the furniture's
    length (3D x); on a piece across that (an end), along its depth (3D y). Mirror images then
    get mirrored grain, so a symmetric cover drapes symmetrically. The best-fitting linear map
    from the flat piece to 3D says which flat direction that is."""
    out = flat.copy()
    for k in np.unique(piece):
        sel = piece == k
        p2 = flat[sel].reshape(-1, 2)
        p3 = corners3d[sel].reshape(-1, 3)
        c2, c3 = p2.mean(axis=0), p3.mean(axis=0)
        jac, *_ = np.linalg.lstsq(p2 - c2, p3 - c3, rcond=None)  # (2, 3): flat -> 3D
        best = None
        for axis in (np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])):
            d = np.linalg.pinv(jac.T) @ axis  # the flat direction that goes along it in 3D
            reach = float(np.linalg.norm(jac.T @ d))
            if np.linalg.norm(d) > 0 and reach > ALONG:
                best = d / np.linalg.norm(d)
                break
        if best is None:  # a piece lying across both: its long side
            _, _, vt = np.linalg.svd(p2 - c2, full_matrices=False)
            best = vt[0]
        ang = np.arctan2(best[0], best[1])  # turn best onto (0, 1)
        r = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
        out[sel] = ((p2 - c2) @ r.T).reshape(-1, 3, 2)
    return out


ALONG = 0.5  # param-ok: the piece runs at least half along that 3D direction


def seam_hinges(faces: NDArray[np.int64], piece: NDArray[np.int64], hinges: Any) -> Any:
    """Which bending hinges (rows [o0, o1, v1, v2], v1-v2 the shared edge) lie on a seam: the
    two triangles at the edge belong to different pieces."""
    e = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    pc = np.tile(piece, 3)  # param-ok: three edges per triangle
    n = int(faces.max()) + 1
    key = e[:, 0].astype(np.int64) * n + e[:, 1]
    order = np.argsort(key, kind="stable")
    key, pc = key[order], pc[order]
    first = np.r_[True, key[1:] != key[:-1]]
    lo = np.minimum.reduceat(pc, np.flatnonzero(first))
    hi = np.maximum.reduceat(pc, np.flatnonzero(first))
    seam_keys = key[first][lo != hi]
    rows = np.asarray(hinges).reshape(-1, 4)  # param-ok: [o0, o1, v1, v2]
    h = np.sort(rows[:, 2:], axis=1).astype(np.int64)
    return np.isin(h[:, 0] * n + h[:, 1], seam_keys)


def run(
    c: Any, colliders: list[trimesh.Trimesh], params: EffectiveParams, log: Any = print
) -> tuple[list[Any], dict[str, Any]]:
    """The fall with Style3D: the frames (positions, mm) and how long it took."""
    import newton
    import warp as wp
    from newton.solvers import style3d

    wp.config.quiet = True
    wp.init()
    if c.flat is None:
        raise ValueError("the cloth has no flat pieces (drape.cloth makes them)")
    thick = _p(params, "drape.thickness_mm") / MM_PER_M
    builder = newton.ModelBuilder()
    newton.solvers.SolverStyle3D.register_custom_attributes(builder)
    flat = grain(c.flat, c.piece, c.x[c.faces]) / MM_PER_M
    n = len(c.x)
    normals = trimesh.Trimesh(c.x, c.faces, process=False).vertex_normals
    start = (c.x + normals * _p(params, "drape.thickness_mm")) / MM_PER_M
    style3d.add_cloth_mesh(
        builder,
        pos=wp.vec3(0.0, 0.0, 0.0),
        rot=wp.quat(0.0, 0.0, 0.0, 1.0),  # no turn
        vel=wp.vec3(0.0, 0.0, 0.0),
        vertices=start.tolist(),
        indices=c.faces.astype(int).ravel().tolist(),
        panel_verts=flat.reshape(-1, 2).tolist(),
        panel_indices=list(range(3 * len(c.faces))),  # param-ok: three corners per triangle
        density=_p(params, "drape.fabric_g_m2") / G_PER_KG,
        particle_radius=thick,
        tri_aniso_ke=wp.vec3(
            _p(params, "drape.style3d_stretch_weft"),
            _p(params, "drape.style3d_stretch_warp"),
            _p(params, "drape.style3d_stretch_shear"),
        ),
        edge_aniso_ke=wp.vec3(
            _p(params, "drape.style3d_bend_weft"),
            _p(params, "drape.style3d_bend_warp"),
            _p(params, "drape.style3d_bend_shear"),
        ),
    )
    for m in colliders:  # the furniture, the balloons, the chair space: fixed in place
        builder.add_shape_mesh(
            body=-1,
            mesh=newton.Mesh(
                np.asarray(m.vertices, np.float32) / MM_PER_M, np.asarray(m.faces, np.int32).ravel()
            ),
        )
    builder.add_ground_plane()
    model = builder.finalize()
    if str(params["drape.hem"]) == "held":  # the drawcord pulled tight: the hem stays (ADR-060)
        from coverengine.drape import hem_points

        flags = model.particle_flags.numpy() if model.particle_flags is not None else None
        if flags is not None:
            hem = hem_points(c, _p(params, "drape.hem_band_mm"))
            flags[hem] = flags[hem] & ~int(newton.ParticleFlags.ACTIVE)
            model.particle_flags = wp.array(flags, dtype=wp.int32)
            log(f"the hem held: {len(hem)} points")
    stiffer = _p(params, "drape.seam_bend_factor")
    if model.edge_bending_properties is not None and model.edge_indices is not None:
        # a sewn seam (two layers, the allowance folded over, the stitching) bends less easily
        on = seam_hinges(c.faces, c.piece, model.edge_indices.numpy())
        bend: Any = model.edge_bending_properties
        props = bend.numpy()
        props[on, 0] *= stiffer
        bend.assign(props)
        log(f"the seams {stiffer:g}x stiffer: {int(on.sum())} hinges")
    model.soft_contact_ke = _p(params, "drape.style3d_contact_ke")
    model.soft_contact_kd = _p(params, "drape.style3d_contact_kd")
    model.soft_contact_mu = _p(params, "drape.friction")
    model.set_gravity((0.0, 0.0, -G))
    solver = newton.solvers.SolverStyle3D(model=model, iterations=int(params["drape.iterations"]))
    s0, s1 = model.state(), model.state()
    control = model.control()
    pipeline = newton.CollisionPipeline(model)
    contacts = pipeline.contacts()

    fps = _p(params, "drape.steps_per_second")
    sub = int(params["drape.style3d_substeps"])
    dt = 1.0 / fps / sub
    steps = int(_p(params, "drape.seconds") * fps)
    settle = int(_p(params, "drape.settle_seconds") * fps)
    every = max(1, (steps + settle) // int(params["drape.frames"]))
    rest = _p(params, "drape.rest_mm_s") / MM_PER_M
    frames = [_mm(s0.particle_q, n)]
    log(f"Style3D: {n} points, {len(c.faces)} triangles, {steps} frames of {sub} substeps")
    # the fall, then (if it still moves) settling: the same physics with the speed damped every
    # frame, so the cover reaches the shape it keeps at rest instead of a moment in the fall
    keep = 1.0 - _p(params, "drape.settle_damping")
    step, speed, rested = 0, float("inf"), False
    for step in range(steps + settle):
        pipeline.collide(s0, contacts)
        for _ in range(sub):
            s0.clear_forces()
            solver.step(s0, s1, control, contacts, dt)
            s0, s1 = s1, s0
        if step >= steps and s0.particle_qd is not None:
            s0.particle_qd.assign(s0.particle_qd.numpy() * keep)
        if (step + 1) % every == 0:
            frames.append(_mm(s0.particle_q, n))
        speed = float(np.percentile(np.linalg.norm(_mm(s0.particle_qd, n), axis=1), 99))  # param-ok
        if step % 20 == 0:  # param-ok: a progress line every 20 frames
            phase = "settling" if step >= steps else "falling"
            log(f"  frame {step + 1}/{steps}, {phase}: 99 % slower than {speed:.0f} mm/s")
        if step > steps // 4 and speed < rest * MM_PER_M:  # param-ok: rests only after a quarter
            frames.append(_mm(s0.particle_q, n))
            rested = True
            break
    return frames, {
        "engine": "style3d",
        "steps": step + 1,
        "seconds_simulated": round((step + 1) / fps, 2),
        "settled_frames": max(0, step + 1 - steps),
        "at_rest": rested,
        "end_speed_mm_s": round(speed, 1),
    }
