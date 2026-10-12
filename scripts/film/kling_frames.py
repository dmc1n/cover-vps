"""Start and end frames for Kling image-to-video (ADR-125, docs/plans/kling-shots.md).

Kling turns one still (and, for a transition, a last still) into a 5 s clip. The still decides
almost everything: the cover's shape, its colour, the light. So these are single pictures, made
with more care than the frames of a film: the same scene parts as the start film and the reel
(render_hero.py, render_reel.py; the SUNS Kota 2-seater, its real cover from our data in sand),
more samples, and a closer fabric:

- **a woven canvas**: a procedural plain weave at the real yarn pitch (about 0.7 mm) in the
  fabric's own grain (the pieces' flat UV), each yarn a little lighter or darker along its
  length (solution-dyed acrylic reads slightly heathered), a soft mottle and fine creases on top
  of the scanned weave; a matt roughness with the sheen of acrylic;
- **the double stitching standing up**: the thread rows of seams.png get their own relief and
  a slightly glossier thread in the close-ups, so they read as stitches, not as a printed line
  (from further away the raised dashes alias into a serrated edge, so the wide shots keep the
  film's flat thread).

Shots (each at 16:9 1920 × 1080 and 4:5 1080 × 1350; ``--aspects`` picks):

- ``fit``: the bare sofa on the terrace (``fit-start``), the cover still settling
  (``fit-mid``, the cloth solver's fall.npz) and the cover settled (``fit-end``), one camera;
- ``rain``: the moment the rain starts: overcast, wet stone, the coating beading (Kling rains);
- ``villa``: a whitewashed terrace on Ibiza at golden hour, the Kota sofa and the Sato lounger
  under their covers, the sea to the horizon (``--more sato=DIR``);
- ``cut``: the cutting head on the sand fabric, its kerf behind it, the pen lines beside it;
- ``sew``: close along a double-stitched seam of the draped cover;
- ``vent``: an air vent: the hood, its plastic insert, the dark membrane behind.

    scripts/film/blender.sh -P scripts/film/kling_frames.py -- --shot fit --data DIR \
        --assets DIR --out DIR [--aspects 16x9,4x5] [--samples 160] [--scale 1.0] [--only TAG]

Pictures OUT/SHOT-TAG-ASPECT.png; those that exist are skipped. ``--scale 0.25 --samples 16``
is a quick look at the framing.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Callable
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_hero as rh  # noqa: E402
import render_reel as rr  # noqa: E402

node, link, math_node, smooth, lin = rh.node, rh.link, rh.math_node, rh.smooth, rh.lin

ASPECTS = {"16x9": (1920, 1080), "4x5": (1080, 1350)}
YARN_PITCH = 0.0007  # m: acrylic outdoor canvas, about 14 yarns a centimetre each way


def args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--assets", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--aspects", default="16x9,4x5")
    ap.add_argument("--samples", type=int, default=160)
    ap.add_argument("--scale", type=float, default=1.0, help="0.25: a quick look")
    ap.add_argument("--only", default="", help="TAG[,TAG]: these states only")
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--more", nargs="*", default=[], help="NAME=DIR: other covers (villa)")
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    a.size = "1920x1080"  # render_settings wants one; each picture sets its own
    a.frames, a.every, a.dry = "", 1, False
    return a


# ---- the fabric -----------------------------------------------------------------------------
def _chain_normal(nt, b, new_bump) -> None:
    """Put `new_bump` between the Principled BSDF's normal source and everything it fed."""
    if b.inputs["Normal"].links:
        src = b.inputs["Normal"].links[0].from_socket
        targets = [lk.to_socket for lk in src.links]
        link(nt, src, new_bump.inputs["Normal"])
    else:
        targets = [b.inputs["Normal"]]
    for t in targets:
        if t.node != new_bump:
            link(nt, new_bump.outputs["Normal"], t)


