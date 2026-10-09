"""The hero film's data from one catalogue model (ADR-108): everything the renderer shows of the
cover is our own engine output, written to one folder for Blender.

- `cover.npz`:
  - the sewn pieces split at their seams (`faces`, `piece`), with every point's flat position in
    its own piece (`uv`, metres: the true lengths, so the weave lies along the fabric's grain);
  - the drape's fall (`frames`, Style3D, drape.bin) and the designed shape (`design`); the
    sewn cloth itself (`weld`: every point's sewn point, `weld_faces`) for the lowering;
  - the rain check's own drop paths on the draped cover (`paths`, `path_len`).
- `seams.png`: the stitching in the pieces' flat layout (`uv`, `uv_size`): red the relief in
  0..4 mm (the seam allowance folded under the lapping panel, the rows pulled in, the hem's
  cord channel and the soft pleats its cord gathers, a faint pucker along the seams), green the
  thread. Two rows of stitches on the panel that laps over (the higher one, so the water runs
  off; on an upright seam the front one), 4 and 10 mm from the seam; the hem
  stitched 32 mm up. Measured in the flat pieces at 0.35 mm, so every row runs exactly parallel
  to its seam.
- `pieces.json`: the finished pieces as cut (cut.dxf: CUT outlines and the PEN marks, in metres).
- `furniture.glb`: the furniture, from the model.

Units: metres, Z up, the ground at z = 0 (the engine's frame, scaled).

    uv run python scripts/film/hero_data.py ~/cover-data/models/suns-2-seater-kota OUT
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import ezdxf
import numpy as np
from coverengine import drape as dr
from coverengine.params import Registry
from PIL import Image, ImageDraw
from scipy import ndimage

M = 1000.0  # mm per metre
PX_MM = 0.35  # the stitching's picture: one pixel
GAP_MM = 30.0  # room between pieces in the layout
ROWS_MM = (4.0, 10.0)  # the two rows of a seam, from the seam line
HEM_ROW_MM = 32.0  # the hem's row, from the hem
STITCH_MM = 4.5  # one stitch and its gap
HEIGHT_MM = 4.0  # the relief's range in the picture
BASE_MM = 1.6  # the plain fabric's level in it
QMAX = 65535


def boundary_edges(f: np.ndarray) -> np.ndarray:
    e = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    e, count = np.unique(e, axis=0, return_counts=True)
    return e[count == 1]


def pack(uv: np.ndarray, pid: np.ndarray) -> np.ndarray:
    """The flat pieces side by side in rows (largest first), none overlapping: one picture holds
    every piece's stitching."""
    out = uv.copy()
    ks = sorted(np.unique(pid), key=lambda k: -float(np.ptp(uv[pid == k], axis=0).prod()))
    total = sum(float(np.ptp(uv[pid == k], axis=0).prod()) for k in ks)
    width = 1.6 * total**0.5
    x = y = row = 0.0
    for k in ks:
        p = uv[pid == k]
        w, h = np.ptp(p, axis=0)
        if x > 0 and x + w > width:
            x, y, row = 0.0, y + row + GAP_MM, 0.0
        out[pid == k] = p - p.min(axis=0) + (x + GAP_MM, y + GAP_MM)
        x += w + GAP_MM
        row = max(row, float(h))
    return out


def chains(edges: np.ndarray) -> list[tuple[int, int]]:
    """The edges in walking order, each run of joined edges continuous (the stitches along a
    seam keep their rhythm over the mesh's points)."""
    nbr: dict[int, list[int]] = {}
    for a, b in edges.tolist():
        nbr.setdefault(a, []).append(b)
        nbr.setdefault(b, []).append(a)
    seen: set[tuple[int, int]] = set()
    out: list[tuple[int, int]] = []
    ends = [v for v, n in nbr.items() if len(n) == 1] + list(nbr)
    for v0 in ends:
        v = v0
        while True:
            nxt = [u for u in nbr[v] if (min(u, v), max(u, v)) not in seen]
            if not nxt:
                break
            u = nxt[0]
            seen.add((min(u, v), max(u, v)))
            out.append((v, u))
            v = u
    return out


