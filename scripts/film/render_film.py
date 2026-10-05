"""The shop's welcome film (ADR-065): a real SUNS sofa on a terrace as a storm comes in; the
cover is laid over it and falls exactly as the Style3D simulation computed (drape.bin, in real
time); then the rain comes and beads off the Coverlast fabric. Path-traced with Blender Cycles.

Run inside Blender (4.2 LTS), for example in the Playwright image that has its X libraries:

    blender -b -P scripts/film/render_film.py -- --model DIR --hdri FILE --out DIR
        [--frames 1-300] [--size 1920x1080] [--samples 64] [--colour 3d4039] [--still 150]

DIR holds model.glb, drape.json and drape.bin of one model (cover drape, ADR-058). The frames
are written as PNG (resumable: existing frames are skipped); scripts/film/encode.sh makes the
MP4 and WebM. Everything is deterministic (seeded particles, fixed noise).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

FPS = 24
T_SOFA = 30  # the sofa alone, the storm coming
T_LOWER = 40  # the cover is laid over it (two people would take about this long)
T_FALL = 110  # the Style3D fall and settling, close to real time
T_HOLD = 20
T_RAIN = 130  # rain, the fabric getting wet, the water beading off
LAST = T_SOFA + T_LOWER + T_FALL + T_HOLD + T_RAIN


def args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--hdri", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frames", default=f"1-{LAST}")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--colour", default="3d4039")
    ap.add_argument("--still", type=int, default=0, help="render only this frame (a test)")
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])


def srgb(hexcol: str) -> tuple[float, float, float, float]:
    c = [int(hexcol[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (lin[0], lin[1], lin[2], 1.0)


def node(nt: bpy.types.NodeTree, kind: str, **props: object) -> bpy.types.Node:
    n = nt.nodes.new(kind)
    for k, v in props.items():
        if k.startswith("in_"):
            n.inputs[k[3:].replace("_", " ")].default_value = v
        else:
            setattr(n, k, v)
    return n


def key(target: object, path: str, frames_values: list[tuple[int, object]],
        interp: str = "BEZIER") -> None:  # fmt: skip
    """Keyframes on an object property, or on a node socket's value (path "")."""
    for f, v in frames_values:
        if isinstance(target, bpy.types.NodeSocket):
            target.default_value = v
            target.keyframe_insert("default_value", frame=f)
        else:
            setattr(target, path, v)
            target.keyframe_insert(path, frame=f)
    ad = getattr(target, "id_data", target).animation_data
    if ad and ad.action:
        for fc in ad.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = interp


# ---- materials ------------------------------------------------------------------------------
def upholstery() -> bpy.types.Material:
    m = bpy.data.materials.new("upholstery")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb("b9bab3")
    b.inputs["Roughness"].default_value = 0.9
    b.inputs["Sheen Weight"].default_value = 0.5
    tex = node(nt, "ShaderNodeTexNoise", in_Scale=900.0, in_Detail=2.0)
    bump = node(nt, "ShaderNodeBump", in_Strength=0.25, in_Distance=0.0005)
    nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def plinth() -> bpy.types.Material:
    m = bpy.data.materials.new("plinth")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = srgb("1c1c1c")
    b.inputs["Roughness"].default_value = 0.45
    b.inputs["Metallic"].default_value = 0.6
    return m


