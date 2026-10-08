"""Map the red marks of a Desk picture onto the 3D cover (Rens's rejections, 8 Oct 2026; ADR-100).

The Desk snapshot has no camera stored, so the camera is found again: the cover's panels are
rendered from candidate views (three.js perspective, fov 40, Z up, as the Viewer) and compared
with the picture's silhouette and its flat panel colours; then every thick red stroke is traced
back onto the panel and 3D point under it.

  uv run python scripts/desk_marks.py MODEL_DIR PICTURE OUT_PREFIX

Writes OUT_PREFIX.json (camera, IoU, per stroke the panels hit and 3D points) and OUT_PREFIX.png
(the picture with the fitted panel outlines and names). A fit with IoU under about 0.9 is a
guess: treat its mapping as a proposal for a person to check.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage, optimize

FOV = 40.0
SCALE = 4  # silhouette work at 1/4 resolution
BG = np.array([[249, 246, 232], [214, 205, 182], [235, 228, 210]], float)


def masks(img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(cover, ignore, red) masks at full resolution."""
    rgb = img[..., :3].astype(float)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    red_any = (r > 150) & (g < 110) & (b < 110)
    red = ndimage.binary_opening(red_any, iterations=2)  # the pen is thick; vent edges are thin
    cream = np.linalg.norm(rgb - BG[0], axis=-1) < 12
    white = (r > 240) & (g > 240) & (b > 240)
    # grid lines are thin: closing the cream area swallows them, not the panels
    bg = ndimage.binary_closing(cream | red, iterations=4) & ~ndimage.binary_erosion(
        ~cream & ~red, iterations=6
    )
    cover = ~bg & ~white & ~red
    cover = ndimage.binary_opening(cover, iterations=3)
    lab, n = ndimage.label(cover)
    if n:
        sizes = ndimage.sum(cover, lab, range(1, n + 1))
        keep = np.flatnonzero(sizes > 0.02 * sizes.max()) + 1
        cover = np.isin(lab, keep)
    cover = ndimage.binary_fill_holes(ndimage.binary_closing(cover | red, iterations=3)) & ~red
    ignore = ndimage.binary_dilation(red_any | white, iterations=4)
    return cover, ignore, red


class Cam:
    def __init__(self, x: np.ndarray, centre: np.ndarray, size: float, w: int, h: int) -> None:
        az, el, dist, tx, ty, tz = x
        self.w, self.h = w, h
        target = centre + np.array([tx, ty, tz]) * size
        d = dist * size
        eye = target + d * np.array(
            [math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)]
        )
        f = target - eye
        f /= np.linalg.norm(f)
        right = np.cross(f, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, f)
        self.eye, self.f, self.right, self.up = eye, f, right, up
        self.focal = (h / 2) / math.tan(math.radians(FOV / 2))

    def project(self, p: np.ndarray) -> np.ndarray:
        q = p - self.eye
        z = q @ self.f
        x = q @ self.right / z * self.focal + self.w / 2
        y = -(q @ self.up) / z * self.focal + self.h / 2
        return np.column_stack([x, y])

    def ray(self, px: float, py: float) -> np.ndarray:
        d = self.f * self.focal + self.right * (px - self.w / 2) - self.up * (py - self.h / 2)
        return d / np.linalg.norm(d)


def render_labels(
    cam: Cam, verts: np.ndarray, faces: np.ndarray, labels: np.ndarray, w: int, h: int
) -> np.ndarray:
    """Label buffer (-1 = nothing), painter's order far to near."""
    p = cam.project(verts)
    cen = verts[faces].mean(axis=1)
    order = np.argsort(-((cen - cam.eye) @ cam.f))
    im = Image.new("I", (w, h), 0)
    dr = ImageDraw.Draw(im)
    for fi in order:
        dr.polygon([tuple(p[i]) for i in faces[fi]], fill=int(labels[fi]) + 1)
    return np.asarray(im, np.int64) - 1


