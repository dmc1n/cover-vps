"""The home page's hero film (ADR-101): what we really make, path-traced from our own data.

Five calm shots, one loop:

1. **terrace**: the SUNS Kota 2-seater under its made-to-measure sand Coverlast cover on a stone
   terrace against a dark green plaster wall, overcast light; a slow dolly. The cover is the
   Style3D drape of our own pieces (drape.bin), not a modelled shape.
2. **seam**: close on a corner: the double-stitched seams (two rows on the panel that laps
   over, as we sew them), the woven texture and the soft sheen of the coated canvas, the hem.
   The stitches are placed in the flat pieces (exact distances from the seam line), so they
   follow the fabric.
3. **table**: our cut pieces (cut.dxf: outlines and pen marks) on the cutting table's felt.
4. **on**: the cover lowered over the sofa by its ridge (hero_fall.py), blending into the drape.
5. **rain**: light rain; the water runs off along the paths our rain check computed on the
   draped cover (drape_rain.json): the drops run down them and the fabric darkens behind them,
   while the coating beads the rest.

    blender -b -P scripts/film/render_hero.py -- --data DIR --assets DIR --out DIR
        [--frames 1-344] [--size 1920x1080] [--samples 48] [--every 1]

DIR: cover.npz, fall.npz, pieces.json, furniture.glb (hero_data.py, hero_fall.py); assets from
hero_assets.py. Frames that exist are skipped (resumable); PNG per frame, encode.py-style
encoding in hero_encode.py.
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

# the shots: name, frames (24 fps)
SHOTS = [("terrace", 84), ("seam", 60), ("table", 60), ("on", 64), ("rain", 108)]
SAND = "c8b593"  # the configurator's sand (main.tsx COLOURS.sand), as the swatch looks
SAND_ALBEDO = "c4a678"  # the albedo that renders as that swatch under this light (AgX)
THREAD = "e4d9c2"  # a matching thread, a shade lighter
WALL = "e6e1d6"  # a warm lime plaster, near S2DIO off white
INK = "2a3a5c"  # the cutting table's pen, a blue-black
FELT = "34363a"  # the cutting table's vacuum felt
TABLE_AT = Vector((40.0, 0.0, 0.0))  # the workshop is somewhere else on the same ground
TABLE_Z = 0.9


def args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--assets", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frames", default="")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--samples", type=int, default=48)
    ap.add_argument("--every", type=int, default=1, help="render every n-th frame (previews)")
    ap.add_argument("--threads", type=int, default=0)
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])


def start(name: str) -> int:
    f = 1
    for n, length in SHOTS:
        if n == name:
            return f
        f += length
    raise KeyError(name)


def span(name: str) -> tuple[int, int]:
    s = start(name)
    return s, s + dict(SHOTS)[name] - 1


TOTAL = sum(n for _, n in SHOTS)


def lin(hexcol: str) -> tuple[float, float, float, float]:
    c = [int(hexcol[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    v = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (v[0], v[1], v[2], 1.0)


def node(nt, kind, x=0, **kw):
    n = nt.nodes.new(kind)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def link(nt, a, b):
    nt.links.new(a, b)


def math_node(nt, op, a, b=None, c=None, clamp=False):
    m = node(nt, "ShaderNodeMath", operation=op, use_clamp=clamp)
    for i, v in enumerate((a, b, c)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            m.inputs[i].default_value = v
        else:
            link(nt, v, m.inputs[i])
    return m.outputs[0]


def smooth(nt, v, lo, hi):
    """smoothstep(lo, hi, v), or falling when lo > hi"""
    r = node(nt, "ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
    r.inputs["From Min"].default_value, r.inputs["From Max"].default_value = lo, hi
    link(nt, v, r.inputs["Value"])
    return r.outputs["Result"]


def image(nt, path: Path, vec, colour: bool = True, box: bool = False):
    t = node(nt, "ShaderNodeTexImage")
    if box:
        t.projection, t.projection_blend = "BOX", 0.25
    t.image = bpy.data.images.load(str(path), check_existing=True)
    if not colour:
        t.image.colorspace_settings.name = "Non-Color"
    t.interpolation = "Cubic"
    link(nt, vec, t.inputs["Vector"])
    return t


def pbr(name: str, folder: Path, metres: float, tint=None, rough_add=0.0, normal=1.0):
    """A scanned material (Poly Haven) on the object's UV or box-projected world position."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = node(nt, "ShaderNodeTexCoord")
    mp = node(nt, "ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / metres,) * 3
    link(nt, tc.outputs["Object"], mp.inputs["Vector"])
    vec = mp.outputs[0]
    d = image(nt, folder / "Diffuse.jpg", vec, box=True)
    col = d.outputs["Color"]
    if tint is not None:
        mix = node(nt, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        mix.inputs[0].default_value = 1.0
        link(nt, col, mix.inputs[6])
        mix.inputs[7].default_value = tint
        col = mix.outputs[2]
    r = image(nt, folder / "Rough.jpg", vec, colour=False, box=True)
    ra = math_node(nt, "ADD", r.outputs["Color"], rough_add, clamp=True)
    # rain on it: darker and glossy (a "wet" value, 0..1)
    wet = node(nt, "ShaderNodeValue", name="wet", label="wet")
    dark = node(nt, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    link(nt, wet.outputs[0], dark.inputs[0])
    link(nt, col, dark.inputs[6])
    dark.inputs[7].default_value = (0.62, 0.62, 0.62, 1)
    link(nt, dark.outputs[2], b.inputs["Base Color"])
    gloss = node(nt, "ShaderNodeMix", data_type="FLOAT")
    link(nt, wet.outputs[0], gloss.inputs[0])
    link(nt, ra, gloss.inputs[2])
    gloss.inputs[3].default_value = 0.12
    link(nt, gloss.outputs[0], b.inputs["Roughness"])
    nm = image(nt, folder / "nor_gl.jpg", vec, colour=False, box=True)
    nmap = node(nt, "ShaderNodeNormalMap")
    nmap.inputs["Strength"].default_value = normal
    link(nt, nm.outputs["Color"], nmap.inputs["Color"])
    link(nt, nmap.outputs["Normal"], b.inputs["Normal"])
    return m


def simple(name: str, hexcol: str, rough: float, metal: float = 0.0) -> bpy.types.Material:
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = lin(hexcol)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


# ---- the cover's fabric -------------------------------------------------------------------
def coverlast(assets: Path, seams: Path | None = None, uv_size=(1.0, 1.0)) -> bpy.types.Material:
    """Sunbrella Coverlast in sand: a fine plain weave (a scanned weave's normals and roughness,
    in the fabric's own grain), a soft sheen; the double-stitched seams and the hem from the
    baked picture (hero_data.py: relief and thread, in the flat pieces); when it rains, the
    coating beads the water and the paths where it runs turn glossy and a little darker."""
    m = bpy.data.materials.new("coverlast" if seams else "coverlast-flat")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    if seams:
        uv = node(nt, "ShaderNodeUVMap", uv_map="flat").outputs["UV"]
    else:
        uv = node(nt, "ShaderNodeTexCoord").outputs["Object"]
    weave_dir = assets / "stretch_poplin"
    mp = node(nt, "ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / 0.17,) * 3  # Coverlast's weave is a little coarser
    link(nt, uv, mp.inputs["Vector"])
    wn = image(nt, weave_dir / "nor_gl.jpg", mp.outputs[0], colour=False)
    wd = image(nt, weave_dir / "Diffuse.jpg", mp.outputs[0])
    wr = image(nt, weave_dir / "Rough.jpg", mp.outputs[0], colour=False)
    wet_now = node(nt, "ShaderNodeValue", name="wet", label="wet")  # the rain shot, 0..1
    stream = node(nt, "ShaderNodeAttribute", attribute_name="stream").outputs["Fac"]

    weave_n = node(nt, "ShaderNodeNormalMap")
    weave_n.inputs["Strength"].default_value = 0.8
    link(nt, wn.outputs["Color"], weave_n.inputs["Color"])
    normal = weave_n.outputs["Normal"]
    thread = None
    if seams:
        sm = node(nt, "ShaderNodeMapping")
        sm.inputs["Scale"].default_value = (1 / uv_size[0], 1 / uv_size[1], 1)
        link(nt, uv, sm.inputs["Vector"])
        st = image(nt, seams, sm.outputs[0], colour=False)
        st.interpolation = "Cubic"
        sep = node(nt, "ShaderNodeSeparateColor")
        link(nt, st.outputs["Color"], sep.inputs["Color"])
        relief = node(nt, "ShaderNodeBump")
        relief.inputs["Strength"].default_value = 1.0
        relief.inputs["Distance"].default_value = 0.004  # the picture's red is 0..4 mm
        link(nt, sep.outputs["Red"], relief.inputs["Height"])
        link(nt, normal, relief.inputs["Normal"])
        normal = relief.outputs["Normal"]
        thread = sep.outputs["Green"]
    else:  # fabric lying loose on the table: soft, low waves
        waves = node(nt, "ShaderNodeTexNoise")
        waves.inputs["Scale"].default_value = 3.0
        waves.inputs["Detail"].default_value = 2.0
        link(nt, uv, waves.inputs["Vector"])
        wb_ = node(nt, "ShaderNodeBump")
        wb_.inputs["Strength"].default_value = 1.0
        wb_.inputs["Distance"].default_value = 0.004
        link(nt, waves.outputs["Fac"], wb_.inputs["Height"])
        link(nt, normal, wb_.inputs["Normal"])
        normal = wb_.outputs["Normal"]

    # -- the colour: sand, with the weave's own light and dark; the thread a shade lighter
    lum = node(nt, "ShaderNodeRGBToBW")
    link(nt, wd.outputs["Color"], lum.inputs["Color"])
    var = node(nt, "ShaderNodeMapRange")
    var.inputs["From Min"].default_value, var.inputs["From Max"].default_value = 0.35, 0.75
    var.inputs["To Min"].default_value, var.inputs["To Max"].default_value = 0.92, 1.05
    link(nt, lum.outputs["Val"], var.inputs["Value"])
    sand = node(nt, "ShaderNodeRGB", name="sand")
    sand.outputs[0].default_value = lin(SAND_ALBEDO)
    tinted = node(nt, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    tinted.inputs[0].default_value = 1.0
    link(nt, sand.outputs[0], tinted.inputs[6])
    gray = node(nt, "ShaderNodeCombineColor")
    for i in range(3):
        link(nt, var.outputs["Result"], gray.inputs[i])
    link(nt, gray.outputs[0], tinted.inputs[7])
    col = tinted.outputs[2]
    if thread is not None:
        with_thread = node(nt, "ShaderNodeMix", data_type="RGBA")
        link(nt, thread, with_thread.inputs[0])
        link(nt, col, with_thread.inputs[6])
        with_thread.inputs[7].default_value = lin(THREAD)
        col = with_thread.outputs[2]
    # where the water runs: a little darker, much glossier (the coating keeps it on top)
    wetness = math_node(nt, "MULTIPLY", stream, wet_now.outputs[0])
    darker = node(nt, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    link(nt, math_node(nt, "MULTIPLY", wetness, 0.6), darker.inputs[0])
    link(nt, col, darker.inputs[6])
    darker.inputs[7].default_value = (0.8, 0.77, 0.72, 1)
    link(nt, darker.outputs[2], b.inputs["Base Color"])

    # -- roughness and sheen
    rr = node(nt, "ShaderNodeMapRange")
    rr.inputs["To Min"].default_value, rr.inputs["To Max"].default_value = 0.55, 0.75
    link(nt, wr.outputs["Color"], rr.inputs["Value"])
    rough = node(nt, "ShaderNodeMix", data_type="FLOAT")
    link(nt, wetness, rough.inputs[0])
    link(nt, rr.outputs["Result"], rough.inputs[2])
    rough.inputs[3].default_value = 0.35
    link(nt, rough.outputs[0], b.inputs["Roughness"])
    b.inputs["Sheen Weight"].default_value = 0.3
    b.inputs["Sheen Roughness"].default_value = 0.4
    b.inputs["Sheen Tint"].default_value = (1.0, 0.97, 0.92, 1)
    b.inputs["Specular IOR Level"].default_value = 0.4

    # -- beads: the coating keeps the rain in round drops; they appear as it rains
    bead_map = node(nt, "ShaderNodeMapping")
    bead_map.inputs["Scale"].default_value = (1 / 0.012,) * 3
    link(nt, uv, bead_map.inputs["Vector"])
    vor = node(nt, "ShaderNodeTexVoronoi", feature="F1")
    vor.inputs["Randomness"].default_value = 1.0
    link(nt, bead_map.outputs[0], vor.inputs["Vector"])
    cell = node(nt, "ShaderNodeSeparateColor")
    link(nt, vor.outputs["Color"], cell.inputs["Color"])
    radius = math_node(nt, "MULTIPLY_ADD", cell.outputs[1], 0.2, 0.06)  # in cells
    # only some cells hold a drop, more as the rain goes on
    share = math_node(nt, "MULTIPLY", wet_now.outputs[0], 0.35)
    appear = smooth(nt, math_node(nt, "SUBTRACT", share, cell.outputs[0]), -0.03, 0.03)
    inside = math_node(nt, "DIVIDE", vor.outputs["Distance"], radius)
    sq = math_node(nt, "MINIMUM", math_node(nt, "MULTIPLY", inside, inside), 1.0)
    cap = math_node(nt, "POWER", math_node(nt, "SUBTRACT", 1.0, sq), 0.5)  # a round drop
    bead = math_node(nt, "MULTIPLY", cap, appear)
    bead_bump = node(nt, "ShaderNodeBump")
    bead_bump.inputs["Strength"].default_value = 1.0
    bead_bump.inputs["Distance"].default_value = 0.0015
    link(nt, bead, bead_bump.inputs["Height"])
    link(nt, normal, bead_bump.inputs["Normal"])
    link(nt, normal, b.inputs["Normal"])
    bead_mask = smooth(nt, bead, 0.0, 0.04)
    coat = math_node(nt, "MAXIMUM", bead_mask, math_node(nt, "MULTIPLY", wetness, 0.8))
    link(nt, coat, b.inputs["Coat Weight"])
    b.inputs["Coat Roughness"].default_value = 0.02
    b.inputs["Coat IOR"].default_value = 1.33
    link(nt, bead_bump.outputs["Normal"], b.inputs["Coat Normal"])
    return m


# ---- the scene ----------------------------------------------------------------------------
def render_settings(a: argparse.Namespace) -> None:
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end, sc.render.fps = 1, TOTAL, 24
    w, h = (int(x) for x in a.size.split("x"))
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.engine = "CYCLES"
    cy = sc.cycles
    cy.samples = a.samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.015
    cy.use_denoising = True
    cy.denoiser = "OPENIMAGEDENOISE"
    cy.denoising_prefilter = "ACCURATE"
    cy.seed = 7
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 8, 3, 3
    cy.transmission_bounces, cy.transparent_max_bounces = 8, 8
    cy.caustics_reflective = cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    sc.render.use_persistent_data = True
    if a.threads:
        sc.render.threads_mode = "FIXED"
        sc.render.threads = a.threads
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.look = "AgX - Base Contrast"
    sc.view_settings.exposure = 0.0
    sc.render.film_transparent = False
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_depth = "8"
    sc.render.image_settings.compression = 30


def world(a: argparse.Namespace) -> bpy.types.ShaderNodeBackground:
    sc = bpy.context.scene
    w = bpy.data.worlds.new("overcast")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    env = node(nt, "ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(a.assets / "hotel_rooftop_balcony_4k.hdr"))
    tc = node(nt, "ShaderNodeTexCoord")
    mp = node(nt, "ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(-60))
    link(nt, tc.outputs["Generated"], mp.inputs["Vector"])
    link(nt, mp.outputs[0], env.inputs["Vector"])
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.55
    link(nt, env.outputs["Color"], bg.inputs["Color"])
    return bg


def box(name: str, at, size, mat) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=at)
    ob = bpy.context.object
    ob.name = name
    ob.scale = size
    bpy.ops.object.transform_apply(scale=True)  # the textures in metres, not stretched
    ob.data.materials.append(mat)
    return ob


def terrace(a: argparse.Namespace) -> tuple[bpy.types.Object, bpy.types.Material]:
    """A stone terrace against a warm lime-plaster wall, a plant, a low hazy sun from the left;
    returns the sun (it goes in for the rain) and the stone (it gets wet)."""
    sc = bpy.context.scene
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
    floor = bpy.context.object
    floor.name = "floor"
    fm = pbr("stone", a.assets / "large_grey_tiles", 3.6, tint=(0.86, 0.83, 0.78, 1), normal=0.45)
    floor.data.materials.append(fm)
    wm = pbr(
        "plaster",
        a.assets / "white_plaster_02",
        1.6,
        tint=tuple(1.9 * c for c in lin(WALL)),
        normal=0.5,
    )
    box("wall", (0, 2.15, 1.6), (20, 0.2, 3.2), wm)
    box("side", (4.2, -1.5, 1.6), (0.2, 7.5, 3.2), wm)
    plant = a.assets / "potted_plant_04" / "potted_plant_04.gltf"
    if plant.is_file():
        bpy.ops.import_scene.gltf(filepath=str(plant))
        for o in [o for o in bpy.context.selected_objects if o.parent is None]:
            o.scale = (3.4, 3.4, 3.4)
            o.location = (1.85, 1.45, 0.0)
            o.rotation_euler.z = math.radians(30)
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy, sun.angle = 2.6, math.radians(7)
    sun.color = (1.0, 0.93, 0.84)
    so = bpy.data.objects.new("sun", sun)
    # a low late sun from the left: the end lit, the slope raked, the front in soft shade
    so.rotation_euler = Vector((0.9, 0.1, -0.42)).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(so)
    return so, fm


def furniture(a: argparse.Namespace) -> None:
    bpy.ops.import_scene.gltf(filepath=str(a.data / "furniture.glb"))
    parts = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    up = simple("upholstery", "a8a49a", 0.85)
    upn = up.node_tree
    tc = node(upn, "ShaderNodeTexCoord")
    mp = node(upn, "ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / 0.08,) * 3
    link(upn, tc.outputs["Object"], mp.inputs["Vector"])
    nm = image(upn, a.assets / "stretch_poplin" / "nor_gl.jpg", mp.outputs[0], colour=False)
    nmap = node(upn, "ShaderNodeNormalMap")
    link(upn, nm.outputs["Color"], nmap.inputs["Color"])
    link(upn, nmap.outputs["Normal"], upn.nodes["Principled BSDF"].inputs["Normal"])
    upn.nodes["Principled BSDF"].inputs["Sheen Weight"].default_value = 0.5
    plinth = simple("plinth", "2e302e", 0.35, 0.9)
    tops = {o.name: max((o.matrix_world @ v.co).z for v in o.data.vertices) for o in parts}
    lowest = min(min((o.matrix_world @ v.co).z for v in o.data.vertices) for o in parts)
    for o in parts:  # the parts that stay in the lowest 13 cm are the aluminium base
        o.data.materials.clear()
        o.data.materials.append(plinth if tops[o.name] < lowest + 0.13 else up)
        for p in o.data.polygons:
            p.use_smooth = True


def cover(d: dict, mat: bpy.types.Material) -> bpy.types.Object:
    """The sewn cover as one closed surface (the seams joined, so no gap shows), every corner
    with its own piece's flat position as UV (the islands stay apart)."""
    n = int(d["weld"].max()) + 1
    pos = np.zeros((n, 3))
    pos[d["weld"]] = d["frames"][-1]
    me = bpy.data.meshes.new("cover")
    me.from_pydata(pos.tolist(), [], d["weld_faces"].tolist())
    uvl = me.uv_layers.new(name="flat")
    # from_pydata keeps the triangles in order: loop 3t+c is corner c of triangle t
    uvl.data.foreach_set("uv", d["uv"][d["faces"].ravel()].astype(np.float32).ravel())
    me.attributes.new("stream", "FLOAT", "POINT")
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("cover", me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(mat)
    th = ob.modifiers.new("thickness", "SOLIDIFY")
    th.thickness, th.offset = 0.0012, 1.0
    sub = ob.modifiers.new("smooth", "SUBSURF")
    sub.levels = sub.render_levels = 2
    sub.uv_smooth = "PRESERVE_BOUNDARIES"
    return ob


def welded(d: dict, split: np.ndarray) -> np.ndarray:
    n = int(d["weld"].max()) + 1
    out = np.zeros((n, 3))
    out[d["weld"]] = split
    return out


def table(a: argparse.Namespace, mat: bpy.types.Material) -> None:
    """The cutting table: felt, the pieces of cut.dxf in sand, their pen marks in ink."""
    sc = bpy.context.scene
    doc = json.loads((a.data / "pieces.json").read_text())
    pts = np.vstack([np.array(c) for c in doc["cut"]])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    origin = TABLE_AT + Vector((-(lo[0] + hi[0]) / 2, -(lo[1] + hi[1]) / 2, TABLE_Z + 0.0015))
    bpy.ops.mesh.primitive_cube_add(size=1, location=TABLE_AT + Vector((0, 0, TABLE_Z / 2)))
    t = bpy.context.object
    t.scale = (hi[0] - lo[0] + 1.0, hi[1] - lo[1] + 0.9, TABLE_Z)
    bpy.ops.object.transform_apply(scale=True)
    felt = simple("felt", FELT, 0.95)
    fn = felt.node_tree
    tc = node(fn, "ShaderNodeTexCoord")
    noise = node(fn, "ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 900.0
    noise.inputs["Detail"].default_value = 8.0
    link(fn, tc.outputs["Object"], noise.inputs["Vector"])
    bump = node(fn, "ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    link(fn, noise.outputs["Fac"], bump.inputs["Height"])
    link(fn, bump.outputs["Normal"], fn.nodes["Principled BSDF"].inputs["Normal"])
    fn.nodes["Principled BSDF"].inputs["Sheen Weight"].default_value = 0.6
    t.data.materials.append(felt)
    # one sheet of fabric from the roll, the pieces cut in it: the knife's lines show the felt
    # through a fine kerf; the openings (the vents) are cut out and lifted away
    bpy.ops.mesh.primitive_plane_add(
        size=1, location=origin + Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, 0))
    )
    sheet = bpy.context.object
    sheet.name = "sheet"
    sheet.scale = (hi[0] - lo[0] + 0.12, hi[1] - lo[1] + 0.12, 1)
    bpy.ops.object.transform_apply(scale=True)
    sheet.data.materials.append(mat)
    sheet.modifiers.new("t", "SOLIDIFY").thickness = 0.0012
    kerf = simple("kerf", "141516", 0.9)
    outlines = [np.array(c)[:-1] if np.allclose(c[0], c[-1]) else np.array(c) for c in doc["cut"]]
    boxes = [(c.min(axis=0), c.max(axis=0)) for c in outlines]

    def inner(i: int) -> bool:  # an opening (a vent) cut inside a piece
        lo_i, hi_i = boxes[i]
        return any(j != i and (lo_j <= lo_i).all() and (hi_i <= hi_j).all()
                   for j, (lo_j, hi_j) in enumerate(boxes))  # fmt: skip

    for i, c in enumerate(outlines):
        if inner(i):  # the felt shows through the opening
            me = bpy.data.meshes.new(f"opening{i}")
            me.from_pydata([(x, y, 0.00006) for x, y in c], [], [list(range(len(c)))])
            ob = bpy.data.objects.new(f"opening{i}", me)
            sc.collection.objects.link(ob)
            ob.location = origin
            me.materials.append(felt)
        cu = bpy.data.curves.new(f"cut{i}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.0005
        sp = cu.splines.new("POLY")
        sp.points.add(len(c) - 1)
        for p, (x, y) in zip(sp.points, c, strict=True):
            p.co = (x, y, 0.0, 1)
        sp.use_cyclic_u = True
        ob = bpy.data.objects.new(f"cut{i}", cu)
        ob.location = origin
        ob.scale.z = 0.4  # a slit, not a cord
        cu.materials.append(kerf)
        sc.collection.objects.link(ob)
    ink = simple("ink", INK, 0.6)
    for i, line in enumerate(doc["pen"]):
        cu = bpy.data.curves.new(f"pen{i}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.00035
        sp = cu.splines.new("POLY")
        sp.points.add(len(line) - 1)
        for p, (x, y) in zip(sp.points, line, strict=True):
            p.co = (x, y, 0.0003, 1)
        ob = bpy.data.objects.new(f"pen{i}", cu)
        ob.location = origin
        cu.materials.append(ink)
        sc.collection.objects.link(ob)
    for i, tx in enumerate(doc["text"]):
        cu = bpy.data.curves.new(f"label{i}", "FONT")
        cu.body = tx["text"]
        cu.size = tx["h"] * 1.4
        ob = bpy.data.objects.new(f"label{i}", cu)
        ob.location = origin + Vector((tx["at"][0], tx["at"][1], 0.0002))
        ob.rotation_euler.z = math.radians(tx["rot"])
        cu.materials.append(ink)
        sc.collection.objects.link(ob)
    # the gantry with its knife and pen head, crossing the table
    alu = simple("alu", "c9cbcc", 0.3, 1.0)
    bpy.ops.mesh.primitive_cube_add(size=1)
    beam = bpy.context.object
    beam.name = "gantry"
    beam.scale = (0.16, hi[1] - lo[1] + 1.1, 0.12)
    beam.location = TABLE_AT + Vector((0.0, 0.0, TABLE_Z + 0.22))
    beam.data.materials.append(alu)
    bpy.ops.mesh.primitive_cube_add(size=1)
    head = bpy.context.object
    head.name = "head"
    head.scale = (0.2, 0.16, 0.22)
    head.location = TABLE_AT + Vector((0.0, -0.3, TABLE_Z + 0.16))
    head.data.materials.append(simple("head", "1e2124", 0.4, 0.2))
    # the workshop's light: a long soft panel overhead
    lt = bpy.data.lights.new("bay", "AREA")
    lt.shape, lt.size, lt.size_y, lt.energy = "RECTANGLE", 5, 2.5, 450
    lt.color = (1.0, 0.97, 0.92)
    lo_ = bpy.data.objects.new("bay", lt)
    lo_.location = TABLE_AT + Vector((0, 0.6, TABLE_Z + 2.6))
    lo_.rotation_euler = (math.radians(-12), 0, 0)
    sc.collection.objects.link(lo_)
    lo_.visible_camera = False
    for o in (beam, head):
        o.location.x -= 1.0
        o.keyframe_insert("location", frame=start("table"))
    for o, dx in ((beam, 0.7), (head, 0.7)):
        o.location.x += dx
        o.keyframe_insert("location", frame=span("table")[1])
    for o in (beam, head):
        for fc in o.animation_data.action.fcurves:
            for k in fc.keyframe_points:
                k.interpolation = "LINEAR"


# ---- the rain -----------------------------------------------------------------------------
def rain() -> tuple[bpy.types.Object, bpy.types.Object]:
    sc = bpy.context.scene
    water = simple("water", "ffffff", 0.02)
    wb = water.node_tree.nodes["Principled BSDF"]
    wb.inputs["Transmission Weight"].default_value = 1.0
    wb.inputs["IOR"].default_value = 1.33
    # a falling drop catches the sky: against the dark wall it shows as a light streak
    wb.inputs["Emission Color"].default_value = lin("dfe6ea")
    wb.inputs["Emission Strength"].default_value = 1.4
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.0016, segments=10, ring_count=6, location=(0, 0, -5)
    )
    drop = bpy.context.object
    drop.scale = (1.0, 1.0, 2.6)
    bpy.ops.object.transform_apply(scale=True)
    drop.data.materials.append(water)
    bpy.ops.mesh.primitive_plane_add(size=7.0, location=(0, -0.6, 4.2))
    sky = bpy.context.object
    sky.show_instancer_for_render = False
    ps = sky.modifiers.new("rain", "PARTICLE_SYSTEM").particle_system
    st = ps.settings
    s0, s1 = span("rain")
    st.count, st.lifetime = 90000, 30
    st.frame_start, st.frame_end = s0 - 30, s1
    st.normal_factor, st.object_align_factor = 0.0, (0.25, 0.1, -7.5)
    st.effector_weights.gravity = 0.0
    st.render_type, st.instance_object = "OBJECT", drop
    st.particle_size, st.size_random = 1.0, 0.4
    ps.seed = 11
    clear = bpy.data.materials.new("clear")
    clear.use_nodes = True
    out = clear.node_tree.nodes["Material Output"]
    clear.node_tree.links.new(
        node(clear.node_tree, "ShaderNodeBsdfTransparent").outputs[0], out.inputs["Surface"]
    )
    sky.data.materials.append(clear)
    # the drops that run off the cover, one per path of the rain check (moved per frame)
    me = bpy.data.meshes.new("runners")
    runners = bpy.data.objects.new("runners", me)
    sc.collection.objects.link(runners)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.0, segments=16, ring_count=8, location=(0, 0, -5))
    bead = bpy.context.object
    bead.name = "runner_drop"
    for p in bead.data.polygons:
        p.use_smooth = True
    # water on the fabric: the sky's highlight on a drop
    # (pure glass reads as a dark speck here: it shows the shade under the hem), so: the
    # fabric's colour under a clear, glossy skin
    clear_water = simple("drop", SAND_ALBEDO, 0.04)
    cw = clear_water.node_tree.nodes["Principled BSDF"]
    cw.inputs["Coat Weight"].default_value = 1.0
    cw.inputs["Coat Roughness"].default_value = 0.01
    bead.data.materials.append(clear_water)
    runners.visible_shadow = False
    gn = runners.modifiers.new("drops", "NODES")
    ng = bpy.data.node_groups.new("drops", "GeometryNodeTree")
    ng.interface.new_socket(name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket(name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    gi, go = node(ng, "NodeGroupInput"), node(ng, "NodeGroupOutput")
    inst = node(ng, "GeometryNodeInstanceOnPoints")
    obj = node(ng, "GeometryNodeObjectInfo")
    obj.inputs[0].default_value = bead
    sz = node(ng, "GeometryNodeInputNamedAttribute", data_type="FLOAT_VECTOR")
    sz.inputs["Name"].default_value = "size"
    rot = node(ng, "GeometryNodeInputNamedAttribute", data_type="FLOAT_VECTOR")
    rot.inputs["Name"].default_value = "rot"
    ng.links.new(gi.outputs[0], inst.inputs["Points"])
    ng.links.new(obj.outputs["Geometry"], inst.inputs["Instance"])
    ng.links.new(sz.outputs["Attribute"], inst.inputs["Scale"])
    ng.links.new(rot.outputs["Attribute"], inst.inputs["Rotation"])
    real = node(ng, "GeometryNodeRealizeInstances")
    ng.links.new(inst.outputs[0], real.inputs[0])
    ng.links.new(real.outputs[0], go.inputs[0])
    gn.node_group = ng
    return sky, runners


def nearest(pos: np.ndarray, q: np.ndarray) -> np.ndarray:
    """The index of the closest point for each query (Blender's Python has no scipy)."""
    out = np.empty(len(q), np.int64)
    for i in range(0, len(q), 256):
        d = ((q[i : i + 256, None, :] - pos[None, :, :]) ** 2).sum(axis=2)
        out[i : i + 256] = d.argmin(axis=1)
    return out


def within(pos: np.ndarray, q: np.ndarray, r: float) -> list[np.ndarray]:
    out = []
    for i in range(0, len(q), 256):
        d = ((q[i : i + 256, None, :] - pos[None, :, :]) ** 2).sum(axis=2)
        out += [np.flatnonzero(row < r * r) for row in d]
    return out


class Runoff:
    """The rain check's drop paths on the draped cover, as drops that run down them: each path
    smoothed and held on the surface, a drop starting at its top at its own moment, moving at a
    steady pace; the fabric behind it stays wet."""

    SPEED = 0.16  # m/s down the cover
    RADIUS = 0.0032

    def __init__(self, d: dict, pos: np.ndarray, normals: np.ndarray) -> None:
        self.pos = pos
        self.paths, self.lengths = [], []
        rng = np.random.default_rng(4)
        for p, n in zip(d["paths"], d["path_len"], strict=True):
            p = p[:n].astype(np.float64)
            for _ in range(3):  # Chaikin: the 15 mm grid's staircase rounded
                q = np.empty((2 * len(p) - 2, 3))
                q[0::2] = 0.75 * p[:-1] + 0.25 * p[1:]
                q[1::2] = 0.25 * p[:-1] + 0.75 * p[1:]
                p = np.vstack([p[:1], q, p[-1:]])
            near = nearest(pos, p)
            p = pos[near] + normals[near] * (self.RADIUS * 0.5 + 0.0012)
            seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
            keep = np.concatenate([[True], seg > 1e-4])
            p = p[keep]
            s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])
            if s[-1] < 0.05:
                continue
            self.paths.append((p, s))
        self.t0 = rng.uniform(0.0, 3.6, len(self.paths))
        self.size = rng.uniform(0.6, 1.0, len(self.paths))
        # the fabric points along each path, with how far along it they are
        self.wet_by = []
        for p, s in self.paths:
            pts: dict[int, float] = {}
            for i, ids in enumerate(within(pos, p, 0.016)):
                for j in ids.tolist():
                    pts.setdefault(j, s[i])
            self.wet_by.append((np.array(list(pts)), np.array(list(pts.values()))))

    HANG = 0.45  # s a drop gathers at the hem before it lets go
    G = 9.81

    def at(self, t: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """The drops at time t (s) into the rain: where, their scale (x, y along the motion,
        z), their direction; and the wetness of every cover point. Each path carries a drop
        once; a drop runs down, gathers at the hem's edge and falls."""
        where, scale, dirs = [], [], []
        wet = np.zeros(len(self.pos))
        r = self.RADIUS
        for k, ((p, s), (pts, along)) in enumerate(zip(self.paths, self.wet_by, strict=True)):
            for lag in (0.0,):
                dist = (t - self.t0[k] - lag) * self.SPEED
                if dist <= 0:
                    continue
                wet[pts] = np.maximum(wet[pts], np.clip((dist - along) / 0.03, 0, 1) * 0.9)
                size = self.size[k] * r
                if dist < s[-1]:  # running down the cover
                    i = int(np.searchsorted(s, dist) - 1)
                    i = max(min(i, len(p) - 2), 0)
                    f = (dist - s[i]) / max(s[i + 1] - s[i], 1e-9)
                    where.append(p[i] + (p[i + 1] - p[i]) * f)
                    dirs.append(p[i + 1] - p[i])
                    scale.append((size * 0.8, size * 1.6, size * 0.45))
                    continue
                after = (dist - s[-1]) / self.SPEED  # s since it reached the edge
                end = p[-1].copy()
                if after < self.HANG:  # gathering at the edge, hanging a little lower
                    grow = 1.0 + 0.4 * after / self.HANG
                    where.append(end - (0, 0, size * 0.6 * grow))
                    dirs.append(np.array([0.0, 0.0, -1.0]))
                    scale.append((size * grow, size * 1.3 * grow, size * grow))
                    continue
                tf = after - self.HANG
                z = end[2] - size - 0.5 * self.G * tf * tf
                if z < 0.004:
                    continue
                v = self.G * tf
                # the camera's shutter (1/48 s) draws a falling drop as a short streak
                stretch = min(max(1.0, v / 48.0 / (2 * size * 1.4)), 14.0)
                where.append(np.array([end[0], end[1], z]))
                dirs.append(np.array([0.0, 0.0, -1.0]))
                scale.append((size * 1.2, size * 1.4 * stretch, size * 1.2))
        return np.array(where), np.array(scale), np.array(dirs), wet


def set_runners(ob: bpy.types.Object, where, scale, dirs) -> None:
    me = ob.data
    me.clear_geometry()
    if len(where) == 0:
        return
    me.vertices.add(len(where))
    me.vertices.foreach_set("co", where.astype(np.float32).ravel())
    yaw = np.arctan2(dirs[:, 1], dirs[:, 0]) - math.pi / 2
    pitch = np.arctan2(dirs[:, 2], np.linalg.norm(dirs[:, :2], axis=1))
    rot = np.column_stack([pitch, np.zeros(len(yaw)), yaw])
    for name, v in (("size", np.asarray(scale)), ("rot", rot)):
        at = me.attributes.new(name, "FLOAT_VECTOR", "POINT")
        at.data.foreach_set("vector", v.astype(np.float32).ravel())
    me.update()


# ---- cameras ------------------------------------------------------------------------------
def camera(
    name: str, lens: float, fstop: float, path: list, focus: list, shift: float = 0.0
) -> bpy.types.Object:
    """A camera moving on a straight, eased line between its keys over its shot."""
    sc = bpy.context.scene
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    sc.collection.objects.link(cam)
    cam.data.lens = lens
    cam.data.sensor_width = 36
    cam.data.shift_x = shift
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = fstop
    cam.data.dof.aperture_blades = 7
    cam.data.clip_start = 0.02
    aim = bpy.data.objects.new(name + "-aim", None)
    sc.collection.objects.link(aim)
    cam.data.dof.focus_object = aim
    tr = cam.constraints.new("TRACK_TO")
    tr.target = aim
    s0, s1 = span(name)
    for f, p, q in ((s0, path[0], focus[0]), (s1, path[1], focus[1])):
        cam.location = p
        cam.keyframe_insert("location", frame=f)
        aim.location = q
        aim.keyframe_insert("location", frame=f)
    for o in (cam, aim):
        for fc in o.animation_data.action.fcurves:
            for k in fc.keyframe_points:
                k.interpolation = "SINE"
                k.easing = "EASE_IN_OUT" if name != "terrace" else "EASE_OUT"
    m = sc.timeline_markers.new(name, frame=s0)
    m.camera = cam
    return cam


def hold(target, path: str, values: dict[str, float]) -> None:
    """A value per shot, switching at the cut."""
    for name, v in values.items():
        setattr(target, path, v)
        target.keyframe_insert(path, frame=start(name))
    for fc in target.id_data.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "CONSTANT"


def build(a: argparse.Namespace):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    render_settings(a)
    sky_light = world(a)
    sun, stone = terrace(a)
    furniture(a)
    d = dict(np.load(a.data / "cover.npz"))
    mat = coverlast(a.assets, a.data / "seams.png", tuple(d["uv_size"]))
    cov = cover(d, mat)
    table(a, coverlast(a.assets))
    sky, runners = rain()
    # the light per shot: the hazy sun goes in for the rain; the workshop has its own light
    sc = bpy.context.scene
    hold(sun.data, "energy", {"terrace": 4.5, "seam": 4.5, "table": 0.0, "on": 4.5, "rain": 0.0})
    hold(sky_light.inputs["Strength"], "default_value",
         {"terrace": 0.32, "seam": 0.32, "table": 0.3, "on": 0.32, "rain": 0.7})  # fmt: skip
    hold(sc.view_settings, "exposure",
         {"terrace": -0.35, "seam": -0.35, "table": -0.6, "on": -0.35, "rain": 0.0})  # fmt: skip
    # the cameras (the sofa: x along its length, its front towards -y, ground z = 0); the
    # subject a little right of centre, so the headline sits on the calm left
    camera("terrace", 45, 5.6, [(-2.55, -3.9, 0.86), (-2.2, -3.7, 0.82)],
           [(0.25, 0.0, 0.38), (0.3, 0.0, 0.38)], shift=-0.1)  # fmt: skip
    camera("seam", 70, 5.6, [(-1.42, -1.2, 0.52), (-1.32, -1.26, 0.48)],
           [(-0.8, -0.56, 0.24), (-0.8, -0.58, 0.22)], shift=-0.04)  # fmt: skip
    camera("table", 40, 4.5,
           [TABLE_AT + Vector((-2.25, -1.6, TABLE_Z + 0.8)),
            TABLE_AT + Vector((-2.05, -1.55, TABLE_Z + 0.76))],
           [TABLE_AT + Vector((-1.5, -0.25, TABLE_Z)), TABLE_AT + Vector((-1.35, -0.22, TABLE_Z))],
           shift=-0.04)  # fmt: skip
    camera("on", 35, 5.6, [(-2.25, -2.55, 0.7), (-2.05, -2.35, 0.66)],
           [(-0.15, -0.3, 0.42), (-0.15, -0.3, 0.4)], shift=-0.06)  # fmt: skip
    camera("rain", 45, 4.5, [(1.95, -2.7, 0.62), (1.75, -2.45, 0.58)],
           [(0.05, -0.35, 0.36), (0.05, -0.38, 0.35)], shift=-0.06)  # fmt: skip
    wet = stone.node_tree.nodes["wet"].outputs[0]
    r0, r1 = span("rain")
    for f, v in ((r0 - 1, 0.0), (r0, 0.35), (r0 + 48, 0.85)):
        wet.default_value = v
        wet.keyframe_insert("default_value", frame=f)
    return cov, d, mat, sky, runners


def main() -> None:
    a = args()
    cov, d, mat, sky, runners = build(a)
    sc = bpy.context.scene
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "shots.json").write_text(json.dumps(SHOTS))
    todo: list[int] = []
    for part in (a.frames or f"1-{TOTAL}").split(","):
        lo_, _, hi_ = part.partition("-")
        todo += list(range(int(lo_), int(hi_ or lo_) + 1, a.every))
    weld = d["weld"]
    split_final = d["frames"][-1].astype(np.float64)
    final = welded(d, split_final)  # the Style3D drape, on the sewn points
    fall_path = a.data / "fall.npz"
    fall = np.load(fall_path)["frames"] if fall_path.is_file() else None  # sewn points
    # normals of the draped cover, for the running drops
    normals = np.zeros(len(final) * 3)
    cov.data.vertices.foreach_get("normal", normals)
    run = Runoff(d, split_final, normals.reshape(-1, 3)[weld])
    wet_value = mat.node_tree.nodes["wet"].outputs[0]
    r0, r1 = span("rain")
    o0, o1 = span("on")
    if any(r0 <= f <= r1 for f in todo):
        sc.frame_set(r0 - 30)
        bpy.ops.ptcache.bake_all(bake=True)
    stream = cov.data.attributes["stream"]
    for f in todo:
        path = a.out / f"hero-{f:04d}.png"
        if path.is_file():
            continue
        sc.frame_set(f)
        # the cover: lowered in the "on" shot, the Style3D drape everywhere else
        if fall is not None and o0 <= f <= o1:
            k = (f - o0) / max(o1 - o0, 1)
            i = min(int(round(k * (len(fall) - 1))), len(fall) - 1)
            blend = np.clip((k - 0.72) / 0.28, 0, 1)
            blend = blend * blend * (3 - 2 * blend)
            co = fall[i] * (1 - blend) + final * blend
        else:
            co = final
        cov.data.vertices.foreach_set("co", co.astype(np.float32).ravel())
        cov.data.update()
        in_rain = r0 <= f <= r1
        t = (f - r0) / 24.0
        wet_value.default_value = float(np.clip(t / 2.0, 0, 1)) if in_rain else 0.0
        if in_rain:
            where, sizes, dirs, wet = run.at(t)
            set_runners(runners, where, sizes, dirs)
            wet_sewn = np.zeros(len(final))
            np.maximum.at(wet_sewn, weld, wet)
            stream.data.foreach_set("value", wet_sewn.astype(np.float32))
        else:
            set_runners(runners, np.zeros((0, 3)), [], [])
            stream.data.foreach_set("value", np.zeros(len(final), np.float32))
        sky.hide_render = not in_rain
        sc.render.use_motion_blur = in_rain
        sc.render.motion_blur_shutter = 0.5
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print("rendered", path.name, flush=True)


main()