def coverlast(colour: str) -> bpy.types.Material:
    """Sunbrella Coverlast: a woven polyester with a coating: a fine weave, a soft sheen; wet,
    it darkens a little, turns glossy and the water stands on it in beads."""
    m = bpy.data.materials.new("coverlast")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    out = nt.nodes["Material Output"]
    coord = node(nt, "ShaderNodeTexCoord")
    wetv = node(nt, "ShaderNodeValue", name="wet", label="wet")
    wetv.outputs[0].default_value = 0.0
    # the weave: two fine sets of bands at right angles (about 1.2 mm, warp and weft)
    warp = node(nt, "ShaderNodeTexWave", wave_type="BANDS", bands_direction="X",
                in_Scale=420.0, in_Distortion=0.6)  # fmt: skip
    weft = node(nt, "ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y",
                in_Scale=420.0, in_Distortion=0.6)  # fmt: skip
    for t in (warp, weft):
        nt.links.new(coord.outputs["Object"], t.inputs["Vector"])
    weave = node(nt, "ShaderNodeMath", operation="MULTIPLY")
    nt.links.new(warp.outputs["Fac"], weave.inputs[0])
    nt.links.new(weft.outputs["Fac"], weave.inputs[1])
    # the beads: round drops scattered over the fabric, showing with the wet value
    vor2 = node(nt, "ShaderNodeTexVoronoi", in_Scale=120.0, in_Randomness=1.0)
    nt.links.new(coord.outputs["Object"], vor2.inputs["Vector"])
    drop = node(nt, "ShaderNodeMapRange", in_From_Min=0.12, in_From_Max=0.32, in_To_Min=1.0,
                in_To_Max=0.0)  # fmt: skip
    nt.links.new(vor2.outputs["Distance"], drop.inputs["Value"])
    beads = node(nt, "ShaderNodeMath", operation="MULTIPLY")
    nt.links.new(drop.outputs["Result"], beads.inputs[0])
    nt.links.new(wetv.outputs[0], beads.inputs[1])
    # height: the weave, plus the beads standing on it
    height = node(nt, "ShaderNodeMath", operation="ADD")
    nt.links.new(weave.outputs[0], height.inputs[0])
    big = node(nt, "ShaderNodeMath", operation="MULTIPLY", in_Value=6.0)
    big.inputs[1].default_value = 6.0
    nt.links.new(beads.outputs[0], big.inputs[0])
    nt.links.new(big.outputs[0], height.inputs[1])
    bump = node(nt, "ShaderNodeBump", in_Strength=0.6, in_Distance=0.0008)
    nt.links.new(height.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    # colour: a touch darker when wet; roughness: matt dry, glossy beads and film when wet
    dry_col = node(nt, "ShaderNodeRGB")
    dry_col.outputs[0].default_value = srgb(colour)
    darker = node(nt, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    darker.inputs[7].default_value = (0.78, 0.78, 0.8, 1.0)
    nt.links.new(wetv.outputs[0], darker.inputs[0])
    nt.links.new(dry_col.outputs[0], darker.inputs[6])
    nt.links.new(darker.outputs[2], b.inputs["Base Color"])
    rough = node(nt, "ShaderNodeMapRange", in_From_Min=0.0, in_From_Max=1.0, in_To_Min=0.78,
                 in_To_Max=0.42)  # fmt: skip
    nt.links.new(wetv.outputs[0], rough.inputs["Value"])
    rmix = node(nt, "ShaderNodeMath", operation="SUBTRACT", use_clamp=True)
    nt.links.new(rough.outputs["Result"], rmix.inputs[0])
    nt.links.new(beads.outputs[0], rmix.inputs[1])
    nt.links.new(rmix.outputs[0], b.inputs["Roughness"])
    b.inputs["Sheen Weight"].default_value = 0.35
    b.inputs["Sheen Roughness"].default_value = 0.4
    coat = node(nt, "ShaderNodeMath", operation="MULTIPLY")
    coat.inputs[1].default_value = 1.0
    nt.links.new(beads.outputs[0], coat.inputs[0])
    nt.links.new(coat.outputs[0], b.inputs["Coat Weight"])
    b.inputs["Coat Roughness"].default_value = 0.03
    nt.links.new(b.outputs[0], out.inputs["Surface"])
    return m


def decking() -> bpy.types.Material:
    """A terrace of hardwood boards (14 cm, small gaps), darker and glossier when wet."""
    m = bpy.data.materials.new("decking")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    wet = node(nt, "ShaderNodeValue", name="wet", label="wet")
    wet.outputs[0].default_value = 0.0
    coord = node(nt, "ShaderNodeTexCoord")
    brick = node(nt, "ShaderNodeTexBrick", offset=0.37, offset_frequency=1, squash=1.0,
                 squash_frequency=1, in_Scale=1.0, in_Mortar_Size=0.004,
                 in_Brick_Width=2.4, in_Row_Height=0.14)  # fmt: skip
    brick.inputs["Color1"].default_value = srgb("6e4b34")
    brick.inputs["Color2"].default_value = srgb("8a6447")
    brick.inputs["Mortar"].default_value = srgb("1a120c")
    nt.links.new(coord.outputs["Object"], brick.inputs["Vector"])
    grain = node(nt, "ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y",
                 in_Scale=55.0, in_Distortion=1.2, in_Detail=4.0)  # fmt: skip
    nt.links.new(coord.outputs["Object"], grain.inputs["Vector"])
    mix = node(nt, "ShaderNodeMix", data_type="RGBA", blend_type="OVERLAY")
    mix.inputs[0].default_value = 0.18
    nt.links.new(brick.outputs["Color"], mix.inputs[6])
    nt.links.new(grain.outputs["Color"], mix.inputs[7])
    wetdark = node(nt, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    wetdark.inputs[7].default_value = (0.55, 0.55, 0.55, 1.0)
    nt.links.new(wet.outputs[0], wetdark.inputs[0])
    nt.links.new(mix.outputs[2], wetdark.inputs[6])
    nt.links.new(wetdark.outputs[2], b.inputs["Base Color"])
    rough = node(nt, "ShaderNodeMapRange", in_To_Min=0.62, in_To_Max=0.12)
    nt.links.new(wet.outputs[0], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], b.inputs["Roughness"])
    bump = node(nt, "ShaderNodeBump", in_Strength=0.3)
    nt.links.new(brick.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def seam_ribs(mat: bpy.types.Material) -> bpy.types.NodeTree:
    """Geometry nodes: a soft rib of fabric (5 mm) along every sewn seam: the edges marked
    'seam'. It runs after the shape keys, so the seams fall with the cloth."""
    ng = bpy.data.node_groups.new("seam ribs", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gin, gout = node(ng, "NodeGroupInput"), node(ng, "NodeGroupOutput")
    attr = node(ng, "GeometryNodeInputNamedAttribute", data_type="FLOAT")
    attr.inputs["Name"].default_value = "seam"
    to_curve = node(ng, "GeometryNodeMeshToCurve")
    circle = node(ng, "GeometryNodeCurvePrimitiveCircle")
    circle.inputs["Resolution"].default_value = 6
    circle.inputs["Radius"].default_value = 0.0025
    tube = node(ng, "GeometryNodeCurveToMesh")
    setmat = node(ng, "GeometryNodeSetMaterial")
    setmat.inputs["Material"].default_value = mat
    join = node(ng, "GeometryNodeJoinGeometry")
    ng.links.new(gin.outputs[0], to_curve.inputs["Mesh"])
    ng.links.new(attr.outputs["Attribute"], to_curve.inputs["Selection"])
    ng.links.new(to_curve.outputs[0], tube.inputs["Curve"])
    ng.links.new(circle.outputs["Curve"], tube.inputs["Profile Curve"])
    ng.links.new(tube.outputs[0], setmat.inputs["Geometry"])
    ng.links.new(gin.outputs[0], join.inputs[0])
    ng.links.new(setmat.outputs[0], join.inputs[0])
    ng.links.new(join.outputs[0], gout.inputs[0])
    return ng


def water() -> bpy.types.Material:
    m = bpy.data.materials.new("raindrop")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.9, 0.93, 1.0, 1.0)
    b.inputs["Transmission Weight"].default_value = 0.85
    b.inputs["Roughness"].default_value = 0.05
    b.inputs["IOR"].default_value = 1.33
    b.inputs["Alpha"].default_value = 0.45
    b.inputs["Emission Color"].default_value = (0.8, 0.85, 0.95, 1.0)
    b.inputs["Emission Strength"].default_value = 0.08  # lit by the grey sky all round
    return m


# ---- the scene ------------------------------------------------------------------------------
def build(a: argparse.Namespace) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.frame_start, sc.frame_end = 1, LAST
    w, h = (int(x) for x in a.size.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = a.samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.cycles.seed = 7
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"

    # the sky and light of an approaching storm; it darkens when the rain comes
    world = bpy.data.worlds.new("storm")
    sc.world = world
    world.use_nodes = True
    wn = world.node_tree
    env = node(wn, "ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(a.hdri))
    mapping = node(wn, "ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(200))
    tc = node(wn, "ShaderNodeTexCoord")
    wn.links.new(tc.outputs["Generated"], mapping.inputs["Vector"])
    wn.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    bg = wn.nodes["Background"]
    wn.links.new(env.outputs["Color"], bg.inputs["Color"])
    rain_from = T_SOFA + T_LOWER + T_FALL + T_HOLD
    key(bg.inputs["Strength"], "", [(1, 1.0), (rain_from - 10, 1.0), (rain_from + 20, 0.62)])

    # the terrace
    bpy.ops.mesh.primitive_plane_add(size=14, location=(0, 0, 0))
    deck = bpy.context.object
    # the furniture: a real SUNS model (3D Warehouse), its own materials from the photo
    bpy.ops.import_scene.gltf(filepath=str(a.model / "model.glb"))
    up, base = upholstery(), plinth()
    for ob in list(bpy.context.selected_objects):
        if ob.type != "MESH":
            continue
        top = max((ob.matrix_world @ Vector(c)).z for c in ob.bound_box)
        ob.data.materials.clear()
        ob.data.materials.append(base if top < 0.11 else up)
        for p in ob.data.polygons:
            p.use_smooth = False

    # the cover: the Style3D fall, frame by frame, as absolute shape keys (real time)
    doc = json.loads((a.model / "drape.json").read_text())
    n = int(doc["points_per_frame"])
    lo, hi = (np.array(x) for x in doc["frame_box_mm"])
    raw = np.frombuffer((a.model / "drape.bin").read_bytes(), dtype=np.uint16)
    frames = raw.reshape(-1, n, 3).astype(np.float64) / 65535 * (hi - lo) + lo
    frames /= 1000.0  # mm → m (Z up, as Blender)
    faces = doc["faces"]
    me = bpy.data.meshes.new("cover")
    me.from_pydata(frames[0].tolist(), [], faces)
    me.update()
    cover = bpy.data.objects.new("cover", me)
    sc.collection.objects.link(cover)
    for p in me.polygons:
        p.use_smooth = True
    cover.shape_key_add(name="f0")
    for i in range(1, len(frames)):
        k = cover.shape_key_add(name=f"f{i}")
        k.data.foreach_set("co", frames[i].ravel().astype(np.float32))
    keys = me.shape_keys
    keys.use_relative = False
    t0 = T_SOFA + T_LOWER
    key(keys, "eval_time", [(t0, 0.0), (t0 + T_FALL, 10.0 * (len(frames) - 1))], "LINEAR")
    # before the fall: laid over the sofa from above, as two people would do it
    key(cover, "location", [(T_SOFA, (0.0, 0.0, 1.3)), (t0, (0.0, 0.0, 0.0))])
    key(cover, "hide_render", [(1, True), (T_SOFA, False)], "CONSTANT")
    mat, deck_mat = coverlast(a.colour), decking()
    me.materials.append(mat)
    seams = a.model / "seams.json"  # the edges where two pieces are sewn (from panels.npz)
    if seams.is_file():
        index = {tuple(sorted(e.vertices)): e.index for e in me.edges}
        flag = np.zeros(len(me.edges), np.float32)
        for u, v in json.loads(seams.read_text())["edges"]:
            i = index.get((min(u, v), max(u, v)))
            if i is not None:
                flag[i] = 1.0
        me.attributes.new("seam", "FLOAT", "EDGE").data.foreach_set("value", flag)
        cover.modifiers.new("seams", "NODES").node_group = seam_ribs(mat)
    sol = cover.modifiers.new("thickness", "SOLIDIFY")
    sol.thickness = 0.0012
    sol.offset = 1.0
    cover.modifiers.new("smooth", "SUBSURF").levels = 1
    cover.modifiers["smooth"].render_levels = 1
    deck.data.materials.append(deck_mat)
    for m in (mat, deck_mat):  # the cover and the deck get wet together
        key(m.node_tree.nodes["wet"].outputs[0], "", [(rain_from + 5, 0.0), (rain_from + 90, 1.0)])

    # the rain: drops falling at 7 m/s, stopped by the cover and the deck
    # a drop as the camera sees it at 1/48 s: a streak of about 14 cm
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.0016, segments=8, ring_count=6,
                                         location=(0, 0, -5))  # fmt: skip
    drop = bpy.context.object
    drop.scale = (1, 1, 45)
    drop.data.materials.append(water())
    bpy.ops.mesh.primitive_plane_add(size=5.0, location=(0.4, 0.2, 4.2))
    sky = bpy.context.object
    ps = sky.modifiers.new("rain", "PARTICLE_SYSTEM").particle_system
    st = ps.settings
    sky.show_instancer_for_render = False  # the drops show, the plane they come from does not
    st.count = 38000
    st.frame_start, st.frame_end = rain_from, LAST
    st.lifetime = 40
    st.normal_factor = 0.0
    st.object_align_factor = (0.2, 0.0, -7.0)
    st.effector_weights.gravity = 0.0
    st.render_type = "OBJECT"
    st.instance_object = drop
    st.particle_size = 1.0
    st.size_random = 0.3
    st.use_rotations = False
    ps.seed = 11
    for ob in (cover, deck):
        ob.modifiers.new("collision", "COLLISION")
        ob.collision.use_particle_kill = True

    # the camera: low and close, drifting slowly round the front corner
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 42
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 5.6
    cam = bpy.data.objects.new("cam", cam_data)
    sc.collection.objects.link(cam)
    sc.camera = cam
    target = bpy.data.objects.new("target", None)
    sc.collection.objects.link(target)
    target.location = (0.0, 0.0, 0.42)
    cam_data.dof.focus_object = target
    track = cam.constraints.new("TRACK_TO")
    track.target = target
    for f, ang, dist, z in ((1, -38, 3.7, 1.25), (LAST, -16, 3.3, 1.05)):
        r = math.radians(ang)
        cam.location = (dist * math.sin(r), -dist * math.cos(r), z)
        cam.keyframe_insert("location", frame=f)
    for fc in cam.animation_data.action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = "SINE"
            kp.easing = "EASE_IN_OUT"


def main() -> None:
    a = args()
    build(a)
    sc = bpy.context.scene
    a.out.mkdir(parents=True, exist_ok=True)
    sc.frame_set(1)
    bpy.ops.ptcache.bake_all(bake=True)  # the rain, computed through once (any frame can render)
    if a.still:
        sc.frame_set(a.still)
        sc.render.filepath = str(a.out / f"still-{a.still:04d}.png")
        bpy.ops.render.render(write_still=True)
        return
    first, last = (int(x) for x in a.frames.split("-"))
    for f in range(first, last + 1):
        path = a.out / f"frame-{f:04d}.png"
        if path.is_file():
            continue
        sc.frame_set(f)
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)


main()