def fit(verts, faces, labels, img: np.ndarray, colour_weight: float = 0.6):
    H, W = img.shape[:2]
    cover, ignore, _ = masks(img)
    w, h = W // SCALE, H // SCALE
    small = lambda m: np.asarray(Image.fromarray(m).resize((w, h)), bool)  # noqa
    cs, ig = small(cover), small(ignore)
    col = np.asarray(Image.fromarray(img).resize((w, h), Image.NEAREST), float)
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    centre, size = (lo + hi) / 2, float(np.linalg.norm(hi - lo))
    nl = int(labels.max()) + 1
    full_faces, full_labels = faces, labels
    if len(faces) > 6000:  # speed: a spread subset, holes closed below
        pick = np.random.default_rng(0).choice(len(faces), 6000, replace=False)
        faces, labels = faces[pick], labels[pick]

    def loss(x):
        if not (0.05 < x[1] < 1.52 and 0.3 < x[2] < 8):
            return 3.0
        cam = Cam(x, centre, size, w, h)
        if ((verts - cam.eye) @ cam.f).min() <= 1.0:
            return 3.0
        lab = render_labels(cam, verts, faces, labels, w, h)
        r = ndimage.binary_closing(lab >= 0, iterations=2)
        a, b = r & ~ig, cs & ~ig
        inter, union = (a & b).sum(), (a | b).sum()
        iou = inter / max(union, 1)
        sel = a & b & (lab >= 0)
        if sel.sum() < 20:
            return 2.0 - iou
        L = lab[sel]
        C = col[sel]
        cnt = np.bincount(L, minlength=nl).astype(float)
        mean = (
            np.stack([np.bincount(L, C[:, k], nl) for k in range(3)], 1)
            / np.maximum(cnt, 1)[:, None]
        )
        var = ((C - mean[L]) ** 2).sum(axis=1).mean()
        incons = min(var / 900.0, 1.0)
        return (1 - iou) + colour_weight * incons

    grid = []
    for az in np.radians(np.arange(0, 360, 15)):
        for el in np.radians([15, 25, 35, 45, 55, 65, 75]):
            for dist in (1.0, 1.5, 2.2):
                x = np.array([az, el, dist, 0, 0, 0])
                grid.append((loss(x), x))
    grid.sort(key=lambda t: t[0])
    res = None
    step = np.array([0.12, 0.08, 0.2, 0.04, 0.04, 0.04])
    for _, s in grid[:5]:
        simplex = np.vstack([s] + [s + np.eye(6)[i] * step[i] for i in range(6)])
        r = optimize.minimize(
            loss,
            s,
            method="Nelder-Mead",
            options={"xatol": 1e-3, "fatol": 1e-4, "maxiter": 700, "initial_simplex": simplex},
        )
        if res is None or r.fun < res.fun:
            res = r
    cam = Cam(res.x, centre, size, w, h)
    lab = render_labels(cam, verts, full_faces, full_labels, w, h)
    a, b = (lab >= 0) & ~ig, cs & ~ig
    iou = (a & b).sum() / max((a | b).sum(), 1)
    return res.x, float(iou), float(res.fun), centre, size


def strokes(red: np.ndarray) -> list[np.ndarray]:
    lab, n = ndimage.label(ndimage.binary_dilation(red, iterations=3))
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero((lab == i) & red)
        if len(xs) > 30:
            out.append(np.column_stack([xs, ys]))
    return out