def weave_height(nt, uv, pitch: float = YARN_PITCH):
    """A plain weave's height (0..1) at a UV in metres: warp along V, weft along U, each yarn
    rounded across and passing over and under the yarns it crosses. Returns (height, warp_on_top
    mask, warp coordinate, weft coordinate)."""
    sep = node(nt, "ShaderNodeSeparateXYZ")
    link(nt, uv, sep.inputs[0])
    u = math_node(nt, "DIVIDE", sep.outputs["X"], pitch)
    v = math_node(nt, "DIVIDE", sep.outputs["Y"], pitch)
    fu, fv = math_node(nt, "FRACT", u), math_node(nt, "FRACT", v)
    par = math_node(nt, "FLOORED_MODULO",
                    math_node(nt, "ADD", math_node(nt, "FLOOR", u), math_node(nt, "FLOOR", v)),
                    2.0)  # fmt: skip
    sgn = math_node(nt, "MULTIPLY_ADD", par, -2.0, 1.0)  # +1 / -1, a checkerboard
    across_u = math_node(nt, "POWER", math_node(nt, "SINE", math_node(nt, "MULTIPLY", fu,
                                                                       math.pi)), 0.6)  # fmt: skip
    across_v = math_node(nt, "POWER", math_node(nt, "SINE", math_node(nt, "MULTIPLY", fv,
                                                                       math.pi)), 0.6)  # fmt: skip
    over_v = math_node(nt, "MULTIPLY", sgn, math_node(nt, "SINE", math_node(nt, "MULTIPLY", fv,
                                                                            math.pi)))  # fmt: skip
    over_u = math_node(nt, "MULTIPLY", sgn, math_node(nt, "SINE", math_node(nt, "MULTIPLY", fu,
                                                                            math.pi)))  # fmt: skip
    warp = math_node(nt, "MULTIPLY", across_u, math_node(nt, "MULTIPLY_ADD", over_v, 0.5, 0.5))
    weft = math_node(nt, "MULTIPLY", across_v, math_node(nt, "MULTIPLY_ADD", over_u, -0.5, 0.5))
    h = math_node(nt, "MAXIMUM", warp, weft)
    warp_top = math_node(nt, "GREATER_THAN", warp, weft)
    return h, warp_top, u, v


