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


def grain(flat: Array, piece: NDArray[np.int64]) -> Array:
    """Every piece's flat corners turned so its long side runs along y (the warp)."""
    out = flat.copy()
    for k in np.unique(piece):
        sel = piece == k
        pts = flat[sel].reshape(-1, 2)
        c = pts.mean(axis=0)
        _, _, vt = np.linalg.svd(pts - c, full_matrices=False)
        long_axis = vt[0]
        # rotate long_axis onto (0, 1)
        ang = np.arctan2(long_axis[0], long_axis[1])
        r = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
        out[sel] = ((flat[sel].reshape(-1, 2) - c) @ r.T).reshape(-1, 3, 2)
    return out


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
    flat = grain(c.flat, c.piece) / MM_PER_M
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
    every = max(1, steps // int(params["drape.frames"]))
    rest = _p(params, "drape.rest_mm_s") / MM_PER_M
    frames = [_mm(s0.particle_q, n)]
    log(f"Style3D: {n} points, {len(c.faces)} triangles, {steps} frames of {sub} substeps")
    step = 0
    for step in range(steps):
        pipeline.collide(s0, contacts)
        for _ in range(sub):
            s0.clear_forces()
            solver.step(s0, s1, control, contacts, dt)
            s0, s1 = s1, s0
        if (step + 1) % every == 0:
            frames.append(_mm(s0.particle_q, n))
        speed = float(np.percentile(np.linalg.norm(_mm(s0.particle_qd, n), axis=1), 99))  # param-ok
        if step % 20 == 0:  # param-ok: a progress line every 20 frames
            log(f"  frame {step + 1}/{steps}: 99 % slower than {speed:.0f} mm/s")
        if step > steps // 4 and speed < rest * MM_PER_M:  # param-ok: rests only after a quarter
            frames.append(_mm(s0.particle_q, n))
            break
    return frames, {
        "engine": "style3d",
        "steps": step + 1,
        "seconds_simulated": round((step + 1) / fps, 2),
    }