def lines(uv: np.ndarray, edges: np.ndarray, shape: tuple[int, int]) -> tuple[Any, Any, Any]:
    """The edges drawn into a picture: where a line is, the length along it there and its
    direction (so a point beside it gets its exact length along it, not the pixel's)."""
    on = np.zeros(shape, bool)
    along = np.zeros(shape, np.float32)
    tang = np.zeros((2, *shape), np.float32)
    run = 0.0
    for a, b in chains(edges):
        p, q = uv[a] / PX_MM, uv[b] / PX_MM
        n = max(int(np.linalg.norm(q - p) * 2), 1)
        t = np.linspace(0, 1, n + 1)[:, None]
        pts = np.rint(p + (q - p) * t).astype(int)
        on[pts[:, 1], pts[:, 0]] = True
        exact = p + (q - p) * t
        along[pts[:, 1], pts[:, 0]] = (
            run
            + t[:, 0] * float(np.linalg.norm(q - p)) * PX_MM
            - (((pts - exact) @ ((q - p) / max(np.linalg.norm(q - p), 1e-9))) * PX_MM)
        )
        tang[:, pts[:, 1], pts[:, 0]] = ((q - p) / max(np.linalg.norm(q - p), 1e-9))[:, None]
        run += float(np.linalg.norm(q - p)) * PX_MM
    return on, along, tang


def bake(uv, faces, lap, hem) -> tuple[Image.Image, tuple[float, float]]:
    size = uv.max(axis=0) + GAP_MM
    w, h = (int(np.ceil(v / PX_MM)) for v in size)
    mask_img = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask_img)
    for f in faces:
        draw.polygon([tuple(uv[i] / PX_MM) for i in f], fill=255)
    inside = np.asarray(mask_img) > 0
    height = np.full((h, w), BASE_MM, np.float32)
    thread = np.zeros((h, w), np.float32)

    def dash(s):
        phase = np.mod(s, STITCH_MM) / STITCH_MM
        return np.sqrt(np.clip(np.sin(np.pi * np.clip(phase / 0.8, 0, 1)), 0, 1))

    def smooth(x, lo, hi):
        t = np.clip((x - lo) / (hi - lo), 0, 1)
        return t * t * (3 - 2 * t)

    for edges, rows, kind in ((lap, ROWS_MM, "seam"), (hem, (HEM_ROW_MM,), "hem")):
        if not len(edges):
            continue
        on, along, tang = lines(uv, edges, (h, w))
        dist, (iy, ix) = ndimage.distance_transform_edt(~on, return_indices=True)
        d = (dist * PX_MM).astype(np.float32)
        gy, gx = np.mgrid[0:h, 0:w]
        s = along[iy, ix] + ((gx - ix) * tang[0, iy, ix] + (gy - iy) * tang[1, iy, ix]) * PX_MM
        del dist, iy, ix, gy, gx, tang
        wobble = np.sin(2 * np.pi * s / 310.0) * 2.5  # no two pleats quite alike
        if kind == "seam":  # the allowance folded under: a soft raised band
            height += 0.6 * smooth(d, 0.0, 2.5) * smooth(-d, -15.0, -11.0)
            # the stitching pulls the fabric in a little: a faint pucker along the seam
            height += 0.2 * np.exp(-d / 12.0) * np.sin(2 * np.pi * s / 22.0 + wobble)
        else:  # the hem's cord channel, and the cord gathering the fabric into soft pleats
            height += 0.9 * smooth(d, 0.0, 6.0) * smooth(-d, -46.0, -30.0)
            # the pleats: uneven, strongest at the hem, gone a few centimetres up
            pleat = np.sin(2 * np.pi * s / 41.0 + wobble + 0.8 * np.sin(2 * np.pi * s / 127.0))
            height += 0.7 * np.exp(-d / 26.0) * pleat * (0.6 + 0.4 * np.sin(2 * np.pi * s / 173.0))
        for r in rows:
            off = d - r
            height -= 0.25 * np.exp(-((off / 0.7) ** 2))
            t = np.exp(-((off / 0.4) ** 2)) * dash(s)
            height += 0.5 * t
            thread = np.maximum(thread, t)
        del d, s
    height = np.where(inside, height, BASE_MM)
    thread = np.where(inside, thread, 0.0)
    rgb = np.zeros((h, w, 3), np.uint8)
    rgb[..., 0] = np.clip(height / HEIGHT_MM * 255, 0, 255).astype(np.uint8)
    rgb[..., 1] = np.clip(thread * 255, 0, 255).astype(np.uint8)
    # the picture's rows run up the V axis: row 0 is the bottom
    return Image.fromarray(rgb[::-1]), (w * PX_MM, h * PX_MM)


