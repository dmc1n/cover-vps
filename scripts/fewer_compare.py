"""A compare sheet for one drawing cover: the drawing, the old cover and the new one (ADR-097).

    uv run python scripts/fewer_compare.py OUT.png --pdf FILE --old MODEL_DIR --new MODEL_DIR

Each cover is drawn from above-right, from above-left (the back) and straight from above, its
pieces coloured and named, its seams dark; the title gives the pieces (without vent parts), the
worst stretch and the warnings. For looking, not for the cutting table.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from coverengine.export.drawing import _projected, load_cover
from coverengine.palette import PIECES
from coverengine.params import Registry
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.figure import Figure


def _eye(az_deg: float) -> np.ndarray:
    a = np.radians(az_deg)
    e = np.array([np.cos(a), np.sin(a), 0.8])
    return e / np.linalg.norm(e)


def _draw(ax, cover, eye, up_hint) -> None:  # type: ignore[no-untyped-def]
    from coverengine.export.drawing import View

    right = np.cross(up_hint, eye) if abs(eye[2]) > 0.99 else np.cross(-eye, [0, 0, 1])
    right /= np.linalg.norm(right)
    view = View("v", eye, right, np.cross(right, -eye))
    n = np.cross(
        cover.points[cover.welded[:, 1]] - cover.points[cover.welded[:, 0]],
        cover.points[cover.welded[:, 2]] - cover.points[cover.welded[:, 0]],
    )
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    # both sides drawn (the cover's faces may point either way): nearest last
    faces = cover.welded
    depth = (cover.points[faces] @ view.eye).mean(axis=1)
    order = np.argsort(depth, kind="stable")
    light = view.eye + 0.6 * view.up - 0.3 * view.right
    light /= np.linalg.norm(light)
    shade = 0.6 + 0.4 * np.abs(n @ light)
    base = np.array(PIECES)[cover.labels % len(PIECES)]
    rgb = np.clip(base * shade[:, None], 0, 1)
    p2 = _projected(cover, view, cover.points)
    ax.add_collection(
        PolyCollection(
            list(p2[faces[order]]), facecolors=rgb[order], edgecolors=rgb[order], linewidths=0.2
        )
    )
    ax.add_collection(LineCollection(list(p2[cover.seam_edges]), colors="#1a1d24", linewidths=0.7))
    for k, name in enumerate(cover.names):
        sel = cover.labels == k
        if not sel.any():
            continue
        c = cover.points[faces[sel]].mean(axis=(0, 1))
        # only label pieces facing the viewer
        if float((n[sel] @ view.eye).mean()) * 1 < -0.2 and abs(eye[2]) < 0.99:
            continue
        q = _projected(cover, view, c[None])[0]
        ax.text(
            q[0],
            q[1],
            name.replace("skirt-", "s-"),
            fontsize=4.5,
            ha="center",
            va="center",
            color="black",
            bbox={"boxstyle": "round,pad=0.1", "fc": "white", "alpha": 0.6, "lw": 0},
        )
    lo, hi = p2.min(axis=0), p2.max(axis=0)
    pad = 0.04 * float(np.ptp(p2, axis=0).max())
    ax.set_xlim(lo[0] - pad, hi[0] + pad)
    ax.set_ylim(lo[1] - pad, hi[1] + pad)
    ax.set_aspect("equal")
    ax.axis("off")


def _title(model: Path) -> str:
    fin = json.loads((model / "finished.json").read_text())
    pat = json.loads((model / "pattern.json").read_text())
    pcs = [p for p in fin["pieces"] if not p["name"].startswith("vent-")]
    vents = sum(int(p["quantity"]) for p in fin["pieces"] if p["name"] == "vent-hood")
    return (
        f"{len(pcs)} pieces, {vents} vents, worst stretch "
        f"{pat['summary']['max_stretch_pct']:.2f} %, {len(pat['warnings'])} warnings"
    )


def sheet(out: Path, pdf: Path, covers: list[tuple[str, Path]]) -> Path:
    import pymupdf

    params = Registry.load(None).resolve()
    rows = 1 + len(covers)
    fig = Figure(figsize=(15, 5.2 * rows + 4), dpi=110)
    grid = fig.add_gridspec(
        rows,
        6,
        height_ratios=[2.2] + [1] * (rows - 1),
        hspace=0.15,
        wspace=0.02,
        left=0.01,
        right=0.99,
        top=0.97,
        bottom=0.01,
    )
    doc = pymupdf.open(pdf)
    pages = []
    for p in list(doc)[:2]:
        pix = p.get_pixmap(dpi=110)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)
        ink = np.argwhere(img[:, :, :3].min(axis=2) < 200)
        if len(ink):
            (y0, x0), (y1, x1) = ink.min(axis=0), ink.max(axis=0)
            img = img[y0 : y1 + 1, x0 : x1 + 1]
        pages.append(img)
    for i, img in enumerate(pages):
        span = 6 // len(pages)
        ax = fig.add_subplot(grid[0, i * span : (i + 1) * span])
        ax.imshow(img)
        ax.axis("off")
        ax.set_title(f"drawing {pdf.name}" + (f" p{i + 1}" if len(pages) > 1 else ""), fontsize=9)
    for r, (label, model) in enumerate(covers, start=1):
        pdoc = json.loads((model / "pattern.json").read_text())
        cover = load_cover(model, pdoc, params)
        for c, (eye, name) in enumerate(
            [
                (_eye(-50), "front right"),
                (_eye(130), "back left"),
                (np.array([0.0, 0.0, 1.0]), "top"),
            ]
        ):
            ax = fig.add_subplot(grid[r, c * 2 : c * 2 + 2])
            _draw(ax, cover, eye, np.array([0.0, 1.0, 0.0]))
            ax.set_title(
                f"{label}: {name}" + (f"\n{_title(model)}" if c == 0 else ""),
                fontsize=8,
                loc="left",
            )
    fig.savefig(out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--pdf", type=Path, required=True)
    ap.add_argument("--old", type=Path, required=True)
    ap.add_argument("--new", type=Path, action="append", default=[])
    a = ap.parse_args()
    covers = [("old", a.old)] + [(f"new{'' if i == 0 else i + 1}", p) for i, p in enumerate(a.new)]
    print(sheet(a.out, a.pdf, covers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
