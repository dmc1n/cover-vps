"""The website's story, rendered (ADR-071): the six chapters as photoreal frames, from our own data.

The same shapes the live 3D used (coverengine/story.py): the cover as designed in its pieces,
every piece flat with its true lengths, the cover as Style3D drapes it; now in Blender Cycles: a
real SUNS sofa, the sand Coverlast cover with its weave and seams, a white cutting table with
the fabric, soft studio light on the S2DIO off-white, and rain. The page scrolls through the
frames (Apple-style). Run with scripts/film/gpu_render.py on GPUs, or locally:

    blender -b -P scripts/film/render_story.py -- --data DIR --out DIR [--frames 1-240]
        [--size 1600x900] [--samples 64] [--gpu]

DIR: story.json, story.bin, furniture.glb (/api/shop/story/...), studio.hdr.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np

CH = 40  # frames per chapter
LAST = 6 * CH
SAND = "b39a6e"  # the cover (the owner, 5 Oct: our covers are sand)
PIECES = ["c2a77a", "b0956a", "cdb68c", "a68c62", "bba27a", "d2bf98", "9c8460"]
SEAM = "6b5434"  # the piping: a darker sand, so every seam reads
DARK = "3c443c"  # S2DIO dark green: the rain chapter's backdrop
OFFWHITE = "f1f2f2"  # S2DIO off white
TABLE_Z = 0.82  # the cutting table's top (m)
PLINTH_M = 0.11  # the sofa's dark base: its lowest 11 cm


def args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frames", default=f"1-{LAST}")
    ap.add_argument("--size", default="1600x900")
    ap.add_argument("--samples", type=int, default=64)
    ap.add_argument("--gpu", action="store_true")
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])


def lin(hexcol: str) -> tuple[float, float, float, float]:
    c = [int(hexcol[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    v = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (v[0], v[1], v[2], 1.0)


def node(nt, kind, **kw):
    n = nt.nodes.new(kind)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def keys(target, path, pairs, interp="BEZIER"):
    for f, v in pairs:
        if hasattr(target, "default_value") and path == "":
            target.default_value = v
            target.keyframe_insert("default_value", frame=f)
        else:
            setattr(target, path, v)
            target.keyframe_insert(path, frame=f)
    ad = getattr(target, "id_data", target).animation_data
    for fc in ad.action.fcurves if ad and ad.action else []:
        for kp in fc.keyframe_points:
            kp.interpolation = interp
            kp.easing = "EASE_IN_OUT"


# ---- the data -----------------------------------------------------------------------------
def story(data: Path) -> dict:
    meta = json.loads((data / "story.json").read_text())
    blob = (data / "story.bin").read_bytes()
    n, m = meta["points"], meta["triangles"]
    at = 0

    def f32(k):
        nonlocal at
        a = np.frombuffer(blob, "<f4", k, at).reshape(-1, 3).astype(np.float64)
        at += k * 4
        return a

    design, flat, drape = f32(n * 3), f32(n * 3), f32(n * 3)
    piece = np.frombuffer(blob, np.uint8, n, at).astype(int)
    at += n
    faces = np.frombuffer(blob[at : at + m * 12], "<u4").reshape(-1, 3).astype(int)

    def z_up(v):  # the viewer's Y up back to Blender's Z up
        return np.column_stack([v[:, 0], -v[:, 2], v[:, 1]])

    return {"design": z_up(design), "flat": z_up(flat), "drape": z_up(drape), "piece": piece,
            "faces": faces, "meta": meta}  # fmt: skip


# ---- materials ----------------------------------------------------------------------------
def fabric(name: str, by_piece: bool) -> bpy.types.Material:
    """Coverlast: a fine weave, a soft sheen; per piece a sand tone that becomes one sand
    (`unify`); wet: a little darker and glossy, the water beading (`wet`)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = node(nt, "ShaderNodeTexCoord")
    unify = node(nt, "ShaderNodeValue", name="unify", label="unify")
    wet = node(nt, "ShaderNodeValue", name="wet", label="wet")
    base = node(nt, "ShaderNodeRGB")
    base.outputs[0].default_value = lin(SAND)
    col = base.outputs[0]
    if by_piece:
        attr = node(nt, "ShaderNodeAttribute", attribute_name="piece_colour")
        mix = node(nt, "ShaderNodeMix", data_type="RGBA")
        nt.links.new(unify.outputs[0], mix.inputs[0])
        nt.links.new(attr.outputs["Color"], mix.inputs[6])
        nt.links.new(base.outputs[0], mix.inputs[7])
        col = mix.outputs[2]
    darker = node(nt, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    darker.inputs[7].default_value = (0.8, 0.78, 0.74, 1)
    nt.links.new(wet.outputs[0], darker.inputs[0])
    nt.links.new(col, darker.inputs[6])
    nt.links.new(darker.outputs[2], b.inputs["Base Color"])
    warp = node(nt, "ShaderNodeTexWave", wave_type="BANDS", bands_direction="X")
    weft = node(nt, "ShaderNodeTexWave", wave_type="BANDS", bands_direction="Y")
    for t in (warp, weft):
        t.inputs["Scale"].default_value = 520.0
        t.inputs["Distortion"].default_value = 0.5
        nt.links.new(tc.outputs["Object"], t.inputs["Vector"])
    weave = node(nt, "ShaderNodeMath", operation="MULTIPLY")
    nt.links.new(warp.outputs["Fac"], weave.inputs[0])
    nt.links.new(weft.outputs["Fac"], weave.inputs[1])
    beads = node(nt, "ShaderNodeTexVoronoi")
    beads.inputs["Scale"].default_value = 140.0
    nt.links.new(tc.outputs["Object"], beads.inputs["Vector"])
    drop = node(nt, "ShaderNodeMapRange")
    drop.inputs["From Min"].default_value, drop.inputs["From Max"].default_value = 0.1, 0.3
    drop.inputs["To Min"].default_value, drop.inputs["To Max"].default_value = 1.0, 0.0
    nt.links.new(beads.outputs["Distance"], drop.inputs["Value"])
    wetbead = node(nt, "ShaderNodeMath", operation="MULTIPLY")
    nt.links.new(drop.outputs["Result"], wetbead.inputs[0])
    nt.links.new(wet.outputs[0], wetbead.inputs[1])
    height = node(nt, "ShaderNodeMath", operation="MULTIPLY_ADD")
    nt.links.new(wetbead.outputs[0], height.inputs[0])
    height.inputs[1].default_value = 5.0
    nt.links.new(weave.outputs[0], height.inputs[2])
    bump = node(nt, "ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.0006
    nt.links.new(height.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    rough = node(nt, "ShaderNodeMapRange")
    rough.inputs["To Min"].default_value, rough.inputs["To Max"].default_value = 0.72, 0.4
    nt.links.new(wet.outputs[0], rough.inputs["Value"])
    nt.links.new(rough.outputs["Result"], b.inputs["Roughness"])
    nt.links.new(wetbead.outputs[0], b.inputs["Coat Weight"])
    b.inputs["Coat Roughness"].default_value = 0.03
    b.inputs["Sheen Weight"].default_value = 0.3
    b.inputs["Sheen Roughness"].default_value = 0.45
    alpha = node(nt, "ShaderNodeValue", name="alpha", label="alpha")
    alpha.outputs[0].default_value = 1.0
    nt.links.new(alpha.outputs[0], b.inputs["Alpha"])
    return m


def piping(mat: bpy.types.Material) -> bpy.types.NodeTree:
    """The seams: the cover's open edges (where the pieces meet, and the hem) as a soft rib."""
    ng = bpy.data.node_groups.new("piping", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gin, gout = node(ng, "NodeGroupInput"), node(ng, "NodeGroupOutput")
    faces = node(ng, "GeometryNodeInputMeshEdgeNeighbors")
    one = node(ng, "FunctionNodeCompare", data_type="INT", operation="EQUAL")
    one.inputs[3].default_value = 1
    ng.links.new(faces.outputs["Face Count"], one.inputs[2])
    curve = node(ng, "GeometryNodeMeshToCurve")
    ng.links.new(gin.outputs[0], curve.inputs["Mesh"])
    ng.links.new(one.outputs[0], curve.inputs["Selection"])
    circ = node(ng, "GeometryNodeCurvePrimitiveCircle")
    circ.inputs["Resolution"].default_value = 6
    circ.inputs["Radius"].default_value = 0.0055
    tube = node(ng, "GeometryNodeCurveToMesh")
    ng.links.new(curve.outputs[0], tube.inputs["Curve"])
    ng.links.new(circ.outputs["Curve"], tube.inputs["Profile Curve"])
    setm = node(ng, "GeometryNodeSetMaterial")
    setm.inputs["Material"].default_value = mat
    ng.links.new(tube.outputs[0], setm.inputs["Geometry"])
    join = node(ng, "GeometryNodeJoinGeometry")
    ng.links.new(gin.outputs[0], join.inputs[0])
    ng.links.new(setm.outputs[0], join.inputs[0])
    ng.links.new(join.outputs[0], gout.inputs[0])
    return ng


def simple(name: str, hexcol: str, rough: float, metal: float = 0.0) -> bpy.types.Material:
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = lin(hexcol)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    alpha = node(m.node_tree, "ShaderNodeValue", name="alpha", label="alpha")
    alpha.outputs[0].default_value = 1.0
    m.node_tree.links.new(alpha.outputs[0], b.inputs["Alpha"])
    return m


# ---- the scene ----------------------------------------------------------------------------
def build(a: argparse.Namespace) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.render.fps = 1, LAST, 24
    w, h = (int(x) for x in a.size.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.engine = "CYCLES"
    sc.cycles.samples = a.samples
    sc.cycles.use_denoising = True
    sc.cycles.seed = 3
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Medium High Contrast"
    sc.view_settings.exposure = -0.3
    if a.gpu:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                if any(d.type == kind for d in prefs.devices):
                    break
            except TypeError:
                continue
        for d in prefs.devices:
            d.use = d.type != "CPU"
        sc.cycles.device = "GPU"
        # OpenImageDenoise: the OptiX denoiser needs driver parts cloud GPUs often lack
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    sc.render.image_settings.file_format = "WEBP"
    sc.render.image_settings.quality = 82

    # the studio: soft light, an off-white sweep
    world = bpy.data.worlds.new("studio")
    sc.world = world
    world.use_nodes = True
    env = node(world.node_tree, "ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(a.data / "studio.hdr"))
    bg = world.node_tree.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.55
    world.node_tree.links.new(env.outputs["Color"], bg.inputs["Color"])
    bpy.ops.mesh.primitive_plane_add(size=1)
    sweep = bpy.context.object
    me = sweep.data
    verts = []
    for i in range(25):  # a cyclorama: floor curving up into the back wall
        t = i / 24
        y = -6 + 10 * min(t / 0.7, 1.0)
        z = 0.0 if t < 0.7 else 2.5 * (1 - math.cos((t - 0.7) / 0.3 * math.pi / 2))
        y = y if t < 0.7 else 4 + 2.5 * math.sin((t - 0.7) / 0.3 * math.pi / 2)
        verts += [(-14, y, z), (14, y, z)]
    me.clear_geometry()
    me.from_pydata(verts, [], [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(24)])
    for p in me.polygons:
        p.use_smooth = True
    sweep_mat = simple("sweep", OFFWHITE, 0.9)
    me.materials.append(sweep_mat)
    key = bpy.data.lights.new("key", "AREA")
    key.energy, key.size = 1300, 3
    k = bpy.data.objects.new("key", key)
    k.location, k.rotation_euler = (3.5, -3.5, 4.5), (math.radians(45), 0, math.radians(40))
    sc.collection.objects.link(k)
    rim = bpy.data.lights.new("rim", "AREA")
    rim.energy, rim.size = 700, 2
    r = bpy.data.objects.new("rim", rim)
    r.location, r.rotation_euler = (-3.0, 3.5, 3.0), (math.radians(-50), 0, math.radians(-140))
    sc.collection.objects.link(r)

    s = story(a.data)
    # the furniture (its cushions and plinth from the glb's colours), fading where asked
    bpy.ops.import_scene.gltf(filepath=str(a.data / "furniture.glb"))
    sofa = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    up = simple("upholstery", "c9cbc5", 0.85)
    vc = node(up.node_tree, "ShaderNodeAttribute", attribute_name="Color")  # the glb's colours
    up.node_tree.links.new(
        vc.outputs["Color"], up.node_tree.nodes["Principled BSDF"].inputs["Base Color"]
    )
    plinth = simple("plinth", "2b302b", 0.45, 0.3)  # the dark aluminium base
    for o in sofa:
        o.data.materials.clear()
        o.data.materials.append(up)
        o.data.materials.append(plinth)
        low = min(v.co.z for v in o.data.vertices) + PLINTH_M
        for p in o.data.polygons:
            p.use_smooth = True
            p.material_index = 1 if p.center.z < low else 0
    # the cover: one mesh, shape keys for its stages
    cover_me = bpy.data.meshes.new("cover")
    cover_me.from_pydata(s["design"].tolist(), [], s["faces"].tolist())
    cover = bpy.data.objects.new("cover", cover_me)
    sc.collection.objects.link(cover)
    for p in cover_me.polygons:
        p.use_smooth = True
    colours = np.array([lin(PIECES[k % len(PIECES)]) for k in s["piece"]], dtype=np.float32)
    att = cover_me.color_attributes.new("piece_colour", "FLOAT_COLOR", "POINT")
    att.data.foreach_set("color", colours.ravel())
    centre = np.zeros((s["piece"].max() + 1, 3))
    for k in range(len(centre)):
        centre[k] = s["design"][s["piece"] == k].mean(axis=0)
    apart = s["design"] + centre[s["piece"]] * np.array([0.22, 0.22, 0.12])
    flat = s["flat"].copy()
    flat[:, 2] = TABLE_Z + 0.004
    lifted = 0.5 * (flat + s["drape"])
    lifted[:, 2] += 0.9
    cover.shape_key_add(name="design")
    kb = {}
    for name, arr in (("apart", apart), ("flat", flat), ("lifted", lifted), ("drape", s["drape"])):
        kb[name] = cover.shape_key_add(name=name)
        kb[name].data.foreach_set("co", arr.astype(np.float32).ravel())
    c = CH
    keys(
        kb["apart"],
        "value",
        [(2 * c + 1, 0.0), (2 * c + 30, 1.0), (3 * c + 1, 1.0), (3 * c + 30, 0.0)],
    )
    keys(
        kb["flat"],
        "value",
        [(3 * c + 1, 0.0), (3 * c + 30, 1.0), (4 * c + 1, 1.0), (4 * c + 14, 0.0)],
    )
    keys(kb["lifted"], "value", [(4 * c + 1, 0.0), (4 * c + 14, 1.0), (4 * c + 28, 0.0)])
    keys(kb["drape"], "value", [(4 * c + 14, 0.0), (4 * c + 28, 1.0)])
    pipe = simple("piping", SEAM, 0.55)
    cover.modifiers.new("seams", "NODES").node_group = piping(pipe)
    cover.modifiers.new("thickness", "SOLIDIFY").thickness = 0.0015
    cover.modifiers.new("smooth", "SUBSURF").levels = 1
    mat = fabric("coverlast", by_piece=True)
    cover_me.materials.append(mat)
    nt = mat.node_tree
    keys(nt.nodes["alpha"].outputs[0], "", [(c + 1, 0.0), (c + 26, 1.0)])
    keys(nt.nodes["unify"].outputs[0], "", [(4 * c + 14, 0.0), (4 * c + 30, 1.0)])
    keys(nt.nodes["wet"].outputs[0], "", [(5 * c + 1, 0.0), (5 * c + 34, 1.0)])
    # the sofa steps aside while the pieces lie on the table
    for f, v in ((3 * c + 1, 1.0), (3 * c + 22, 0.0), (4 * c + 8, 0.0), (4 * c + 24, 1.0)):
        for m_ in (up, plinth):
            keys(m_.node_tree.nodes["alpha"].outputs[0], "", [(f, v)])
    # the cutting table, with the unrolled fabric under the pieces
    lo, hi = flat.min(axis=0), flat.max(axis=0)
    bpy.ops.mesh.primitive_cube_add(
        size=1, location=((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, TABLE_Z / 2)
    )
    table = bpy.context.object
    table.scale = (hi[0] - lo[0] + 1.2, 2.4, TABLE_Z)
    tmat = simple("table", "e9eae6", 0.6)
    table.data.materials.append(tmat)
    bpy.ops.mesh.primitive_plane_add(
        size=1, location=((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, TABLE_Z + 0.001)
    )
    strip = bpy.context.object
    strip.scale = (hi[0] - lo[0] + 0.6, s["meta"]["roll_m"][1] + 0.04, 1)
    smat = fabric("roll", by_piece=False)
    smat.node_tree.nodes["RGB"].outputs[0].default_value = lin("ddd3c0")
    strip.data.materials.append(smat)
    at = (hi[0] + 0.45, (lo[1] + hi[1]) / 2, TABLE_Z + 0.12)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=s["meta"]["roll_m"][1] + 0.04,
                                        location=at, rotation=(math.pi / 2, 0, 0))  # fmt: skip
    roll = bpy.context.object
    roll.data.materials.append(smat)
    for o in (table, strip, roll):
        o.hide_render = True
        keys(o, "hide_render", [(1, True), (3 * c + 1, False), (4 * c + 24, True)], "CONSTANT")
    for m_ in (tmat, smat):
        fade = [(3 * c + 1, 0.0), (3 * c + 18, 1.0), (4 * c + 8, 1.0), (4 * c + 22, 0.0)]
        keys(m_.node_tree.nodes["alpha"].outputs[0], "", fade)
    # the rain
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.0016, segments=8, ring_count=6, location=(0, 0, -5)
    )
    drop = bpy.context.object
    drop.scale = (1.0, 1.0, 55)  # a streak, as the eye sees falling rain
    bpy.ops.object.transform_apply(scale=True)  # particles ignore the object's own scale
    water = simple("water", "eef3f7", 0.05)
    water.node_tree.nodes["alpha"].outputs[0].default_value = 0.7
    water.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = lin("e6eef4")
    water.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 1.1
    # the studio darkens to the house green for the rain, so the lit drops show
    base = sweep_mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"]
    keys(base, "", [(5 * c - 6, lin(OFFWHITE)), (5 * c + 10, lin(DARK))])
    keys(bg.inputs["Strength"], "", [(5 * c - 6, 0.55), (5 * c + 10, 0.18)])
    keys(rim, "energy", [(5 * c - 6, 700.0), (5 * c + 10, 2600.0)])
    drop.data.materials.append(water)
    bpy.ops.mesh.primitive_plane_add(size=4.5, location=(0, 0, 4.0))
    sky = bpy.context.object
    sky.show_instancer_for_render = False
    ps = sky.modifiers.new("rain", "PARTICLE_SYSTEM").particle_system
    st = ps.settings
    st.count, st.lifetime = 90000, 40
    st.frame_start, st.frame_end = 5 * c + 1, LAST
    st.normal_factor, st.object_align_factor = 0.0, (0.15, 0.0, -7.0)
    st.effector_weights.gravity = 0.0
    st.render_type, st.instance_object = "OBJECT", drop
    st.particle_size, st.size_random = 1.0, 0.3  # the default 0.05 shrank every drop
    ps.seed = 5
    cover.modifiers.new("collision", "COLLISION")
    cover.collision.use_particle_kill = True
    # the camera per chapter: front three-quarter, closer, wider, over the table, back, close
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = 50
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = 8
    aim = bpy.data.objects.new("aim", None)
    sc.collection.objects.link(aim)
    cam.data.dof.focus_object = aim
    t = cam.constraints.new("TRACK_TO")
    t.target = aim
    mid = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, TABLE_Z)
    shots = [
        (1, (3.4, -4.0, 1.6), (0, 0, 0.45)), (c, (3.1, -3.6, 1.5), (0, 0, 0.45)),
        (2 * c, (2.8, -3.3, 1.7), (0, 0, 0.5)), (3 * c - 6, (3.6, -4.2, 2.2), (0, 0, 0.5)),
        (3 * c + 24, (mid[0] + 1.0, mid[1] - 7.5, 8.0), mid),
        (4 * c + 6, (mid[0] + 0.6, mid[1] - 7.0, 7.4), mid),
        (4 * c + 30, (-3.2, -3.8, 1.6), (0, 0, 0.45)), (5 * c + 4, (-2.9, -3.4, 1.5), (0, 0, 0.45)),
        (LAST, (2.6, -3.2, 1.3), (0, 0, 0.45)),
    ]  # fmt: skip
    for f, pos, look in shots:
        keys(cam, "location", [(f, pos)])
        keys(aim, "location", [(f, look)])
    cam.data.dof.aperture_fstop = 8


def main() -> None:
    a = args()
    build(a)
    sc = bpy.context.scene
    a.out.mkdir(parents=True, exist_ok=True)
    first, last = (int(x) for x in a.frames.split("-"))
    if any(o.particle_systems for o in sc.objects) and last > 5 * CH:
        sc.frame_set(1)
        bpy.ops.ptcache.bake_all(bake=True)
    for f in range(first, last + 1):
        path = a.out / f"story-{f:03d}.webp"
        if path.is_file():
            continue
        sc.frame_set(f)
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)


main()