def build(model: Path, out: Path) -> None:
    params = Registry.load(None).resolve()
    c = dr.cloth(model, params)
    assert c.flat is not None
    faces, piece = c.faces, c.piece
    doc = json.loads((model / dr.DRAPE_JSON).read_text())
    n = int(doc["points_per_frame"])
    if n != len(c.x) or not np.array_equal(np.asarray(doc["faces"]), faces):
        raise SystemExit("drape.bin does not match the cut: run cover drape first")
    lo, hi = (np.array(v) for v in doc["frame_box_mm"])
    raw = np.frombuffer((model / dr.DRAPE_BIN).read_bytes(), dtype=np.uint16)
    frames = raw.reshape(-1, n, 3).astype(np.float64) / QMAX * (hi - lo) + lo  # mm, Z up

    # one point per (welded point, piece): the seams split
    keys = np.stack([faces.ravel(), np.repeat(piece, 3)], axis=1)
    uniq, idx = np.unique(keys, axis=0, return_inverse=True)
    idx = idx.reshape(-1, 3)
    uv = np.zeros((len(uniq), 2))
    uv[idx.ravel()] = c.flat.reshape(-1, 2)
    pid = uniq[:, 1]
    weld = uniq[:, 0]
    final = frames[-1][weld]

    # which side of every seam laps over: the higher piece (water runs off), on a vertical
    # seam the one further to the front (the engine's -y; domain rule 6 in CLAUDE.md)
    centre = {k: final[pid == k].mean(axis=0) for k in np.unique(pid)}
    pieces_of_weld: dict[int, set[int]] = {}
    for w, k in zip(weld.tolist(), pid.tolist(), strict=True):
        pieces_of_weld.setdefault(w, set()).add(k)
    uv = pack(uv, pid)
    lap_edges, hem_edges = [], []
    for k in np.unique(pid):
        be = boundary_edges(idx[piece == k])
        for a, b in be:
            o = pieces_of_weld[weld[a]] & pieces_of_weld[weld[b]] - {k}
            if not o:
                hem_edges.append((a, b))
                continue
            j = next(iter(o))
            dz = centre[k][2] - centre[j][2]
            if dz > 50 or (abs(dz) <= 50 and centre[k][1] < centre[j][1]):
                lap_edges.append((a, b))
    detail, size_mm = bake(uv, idx, np.array(lap_edges), np.array(hem_edges))

    # the rain check on the draped cover: its drop paths
    rain = json.loads((model / "drape_rain.json").read_text())
    paths = [np.asarray(d["path"], float) for d in rain["drops"] if len(d["path"]) >= 3]
    longest = max(len(p) for p in paths)
    padded = np.full((len(paths), longest, 3), np.nan)
    for i, p in enumerate(paths):
        padded[i, : len(p)] = p

    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        out / "cover.npz",
        faces=idx.astype(np.int32),
        piece=pid.astype(np.int32),
        weld=weld.astype(np.int32),
        names=np.array(c.names),
        weld_faces=faces.astype(np.int32),
        uv=(uv / M).astype(np.float32),
        design=(c.x[weld] / M).astype(np.float32),
        frames=(frames[:, weld] / M).astype(np.float32),
        uv_size=np.array(size_mm, np.float32) / M,
        paths=(padded / M).astype(np.float32),
        path_len=np.array([len(p) for p in paths], np.int32),
    )
    detail.save(out / "seams.png", optimize=True)
    (out / "pieces.json").write_text(json.dumps(cut_pieces(model / "cut.dxf")))
    shutil.copy(model / "model.glb", out / "furniture.glb")
    print(f"{len(uniq)} points, {len(idx)} triangles, {len(frames)} frames, {len(paths)} drops")


def cut_pieces(path: Path) -> dict[str, Any]:
    """The finished pieces as the table cuts them: outlines (CUT) and pen lines (PEN), metres."""
    doc = ezdxf.readfile(path)
    cut, pen, text = [], [], []
    for e in doc.modelspace():
        if e.dxftype() == "LWPOLYLINE":
            pts = [[x / M, y / M] for x, y, *_ in e.get_points()]
            if e.closed:
                pts.append(pts[0])
            (cut if e.dxf.layer == "CUT" else pen).append(pts)
        elif e.dxftype() == "TEXT":
            x, y, *_ = e.dxf.insert
            text.append({"at": [x / M, y / M], "h": e.dxf.height / M, "text": e.dxf.text,
                         "rot": e.dxf.get("rotation", 0.0)})  # fmt: skip
    return {"cut": cut, "pen": pen, "text": text}


if __name__ == "__main__":
    build(Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser())