def canvas(m: bpy.types.Material, close: bool = False) -> bpy.types.Material:
    """The film's Coverlast made closer to the real canvas (see the module's docstring)."""
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    uvn = next((n for n in nt.nodes if n.bl_idname == "ShaderNodeUVMap"), None)
    uv = uvn.outputs["UV"] if uvn else node(nt, "ShaderNodeTexCoord").outputs["Object"]
    h, warp_top, u, v = weave_height(nt, uv)
    # the weave's relief: deep enough to catch a raking sun up close
    wb = node(nt, "ShaderNodeBump")
    wb.inputs["Strength"].default_value = 0.75 if close else 0.45
    wb.inputs["Distance"].default_value = 0.00022
    link(nt, h, wb.inputs["Height"])
    _chain_normal(nt, b, wb)
    # fine creases and the soft unevenness of a coated canvas
    crease = node(nt, "ShaderNodeTexNoise")
    crease.inputs["Scale"].default_value = 26.0
    crease.inputs["Detail"].default_value = 6.0
    crease.inputs["Distortion"].default_value = 0.6
    link(nt, uv, crease.inputs["Vector"])
    cb = node(nt, "ShaderNodeBump")
    cb.inputs["Strength"].default_value = 0.12
    cb.inputs["Distance"].default_value = 0.0012
    link(nt, crease.outputs["Fac"], cb.inputs["Height"])
    _chain_normal(nt, b, cb)

    # heathered yarns: each yarn its own shade along its length, a shade per yarn on top
    def yarn_noise(along, across):
        cmb = node(nt, "ShaderNodeCombineXYZ")
        link(nt, math_node(nt, "FLOOR", across), cmb.inputs["X"])
        link(nt, math_node(nt, "DIVIDE", along, 60.0), cmb.inputs["Y"])
        nz = node(nt, "ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 1.7
        nz.inputs["Detail"].default_value = 1.0
        link(nt, cmb.outputs[0], nz.inputs["Vector"])
        return nz.outputs["Fac"]

    shade = node(nt, "ShaderNodeMix", data_type="FLOAT")
    link(nt, warp_top, shade.inputs[0])
    link(nt, yarn_noise(u, v), shade.inputs[2])  # the weft on top
    link(nt, yarn_noise(v, u), shade.inputs[3])  # the warp on top
    yarn = math_node(nt, "MULTIPLY_ADD", shade.outputs[0], 0.16, 0.92)  # 0.92..1.08
    # the hollows between yarns a little darker (they catch less light even when lit)
    hollow = math_node(nt, "MULTIPLY_ADD", h, 0.10, 0.92)
    mottle = node(nt, "ShaderNodeTexNoise")
    mottle.inputs["Scale"].default_value = 3.5
    mottle.inputs["Detail"].default_value = 3.0
    link(nt, uv, mottle.inputs["Vector"])
    mott = math_node(nt, "MULTIPLY_ADD", mottle.outputs["Fac"], 0.08, 0.96)
    k = math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", yarn, hollow), mott)
    base_src = b.inputs["Base Color"].links[0].from_socket
    tint = node(nt, "ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    tint.inputs[0].default_value = 1.0
    link(nt, base_src, tint.inputs[6])
    gray = node(nt, "ShaderNodeCombineColor")
    for i in range(3):
        link(nt, k, gray.inputs[i])
    link(nt, gray.outputs[0], tint.inputs[7])
    link(nt, tint.outputs[2], b.inputs["Base Color"])
    # matt canvas: rougher than the film's, the yarn tops a touch smoother than the hollows
    for n in nt.nodes:
        if (
            n.bl_idname == "ShaderNodeMapRange"
            and abs(n.inputs["To Min"].default_value - 0.55) < 1e-6
        ):
            n.inputs["To Min"].default_value, n.inputs["To Max"].default_value = 0.66, 0.84
    b.inputs["Sheen Weight"].default_value = 0.45
    b.inputs["Sheen Roughness"].default_value = 0.35
    b.inputs["Specular IOR Level"].default_value = 0.35
    # the stitches: the thread rows of seams.png raised and a little glossier
    seps = [n for n in nt.nodes if n.bl_idname == "ShaderNodeSeparateColor"
            and n.inputs["Color"].links
            and n.inputs["Color"].links[0].from_node.bl_idname == "ShaderNodeTexImage"
            and "seams" in (n.inputs["Color"].links[0].from_node.image.name or "")]  # fmt: skip
    if seps and close:  # from further away the raised dashes alias into a serrated edge
        thread = seps[0].outputs["Green"]
        # render_reel.fabric scales the thread by `stitched`; follow it when present
        for lk in thread.links:
            if lk.to_node.bl_idname == "ShaderNodeMath" and lk.to_node.operation == "MULTIPLY":
                thread = lk.to_node.outputs[0]
                break
        tb = node(nt, "ShaderNodeBump")
        tb.inputs["Strength"].default_value = 1.0
        tb.inputs["Distance"].default_value = 0.0005
        link(nt, thread, tb.inputs["Height"])
        _chain_normal(nt, b, tb)
        rough_src = b.inputs["Roughness"].links[0].from_socket
        r2 = node(nt, "ShaderNodeMix", data_type="FLOAT")
        link(nt, thread, r2.inputs[0])
        link(nt, rough_src, r2.inputs[2])
        r2.inputs[3].default_value = 0.42
        link(nt, r2.outputs[0], b.inputs["Roughness"])
    return m


def fabric(a, d, close: bool = False, name: str = "kling-cover"):
    return canvas(rr.fabric(a.assets, rr.seams_pic(a), tuple(d["uv_size"]), name=name), close)


# ---- the picture ----------------------------------------------------------------------------
def settings(a: argparse.Namespace) -> None:
    """More samples and bounces than the films; the shot's own view settings (exposure, look)
    stay as the shot set them."""
    cy = bpy.context.scene.cycles
    cy.samples = a.samples
    cy.adaptive_threshold = 0.004
    cy.adaptive_min_samples = 64 if a.samples >= 128 else 0
    cy.max_bounces, cy.diffuse_bounces, cy.glossy_bounces = 12, 5, 4
    cy.blur_glossy = 0.5
    cy.seed = 11
    sc = bpy.context.scene
    sc.render.image_settings.compression = 15
    sc.render.image_settings.color_mode = "RGB"  # no alpha channel in what Kling gets


class Cam:
    """One camera per shot, framed per aspect: `views[aspect] = (lens, location, aim, shift_x,
    shift_y, fstop)`; the 4:5 picture fits the sensor's height."""

    def __init__(self) -> None:
        sc = bpy.context.scene
        self.cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        sc.collection.objects.link(self.cam)
        sc.camera = self.cam
        self.aim = bpy.data.objects.new("aim", None)
        sc.collection.objects.link(self.aim)
        c = self.cam.data
        c.sensor_width = 36
        c.sensor_height = 24
        c.clip_start = 0.01
        c.clip_end = 20000
        c.dof.use_dof = True
        c.dof.aperture_blades = 7
        c.dof.focus_object = self.aim
        tr = self.cam.constraints.new("TRACK_TO")
        tr.target = self.aim

    def set(self, aspect: str, view) -> None:
        lens, at, look, sx, sy, fstop = view
        c = self.cam.data
        c.sensor_fit = "HORIZONTAL" if aspect == "16x9" else "VERTICAL"
        c.lens, c.shift_x, c.shift_y = lens, sx, sy
        c.dof.aperture_fstop = fstop
        self.cam.location = Vector(at)
        self.aim.location = Vector(look)


State = tuple[str, Callable[[], None], dict]  # tag, set the scene, views per aspect


# ---- the shots ------------------------------------------------------------------------------
def terrace_sun(a):
    sky, sun, stone = rr.terrace_scene(a)
    rr.mood(sky, sun, bpy.context.scene, "sun")
    sun.data.energy = 5.0
    sun.data.angle = math.radians(3.0)  # a crisper shadow than the film's haze
    return sky, sun, stone


def shot_fit(a, d, reel) -> list[State]:
    terrace_sun(a)
    mat = fabric(a, d)
    cov = rr.lean(rh.cover(d, mat))
    final = rr.draped(d)
    fall = np.load(a.data / "fall.npz")["frames"]

    def bare():
        cov.hide_render = True

    def mid():
        cov.hide_render = False
        rr.set_points(cov, fall[int(len(fall) * 0.42)])

    def end():
        cov.hide_render = False
        rr.set_points(cov, final)

    views = {
        "16x9": (40, (-1.8, -3.35, 1.0), (0.1, -0.05, 0.4), 0.0, 0.0, 6.3),
        "4x5": (30, (-1.8, -3.35, 1.05), (0.05, -0.05, 0.4), 0.0, 0.0, 6.3),
    }
    return [("start", bare, views), ("mid", mid, views), ("end", end, views)]


def shot_rain(a, d, reel) -> list[State]:
    """The moment the rain starts: overcast, the stone wet, the coating beading. No drops on
    the run paths and no streaks: baked into a still they read as white rivets and grey marks,
    and Kling makes the rain run better than a still can show it."""
    sky, sun, stone = rr.terrace_scene(a)
    sc = bpy.context.scene
    rr.mood(sky, sun, sc, "rain")
    sc.view_settings.exposure = 0.15
    mat = fabric(a, d)
    cov = rr.lean(rh.cover(d, mat))
    rr.set_points(cov, rr.draped(d))
    stone.node_tree.nodes["wet"].outputs[0].default_value = 0.9
    rr.set_value(mat, "wet", 1.0)

    def nothing():
        pass

    views = {
        "16x9": (38, (2.35, -3.25, 0.95), (0.05, -0.2, 0.4), 0.0, 0.0, 5.0),
        "4x5": (30, (2.4, -3.35, 0.85), (0.0, -0.15, 0.2), 0.0, 0.0, 5.0),
    }
    return [("start", nothing, views)]


VILLA_SUN = (8.0, 282.0)  # elevation, azimuth: low from the left, raking across the covers


def villa_scene(a):
    """render_reel's Ibiza terrace in a warmer, clearer golden hour and a deeper sea."""
    rr.ibiza_scene(a)
    sc = bpy.context.scene
    sc.view_settings.exposure = -0.3  # the sand stays sand in the low sun, not cream
    w = sc.world.node_tree
    sky = next(n for n in w.nodes if n.bl_idname == "ShaderNodeTexSky")
    sky.sun_elevation = math.radians(VILLA_SUN[0])
    sky.sun_rotation = math.radians(VILLA_SUN[1])
    sky.dust_density = 0.55
    sky.air_density = 1.3
    sky.sun_intensity = 0.5
    sun = bpy.data.objects["sun"]
    sun.data.energy = 7.5
    sun.data.color = (1.0, 0.74, 0.5)
    sun.data.angle = math.radians(0.8)
    el, az = math.radians(VILLA_SUN[0]), math.radians(VILLA_SUN[1])
    dv = Vector((math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el)))
    sun.rotation_euler = (-dv).to_track_quat("-Z", "Y").to_euler()
    # the back wall stands behind the camera, but a sun this low from the left would put the
    # whole terrace in its shadow
    back = bpy.data.objects.get("backwall")
    if back is not None:
        bpy.data.objects.remove(back)
    # Es Vedra smaller and further, a silhouette in the haze rather than a lump
    isl = next(
        o
        for o in bpy.data.objects
        if o.data and o.data.materials and o.data.materials[0].name == "island"
    )
    isl.scale = (110, 75, 190)
    isl.location = (1500, 4600, -70)
    sea = bpy.data.materials["sea"].node_tree.nodes["Principled BSDF"]
    sea.inputs["Base Color"].default_value = lin("0b3247")
    sea.inputs["Roughness"].default_value = 0.1
    sea.inputs["Specular IOR Level"].default_value = 0.5


def shot_villa(a, d, reel) -> list[State]:
    villa_scene(a)
    rh.furniture(a)
    mat = fabric(a, d)
    cov = rr.lean(rh.cover(d, mat))
    rr.set_points(cov, rr.draped(d))
    for (name, folder), (at, turn) in zip([m.split("=", 1) for m in a.more],
                                          [(Vector((2.35, 0.55, 0)), math.radians(-90))],
                                          strict=False):  # fmt: skip
        other_canvas(a, name, Path(folder), at, turn)

    others = [
        o
        for o in bpy.data.objects
        if o.name.startswith("cover")
        and o.type == "MESH"
        and o.data.materials
        and o.data.materials[0].name.startswith("cover-")
    ]
    folders = [Path(m.split("=", 1)[1]) for m in a.more]

    def designed():
        # the lounger's drape sags into its seat (ADR-121); its designed surface spans it, as
        # domain rule 12 wants the cover to
        for o, f in zip(others, folders, strict=False):
            od = dict(np.load(f / "cover.npz"))
            rr.set_points(o, rh.welded(od, od["design"].astype(float)))

    def drape():
        for o, f in zip(others, folders, strict=False):
            rr.set_points(o, rr.draped(dict(np.load(f / "cover.npz"))))

    views = {
        "16x9": (32, (-2.9, -3.7, 1.55), (0.75, 0.55, 0.45), 0.0, 0.05, 6.0),
        "4x5": (24, (-2.4, -3.9, 1.45), (0.85, 0.45, 0.5), 0.0, 0.05, 6.0),
    }
    return [("start", designed, views), ("drape", drape, views)]


def other_canvas(a, name: str, folder: Path, at: Vector, turn: float) -> None:
    """render_reel.other_cover with the canvas fabric."""
    before = set(bpy.data.materials.keys())
    rr.other_cover(a, name, folder, at, turn)
    m = bpy.data.materials.get(f"cover-{name}")
    if m is not None and m.name not in before:
        canvas(m)


def gantry(p: Vector, dirv: Vector, reel: dict) -> None:
    """What holds the cutting head on a real cutter: a carriage on an aluminium beam across
    the table (without it the head floats, which Kling would 'fix' in its own way). The beam
    runs square to the cut, so it crosses the top of the picture instead of filling it."""
    beam_mat = rh.simple("beam", "b9bcbe", 0.32, 1.0)
    beam_mat.node_tree.nodes["Principled BSDF"].inputs["Anisotropic"].default_value = 0.5
    dark = rh.simple("carriage", "2b2d30", 0.4, 0.3)
    span = float(reel["roll"]["width"]) + 0.9
    turn = math.atan2(dirv.y, dirv.x) + math.pi / 2
    for name, off, size, mat in (
        ("beam", Vector((0, 0, 0.33)) + dirv * 0.1, (span, 0.12, 0.14), beam_mat),
        ("rail", Vector((0, 0, 0.405)) + dirv * 0.05, (span, 0.03, 0.02), dark),
        ("carriage", Vector((0, 0, 0.29)), (0.2, 0.15, 0.17), dark),
    ):
        ob = rh.box(name, (0.0, 0.0, 0.0), size, mat)  # its origin stays at its centre
        ob.rotation_euler.z, ob.location = turn, p + off
    # the workshop's far wall, where the camera looks (the film's wall is only behind the table)
    wall = bpy.data.materials.get("workshop-wall")
    if wall is not None:
        ob = rh.box("far-wall", (0.0, 0.0, 0.0), (16.0, 0.2, 4.0), wall)
        ob.rotation_euler.z = turn
        ob.location = Vector((p.x, p.y, 2.0)) + dirv * 3.2


def shot_cut(a, d, reel) -> list[State]:
    # render_reel's cutting shot builds the table, the roll, the kerf and the head; its own
    # camera is replaced by ours
    frame = rr.shot_cut(a, d, reel)
    sc = bpy.context.scene
    old = sc.camera
    frame(30.0, 96)  # the knife a third of the way along its edge
    head = bpy.data.objects["head"]
    p = head.location.copy()
    rot = head.rotation_euler.z
    dirv = Vector((math.cos(rot), math.sin(rot), 0))
    side = Vector((-dirv.y, dirv.x, 0))
    for o in (old, *[o for o in sc.objects if o.name.startswith("aim") and o.type == "EMPTY"]):
        o.hide_render = True
    sc.camera = None
    for m in bpy.data.materials:
        if m.name.startswith("roll-fabric"):
            canvas(m, close=True)
    sc.view_settings.exposure = -0.9  # the sand reads sand, not cream, under the bay light
    gantry(p, dirv, reel)

    def nothing():
        pass

    back = p - dirv * 0.85 - side * 0.45 + Vector((0, 0, 0.3))
    look = p + dirv * 0.1 + Vector((0, 0, 0.15))
    views = {
        "16x9": (40, tuple(back), tuple(look), 0.0, 0.0, 5.6),
        "4x5": (34, tuple(back), tuple(look), 0.0, 0.0, 5.6),
    }
    return [("start", nothing, views)]


def shot_sew(a, d, reel) -> list[State]:
    terrace_sun(a)
    mat = fabric(a, d, close=True)
    cov = rr.lean(rh.cover(d, mat))
    dr = rr.draped(d)
    rr.set_points(cov, dr)
    line = rr.seam_line(d, "skirt-left", ("skirt-front", "top-1"))
    centre = Vector(dr.mean(axis=0))

    def nothing():
        pass

    states = []
    for tag, k in (("start", 0.18), ("high", 0.4)):
        p = rr.along(line, k)
        out = Vector((p.x - centre.x, p.y - centre.y, 0)).normalized()
        view = (out + Vector((0, -1, 0))).normalized()
        views = {
            "16x9": (90, tuple(p + view * 0.5 + Vector((0, 0, 0.14))), tuple(p), 0.0, 0.0, 4.0),
            "4x5": (90, tuple(p + view * 0.46 + Vector((0, 0, 0.12))), tuple(p), 0.0, 0.0, 4.0),
        }
        states.append((tag, nothing, views))
    return states


def shot_vent(a, d, reel) -> list[State]:
    terrace_sun(a)
    mat = fabric(a, d, close=True)
    cov = rr.lean(rh.cover(d, mat))
    rr.set_points(cov, rr.draped(d))
    vents = reel.get("vents", [])
    v = next((x for x in vents if x["piece"] == "skirt-left"), vents[0])
    hood_mat = canvas(rr.hood_material(a.assets, *v["size"]), close=True)
    rr.vent_hood(v, hood_mat, depth=0.09)
    c, n = Vector(v["centre"]), Vector(v["normal"])
    side = Vector(v["up"]).cross(n).normalized()

    def nothing():
        pass

    # from low and to the side, so the eye sees under the hood: the insert and the membrane
    low = Vector((0, 0, 0.035 - c.z))  # the eye 3.5 cm above the stone
    at = c + n * 0.42 + side * 0.4 + low
    look = c + Vector((0, 0, -0.075))
    views = {
        "16x9": (45, tuple(at), tuple(look), 0.0, 0.05, 4.0),
        "4x5": (45, tuple(at), tuple(look), 0.0, 0.05, 4.0),
    }
    # in profile: how far the hood stands out, the insert's bow at its lower edge
    at2 = c + n * 0.2 + side * 0.55 + Vector((0, 0, 0.09 - c.z))
    views2 = {
        "16x9": (60, tuple(at2), tuple(c + n * 0.03 + Vector((0, 0, -0.05))), 0.0, 0.0, 4.0),
        "4x5": (60, tuple(at2), tuple(c + n * 0.03 + Vector((0, 0, -0.05))), 0.0, 0.0, 4.0),
    }
    # close and from just above the stone, a wide lens: up under the hood's open edge, where
    # the insert's bow and a band of the dark membrane show
    at3 = c + n * 0.25 + side * 0.3 + Vector((0, 0, 0.02 - c.z))
    look3 = c + n * 0.04 + Vector((0, 0, -0.08))
    views3 = {
        "16x9": (24, tuple(at3), tuple(look3), 0.0, 0.0, 8.0),
        "4x5": (21, tuple(at3), tuple(look3), 0.0, 0.0, 8.0),
    }
    return [("start", nothing, views), ("side", nothing, views2), ("under", nothing, views3)]


SHOTS = {
    "fit": shot_fit,
    "rain": shot_rain,
    "villa": shot_villa,
    "cut": shot_cut,
    "sew": shot_sew,
    "vent": shot_vent,
}


def main() -> None:
    a = args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    d = dict(np.load(a.data / "cover.npz"))
    reel_path = a.data / "reel.json"
    import json

    reel = json.loads(reel_path.read_text()) if reel_path.is_file() else {}
    rh.render_settings(a)
    states = SHOTS[a.shot](a, d, reel)
    settings(a)
    cam = Cam()
    sc = bpy.context.scene
    only = {t for t in a.only.split(",") if t}
    a.out.mkdir(parents=True, exist_ok=True)
    for tag, apply, views in states:
        if only and tag not in only:
            continue
        for aspect in [x for x in a.aspects.split(",") if x]:
            w, h = ASPECTS[aspect]
            path = a.out / f"{a.shot}-{tag}-{aspect}.png"
            if path.is_file():
                continue
            sc.render.resolution_x = max(int(w * a.scale), 64)
            sc.render.resolution_y = max(int(h * a.scale), 64)
            apply()
            cam.set(aspect, views[aspect])
            sc.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            print("rendered", path.name, flush=True)


if __name__ == "__main__":
    main()
