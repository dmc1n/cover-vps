"""The cover going on, for the hero film (ADR-108): our sewn pieces lowered over the furniture by
the ridge, as two people put a cover on, with Blender's cloth solver; the rest of the film shows
the Style3D drape itself (drape.bin), and the shot blends into it as the cover comes to rest.

    blender -b -P scripts/film/hero_fall.py -- --data DIR [--frames 72]

DIR holds cover.npz and furniture.glb (scripts/film/hero_data.py); writes DIR/fall.npz with the
sewn points' positions per frame (metres, Z up).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import bpy
import numpy as np

LIFT_M = 0.3  # the cover starts this far above where it ends
RIDGE_M = 0.05  # the band under the highest line that the hands hold
TOP_HOLD = 0.12  # the top pieces are barely held: they settle under their own weight


def args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--frames", type=int, default=72)
    ap.add_argument("--lower", type=int, default=40, help="frames the lowering takes")
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])


def main() -> None:
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.render.fps = 1, a.frames, 24
    d = np.load(a.data / "cover.npz")
    weld, faces = d["weld"], d["weld_faces"]
    n = int(weld.max()) + 1
    pos = np.zeros((n, 3), np.float64)
    pos[weld] = d["design"]
    me = bpy.data.meshes.new("cloth")
    me.from_pydata(pos.tolist(), [], faces.tolist())
    me.validate()
    ob = bpy.data.objects.new("cloth", me)
    sc.collection.objects.link(ob)
    top = pos[:, 2].max()
    group = ob.vertex_groups.new(name="hands")
    # the hands hold the ridge and the top keeps its shape; the skirts hang from it, freer
    # towards the hem, so they swing a little and the hem settles last
    names = [str(x) for x in d["names"]] if "names" in d.files else []
    on_top = np.zeros(n, bool)
    for k, name in enumerate(names):
        if name.startswith("top"):
            on_top[weld[d["piece"] == k]] = True
    weight = np.where(on_top, TOP_HOLD, 0.0)
    weight[pos[:, 2] > top - RIDGE_M] = 1.0
    for i, w in enumerate(weight.tolist()):
        if w > 0:
            group.add([i], w, "REPLACE")
    ob.location.z = LIFT_M
    ob.keyframe_insert("location", frame=1)
    ob.location.z = 0.0
    ob.keyframe_insert("location", frame=a.lower)
    for fc in ob.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation, k.easing = "SINE", "EASE_IN_OUT"
    cl = ob.modifiers.new("cloth", "CLOTH")
    s = cl.settings
    s.quality = 10
    s.mass = 0.12  # kg per point: about the cover's 1.1 kg over the sewn points, made heavier
    s.tension_stiffness = s.compression_stiffness = 40
    s.shear_stiffness = 25
    s.bending_stiffness = 3.0  # a coated canvas: it folds easily, but in soft rolls
    s.air_damping = 3.0
    s.vertex_group_mass = "hands"
    s.pin_stiffness = 4.0
    cs = cl.collision_settings
    cs.distance_min = 0.005
    cs.collision_quality = 4
    cl.point_cache.frame_start, cl.point_cache.frame_end = 1, a.frames
    bpy.ops.import_scene.gltf(filepath=str(a.data / "furniture.glb"))
    for o in [o for o in bpy.context.selected_objects if o.type == "MESH"]:
        o.modifiers.new("collision", "COLLISION")
        o.collision.thickness_outer = 0.008
        o.collision.cloth_friction = 8.0
    out = np.zeros((a.frames, n, 3), np.float32)
    for f in range(1, a.frames + 1):
        sc.frame_set(f)
        ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        co = np.zeros(n * 3)
        ev.data.vertices.foreach_get("co", co)
        mw = np.array(ev.matrix_world)
        p = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
        out[f - 1] = p
        print("frame", f, "lowest", round(float(p[:, 2].min()), 3), flush=True)
    np.savez_compressed(a.data / "fall.npz", frames=out)


main()
