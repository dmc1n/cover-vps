"""The scroll story's chapters and the website's clips, path-traced from our own data (ADR-121).

The same scene parts as the start film (render_hero.py: the stone terrace, the Kota sofa, the
sand Coverlast with its real stitching, the rain check's paths), one shot per call:

Story chapters (scrubbed by the scroll, 60 pictures each, 1600 × 900):

- ``st1`` *Your furniture*: the bare sofa on the terrace; its length, depth and height drawn in
  as dimension lines, to the centimetre.
- ``st2`` *We calculate the cover*: the designed cover surface rises around the sofa, a thin
  line of light where it is being computed, translucent first, then fabric.
- ``st3`` *Seams and pieces*: the designed cover steps apart into its real pieces; the seams
  between them show.
- ``st4`` *Flat, on the roll*: in the workshop the pieces lay themselves flat, each onto its
  place in the nest on the 152 cm roll; the pen writes the labels of cut.dxf, the knife cuts.
- ``st5`` *Cut, sewn, fitted*: close along a double-stitched seam; then the cover is lowered
  over the sofa and settles (the cloth solver, into the Style3D drape).
- ``st6`` *Tested in the rain*: the sun goes in, the stone darkens, the coating beads and the
  water runs down the paths the rain check computed. No falling drops: the page draws those in
  time (RainLayer.tsx), so they never stand still or rise when the visitor scrolls.

Clips (looped in arch frames, 4:5, 720 × 900): ``cut`` the knife cutting a piece on the table,
``sew`` the double stitching up close, ``vent`` an air vent's hood, ``fit`` the cover lowered,
``runoff`` the rain running off, ``range`` other covers from the catalogue; and ``ibiza`` (16:9)
the cover at a whitewashed villa over the sea, for the end of the page.

    blender -b -P scripts/film/render_reel.py -- --shot st1 --data DIR --assets DIR --out DIR
        [--frames 1-60] [--every 1] [--size WxH] [--samples 32] [--more NAME=DIR ...]

DIR: hero_data.py's folder plus reel.json (reel_data.py). Pictures NAME-0001.png …; those that
exist are skipped. Run it through scripts/film/blender.sh (nice 19, one at a time).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_hero as rh  # noqa: E402  (the film's scene parts)

lin, node, link, math_node, smooth = rh.lin, rh.node, rh.link, rh.math_node, rh.smooth

STORY = (1600, 900)
CARD = (720, 900)
WORK_AT = Vector((80.0, 0.0, 0.0))  # the roll's cutting table, away from the terrace
TABLE_Z = 0.9
LINE = "f4efe6"  # the dimension lines: a warm white, as drawn over a photograph
INK = rh.INK
KERF = "121314"


def args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", required=True)
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--assets", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--frames", default="")
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--size", default="")
    ap.add_argument("--samples", type=int, default=32)
    ap.add_argument("--threads", type=int, default=0)
    ap.add_argument("--more", nargs="*", default=[], help="NAME=DIR: other models (range)")
    ap.add_argument("--dry", action="store_true", help="build and step the shot, render nothing")
    return ap.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])


def ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def ramp(f: float, a: float, b: float) -> float:
    """0 before frame a, 1 after b, eased between."""
    return ease((f - a) / max(b - a, 1e-9))


# ---- the fabric, with what the story needs on top of the film's ----------------------------
def fabric(assets: Path, seams: Path | None, uv_size=(1.0, 1.0), name="reel-cover"):
    """The film's Coverlast (render_hero.coverlast) plus four values the story animates:
    ``stitched`` (0: a flat cut piece, no stitching yet), ``reveal`` (the height up to which the
    computed surface shows), ``opacity`` (translucent while computed) and ``glow`` (the line of
    light at the reveal)."""
    m = rh.coverlast(assets, seams, uv_size)
    m.name = name
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    out = nt.nodes["Material Output"]
    if seams:  # the stitching's relief and thread, scaled by `stitched`
        stitched = node(nt, "ShaderNodeValue", name="stitched", label="stitched")
        stitched.outputs[0].default_value = 1.0

        def from_seams(n) -> bool:  # the Separate Color reading seams.png
            src = n.inputs["Color"].links[0].from_node if n.inputs["Color"].links else None
            return (
                src is not None
                and src.bl_idname == "ShaderNodeTexImage"
                and ("seams" in (src.image.name or ""))
            )

        sep = next(
            n for n in nt.nodes if n.bl_idname == "ShaderNodeSeparateColor" and from_seams(n)
        )
        base = 0.4  # hero_data.py: the plain fabric's level in the picture (1.6 of 4 mm)
        for socket_name in ("Red", "Green"):
            sock = sep.outputs[socket_name]
            targets = [lk.to_socket for lk in sock.links]
            if socket_name == "Red":  # relief: towards the plain level, not to zero
                v = math_node(nt, "SUBTRACT", sock, base)
                v = math_node(nt, "MULTIPLY_ADD", v, stitched.outputs[0], base)
            else:
                v = math_node(nt, "MULTIPLY", sock, stitched.outputs[0])
            for t in targets:
                link(nt, v, t)
    # reveal, opacity, glow: shown below `reveal` (world z), a thin light line at it
    geo = node(nt, "ShaderNodeNewGeometry")
    sepz = node(nt, "ShaderNodeSeparateXYZ")
    link(nt, geo.outputs["Position"], sepz.inputs[0])
    reveal = node(nt, "ShaderNodeValue", name="reveal", label="reveal")
    reveal.outputs[0].default_value = 100.0
    opacity = node(nt, "ShaderNodeValue", name="opacity", label="opacity")
    opacity.outputs[0].default_value = 1.0
    glow = node(nt, "ShaderNodeValue", name="glow", label="glow")
    glow.outputs[0].default_value = 0.0
    below = math_node(nt, "SUBTRACT", reveal.outputs[0], sepz.outputs["Z"])
    shown = smooth(nt, below, 0.0, 0.012)
    alpha = math_node(nt, "MULTIPLY", shown, opacity.outputs[0])
    band = math_node(nt, "MULTIPLY", smooth(nt, math_node(nt, "ABSOLUTE", below), 0.018, 0.0),
                     glow.outputs[0])  # fmt: skip
    em = node(nt, "ShaderNodeEmission")
    em.inputs["Color"].default_value = lin("fff3dc")
    link(nt, math_node(nt, "MULTIPLY", band, 6.0), em.inputs["Strength"])
    clear = node(nt, "ShaderNodeBsdfTransparent")
    mix = node(nt, "ShaderNodeMixShader")
    link(nt, alpha, mix.inputs[0])
    link(nt, clear.outputs[0], mix.inputs[1])
    link(nt, b.outputs[0], mix.inputs[2])
    add = node(nt, "ShaderNodeAddShader")
    link(nt, mix.outputs[0], add.inputs[0])
    link(nt, em.outputs[0], add.inputs[1])
    link(nt, add.outputs[0], out.inputs["Surface"])
    # computed, not yet fabric: a fine grid of lines on the surface while translucent
    grid_amt = math_node(nt, "SUBTRACT", 1.0, opacity.outputs[0])
    wave = node(nt, "ShaderNodeTexWave", wave_type="BANDS", bands_direction="Z")
    wave.inputs["Scale"].default_value = 12.0
    wave.inputs["Distortion"].default_value = 0.0
    link(nt, geo.outputs["Position"], wave.inputs["Vector"])
    lines = smooth(nt, wave.outputs["Fac"], 0.975, 0.995)
    em2 = node(nt, "ShaderNodeEmission")
    em2.inputs["Color"].default_value = lin("fff3dc")
    link(nt, math_node(nt, "MULTIPLY", math_node(nt, "MULTIPLY", lines, grid_amt),
                       math_node(nt, "MULTIPLY", shown, 0.6)),
         em2.inputs["Strength"])  # fmt: skip
    add2 = node(nt, "ShaderNodeAddShader")
    link(nt, add.outputs[0], add2.inputs[0])
    link(nt, em2.outputs[0], add2.inputs[1])
    link(nt, add2.outputs[0], out.inputs["Surface"])
    return m


CLOSE_UPS = {"st5", "sew", "vent"}  # shots that need the stitching at its full 0.35 mm a pixel


def seams_pic(a: argparse.Namespace) -> Path:
    """The stitching picture: full size for the close-ups; elsewhere half (0.7 mm a pixel,
    still finer than a pixel of the frame), which keeps a render under 9 GB of memory."""
    half = a.data / "seams-half.png"
    if a.shot in CLOSE_UPS or not half.is_file():
        return a.data / "seams.png"
    return half


def emissive(name: str, hexcol: str, strength: float) -> bpy.types.Material:
    """Drafting lines over the picture: a soft light colour, faded by an `alpha` value."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    out = nt.nodes["Material Output"]
    em = node(nt, "ShaderNodeEmission")
    em.inputs["Color"].default_value = lin(hexcol)
    em.inputs["Strength"].default_value = strength
    diffuse = nt.nodes["Principled BSDF"]
    diffuse.inputs["Base Color"].default_value = lin(hexcol)
    add = node(nt, "ShaderNodeAddShader")
    link(nt, em.outputs[0], add.inputs[0])
    link(nt, diffuse.outputs[0], add.inputs[1])
    alpha = node(nt, "ShaderNodeValue", name="alpha", label="alpha")
    alpha.outputs[0].default_value = 1.0
    mix = node(nt, "ShaderNodeMixShader")
    link(nt, alpha.outputs[0], mix.inputs[0])
    link(nt, node(nt, "ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
    link(nt, add.outputs[0], mix.inputs[2])
    link(nt, mix.outputs[0], out.inputs["Surface"])
    m["alpha"] = alpha.name
    return m


def faded(hexcol: str, rough: float, name: str, metal: float = 0.0) -> bpy.types.Material:
    """A plain material with an `alpha` value (labels that appear)."""
    m = rh.simple(name, hexcol, rough, metal)
    nt = m.node_tree
    alpha = node(nt, "ShaderNodeValue", name="alpha", label="alpha")
    alpha.outputs[0].default_value = 1.0
    mix = node(nt, "ShaderNodeMixShader")
    link(nt, alpha.outputs[0], mix.inputs[0])
    link(nt, node(nt, "ShaderNodeBsdfTransparent").outputs[0], mix.inputs[1])
    link(nt, nt.nodes["Principled BSDF"].outputs[0], mix.inputs[2])
    link(nt, mix.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
    return m


def set_value(mat: bpy.types.Material, name: str, v: float) -> None:
    n = mat.node_tree.nodes.get(name)
    if n is not None:
        n.outputs[0].default_value = float(v)


# ---- the cover as pieces (split at the seams) ----------------------------------------------
def pieces_mesh(d: dict, mat: bpy.types.Material, subsurf: int = 1) -> bpy.types.Object:
    me = bpy.data.meshes.new("pieces")
    me.from_pydata(d["design"].astype(float).tolist(), [], d["faces"].tolist())
    uvl = me.uv_layers.new(name="flat")
    uvl.data.foreach_set("uv", d["uv"][d["faces"].ravel()].astype(np.float32).ravel())
    me.attributes.new("stream", "FLOAT", "POINT")
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("pieces", me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(mat)
    th = ob.modifiers.new("thickness", "SOLIDIFY")
    th.thickness, th.offset = 0.0012, 1.0
    if subsurf:
        sub = ob.modifiers.new("smooth", "SUBSURF")
        sub.levels = sub.render_levels = subsurf
        sub.uv_smooth = "PRESERVE_BOUNDARIES"
        sub.use_limit_surface, sub.quality = False, 1  # see lean()
    return ob


def lean(ob: bpy.types.Object) -> bpy.types.Object:
    """The film's cover with its smoothing evaluated without the exact limit surface: the
    same look, 0.8 GB instead of 5.4 GB per cover (OpenSubdiv's patch tables on this sewn mesh),
    so a render fits next to the other work on the server."""
    sub = ob.modifiers.get("smooth")
    if sub is not None:
        sub.use_limit_surface, sub.quality = False, 1
    return ob


def set_points(ob: bpy.types.Object, co: np.ndarray) -> None:
    ob.data.vertices.foreach_set("co", co.astype(np.float32).ravel())
    ob.data.update()


class Morph:
    """Each piece from one shape to another as a piece of cloth would travel: turned and moved
    as a whole (the best rigid fit, slerped), its bending blended in, lifted on the way."""

    def __init__(self, src: np.ndarray, dst: np.ndarray, piece: np.ndarray) -> None:
        self.src, self.dst, self.piece = src, dst, piece
        self.parts = []
        for k in np.unique(piece):
            idx = np.flatnonzero(piece == k)
            s, t = src[idx], dst[idx]
            cs, ct = s.mean(axis=0), t.mean(axis=0)
            h = (s - cs).T @ (t - ct)
            u, _, vt = np.linalg.svd(h)
            dfix = np.diag([1.0, 1.0, np.sign(np.linalg.det(vt.T @ u.T)) or 1.0])
            r = vt.T @ dfix @ u.T
            q = Matrix(r.tolist()).to_quaternion()
            rest = t - ((s - cs) @ r.T + ct)
            self.parts.append((idx, cs, ct, q, rest))

    def at(self, ts: dict[int, float] | float, lift: float = 0.0) -> np.ndarray:
        out = np.empty_like(self.src)
        for k, (idx, cs, ct, q, rest) in zip(np.unique(self.piece), self.parts, strict=True):
            t = ts if isinstance(ts, float) else ts.get(int(k), 0.0)
            e = ease(t)
            r = np.array(Quaternion().slerp(q, e).to_matrix())
            c = cs + (ct - cs) * e + np.array([0, 0, lift * math.sin(math.pi * e)])
            out[idx] = (self.src[idx] - cs) @ r.T + c + rest * e
        return out


def apart(d: dict, how: float = 1.0) -> np.ndarray:
    """The designed pieces stepped apart from the middle, the top ones up."""
    des = d["design"].astype(float)
    mid = des.mean(axis=0)
    out = des.copy()
    for k in np.unique(d["piece"]):
        sel = d["piece"] == k
        c = des[sel].mean(axis=0) - mid
        out[sel] += c * np.array([0.22, 0.26, 0.0]) * how + np.array([0, 0, 0.06 + 0.14 * max(
            c[2], 0)]) * how  # fmt: skip
    return out


# ---- scenes -------------------------------------------------------------------------------
def terrace_scene(a: argparse.Namespace, sofa: bool = True):
    rh.render_settings(a)
    sky = rh.world(a)
    sun, stone = rh.terrace(a)
    if sofa:
        rh.furniture(a)
    return sky, sun, stone


def mood(sky, sun, sc, kind: str, k: float = 1.0) -> None:
    """The film's light: the hazy low sun, or the overcast of the rain (k: how far in)."""
    sunny = (4.5, 0.32, -0.35)
    rainy = (0.0, 0.7, 0.0)
    a, b = (sunny, rainy) if kind == "rain" else (rainy, sunny)
    v = [x + (y - x) * k for x, y in zip(a, b, strict=True)]
    sun.data.energy, sky.inputs["Strength"].default_value, sc.view_settings.exposure = v


def camera(lens: float, fstop: float, shift: float = 0.0, portrait: bool = False):
    sc = bpy.context.scene
    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    cam.data.lens = lens
    cam.data.sensor_width = 36
    cam.data.sensor_fit = "HORIZONTAL" if not portrait else "VERTICAL"
    if portrait:
        cam.data.sensor_height = 36
    cam.data.shift_x = shift
    cam.data.dof.use_dof = True
    cam.data.dof.aperture_fstop = fstop
    cam.data.dof.aperture_blades = 7
    cam.data.clip_start = 0.01
    aim = bpy.data.objects.new("aim", None)
    sc.collection.objects.link(aim)
    cam.data.dof.focus_object = aim
    tr = cam.constraints.new("TRACK_TO")
    tr.target = aim
    return cam, aim


def move(cam, aim, k: float, path, look) -> None:
    """The camera between its two keys, eased (k 0..1 over the shot)."""
    e = ease(k)
    cam.location = Vector(path[0]).lerp(Vector(path[1]), e)
    aim.location = Vector(look[0]).lerp(Vector(look[1]), e)


def text_obj(body: str, size: float, mat, at, rot=(0.0, 0.0, 0.0), font=None, align="CENTER"):
    cu = bpy.data.curves.new("t", "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = align
    if font is not None:
        cu.font = font
    ob = bpy.data.objects.new("t", cu)
    ob.location = at
    ob.rotation_euler = rot
    cu.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def polyline(pts, mat, radius: float, name="line", closed=False) -> bpy.types.Object:
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = radius
    cu.bevel_resolution = 2
    cu.use_fill_caps = True
    # drawn by length (bevel_factor_end: how far the pen or the knife has come)
    cu.bevel_factor_mapping_start = cu.bevel_factor_mapping_end = "SPLINE"
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for p, q in zip(sp.points, pts, strict=True):
        p.co = (q[0], q[1], q[2] if len(q) > 2 else 0.0, 1)
    sp.use_cyclic_u = closed
    ob = bpy.data.objects.new(name, cu)
    cu.materials.append(mat)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def furniture_box() -> tuple[Vector, Vector]:
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in bpy.context.scene.objects:
        if o.type != "MESH" or o.name in ("floor", "wall", "side") or o.name.startswith("pot"):
            continue
        if not o.data.materials or o.data.materials[0].name not in ("upholstery", "plinth"):
            continue
        for v in o.data.vertices:
            w = o.matrix_world @ v.co
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
    return lo, hi


class Dimensions:
    """The furniture's length, depth and height as drafting lines that draw themselves."""

    def __init__(self, a: argparse.Namespace) -> None:
        lo, hi = furniture_box()
        self.font = bpy.data.fonts.load(str(a.assets / "WorkSans.ttf"))
        self.mat = emissive("dimension", LINE, 2.2)
        off = 0.16
        y0, x0 = lo.y - off, lo.x - off
        z0 = 0.004
        tick = 0.05
        r = 0.0016
        mm = [round((hi.x - lo.x) * 100), round((hi.y - lo.y) * 100), round(hi.z * 100)]
        self.lines = [
            # length along the front, on the stone
            ([(lo.x, y0, z0), (hi.x, y0, z0)],
             [[(lo.x, lo.y - 0.03, z0), (lo.x, y0 - tick, z0)],
              [(hi.x, lo.y - 0.03, z0), (hi.x, y0 - tick, z0)]],
             (f"{mm[0]} cm", ((lo.x + hi.x) / 2, y0, z0 + 0.025), (math.radians(90), 0, 0))),
            # depth along the left side
            ([(x0, lo.y, z0), (x0, hi.y, z0)],
             [[(lo.x - 0.03, lo.y, z0), (x0 - tick, lo.y, z0)],
              [(lo.x - 0.03, hi.y, z0), (x0 - tick, hi.y, z0)]],
             (f"{mm[1]} cm", (x0, (lo.y + hi.y) / 2, z0 + 0.025),
              (math.radians(90), 0, math.radians(-90)))),
            # height, upright at the front left corner
            ([(x0, y0, z0), (x0, y0, hi.z)],
             [[(x0 - tick, y0, hi.z), (lo.x + 0.1, y0, hi.z)]],
             (f"{mm[2]} cm", (x0 - 0.035, y0, hi.z / 2), (math.radians(90), 0, 0))),
        ]  # fmt: skip
        self.obs = []
        for main, ticks, (label, at, rot) in self.lines:
            ob = polyline(main, self.mat, r, "dim")
            tks = [polyline(t, self.mat, r * 0.8, "tick") for t in ticks]
            tm = emissive("dimlabel", LINE, 2.2)
            right = "cm" in label and at[2] > 0.1  # the height: beside its line, to the left
            tx = text_obj(label, 0.07, tm, at, rot, self.font, "RIGHT" if right else "CENTER")
            self.obs.append((ob, tks, tx, tm))

    def at(self, f: float, start: float, each: float, gap: float) -> None:
        for i, (ob, tks, tx, tm) in enumerate(self.obs):
            k0 = start + i * gap
            for t in tks:
                t.data.bevel_factor_end = max(ramp(f, k0, k0 + each * 0.35), 1e-3)
            ob.data.bevel_factor_end = max(ramp(f, k0 + each * 0.2, k0 + each), 1e-3)
            set_value(tm, "alpha", ramp(f, k0 + each * 0.6, k0 + each * 1.2))
            hide = f < k0
            for o in (ob, tx, *tks):
                o.hide_render = hide


# ---- the workshop: the roll on the cutting table -------------------------------------------
class Roll:
    """The 152 cm roll unrolled on the felt of the cutting table: the pieces land on their
    places in the nest (reel.json), the pen writes their labels and lines, the knife cuts."""

    def __init__(self, a: argparse.Namespace, reel: dict, fabric_flat) -> None:
        r = reel["roll"]
        self.r = r
        L, W = r["length"], r["width"]
        self.origin = WORK_AT + Vector((-L / 2, -W / 2, TABLE_Z + 0.0016))
        top = WORK_AT + Vector((0, 0, TABLE_Z / 2))
        bpy.ops.mesh.primitive_cube_add(size=1, location=top)
        t = bpy.context.object
        t.name = "table"
        t.scale = (L + 1.6, W + 0.9, TABLE_Z)
        bpy.ops.object.transform_apply(scale=True)
        felt = rh.simple("felt", rh.FELT, 0.95)
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
        # the fabric off the roll: one long sheet, the roll itself at the far end
        bpy.ops.mesh.primitive_plane_add(size=1)
        sheet = bpy.context.object
        sheet.name = "sheet"
        sheet.scale = (L + 0.35, W, 1)
        bpy.ops.object.transform_apply(scale=True)
        sheet.location = self.origin + Vector(((L + 0.35) / 2 - 0.05, W / 2, -0.0004))
        sheet.data.materials.append(fabric_flat)
        sheet.modifiers.new("t", "SOLIDIFY").thickness = 0.0012
        at = self.origin + Vector((L + 0.42, W / 2, 0.1))
        bpy.ops.mesh.primitive_cylinder_add(radius=0.1, depth=W, location=at,
                                            rotation=(math.pi / 2, 0, 0), vertices=96)  # fmt: skip
        roll = bpy.context.object
        roll.data.materials.append(fabric_flat)
        for p in roll.data.polygons:
            p.use_smooth = True
        core = rh.simple("core", "8a6d4a", 0.8)
        bpy.ops.mesh.primitive_cylinder_add(radius=0.04, depth=W + 0.03, location=at,
                                            rotation=(math.pi / 2, 0, 0), vertices=48)  # fmt: skip
        bpy.context.object.data.materials.append(core)
        self.kerf = rh.simple("kerf", KERF, 0.9)
        self.ink = rh.simple("ink", INK, 0.6)
        self.groups = sorted({c["group"] for c in r["cut"]})
        self.cuts, self.pens, self.texts = [], [], []
        o = self.origin
        for c in r["cut"]:
            pts = [(o.x + x, o.y + y, o.z + 0.0003) for x, y in c["line"]]
            ob = polyline(pts, self.kerf, 0.0006, "cut", closed=True)
            ob.scale.z = 0.4
            self.cuts.append((c["group"], ob))
        for p in r["pen"]:
            pts = [(o.x + x, o.y + y, o.z + 0.0042) for x, y in p["line"]]
            self.pens.append((p["group"], polyline(pts, self.ink, 0.00035, "pen")))
        self.text_mats = {}
        for t in r["text"]:
            g = t["group"]
            if g not in self.text_mats:
                self.text_mats[g] = faded(INK, 0.6, f"label{g}")
            cu = bpy.data.curves.new("label", "FONT")
            cu.body = t["text"]
            cu.size = t["h"] * 1.4
            ob = bpy.data.objects.new("label", cu)
            ob.location = o + Vector((t["at"][0], t["at"][1], 0.0042))
            ob.rotation_euler.z = math.radians(t["rot"])
            cu.materials.append(self.text_mats[g])
            bpy.context.scene.collection.objects.link(ob)
            self.texts.append((g, ob))

    def flat(self, d: dict) -> np.ndarray:
        """Every sewn piece's flat pattern at its place on the roll (world, metres)."""
        out = d["design"].astype(float).copy()
        for k, tr in self.r["pieces"].items():
            sel = d["piece"] == int(k)
            p = d["uv"][sel].astype(float) @ np.asarray(tr["A"]).T + np.asarray(tr["b"])
            out[sel, 0] = self.origin.x + p[:, 0]
            out[sel, 1] = self.origin.y + p[:, 1]
            out[sel, 2] = self.origin.z + 0.0008
        return out

    def at(self, pen: float, cut: float) -> None:
        """How far the pen (0..1) and the knife (0..1) have come, group after group."""
        n = len(self.groups)

        def share(k: float, g: int) -> float:
            i = self.groups.index(g)
            return min(max(k * n - i, 0.0), 1.0)

        for g, ob in self.pens:
            s = share(pen, g)
            ob.data.bevel_factor_end = max(s, 1e-3)
            ob.hide_render = s <= 0
        for g, mat in self.text_mats.items():
            set_value(mat, "alpha", ease(share(pen, g) * 1.4 - 0.3))
        for g, ob in self.texts:
            ob.hide_render = share(pen, g) <= 0.2
        for g, ob in self.cuts:
            s = share(cut, g)
            ob.data.bevel_factor_end = max(s, 1e-3)
            ob.hide_render = s <= 0


def workshop_light(a: argparse.Namespace | None = None) -> None:
    """The workshop: a long soft light over the table; with the assets, a concrete floor and a
    pale plastered wall behind, so no shot looks into the void."""
    sc = bpy.context.scene
    if a is not None:
        floor = rh.pbr("concrete", a.assets / "concrete_floor_02", 3.0, normal=0.5)
        bpy.ops.mesh.primitive_plane_add(size=40, location=WORK_AT)
        bpy.context.object.data.materials.append(floor)
        wall = rh.pbr("workshop-wall", a.assets / "white_plaster_02", 2.0,
                      tint=tuple(1.7 * c for c in lin("e2ddd2")), normal=0.4)  # fmt: skip
        rh.box("back", WORK_AT + Vector((0, 3.4, 2.0)), (16, 0.2, 4.0), wall)
    lt = bpy.data.lights.new("bay", "AREA")
    lt.shape, lt.size, lt.size_y, lt.energy = "RECTANGLE", 6, 2.5, 650
    lt.color = (1.0, 0.97, 0.92)
    lo = bpy.data.objects.new("bay", lt)
    lo.location = WORK_AT + Vector((0, 0.6, TABLE_Z + 2.6))
    lo.rotation_euler = (math.radians(-12), 0, 0)
    sc.collection.objects.link(lo)
    lo.visible_camera = False


# ---- the rain on the cover, without falling drops ------------------------------------------
class Runs(rh.Runoff):
    """The film's runoff, the drops kept on the cloth (they gather at the hem and stay, they do
    not fall): what is baked into a scrubbed picture must look right when the scroll runs
    backwards, and a drop falling from the hem would rise."""

    def at(self, t: float):
        where, scale, dirs = [], [], []
        wet = np.zeros(len(self.pos))
        r = self.RADIUS
        for k, ((p, s), (pts, along)) in enumerate(zip(self.paths, self.wet_by, strict=True)):
            dist = (t - self.t0[k]) * self.SPEED
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
            else:  # gathered at the hem's edge, hanging a little
                grow = 1.0 + 0.4 * min((dist - s[-1]) / self.SPEED / self.HANG, 1.0)
                where.append(p[-1] - (0, 0, size * 0.6 * grow))
                dirs.append(np.array([0.0, 0.0, -1.0]))
                scale.append((size * grow, size * 1.3 * grow, size * grow))
        return np.array(where), np.array(scale), np.array(dirs), wet


# ---- the air vent's hood -------------------------------------------------------------------
def vent_hood(v: dict, mat_cover, depth: float = 0.05) -> list[bpy.types.Object]:
    """The vent as we make it: an opening under a hood of the same fabric, sewn on at its top
    and sides, held open by a plastic insert; a dark mesh membrane behind against dirt."""
    c, n, up = (Vector(v[k]) for k in ("centre", "normal", "up"))
    side = up.cross(n).normalized()
    w, h = v["size"]
    out = []
    # the hood: a shell from the top seam out and down, its sides closed
    me = bpy.data.meshes.new("hood")
    rows, cols = 10, 24
    verts = []
    for i in range(rows + 1):
        s = i / rows  # 0 at the top seam, 1 at the open lower edge
        out_ = depth * math.sin(s * math.pi / 2) ** 1.3
        for j in range(cols + 1):
            u = j / cols - 0.5
            cap = 1.0 - (2 * abs(u)) ** 6  # the sides close in
            p = c + up * (h / 2 - s * h * 1.02) + side * (u * w) + n * (0.002 + out_ * cap)
            verts.append(p)
    faces = [(i * (cols + 1) + j, i * (cols + 1) + j + 1, (i + 1) * (cols + 1) + j + 1,
              (i + 1) * (cols + 1) + j) for i in range(rows) for j in range(cols)]  # fmt: skip
    me.from_pydata([tuple(p) for p in verts], [], faces)
    uvl = me.uv_layers.new(name="flat")
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            uvl.data[li].uv = ((vi % (cols + 1)) / cols * w, (vi // (cols + 1)) / rows * h)
    me.attributes.new("stream", "FLOAT", "POINT")
    for p in me.polygons:
        p.use_smooth = True
    hood = bpy.data.objects.new("hood", me)
    bpy.context.scene.collection.objects.link(hood)
    me.materials.append(mat_cover)
    hood.modifiers.new("t", "SOLIDIFY").thickness = 0.0012
    sub = hood.modifiers.new("s", "SUBSURF")
    sub.levels = sub.render_levels = 1
    out.append(hood)
    # the opening behind it: a dark mesh membrane
    mesh_mat = rh.simple("membrane", "1d1f1e", 0.7)
    mn = mesh_mat.node_tree
    tc = node(mn, "ShaderNodeTexCoord")
    grid = node(mn, "ShaderNodeTexBrick")
    grid.inputs["Scale"].default_value = 160.0
    grid.inputs["Mortar Size"].default_value = 0.25
    grid.offset = 0.0
    grid.inputs["Color1"].default_value = lin("0b0c0c")
    grid.inputs["Color2"].default_value = lin("0b0c0c")
    grid.inputs["Mortar"].default_value = lin("3a3d3b")
    link(mn, tc.outputs["Object"], grid.inputs["Vector"])
    link(mn, grid.outputs["Color"], mn.nodes["Principled BSDF"].inputs["Base Color"])
    bpy.ops.mesh.primitive_plane_add(size=1)
    hole = bpy.context.object
    hole.name = "membrane"
    hole.scale = (w * 0.9, h * 0.86, 1)
    hole.rotation_euler = Matrix((side, up, n)).transposed().to_euler()
    hole.location = c + n * 0.0015 - up * 0.01
    hole.data.materials.append(mesh_mat)
    out.append(hole)
    # the insert: a grey plastic bow along the hood's open edge, holding it out
    plastic = rh.simple("insert", "6f7270", 0.45)
    pts = []
    for j in range(25):
        u = j / 24 - 0.5
        cap = 1.0 - (2 * abs(u)) ** 6
        pts.append(tuple(c - up * (h / 2 + 0.002) + side * (u * w * 0.94) + n * (0.004 + (depth
                         - 0.006) * cap)))  # fmt: skip
    out.append(polyline(pts, plastic, 0.0032, "insert"))
    return out


# ---- the shots ----------------------------------------------------------------------------
TERRACE_LOOK = (0.25, 0.0, 0.38)


def shot_st1(a, d, reel):
    sky, sun, stone = terrace_scene(a)
    dims = Dimensions(a)
    cam, aim = camera(42, 5.6, shift=-0.1)
    path = [(-2.75, -3.95, 1.0), (-2.15, -4.15, 0.92)]
    look = [(0.15, 0.0, 0.4), (0.25, 0.0, 0.38)]
    sc = bpy.context.scene
    mood(sky, sun, sc, "sun")

    def frame(f, n):
        move(cam, aim, (f - 1) / (n - 1), path, look)
        dims.at(f, 6, 22, 9)

    return frame


def shot_st2(a, d, reel):
    sky, sun, stone = terrace_scene(a)
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    cov = lean(rh.cover(d, mat))
    set_points(cov, rh.welded(d, d["design"].astype(float)))
    cam, aim = camera(42, 5.6, shift=-0.1)
    path = [(-2.15, -4.15, 0.92), (-1.2, -4.35, 1.15)]
    look = [(0.25, 0.0, 0.38), (0.3, 0.0, 0.42)]
    top = float(d["design"][:, 2].max())
    sc = bpy.context.scene
    mood(sky, sun, sc, "sun")

    def frame(f, n):
        move(cam, aim, (f - 1) / (n - 1), path, look)
        k = ramp(f, 4, 40)
        set_value(mat, "reveal", -0.02 + (top + 0.05) * k)
        set_value(mat, "glow", 1.0 - ramp(f, 38, 46))
        set_value(mat, "opacity", 0.32 + 0.68 * ramp(f, 34, 54))
        set_value(mat, "stitched", ramp(f, 40, 56))

    return frame


def shot_st3(a, d, reel):
    sky, sun, stone = terrace_scene(a)
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    ob = pieces_mesh(d, mat)
    des = d["design"].astype(float)
    far = apart(d)
    cam, aim = camera(40, 5.6, shift=-0.1)
    path = [(-1.2, -4.35, 1.15), (0.9, -4.2, 1.75)]
    look = [(0.3, 0.0, 0.42), (0.2, 0.05, 0.5)]
    sc = bpy.context.scene
    mood(sky, sun, sc, "sun")
    ks = np.unique(d["piece"])
    high_first = sorted(ks, key=lambda k: -des[d["piece"] == k][:, 2].mean())
    order = {int(k): i for i, k in enumerate(high_first)}

    def frame(f, n):
        move(cam, aim, (f - 1) / (n - 1), path, look)
        co = des.copy()
        for k, i in order.items():
            sel = d["piece"] == k
            e = ramp(f, 6 + 3 * i, 30 + 3 * i)
            co[sel] = des[sel] + (far[sel] - des[sel]) * e
        set_points(ob, co)

    return frame


def shot_st4(a, d, reel):
    rh.render_settings(a)
    sky = rh.world(a)
    sky.inputs["Strength"].default_value = 0.3
    bpy.context.scene.view_settings.exposure = -0.6
    workshop_light(a)
    flat_mat = fabric(a.assets, None, name="roll-fabric")
    roll = Roll(a, reel, flat_mat)
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    ob = pieces_mesh(d, mat, subsurf=0)
    src = apart(d)
    mid = src.mean(axis=0)
    src = src - mid + np.array([WORK_AT.x, WORK_AT.y - 0.1, TABLE_Z + 1.0])
    dst = roll.flat(d)
    morph = Morph(src, dst, d["piece"])
    L = reel["roll"]["length"]
    cam, aim = camera(30, 5.6, shift=0.0)
    path = [WORK_AT + Vector((-0.4, -3.9, TABLE_Z + 2.3)), WORK_AT + Vector((0.3, -3.2, 2.9))]
    look = [WORK_AT + Vector((0.0, 0.25, TABLE_Z + 0.35)), WORK_AT + Vector((0.2, 0.3, TABLE_Z))]
    ks = sorted(int(k) for k in np.unique(d["piece"]))
    _ = L

    def frame(f, n):
        move(cam, aim, (f - 1) / (n - 1), path, look)
        ts = {k: ramp(f, 3 + 4 * i, 24 + 4 * i) for i, k in enumerate(ks)}
        set_points(ob, morph.at(ts, lift=0.12))
        set_value(mat, "stitched", 1.0 - ramp(f, 6, 26))
        roll.at(ramp(f, 34, 50), ramp(f, 46, 60))

    return frame


def shot_st5(a, d, reel):
    sky, sun, stone = terrace_scene(a)
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    cov = lean(rh.cover(d, mat))
    final = rh.welded(d, d["frames"][-1].astype(float))
    fall_path = a.data / "fall.npz"
    fall = np.load(fall_path)["frames"] if fall_path.is_file() else None
    cam, aim = camera(70, 5.6, shift=-0.04)
    sc = bpy.context.scene
    mood(sky, sun, sc, "sun")
    seam_path = [(-1.5, -1.3, 0.56), (-1.0, -1.45, 0.5)]
    seam_look = [(-0.82, -0.56, 0.26), (-0.55, -0.6, 0.27)]
    on_path = [(-2.35, -2.75, 0.78), (-2.1, -2.5, 0.7)]
    on_look = [(-0.1, -0.3, 0.45), (-0.12, -0.3, 0.42)]
    CUT = 20

    def frame(f, n):
        if f <= CUT:
            cam.data.lens, cam.data.shift_x = 70, -0.04
            move(cam, aim, (f - 1) / (CUT - 1), seam_path, seam_look)
            co = final
        else:
            cam.data.lens, cam.data.shift_x = 35, -0.08
            k = (f - CUT - 1) / (n - CUT - 1)
            move(cam, aim, k, on_path, on_look)
            if fall is not None:
                kk = min(k / 0.9, 1.0)
                i = min(int(round(kk * (len(fall) - 1))), len(fall) - 1)
                blend = ease((kk - 0.72) / 0.28)
                co = fall[i] * (1 - blend) + final * blend
            else:
                co = final
        set_points(cov, co)

    return frame


def shot_st6(a, d, reel):
    sky, sun, stone = terrace_scene(a)
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    cov = lean(rh.cover(d, mat))
    final = rh.welded(d, d["frames"][-1].astype(float))
    set_points(cov, final)
    normals = np.zeros(len(final) * 3)
    cov.data.vertices.foreach_get("normal", normals)
    run = Runs(d, d["frames"][-1].astype(float), normals.reshape(-1, 3)[d["weld"]])
    sky_, runners = rain_parts()
    stream = cov.data.attributes["stream"]
    wet_stone = stone.node_tree.nodes["wet"].outputs[0]
    cam, aim = camera(45, 4.5, shift=-0.06)
    path = [(2.05, -2.85, 0.66), (1.7, -2.4, 0.58)]
    look = [(0.05, -0.33, 0.37), (0.05, -0.38, 0.35)]
    sc = bpy.context.scene

    def frame(f, n):
        move(cam, aim, (f - 1) / (n - 1), path, look)
        k = ramp(f, 1, 14)
        mood(sky, sun, sc, "rain", k)
        t = max(f - 6, 0) / (n - 6) * 7.0  # seconds of rain
        wet_stone.default_value = 0.85 * ramp(f, 3, 40)
        set_value(mat, "wet", min(t / 2.0, 1.0))
        where, sizes, dirs, wet = run.at(t)
        rh.set_runners(runners, where, sizes, dirs)
        wet_sewn = np.zeros(len(final))
        np.maximum.at(wet_sewn, d["weld"], wet)
        stream.data.foreach_set("value", wet_sewn.astype(np.float32))

    return frame


def rain_parts():
    """The film's rain objects; the falling rain's particles off (they are hidden here)."""
    sky, runners = rh.rain()
    bpy.data.objects.remove(sky)
    return None, runners


# ---- the clips -----------------------------------------------------------------------------
def draped(d: dict) -> np.ndarray:
    """The Style3D drape on the sewn points."""
    return rh.welded(d, d["frames"][-1].astype(float))


def seam_line(d: dict, a: str, others: tuple[str, ...]) -> np.ndarray:
    """The seam between piece `a` and the `others` on the draped cover, from the hem up."""
    names = [str(n).lower() for n in d["names"]]
    wa = set(d["weld"][d["piece"] == names.index(a)].tolist())
    wb: set[int] = set()
    for o in others:
        wb |= set(d["weld"][d["piece"] == names.index(o)].tolist())
    ids = np.array(sorted(wa & wb))
    p = draped(d)[ids]
    # walk it from the lowest point, always to the nearest unvisited point
    left = list(range(len(p)))
    cur = int(np.argmin(p[:, 2]))
    order = [cur]
    left.remove(cur)
    while left:
        q = np.array(left)
        cur = int(q[np.argmin(np.linalg.norm(p[q] - p[cur], axis=1))])
        order.append(cur)
        left.remove(cur)
    line = p[order]
    for _ in range(3):  # smoothed: the camera glides
        line[1:-1] = 0.25 * line[:-2] + 0.5 * line[1:-1] + 0.25 * line[2:]
    return line


def along(line: np.ndarray, k: float) -> Vector:
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(line, axis=0), axis=1))])
    x = min(max(k, 0.0), 1.0) * s[-1]
    i = int(min(np.searchsorted(s, x), len(s) - 1))
    i = max(i, 1)
    f = (x - s[i - 1]) / max(s[i] - s[i - 1], 1e-9)
    return Vector(line[i - 1] + (line[i] - line[i - 1]) * f)


def hood_material(assets: Path, w: float, h: float) -> bpy.types.Material:
    """The hood's fabric: the plain Coverlast, its top and sides stitched (two rows on top)."""
    m = rh.coverlast(assets, None)
    m.name = "hood"
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    uv = node(nt, "ShaderNodeUVMap", uv_map="flat").outputs["UV"]
    sep = node(nt, "ShaderNodeSeparateXYZ")
    link(nt, uv, sep.inputs[0])
    u, v = sep.outputs["X"], sep.outputs["Y"]

    def row(coord, at, along_):
        d = math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", coord, at))
        line = smooth(nt, d, 0.0007, 0.0)
        phase = math_node(nt, "FRACT", math_node(nt, "DIVIDE", along_, 0.0045))
        dash = smooth(nt, math_node(nt, "ABSOLUTE", math_node(nt, "SUBTRACT", phase, 0.4)),
                      0.38, 0.28)  # fmt: skip
        return math_node(nt, "MULTIPLY", line, dash)

    t = row(v, 0.006, u)
    t = math_node(nt, "MAXIMUM", t, row(v, 0.012, u))
    t = math_node(nt, "MAXIMUM", t, row(u, 0.007, v))
    t = math_node(nt, "MAXIMUM", t, row(u, w - 0.007, v))
    base_in = b.inputs["Base Color"].links[0].from_socket
    mix = node(nt, "ShaderNodeMix", data_type="RGBA")
    link(nt, t, mix.inputs[0])
    link(nt, base_in, mix.inputs[6])
    mix.inputs[7].default_value = lin(rh.THREAD)
    link(nt, mix.outputs[2], b.inputs["Base Color"])
    bump = node(nt, "ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.8
    bump.inputs["Distance"].default_value = 0.0006
    link(nt, t, bump.inputs["Height"])
    old = b.inputs["Normal"].links[0].from_socket if b.inputs["Normal"].links else None
    if old is not None:
        link(nt, old, bump.inputs["Normal"])
    link(nt, bump.outputs["Normal"], b.inputs["Normal"])
    _ = h
    return m


def knife_head() -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    """The cutting head, seen close: a brushed aluminium body, a black collar, the blade."""
    alu = rh.simple("alu", "c4c7c9", 0.28, 1.0)
    alu.node_tree.nodes["Principled BSDF"].inputs["Anisotropic"].default_value = 0.7
    black = rh.simple("anodised", "1b1c1e", 0.35, 0.6)
    steel = rh.simple("steel", "d7dadc", 0.15, 1.0)
    root = bpy.data.objects.new("head", None)
    bpy.context.scene.collection.objects.link(root)
    parts = []
    for r, z0, z1, mat, bevel in ((0.034, 0.045, 0.22, alu, 0.004), (0.026, 0.024, 0.047, black,
                                  0.002), (0.008, 0.006, 0.026, steel, 0.0008)):  # fmt: skip
        bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=z1 - z0, vertices=64,
                                            location=(0, 0, (z0 + z1) / 2))  # fmt: skip
        ob = bpy.context.object
        ob.data.materials.append(mat)
        bv = ob.modifiers.new("b", "BEVEL")
        bv.width, bv.segments = bevel, 3
        for p in ob.data.polygons:
            p.use_smooth = True
        ob.parent = root
        parts.append(ob)
    # the blade: a thin steel wedge, its point on the fabric
    me = bpy.data.meshes.new("blade")
    t = 0.0004
    v = [(-0.004, -t, 0.007), (0.004, -t, 0.007), (0.0015, -t, 0.0003), (-0.004, t, 0.007),
         (0.004, t, 0.007), (0.0015, t, 0.0003)]  # fmt: skip
    me.from_pydata(v, [], [(0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)])
    blade = bpy.data.objects.new("blade", me)
    bpy.context.scene.collection.objects.link(blade)
    me.materials.append(steel)
    blade.parent = root
    parts.append(blade)
    return root, parts


def shot_cut(a, d, reel):
    rh.render_settings(a)
    sky = rh.world(a)
    sky.inputs["Strength"].default_value = 0.3
    bpy.context.scene.view_settings.exposure = -0.5
    workshop_light(a)
    flat_mat = fabric(a.assets, None, name="roll-fabric")
    roll = Roll(a, reel, flat_mat)
    roll.at(1.0, 1.0)  # everything drawn and cut ...
    # ... but the top's outline, which the knife is cutting now
    names = [str(n).lower() for n in d["names"]]
    top = max(range(len(names)), key=lambda k: (d["piece"] == k).sum())  # the largest piece
    group = int(reel["roll"]["pieces"][str(top)]["group"])
    line = np.asarray(reel["roll"]["cut"][group]["line"])
    o = roll.origin
    seg = np.vstack([line, line[:1]])
    lens_ = np.linalg.norm(np.diff(seg, axis=0), axis=1)
    j = int(np.argmax(lens_))  # its longest straight edge
    a0, a1 = seg[j], seg[j + 1]
    start = a0 + (a1 - a0) * 0.15
    path3 = [(o.x + x, o.y + y, o.z + 0.0004) for x, y in (start, a1)]
    live = polyline(path3, roll.kerf, 0.0009, "live")
    live.scale.z = 0.4
    roll.cuts[group][1].hide_render = True  # its kerf is the live one
    head, _ = knife_head()
    dirv = Vector((*(a1 - a0), 0)).normalized()
    side = Vector((-dirv.y, dirv.x, 0))
    head.rotation_euler.z = math.atan2(dirv.y, dirv.x)
    cam, aim = camera(55, 5.6, portrait=True)
    run = 0.9  # metres the knife cuts in the clip
    total = float(np.linalg.norm(a1 - start))

    def frame(f, n):
        k = (f - 1) / (n - 1)
        frac = min(k * run / total, 1.0)
        live.data.bevel_factor_end = max(frac, 1e-3)
        p = Vector(path3[0]).lerp(Vector(path3[1]), frac)
        head.location = p
        cam.location = p - dirv * 0.38 - side * 0.32 + Vector((0, 0, 0.2))
        aim.location = p + dirv * 0.05 + Vector((0, 0, 0.012))

    return frame


def shot_sew(a, d, reel):
    sky, sun, stone = terrace_scene(a)
    mood(sky, sun, bpy.context.scene, "sun")
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    cov = lean(rh.cover(d, mat))
    set_points(cov, draped(d))
    line = seam_line(d, "skirt-left", ("skirt-front", "top-1"))
    centre = Vector(draped(d).mean(axis=0))
    cam, aim = camera(100, 4.0, portrait=True)

    def frame(f, n):
        k = 0.02 + 0.5 * ease((f - 1) / (n - 1))
        p = along(line, k)
        out = Vector((p.x - centre.x, p.y - centre.y, 0)).normalized()
        front = Vector((0, -1, 0))
        view = (out + front).normalized()
        cam.location = p + view * 0.42 + Vector((0, 0, 0.12))
        aim.location = p

    return frame


def shot_vent(a, d, reel):
    sky, sun, stone = terrace_scene(a)
    mood(sky, sun, bpy.context.scene, "sun")
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    cov = lean(rh.cover(d, mat))
    set_points(cov, draped(d))
    vents = reel.get("vents", [])
    v = next((x for x in vents if x["piece"] == "skirt-left"), vents[0])
    vent_hood(v, hood_material(a.assets, *v["size"]), depth=0.075)
    c, n = Vector(v["centre"]), Vector(v["normal"])
    side = Vector(v["up"]).cross(n).normalized()
    cam, aim = camera(70, 3.5, portrait=True)

    def frame(f, n_):
        k = ease((f - 1) / (n_ - 1))
        sweep = -0.5 + 0.7 * k
        cam.location = c + n * 0.55 + side * (0.42 + 0.25 * sweep) + Vector((0, 0, -0.12))
        aim.location = c + Vector((0, 0, -0.07))

    return frame


def shot_fit(a, d, reel):
    sky, sun, stone = terrace_scene(a)
    mood(sky, sun, bpy.context.scene, "sun")
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    cov = lean(rh.cover(d, mat))
    final = draped(d)
    fall = np.load(a.data / "fall.npz")["frames"]
    cam, aim = camera(32, 5.6, portrait=True)
    path = [(1.85, -2.6, 0.55), (1.6, -2.35, 0.5)]
    look = [(0.0, -0.15, 0.62), (0.0, -0.15, 0.5)]

    def frame(f, n):
        k = (f - 1) / (n - 1)
        move(cam, aim, k, path, look)
        kk = min(k / 0.72, 1.0)
        i = min(int(round(kk * (len(fall) - 1))), len(fall) - 1)
        blend = ease((kk - 0.72) / 0.28)
        set_points(cov, fall[i] * (1 - blend) + final * blend)

    return frame


def shot_runoff(a, d, reel):
    sky, sun, stone = terrace_scene(a)
    sc = bpy.context.scene
    mood(sky, sun, sc, "rain")
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    cov = lean(rh.cover(d, mat))
    final = draped(d)
    set_points(cov, final)
    normals = np.zeros(len(final) * 3)
    cov.data.vertices.foreach_get("normal", normals)
    run = rh.Runoff(d, d["frames"][-1].astype(float), normals.reshape(-1, 3)[d["weld"]])
    rain_sky, runners = rh.rain()
    stream = cov.data.attributes["stream"]
    stone.node_tree.nodes["wet"].outputs[0].default_value = 0.85
    set_value(mat, "wet", 1.0)
    cam, aim = camera(60, 3.2, portrait=True)
    path = [(1.25, -1.5, 0.78), (1.1, -1.35, 0.74)]
    look = [(0.35, -0.42, 0.42), (0.3, -0.45, 0.4)]
    r0, _ = rh.span("rain")
    sc.frame_set(r0 - 30)
    bpy.ops.ptcache.bake_all(bake=True)
    sc.render.use_motion_blur = True
    sc.render.motion_blur_shutter = 0.5

    def frame(f, n):
        sc.frame_set(r0 + int(f) % 100)  # the falling rain in its steady state
        move(cam, aim, (f - 1) / (n - 1), path, look)
        t = 2.5 + (f - 1) / 24.0
        where, sizes, dirs, wet = run.at(t)
        rh.set_runners(runners, where, sizes, dirs)
        w = np.zeros(len(final))
        np.maximum.at(w, d["weld"], wet)
        stream.data.foreach_set("value", w.astype(np.float32))

    return frame


def other_cover(a, name: str, folder: Path, at: Vector, turn: float) -> None:
    """Another catalogue model under its own cover (its own data folder), placed on the
    terrace."""
    od = dict(np.load(folder / "cover.npz"))
    bpy.ops.import_scene.gltf(filepath=str(folder / "furniture.glb"))
    imported = list(bpy.context.selected_objects)
    parts = [o for o in imported if o.type == "MESH"]
    up = bpy.data.materials.get("upholstery")
    for o in parts:
        o.data.materials.clear()
        o.data.materials.append(up)
    # seen from further away: the stitching picture at a third of its size (1 mm a pixel), so
    # three covers' pictures fit in memory (seams-small.png, made beside seams.png)
    small = folder / "seams-small.png"
    seams = small if small.is_file() else folder / "seams.png"
    mat = fabric(a.assets, seams, tuple(od["uv_size"]), name=f"cover-{name}")
    cov = lean(rh.cover(od, mat))
    set_points(cov, draped(od))
    holder = bpy.data.objects.new(f"place-{name}", None)
    bpy.context.scene.collection.objects.link(holder)
    for o in [*imported, cov]:
        if o.parent is None:
            o.parent = holder
    holder.location = at
    holder.rotation_euler.z = turn


def shot_range(a, d, reel):
    sky, sun, stone = terrace_scene(a)
    mood(sky, sun, bpy.context.scene, "sun")
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    cov = lean(rh.cover(d, mat))
    set_points(cov, draped(d))
    places = [Vector((2.6, 0.2, 0.0)), Vector((-2.9, 0.1, 0.0)), Vector((5.6, 0.1, 0.0))]
    for (name, folder), at in zip([m.split("=", 1) for m in a.more], places, strict=False):
        other_cover(a, name, Path(folder), at, 0.0)
    cam, aim = camera(40, 5.6, portrait=True)
    path = [(-3.0, -4.6, 1.05), (2.4, -4.6, 1.05)]
    look = [(-2.9, 0.0, 0.4), (2.5, 0.0, 0.4)]

    def frame(f, n):
        move(cam, aim, (f - 1) / (n - 1), path, look)

    return frame


# ---- Ibiza: a whitewashed villa terrace over the sea ---------------------------------------
SUN_AZ = 330.0  # the sun's direction (the Nishita sky's rotation): ahead, to the left, over the sea


def ibiza_scene(a: argparse.Namespace):
    """Late afternoon on a villa terrace on Ibiza: terracotta tiles, whitewashed walls and a
    low parapet, a wooden pergola throwing its slatted shade, the sea to the horizon and a rock
    island in the haze; the sun low and warm."""
    sc = bpy.context.scene
    rh.render_settings(a)
    sc.view_settings.look = "AgX - Base Contrast"
    sc.view_settings.exposure = -0.2
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    sky = node(nt, "ShaderNodeTexSky", sky_type="NISHITA")
    sky.sun_elevation = math.radians(9.0)
    sky.sun_rotation = math.radians(SUN_AZ)
    sky.altitude = 60.0
    sky.air_density, sky.dust_density, sky.ozone_density = 1.0, 1.2, 1.0
    sky.sun_size = math.radians(1.2)
    sky.sun_intensity = 0.6
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.45
    link(nt, sky.outputs[0], bg.inputs["Color"])
    sun = bpy.data.lights.new("sun", "SUN")
    sun.energy, sun.angle = 6.5, math.radians(1.0)
    sun.color = (1.0, 0.8, 0.6)
    so = bpy.data.objects.new("sun", sun)
    el, az = math.radians(9.0), math.radians(SUN_AZ)
    d = Vector((math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el)))
    so.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(so)
    haze = lin("e9c9a3")

    def far(mat_name: str, hexcol: str, rough: float, fade: float) -> bpy.types.Material:
        """Far away: the colour gives way to the warm haze with distance."""
        m = rh.simple(mat_name, hexcol, rough)
        mn = m.node_tree
        cd = node(mn, "ShaderNodeCameraData")
        k = smooth(mn, cd.outputs["View Distance"], 300.0, fade)
        em = node(mn, "ShaderNodeEmission")
        em.inputs["Color"].default_value = haze
        em.inputs["Strength"].default_value = 0.9
        mix = node(mn, "ShaderNodeMixShader")
        link(mn, k, mix.inputs[0])
        link(mn, mn.nodes["Principled BSDF"].outputs[0], mix.inputs[1])
        link(mn, em.outputs[0], mix.inputs[2])
        link(mn, mix.outputs[0], mn.nodes["Material Output"].inputs["Surface"])
        return m

    # the sea, far below the terrace, to the horizon
    sea = rh.simple("sea", "1b4a5e", 0.22)
    sn = sea.node_tree
    sb = sn.nodes["Principled BSDF"]
    sb.inputs["IOR"].default_value = 1.33
    sb.inputs["Specular IOR Level"].default_value = 0.35
    tc = node(sn, "ShaderNodeTexCoord")
    mp = node(sn, "ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.06, 0.18, 0.06)
    link(sn, tc.outputs["Object"], mp.inputs["Vector"])
    waves = node(sn, "ShaderNodeTexNoise")
    waves.inputs["Scale"].default_value = 9.0
    waves.inputs["Detail"].default_value = 10.0
    waves.inputs["Roughness"].default_value = 0.62
    link(sn, mp.outputs[0], waves.inputs["Vector"])
    wb = node(sn, "ShaderNodeBump")
    wb.inputs["Strength"].default_value = 0.6
    link(sn, waves.outputs["Fac"], wb.inputs["Height"])
    link(sn, wb.outputs["Normal"], sb.inputs["Normal"])
    bpy.ops.mesh.primitive_plane_add(size=12000, location=(0, 0, -70.0))
    bpy.context.object.data.materials.append(sea)
    # the rock island in the haze (Es Vedrà's silhouette, roughly)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=5, radius=1.0, location=(950, 2700, -70))
    isl = bpy.context.object
    isl.scale = (190, 120, 330)
    disp = isl.modifiers.new("d", "DISPLACE")
    tex = bpy.data.textures.new("rock", "CLOUDS")
    tex.noise_scale = 0.35
    disp.texture, disp.strength = tex, 0.35
    isl.data.materials.append(far("island", "6f5a45", 0.9, 4200.0))
    # the terrace: terracotta tiles, a whitewashed back wall, a low parapet to the sea
    floor_mat = rh.pbr(
        "terracotta", a.assets / "terracotta_floor_tiles", 2.4, tint=(1.5, 1.4, 1.3, 1), normal=0.6
    )
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0.5, -1.0, 0))
    fl = bpy.context.object
    fl.scale = (14, 7.0, 1)
    bpy.ops.object.transform_apply(scale=True)
    fl.data.materials.append(floor_mat)
    white = rh.pbr("lime", a.assets / "white_stucco", 2.0, tint=(1.15, 1.12, 1.06, 1), normal=0.8)
    rh.box("parapet", (0.5, 2.55, 0.3), (14, 0.34, 0.6), white)
    rh.box("cap", (0.5, 2.55, 0.625), (14.1, 0.4, 0.05), white)
    rh.box("backwall", (-6.6, -1.0, 1.6), (0.4, 7.0, 3.2), white)
    rh.box("sidewall", (0.5, -4.6, 1.6), (14, 0.4, 3.2), white)
    # the pergola: four posts, two beams, slats; its shade falls across the terrace
    wood = rh.pbr("wood", a.assets / "rough_wood", 1.2, tint=(0.82, 0.72, 0.6, 1), normal=0.9)
    for x, y in ((-3.6, -2.6), (-3.6, 1.9), (3.4, -2.6), (3.4, 1.9)):
        rh.box("post", (x, y, 1.35), (0.14, 0.14, 2.7), wood)
    for y in (-2.6, 1.9):
        rh.box("beam", (-0.1, y, 2.76), (7.6, 0.16, 0.2), wood)
    for i in range(22):
        rh.box("slat", (-3.55 + i * 0.33, -0.35, 2.92), (0.06, 5.2, 0.1), wood)
    plant = a.assets / "potted_plant_01" / "potted_plant_01.gltf"
    if plant.is_file():
        for at, s, r in (((2.75, 2.05, 0.0), 1.6, 20), ((-3.1, 2.05, 0.0), 1.3, 75)):
            bpy.ops.import_scene.gltf(filepath=str(plant))
            for o in [o for o in bpy.context.selected_objects if o.parent is None]:
                o.scale = (s, s, s)
                o.location = at
                o.rotation_euler.z = math.radians(r)
    tree = a.assets / "island_tree_02" / "island_tree_02.gltf"
    if tree.is_file():
        bpy.ops.import_scene.gltf(filepath=str(tree))
        for o in [o for o in bpy.context.selected_objects if o.parent is None]:
            o.scale = (1.0, 1.0, 1.0)
            o.location = (5.6, 4.2, -1.4)
    return so


def shot_ibiza(a, d, reel):
    ibiza_scene(a)
    rh.furniture(a)
    mat = fabric(a.assets, seams_pic(a), tuple(d["uv_size"]))
    cov = lean(rh.cover(d, mat))
    set_points(cov, draped(d))
    for (name, folder), (at, turn) in zip([m.split("=", 1) for m in a.more],
                                          [(Vector((2.35, 0.55, 0)), math.radians(-90))],
                                          strict=False):  # fmt: skip
        other_cover(a, name, Path(folder), at, turn)
    cam, aim = camera(35, 5.0, shift=-0.08)
    path = [(-2.6, -3.6, 1.62), (-1.7, -3.9, 1.55)]
    look = [(0.4, 0.4, 0.5), (0.5, 0.4, 0.45)]

    def frame(f, n):
        move(cam, aim, (f - 1) / (n - 1), path, look)

    return frame


SHOTS = {
    "st1": (shot_st1, STORY, 60),
    "st2": (shot_st2, STORY, 60),
    "st3": (shot_st3, STORY, 60),
    "st4": (shot_st4, STORY, 60),
    "st5": (shot_st5, STORY, 60),
    "st6": (shot_st6, STORY, 60),
    "cut": (shot_cut, CARD, 96),
    "sew": (shot_sew, CARD, 96),
    "vent": (shot_vent, CARD, 96),
    "fit": (shot_fit, CARD, 88),
    "runoff": (shot_runoff, CARD, 108),
    "range": (shot_range, CARD, 120),
    "ibiza": (shot_ibiza, STORY, 168),
}


def main() -> None:
    a = args()
    build, size, count = SHOTS[a.shot]
    if not a.size:
        a.size = f"{size[0]}x{size[1]}"
    bpy.ops.wm.read_factory_settings(use_empty=True)
    d = dict(np.load(a.data / "cover.npz"))
    reel_path = a.data / "reel.json"
    reel = json.loads(reel_path.read_text()) if reel_path.is_file() else {}
    frame = build(a, d, reel)
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, count
    a.out.mkdir(parents=True, exist_ok=True)
    todo: list[int] = []
    for part in (a.frames or f"1-{count}").split(","):
        lo_, _, hi_ = part.partition("-")
        todo += list(range(int(lo_), int(hi_ or lo_) + 1, a.every))
    for f in todo:
        path = a.out / f"{a.shot}-{f:04d}.png"
        if path.is_file():
            continue
        sc.frame_set(f)
        frame(float(f), count)
        if a.dry:
            print("stepped", f, flush=True)
            continue
        sc.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print("rendered", path.name, flush=True)


if __name__ == "__main__":
    main()