def main() -> None:
    model_dir, pic, prefix = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    data = np.load(model_dir / "panels.npz")
    names = [p["name"] for p in json.loads((model_dir / "panels.json").read_text())["panels"]]
    verts, faces, labels = data["vertices"], data["faces"], data["labels"]
    img = np.asarray(Image.open(pic).convert("RGB"))
    x, iou, fun, centre, size = fit(verts, faces, labels, img)
    H, W = img.shape[:2]
    cam = Cam(x, centre, size, W, H)
    # map the red pixels: ray cast each (thinned) red pixel onto the cover
    _, _, red = masks(img)
    # face-id buffer (painter's order, far to near), then each red pixel's face and 3D point
    cen = verts[faces].mean(axis=1)
    order = np.argsort(-((cen - cam.eye) @ cam.f))
    p2all = cam.project(verts)
    idim = Image.new("RGB", (W, H), (255, 255, 255))
    drw = ImageDraw.Draw(idim)
    for fi in order:
        drw.polygon(
            [tuple(p2all[i]) for i in faces[fi]],
            fill=(int(fi) & 255, (int(fi) >> 8) & 255, (int(fi) >> 16) & 255),
        )
    ib = np.asarray(idim).astype(np.int64)
    fid = ib[..., 0] + (ib[..., 1] << 8) + (ib[..., 2] << 16)
    result = {
        "camera": {
            "azimuth_deg": math.degrees(x[0]),
            "elevation_deg": math.degrees(x[1]),
            "distance": float(x[2]),
            "target_shift": [float(v) for v in x[3:]],
        },
        "iou": round(float(iou), 3),
        "loss": round(fun, 3),
        "strokes": [],
    }
    for s in strokes(red):
        pick = s[:: max(1, len(s) // 150)]
        hits = {}
        pts = []
        for px, py in pick:
            fi = int(fid[py, px])
            if fi >= len(faces):
                continue
            t = verts[faces[fi]]
            n = np.cross(t[1] - t[0], t[2] - t[0])
            d = cam.ray(px, py)
            tt = ((t[0] - cam.eye) @ n) / (d @ n)
            p3 = cam.eye + tt * d
            nm = names[int(labels[fi])]
            hits[nm] = hits.get(nm, 0) + 1
            pts.append([round(float(c)) for c in p3] + [nm, int(px), int(py)])
        result["strokes"].append(
            {
                "pixels": len(s),
                "bbox": [
                    int(s[:, 0].min()),
                    int(s[:, 1].min()),
                    int(s[:, 0].max()),
                    int(s[:, 1].max()),
                ],
                "hit_share": round(len(pts) / len(pick), 2),
                "panels": hits,
                "points": pts,
            }
        )
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(json.dumps(result, indent=1))
    # overlay: panel boundaries (seam edges and outline) and names
    p2 = cam.project(verts)
    over = Image.fromarray(img).convert("RGB")
    dr = ImageDraw.Draw(over)
    vis_n = np.cross(
        verts[faces[:, 1]] - verts[faces[:, 0]], verts[faces[:, 2]] - verts[faces[:, 0]]
    )
    facing = np.einsum("ij,ij->i", vis_n, verts[faces[:, 0]] - cam.eye) < 0
    # edges between different labels, drawn where at least one side faces us
    edges = {}
    for fi, t in enumerate(faces):
        for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
            k = (min(a, b), max(a, b))
            edges.setdefault(k, []).append(fi)
    o = data["original_vertex"]
    weld = {}
    for (a, b), fs in edges.items():
        k = (min(o[a], o[b]), max(o[a], o[b]))
        weld.setdefault(k, []).extend(fs)
    for (a, b), fs in weld.items():
        labs = {int(labels[f]) for f in fs}
        if (len(labs) > 1 or len(fs) == 1) and any(facing[f] for f in fs):
            ia = np.flatnonzero(o == a)[0]
            ib = np.flatnonzero(o == b)[0]
            dr.line([tuple(p2[ia]), tuple(p2[ib])], fill=(20, 60, 200), width=3)
    for li, nm in enumerate(names):
        sel = (labels == li) & facing
        if sel.sum() < 5:
            continue
        c = verts[faces[sel]].reshape(-1, 3).mean(axis=0)
        q = cam.project(c[None])[0]
        dr.text((q[0], q[1]), nm, fill=(0, 0, 160))
    over.save(prefix.with_suffix(".png"))
    print(
        json.dumps({k: result[k] for k in ("camera", "iou", "loss")}),
        [(s["panels"], s["hit_share"]) for s in result["strokes"]],
    )


if __name__ == "__main__":
    main()
