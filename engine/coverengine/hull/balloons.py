"""Balloons under table covers (`hull.support: balloons`, ADR-040).

The workshop puts inflatable balloons on a table top under the cover, so the fabric forms a tent
and water runs off (rule 12). The balloon's own 3D model (`hull.balloon_model`, a model folder
next to the others) gives its real shape. The program tries 1, 2, 3, ... balloons in an even grid
on the table top, each time with the tensioned cover over table and balloons, and measures where
water would stay. How many: `hull.balloon_count`, or (0) the AI chooses from the options, or
without AI the fewest balloons with which all water runs off.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from coverengine.errors import CoverError
from coverengine.hull import drainage
from coverengine.hull.heightmap import rasterize
from coverengine.hull.tension import concave_envelope
from coverengine.io.model_io import load_model
from coverengine.params import EffectiveParams

Array = NDArray[np.float64]
Mask = NDArray[np.bool_]

# The table top: the covered cells within this distance of the highest point (mm).
DECK_MM = 30.0  # param-ok: geometric tolerance
MM2_PER_M2 = 1e6  # param-ok: unit conversion
MM_PER_CM = 10.0  # param-ok: unit conversion
HALF = 0.5  # param-ok: the middle of a grid cell
# The pressed-round balloon top is this much steeper than the minimum slope (degrees).
PRESSED_EXTRA_DEG = 0.5  # param-ok: margin over hull.min_slope_deg


@dataclass
class Shape:
    """The balloon seen from above: heights above its own bottom on a grid of cells h."""

    z: Array  # -inf outside
    size_mm: tuple[float, float, float]


def shape(models_dir: Path, model_id: str, h: float, min_slope_deg: float) -> Shape:
    d = models_dir / model_id
    if not (d / "model.glb").is_file():
        raise CoverError(
            f"hull.balloon_model = {model_id!r}: no such model in {models_dir} (upload the balloon)"
        )
    m = load_model(d)
    v = np.asarray(m.vertices, np.float64)
    v = v - np.array([(v[:, 0].min() + v[:, 0].max()) / 2, (v[:, 1].min() + v[:, 1].max()) / 2,
                      v[:, 2].min()])  # fmt: skip
    hm = rasterize(v, np.asarray(m.faces), h, 0.0)
    size = v.max(axis=0) - v.min(axis=0)
    # under the tensioned fabric the flat top of the balloon is pressed round: no flatter than
    # just over the minimum slope from its highest point
    r = np.hypot(hm.xs[:, None], hm.ys[None, :])
    dome = float(size[2]) - math.tan(math.radians(min_slope_deg + PRESSED_EXTRA_DEG)) * r
    z = np.where(np.isfinite(hm.z), np.minimum(hm.z, dome), -np.inf)
    return Shape(z, (float(size[0]), float(size[1]), float(size[2])))


def _place(obstacle: Array, s: Shape, i: int, j: int) -> Array:
    """The obstacle with one balloon whose centre is on cell (i, j), lying on what is below."""
    out = obstacle.copy()
    ni, nj = s.z.shape
    i0, j0 = i - ni // 2, j - nj // 2
    a0, b0 = max(i0, 0), max(j0, 0)
    a1, b1 = min(i0 + ni, out.shape[0]), min(j0 + nj, out.shape[1])
    if a0 >= a1 or b0 >= b1:
        return out
    cap = s.z[a0 - i0 : a1 - i0, b0 - j0 : b1 - j0]
    under = obstacle[a0:a1, b0:b1]
    base = float(np.max(np.where(np.isfinite(cap) & np.isfinite(under), under, -np.inf)))
    out[a0:a1, b0:b1] = np.maximum(under, base + cap)
    return out


def layouts(deck: Mask, xs: Array, ys: Array, s: Shape, most: int) -> list[list[tuple[int, int]]]:
    """For 1, 2, ... balloons the evenest grid on the table top that fits (no overlap)."""
    ii, jj = np.nonzero(deck)
    if not len(ii):
        return []
    h = float(xs[1] - xs[0])
    lx, ly = (ii.max() - ii.min() + 1) * h, (jj.max() - jj.min() + 1) * h
    fit_x = max(int(lx // s.size_mm[0]), 1)
    fit_y = max(int(ly // s.size_mm[1]), 1)
    best: dict[int, tuple[float, int, int]] = {}
    for nx in range(1, fit_x + 1):
        for ny in range(1, fit_y + 1):
            n = nx * ny
            if n > most:
                continue
            gap = max(lx / nx, ly / ny)  # the widest span of fabric between balloons
            if n not in best or gap < best[n][0]:
                best[n] = (gap, nx, ny)
    out = []
    for n in sorted(best):
        _, nx, ny = best[n]
        cells = [
            (
                int(round(ii.min() + (a + HALF) * (ii.max() - ii.min() + 1) / nx - HALF)),
                int(round(jj.min() + (b + HALF) * (jj.max() - jj.min() + 1) / ny - HALF)),
            )
            for a in range(nx)
            for b in range(ny)
        ]
        out.append(cells)
    return out


@dataclass
class Option:
    cells: list[tuple[int, int]]
    top: Array
    row: dict[str, Any]


def options(
    obstacle: Array,
    inside: Mask,
    xs: Array,
    ys: Array,
    s: Shape,
    params: EffectiveParams,
) -> list[Option]:
    h = float(xs[1] - xs[0])
    min_slope = float(params["hull.min_slope_deg"])  # type: ignore[arg-type]
    patch = float(params["hull.flat_patch_mm"])  # type: ignore[arg-type]
    peak = float(np.max(np.where(inside, obstacle, -np.inf)))
    deck = inside & (obstacle > peak - DECK_MM)
    out = []
    ii, jj = np.nonzero(deck)
    length = float(max(np.ptp(ii), np.ptp(jj)) + 1) * h if len(ii) else 0.0
    usual = max(1, round(length / float(params["hull.balloon_spacing_mm"])))  # type: ignore[arg-type]
    for cells in layouts(deck, xs, ys, s, int(params["hull.balloon_max"])):
        lifted = obstacle
        for i, j in cells:
            lifted = _place(lifted, s, i, j)
        top = concave_envelope(lifted, inside, xs, ys)
        water = drainage.check(top, inside, xs, ys, min_slope, patch)
        flat = drainage.flat_patches(top, inside, h, min_slope, patch)
        row = {
            "balloons": len(cells),
            "grid": [len({c[0] for c in cells}), len({c[1] for c in cells})],
            "water_runs_off": bool(water.drains),
            "flat_m2": round(float(flat.sum()) * h * h / MM2_PER_M2, 3),
            "hollow_m2": round(water.hollow_area_mm2 / MM2_PER_M2, 3),
            "cover_top_mm": round(float(np.max(np.where(inside, top, -np.inf)))),
            "table_length_mm": round(length),
            "usual_for_this_length": len(cells) >= usual,
        }
        out.append(Option(cells, top, row))
    return out


AI_SYSTEM = """You advise a workshop that sews outdoor table covers. Under the cover, balloons lie
on the table top so the fabric forms a tent and rain runs off. Between balloons the fabric runs
straight from one balloon to the next; the slope is all round the balloons. Every table gets at
least one balloon; the workshop's practice is 3 to 4 balloons for a 340 cm long table. You get
the table and the options: how many balloons in which grid, whether all water runs off, how much
of the cover is still flat (m2; flat spots hold water), how high the cover gets, and whether the
number is at least the usual one for this table length. Choose as few balloons as possible with
which water runs off and that suit the workshop's practice. Answer with JSON only:
{"balloons": <one of the options>, "reason": "one or two plain sentences"}"""


def choose(
    rows: list[dict[str, Any]], params: EffectiveParams, product: str
) -> tuple[int, str, str]:
    fixed = int(params["hull.balloon_count"])
    if fixed > 0:
        best = min(rows, key=lambda r: abs(r["balloons"] - fixed))
        return int(best["balloons"]), "setting", f"hull.balloon_count = {fixed}"
    dry = [r for r in rows if r["water_runs_off"] and r["usual_for_this_length"]]
    rule = dry[0] if dry else min(rows, key=lambda r: (r["flat_m2"], -r["balloons"]))
    why = (
        "the fewest balloons with which all water runs off, about one per "
        f"{float(params['hull.balloon_spacing_mm']) / MM_PER_CM:g} cm of table"  # type: ignore[arg-type]
        if dry
        else "no option sheds all water: the one with the least flat area"
    )
    if params["ai.provider"] != "none":
        try:
            from coverengine.ai import ask

            answer = ask(params, AI_SYSTEM, json.dumps({"table": product, "options": rows}))
            n = int(answer["balloons"])
            if any(r["balloons"] == n for r in rows):
                return n, "ai", str(answer.get("reason", ""))
        except Exception as exc:  # noqa: BLE001 - no AI: the rule decides
            return int(rule["balloons"]), "rule", f"the AI could not decide ({exc}); {why}"
    return int(rule["balloons"]), "rule", why


def support(
    obstacle: Array,
    inside: Mask,
    xs: Array,
    ys: Array,
    model_dir: Path,
    params: EffectiveParams,
    product: str,
) -> tuple[Array, dict[str, Any], list[str]]:
    """The tensioned top over the chosen balloons, the report, and warnings."""
    h = float(xs[1] - xs[0])
    min_slope = float(params["hull.min_slope_deg"])  # type: ignore[arg-type]
    s = shape(model_dir.parent, str(params["hull.balloon_model"]), h, min_slope)
    opts = options(obstacle, inside, xs, ys, s, params)
    if not opts:
        return (
            concave_envelope(obstacle, inside, xs, ys),
            {"kind": "balloons", "balloons": 0},
            ["no table top found for balloons"],
        )
    rows = [o.row for o in opts]
    n, by, why = choose(rows, params, product)
    pick = next(o for o in opts if o.row["balloons"] == n)
    warnings = []
    if not pick.row["water_runs_off"] and pick.row["flat_m2"] > 0:
        warnings.append(
            f"with {n} balloon(s) {pick.row['flat_m2']:g} m2 of the cover is still flat"
        )
    report = {
        "kind": "balloons",
        "balloon_model": str(params["hull.balloon_model"]),
        "balloon_size_mm": [round(v, 1) for v in s.size_mm],
        "balloons": n,
        "chosen_by": by,
        "reason": why,
        "positions_mm": [
            [round(float(xs[0] + i * h), 1), round(float(ys[0] + j * h), 1)] for i, j in pick.cells
        ],
        "options": rows,
        "automatic": by != "setting",
        "centre_mm": [0.0, 0.0],
        "radius_mm": round(max(s.size_mm[:2]) / 2, 1),
        "height_mm": round(s.size_mm[2], 1),
    }
    return pick.top, report, warnings


def points_layouts(
    lo: Array, hi: Array, size: tuple[float, float, float], most: int
) -> list[dict[str, Any]]:
    """For 1, 2, ... balloons the evenest grid on a table top from lo to hi (x, y)."""
    lx, ly = float(hi[0] - lo[0]), float(hi[1] - lo[1])
    fit_x, fit_y = max(int(lx // size[0]), 1), max(int(ly // size[1]), 1)
    best: dict[int, tuple[float, int, int]] = {}
    for nx in range(1, fit_x + 1):
        for ny in range(1, fit_y + 1):
            n = nx * ny
            gap = max(lx / nx, ly / ny)
            if n <= most and (n not in best or gap < best[n][0]):
                best[n] = (gap, nx, ny)
    out = []
    for n in sorted(best):
        gap, nx, ny = best[n]
        centres = [
            (float(lo[0] + (a + HALF) * lx / nx), float(lo[1] + (b + HALF) * ly / ny))
            for a in range(nx)
            for b in range(ny)
        ]
        out.append({"balloons": n, "grid": [nx, ny], "centres": centres, "span_mm": round(gap)})
    return out


AI_BOX_SYSTEM = """You advise a workshop that sews outdoor table covers. Under the cover, balloons
lie on the table top; the cover is a box with flat faces over table and balloons, so it forms a
roof and rain runs off. Between balloons the fabric runs straight; the slope is all round them.
Every table gets at least one balloon; the workshop's practice is 3 to 4 balloons for a 340 cm
long table. You get the table length and the options: how many balloons in which grid and the
span of fabric each balloon carries. Choose the number the workshop would use. Answer with JSON
only: {"balloons": <one of the options>, "reason": "one or two plain sentences"}"""


def box_points(
    v: Array, model_dir: Path, params: EffectiveParams, product: str
) -> tuple[Array, dict[str, Any]]:
    """Balloon points on the table top for a box cover, and the report."""
    s_model = model_dir.parent / str(params["hull.balloon_model"])
    if not (s_model / "model.glb").is_file():
        raise CoverError(
            f"hull.balloon_model = {params['hull.balloon_model']!r}: no such model (upload it)"
        )
    b = np.asarray(load_model(s_model).vertices, np.float64)
    b = b - np.array([(b[:, 0].min() + b[:, 0].max()) / 2, (b[:, 1].min() + b[:, 1].max()) / 2,
                      b[:, 2].min()])  # fmt: skip
    size = tuple(float(x) for x in b.max(axis=0) - b.min(axis=0))
    peak = float(v[:, 2].max())
    deck = v[v[:, 2] > peak - DECK_MM]
    lo, hi = deck[:, :2].min(axis=0), deck[:, :2].max(axis=0)
    rows = points_layouts(lo, hi, size, int(params["hull.balloon_max"]))  # type: ignore[arg-type]
    length = float(max(hi - lo))
    spacing = float(params["hull.balloon_spacing_mm"])  # type: ignore[arg-type]
    usual = max(1, round(length / spacing))
    facts = [{k: r[k] for k in ("balloons", "grid", "span_mm")} for r in rows]
    fixed = int(params["hull.balloon_count"])
    rule = next((r for r in rows if r["balloons"] >= usual), rows[-1])
    n, by = int(rule["balloons"]), "rule"
    per, long_cm = spacing / MM_PER_CM, length / MM_PER_CM
    why = f"about one balloon per {per:g} cm of table ({long_cm:.0f} cm long)"
    if fixed > 0:
        n, by, why = (
            min(rows, key=lambda r: abs(r["balloons"] - fixed))["balloons"],
            "setting",
            (f"hull.balloon_count = {fixed}"),
        )
    elif params["ai.provider"] != "none":
        try:
            from coverengine.ai import ask, lessons_text

            answer = ask(
                params,
                AI_BOX_SYSTEM + lessons_text("box"),
                json.dumps({"table": product, "length_mm": round(length), "options": facts}),
            )
            if any(r["balloons"] == int(answer["balloons"]) for r in rows):
                n, by, why = int(answer["balloons"]), "ai", str(answer.get("reason", ""))
        except Exception as exc:  # noqa: BLE001 - no AI: the rule decides
            why = f"the AI could not decide ({exc}); {why}"
    pick = next(r for r in rows if r["balloons"] == n)
    pts = np.vstack([b + np.array([x, y, peak]) for x, y in pick["centres"]])
    report = {
        "kind": "balloons",
        "balloon_model": str(params["hull.balloon_model"]),
        "balloon_size_mm": [round(x, 1) for x in size],
        "balloons": n,
        "chosen_by": by,
        "reason": why,
        "positions_mm": [[round(x, 1), round(y, 1)] for x, y in pick["centres"]],
        "options": facts,
        "automatic": by != "setting",
        "centre_mm": [0.0, 0.0],
        "radius_mm": round(max(size[:2]) / 2, 1),
        "height_mm": round(size[2], 1),
    }
    return pts, report
