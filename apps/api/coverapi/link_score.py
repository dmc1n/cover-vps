"""Which drawing cover and which 3D-model cover are the same product (ADR-132): the signals and
the score behind every proposal in Covers → Links.

The owner, 14 October 2026: "we have drawings and 3D models in the range for the same product;
link them so we can learn from them; propose what belongs together, we confirm it, and correct
it by hand when it is wrong."

A proposal is a score from 0 to 1 with its reasons, never a fact. The signals, each 0..1 or
left out when we do not have it (`links.weights` sets their shares):

- **names**: the drawing's product names (namecode.xlsx, products.json), its price list rows
  (item and "suits", ADR-113/114) and its code against the SUNS model's own name: a family in
  common ("Evora"), and the type ("D-Bed", "sunlounger", "2-seater", "corner"). A type that
  disagrees is a contradiction, not a small minus;
- **size**: the two covers' boxes (length ≥ width, height) in cm, within `links.size_tol_cm`;
- **shape**: the plan shape read from each cover surface (hull.glb) seen from above: straight,
  L, U/C, round;
- **kind**: the configurator kind both sides get (ADR-114 match card for the drawing,
  `match.kind_of` for the model): sofa, corner sofa, lounger, item, dining or round set;
- **side**: left/right from the names, else the hand of an L in plan; two hands that differ are
  a *mirror* pair (one drawing may serve both hands), scored lower, never refused;
- **picture**: the two cover.png renders' silhouettes (and the mirrored one);
- **the product list** itself: a pair namecode.xlsx linked (or only suggested) adds
  `links.sheet_bonus`; when its name says "pair" and the size or plan says no, the score is
  multiplied by `links.contradiction_factor` and the row says why. D2 ("Evora normal D- Bed",
  230 x 204 cm) is the worked example: the sheet linked it to the Evora sunlounger (90 x 220 cm).
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from coverapi import products_sheet as ps

MM_PER_CM = 10.0  # param-ok: units
COVER_N = re.compile(r"(?i)^cover\s*\d+\w?$")
DAYBED = re.compile(r"d\s*-?\s*bed|daybed|day\s+bed", re.I)
SUNLOUNGER = re.compile(r"sun\s*-?\s*lounger|\bligbed|\blounger\b|\blongue\b", re.I)
MIRROR = re.compile(r"mirror|gespiegeld|\bl\s*&\s*r\b|left\s*(?:&|and|/)\s*right", re.I)
CANDIDATES = ("suns-", "arr-")  # what a drawing may be linked to: SUNS models and arrangements


def _read(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def weights(p: Any) -> dict[str, float]:
    """links.weights "names=0.25,size=0.30,..." as a dict."""
    out = {}
    for item in str(p["links.weights"]).split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            out[k.strip()] = float(v)
    return out


# ---- what one cover is ----------------------------------------------------------------------


@dataclass
class Facts:
    """Everything the score reads about one cover, gathered once."""

    id: str
    side_kind: str  # "drawing" | "model"
    code: str = ""
    names: list[str] = field(default_factory=list)  # product names, price list items, own name
    families: set[str] = field(default_factory=set)
    types: set[str] = field(default_factory=set)
    sides: set[str] = field(default_factory=set)  # left / right / both
    kind: str | None = None  # the configurator kind (ADR-114)
    cover_cm: list[float] | None = None  # the cover's box: length ≥ width, height
    furniture_cm: list[float] | None = None  # the furniture's box (models only)
    plan: str = "unknown"  # straight | L | U | round | other
    hand: str | None = None  # the hand of an L in plan: left / right / None (no L, or square)
    silhouette: np.ndarray | None = None
    sheet_linked: list[str] = field(default_factory=list)  # namecode.xlsx: linked SUNS models
    sheet_suggested: list[str] = field(default_factory=list)
    sheet_label: str = ""
    side_doubt: str = ""  # the names disagree on left or right
    no_cover: bool = False
    status: str | None = None  # the Desk status

    def brief(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "code": self.code,
            "name": (self.names[0] if self.names else self.id)[:120],
            "kind": self.kind,
            "cover_cm": self.cover_cm,
            "furniture_cm": self.furniture_cm,
            "plan": self.plan,
            "hand": self.hand,
            "status": self.status,
        }


def lounger_type(text: str) -> str | None:
    """A D-bed (a wide, square-ish bed) is not a sunlounger (a long narrow one): the products
    sheet calls both a "daybed" (products_sheet.kinds), which is how D2 met the sunlounger."""
    if DAYBED.search(text):
        return "d-bed"
    if SUNLOUNGER.search(text):
        return "sunlounger"
    return None


def types_of(texts: Iterable[str]) -> tuple[set[str], set[str]]:
    types: set[str] = set()
    sides: set[str] = set()
    for t in texts:
        k, s = ps.kinds(t)
        lt = lounger_type(t)
        if lt:
            k = (k - {"daybed"}) | {lt}
        types |= k
        sides |= s & {"left", "right"}
        if MIRROR.search(t):
            sides.add("both")
    if {"left", "right"} <= sides:
        sides = {"both"}
    return types, sides


def _box_cm(bbox: Any) -> list[float] | None:
    try:
        lo, hi = bbox
        x, y, z = (float(hi[i]) - float(lo[i]) for i in range(3))
    except (TypeError, ValueError):
        return None
    plan = sorted([x / MM_PER_CM, y / MM_PER_CM])[::-1]
    return [round(v, 1) for v in plan + [z / MM_PER_CM]]


def plan_grid(model_dir: Path, cells: int) -> np.ndarray | None:
    """The cover seen from above: a boolean grid (rows = y from the back, columns = x), read
    from hull.glb's vertices and triangle centres (the hull is dense, so no gaps at this size)."""
    path = model_dir / "hull.glb"
    if not path.is_file():
        return None
    try:
        import trimesh

        m: Any = trimesh.load(path, force="mesh")
        v = np.asarray(m.vertices, dtype=float)
        f = np.asarray(m.faces)
    except Exception:  # noqa: BLE001 - a hull that cannot be read has no plan
        return None
    if len(v) == 0:
        return None
    # hull.glb is glTF (metres, Y up): plan x = x, plan y = -z (ADR model_io)
    pts: Any = np.c_[v[:, 0], -1.0 * v[:, 2]]
    if len(f):
        tri = pts[f]
        pts = np.vstack(
            [
                pts,
                tri.mean(axis=1),
                (tri[:, 0] + tri[:, 1]) / 2.0,
                (tri[:, 1] + tri[:, 2]) / 2.0,
                (tri[:, 0] + tri[:, 2]) / 2.0,
            ]
        )
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    size = hi - lo
    if size.max() <= 0:
        return None
    scale = (cells - 1) / size.max()
    nx, ny = int(size[0] * scale) + 1, int(size[1] * scale) + 1
    ij = np.floor((pts - lo) * scale + 0.5).astype(int)
    grid = np.zeros((ny, nx), dtype=bool)
    grid[ny - 1 - np.clip(ij[:, 1], 0, ny - 1), np.clip(ij[:, 0], 0, nx - 1)] = True
    from scipy import ndimage

    grid = ndimage.binary_closing(grid, iterations=1, border_value=1)
    grid = ndimage.binary_fill_holes(grid)
    return np.asarray(grid, dtype=bool)


def plan_shape(grid: np.ndarray | None) -> tuple[str, str | None]:
    """straight | L | U | round | other, and the hand of an L.

    The empty cells inside the box that touch its border are the shape's notches: none (or
    four small corners on a round one) is straight; one notch on two neighbouring sides is an L;
    one notch on one side only is a U or C. The hand of an L: its long arm and short arm turn
    one way or the other seen from above (the drawings' "left" C7 and "right" C6 are each
    other's mirror image, which is what this tells apart)."""
    if grid is None or grid.size == 0:
        return "unknown", None
    from scipy import ndimage

    ny, nx = grid.shape
    empty = ~grid
    fill = float(grid.mean())
    labels, n = ndimage.label(empty)
    notches = []
    for k in range(1, n + 1):
        cells = labels == k
        share = float(cells.mean())
        if share < 0.03:  # param-ok: a notch smaller than this is the cover's rounding
            continue
        rows, cols = np.nonzero(cells)
        touch = {
            "top": rows.min() == 0,
            "bottom": rows.max() == ny - 1,
            "left": cols.min() == 0,
            "right": cols.max() == nx - 1,
        }
        notches.append(({s for s, t in touch.items() if t}, share))
    corners = [n for n in notches if len(n[0]) == 2]  # noqa: PLR2004 - two sides: a corner
    if not notches:
        return "straight", None
    round_like = 0.70 < fill < 0.86  # param-ok: π/4 ≈ 0.785 with a margin
    if len(notches) == 4 and len(corners) == 4 and round_like:  # noqa: PLR2004 - four corners
        return "round", None
    big = [n for n in notches if n[1] >= 0.12]  # param-ok: a notch this big makes the shape
    if len(big) == 1 and len(big[0][0]) == 2:  # noqa: PLR2004 - an L: one corner cut away
        return "L", _hand(big[0][0], nx, ny)
    if len(big) == 1 and len(big[0][0]) == 1:
        return "U", None
    if not big:
        return "straight", None
    return "other", None


def _hand(missing: set[str], nx: int, ny: int) -> str | None:
    """Which way an L turns: from the full corner, the long arm and the short arm. The
    drawings' C7 ("Left BIG": back along x, arm down on the left) reads as left."""
    if abs(nx - ny) <= max(nx, ny) * 0.04:  # param-ok: arms within 4 %: an L that is its own mirror
        return None
    # the full corner is the one opposite the missing one; both arms run from it, in plan
    # coordinates (x to the right, y to the back)
    x_arm = (1 if "right" in missing else -1, 0)
    y_arm = (0, -1 if "bottom" in missing else 1)
    long_arm, short_arm = (x_arm, y_arm) if nx > ny else (y_arm, x_arm)
    cross = long_arm[0] * short_arm[1] - long_arm[1] * short_arm[0]
    return "left" if cross < 0 else "right"


def silhouette(png: Path, px: int) -> np.ndarray | None:
    """cover.png's silhouette (alpha, or not-white), cropped and scaled to px x 3/4 px."""
    if not png.is_file():
        return None
    try:
        from PIL import Image

        im = Image.open(png).convert("RGBA")
    except Exception:  # noqa: BLE001 - no picture, no signal
        return None
    a = np.asarray(im)
    mask = a[:, :, 3] > 16  # param-ok: alpha above noise
    if mask.all():
        mask = a[:, :, :3].min(axis=2) < 245  # param-ok: not white
    rows, cols = np.nonzero(mask)
    if len(rows) == 0:
        return None
    crop = mask[rows.min() : rows.max() + 1, cols.min() : cols.max() + 1]
    small = Image.fromarray(crop.astype(np.uint8) * 255).resize((px, px * 3 // 4))
    return np.asarray(small) > 127  # param-ok: half grey


def facts(
    model_dir: Path,
    p: Any,
    listing: Mapping[str, Any] | None = None,
    vocab: set[str] | None = None,
) -> Facts:
    """Everything the score needs about one cover (drawing-* or a 3D model)."""
    from coverengine import match as mt
    from coverengine import match_drawings as md
    from coverengine.catalogue import is_no_cover

    d = model_dir
    cover = _read(d / "cover.json")
    desk = _read(d / "desk.json")
    hull = _read(d / "hull.json")
    model = _read(d / "model.json")
    is_drawing = d.name.startswith("drawing-")
    f = Facts(id=d.name, side_kind="drawing" if is_drawing else "model")
    f.no_cover = is_no_cover(cover)
    f.status = desk.get("status")
    f.cover_cm = _box_cm(hull.get("bbox_mm") or (model.get("bbox_mm") if is_drawing else None))
    grid = plan_grid(d, int(p["links.plan_cells"]))
    f.plan, f.hand = plan_shape(grid)
    f.silhouette = silhouette(d / "cover.png", int(p["links.picture_px"]))
    if is_drawing:
        f.code = str(desk.get("code") or d.name.removeprefix("drawing-").upper())
        prod = _read(d / "products.json")
        labels = [str(x) for x in prod.get("labels") or [] if not COVER_N.match(str(x).strip())]
        rows = [r for c in md.codes(d) for r in ((listing or {}).get("rows") or {}).get(c, [])]
        items = [" ".join(str(r.get(k) or "") for k in ("item", "suitable")) for r in rows]
        f.names = labels + [x for x in items if x.strip()]
        f.sheet_label = labels[0] if labels else ""
        suns = prod.get("suns") or {}
        f.sheet_linked = [str(x) for x in suns.get("linked") or []]
        f.sheet_suggested = [str(x) for x in suns.get("suggested") or []]
        fam_words = set().union(*(ps._words(t) for t in f.names)) if f.names else set()
        fam_rows = {w for r in rows for w in md._families(str(r.get("suitable") or ""))}
        f.families = (fam_words & (vocab or fam_words)) | {w for w in fam_rows if " " not in w}
        f.types, _ = types_of(f.names + [f.code])
        # the hand: the product list's name, else the price list's item name ("suits" names
        # the modules' hands, not the set's); the two disagreeing is a doubt, the plan decides
        _, by_label = types_of(labels + [f.code])
        _, by_item = types_of([str(r.get("item") or "") for r in rows])
        if by_label and by_item and by_label != by_item:
            f.side_doubt = (
                f"left or right: the product list says {'/'.join(sorted(by_label))}, "
                f"the price list {'/'.join(sorted(by_item))}"
            )
            f.sides = {f.hand} if f.hand else set()
        else:
            f.sides = by_label or by_item
        try:
            r = md.review(d, p, listing, {})  # type: ignore[arg-type]
        except Exception:  # noqa: BLE001 - a cover the match card cannot read has no kind
            r = None
        f.kind = (r or {}).get("kind")
    else:
        name = d.name.removeprefix("suns-").removeprefix("arr-")
        notes = str(cover.get("notes") or "")
        own = notes.split(": ", 1)[-1] if ": " in notes else name.replace("-", " ")
        f.code = d.name
        f.names = [own, name.replace("-", " ")]
        f.families = ps._words(name) - ps.GENERIC - {"arrangement"}
        f.types, f.sides = types_of([name.replace("-", " ")])
        size = model.get("size_mm")
        if size:
            fz = sorted([float(size[0]) / MM_PER_CM, float(size[1]) / MM_PER_CM])[::-1]
            f.furniture_cm = [round(v, 1) for v in fz + [float(size[2]) / MM_PER_CM]]
        category = str(cover.get("category") or "").split(" › ")[-1]
        if f.furniture_cm:
            f.kind = mt.kind_of(d.name, category, f.furniture_cm)
        refs = _read(d / ps.DRAWINGS_JSON)
        f.sheet_linked = [str(x.get("id")) for x in refs.get("linked") or [] if x.get("id")]
        f.sheet_suggested = [str(x.get("id")) for x in refs.get("suggested") or [] if x.get("id")]
    return f


def gather(
    models: Path, p: Any, listing: Mapping[str, Any] | None = None
) -> tuple[list[Facts], list[Facts]]:
    """(drawings, models) with their facts; covers marked "no cover" are left out."""
    vocab: set[str] = set()
    for d in sorted(models.glob("suns-*")):
        vocab |= ps._words(d.name.removeprefix("suns-")) - ps.GENERIC
    drawings = [
        facts(d, p, listing, vocab)
        for d in sorted(models.glob("drawing-*"))
        if (d / "cover.json").is_file()
    ]
    others = [
        facts(d, p, listing, vocab)
        for pre in CANDIDATES
        for d in sorted(models.glob(pre + "*"))
        if (d / "cover.json").is_file()
    ]
    return [f for f in drawings if not f.no_cover], [f for f in others if not f.no_cover]


# ---- the score of one pair ------------------------------------------------------------------


def _dim(diff: float, tol: float, falloff: float) -> float:
    return max(0.0, 1.0 - max(0.0, abs(diff) - tol) / falloff)


def size_signal(
    a: list[float] | None, b: list[float] | None, p: Any
) -> tuple[float | None, list[float]]:
    if not a or not b:
        return None, []
    tol = float(p["links.size_tol_cm"])
    diffs = [round(b[i] - a[i], 1) for i in range(3)]
    s = [
        _dim(diffs[0], tol, float(p["links.size_falloff_cm"])),
        _dim(diffs[1], tol, float(p["links.size_falloff_cm"])),
        _dim(diffs[2], tol, float(p["links.height_falloff_cm"])),
    ]
    return (s[0] * s[1] * s[2]) ** (1.0 / 3.0), diffs


def picture_signal(a: np.ndarray | None, b: np.ndarray | None) -> tuple[float | None, bool]:
    """IoU of two silhouettes, and whether the mirrored one fits better."""
    if a is None or b is None or a.shape != b.shape:
        return None, False

    def iou(x: np.ndarray, y: np.ndarray) -> float:
        u = float((x | y).sum())
        return float((x & y).sum()) / u if u else 0.0

    straight, flipped = iou(a, b), iou(a, b[:, ::-1])
    return max(straight, flipped), flipped > straight + 0.05  # param-ok: clearly better mirrored


def score(dr: Facts, m: Facts, p: Any) -> dict[str, Any]:
    """One pair's score (0..1), every signal's part and the reasons, best first."""
    w = weights(p)
    sig: dict[str, float] = {}
    reasons: list[str] = []
    doubts: list[str] = []
    # names: a family in common, the type
    fam = sorted(dr.families & m.families)
    common_t = dr.types & m.types
    type_conflict = bool(dr.types and m.types and not common_t)
    if fam or common_t:
        s = (0.6 if fam else 0.0) + (
            0.4 if common_t else 0.0 if type_conflict else 0.2
        )  # param-ok: family 0.6, type 0.4 (unknown half)
        sig["names"] = s
        if fam:
            reasons.append(f"family {', '.join(fam)} in both names")
        if common_t:
            reasons.append(f"both a {', '.join(sorted(common_t))}")
    elif dr.names:
        sig["names"] = 0.0
    if dr.families and m.families and not fam:
        doubts.append(
            f"another family: the drawing names {', '.join(sorted(dr.families))}, "
            f"the model is {', '.join(sorted(m.families))}"
        )
    if type_conflict:
        doubts.append(
            f"the drawing's name says {'/'.join(sorted(dr.types))}, the model is a "
            f"{'/'.join(sorted(m.types))}"
        )
    # size
    s_size, diffs = size_signal(dr.cover_cm, m.cover_cm, p)
    if s_size is not None:
        sig["size"] = s_size
        txt = (
            f"covers {' x '.join(f'{v:g}' for v in dr.cover_cm or [])} and "
            f"{' x '.join(f'{v:g}' for v in m.cover_cm or [])} cm"
        )
        if s_size >= 0.8:  # param-ok: a size that agrees well enough to say so
            reasons.append(f"sizes agree: {txt}")
        elif s_size < 0.3:  # param-ok: a size this far off contradicts a name
            doubts.append(f"sizes differ: {txt}")
    # plan shape
    if dr.plan != "unknown" and m.plan != "unknown":
        same = dr.plan == m.plan
        sig["shape"] = 1.0 if same else 0.5 if "other" in (dr.plan, m.plan) else 0.0
        if same:
            reasons.append(f"both {dr.plan} in plan")
        elif sig["shape"] == 0.0:
            doubts.append(f"plan shape: drawing {dr.plan}, model {m.plan}")
    # kind (ADR-114)
    if dr.kind and m.kind:
        sig["kind"] = 1.0 if dr.kind == m.kind else 0.0
        if dr.kind == m.kind:
            reasons.append(f"same kind ({dr.kind})")
        else:
            doubts.append(f"kind: drawing {dr.kind}, model {m.kind}")
    # side: names first, else the hand of an L
    d_side = "both" if "both" in dr.sides else next(iter(dr.sides), None) or dr.hand
    m_side = next(iter(m.sides - {"both"}), None) or m.hand
    mirror = False
    if d_side and m_side:
        if d_side == "both" or d_side == m_side:
            sig["side"] = 1.0
            reasons.append(
                "a mirrored pair: fits either hand" if d_side == "both" else f"same hand ({m_side})"
            )
        else:
            sig["side"] = 0.5
            mirror = True
            reasons.append(f"mirror image: drawing {d_side}, model {m_side}")
        if dr.side_doubt:
            doubts.append(dr.side_doubt)
    # picture
    s_pic, flipped = picture_signal(dr.silhouette, m.silhouette)
    if s_pic is not None:
        sig["picture"] = s_pic
        if s_pic >= 0.75:  # param-ok: the renders look alike
            reasons.append(
                f"renders alike ({round(100 * s_pic)} %{', mirrored' if flipped else ''})"
            )
    total_w = sum(w.get(k, 0.0) for k in sig)
    base = sum(w.get(k, 0.0) * v for k, v in sig.items()) / total_w if total_w else 0.0
    # the product list
    sheet = None
    if m.id in dr.sheet_linked:
        sheet = "linked"
        base += float(p["links.sheet_bonus"])
        reasons.insert(0, f"product list: “{dr.sheet_label or dr.code}” linked to this model")
    elif m.id in dr.sheet_suggested:
        sheet = "suggested"
        base += float(p["links.sheet_suggested_bonus"])
        reasons.insert(0, f"product list: “{dr.sheet_label or dr.code}” suggests this model")
    contradicted = bool(
        (sheet or fam)
        and (
            (s_size is not None and s_size < 0.3)
            or sig.get("shape") == 0.0  # param-ok: as above
            or type_conflict
        )
    )
    if contradicted:
        base *= float(p["links.contradiction_factor"])
        against = [
            f"the {x} says no"
            for x, bad in (
                ("size", s_size is not None and s_size < 0.3),  # param-ok: as above
                ("plan shape", sig.get("shape") == 0.0),
                ("type", type_conflict),
            )
            if bad
        ]
        doubts.insert(0, "the name says “pair”, but " + " and ".join(against))
    total = max(0.0, min(1.0, base))
    return {
        "drawing_id": dr.id,
        "model_id": m.id,
        "score": round(total, 3),
        "signals": {k: round(v, 3) for k, v in sig.items()},
        "reasons": reasons,
        "doubts": doubts,
        "mirror": mirror,
        "sheet": sheet,
        "size_diff_cm": diffs,
    }


def proposals(
    drawings: list[Facts], models: list[Facts], p: Any, per_drawing: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """Per drawing its best pairs from `links.propose_min` on (at most `per_drawing`; a pair
    whose sizes do not agree at all is no proposal of ours), and every pair the product list
    links whatever its score, so a person sees it (D2 and the Evora sunlounger); and the
    drawings left with none."""
    by_id = {m.id: m for m in models}
    out: list[dict[str, Any]] = []
    alone: list[str] = []
    floor = float(p["links.propose_min"])
    for dr in drawings:
        scored = sorted(
            (score(dr, m, p) for m in models), key=lambda r: (-r["score"], r["model_id"])
        )
        keep = [r for r in scored if r["score"] >= floor and r["signals"].get("size", 1.0) > 0][
            :per_drawing
        ]
        named = [score(dr, by_id[mid], p) for mid in dr.sheet_linked if mid in by_id]
        seen = {r["model_id"] for r in keep}
        keep += [r for r in named if r["model_id"] not in seen]
        if not keep:
            alone.append(dr.id)
        out += keep
    return out, alone


def strength(r: Mapping[str, Any], p: Any) -> str:
    """high (bulk-confirmable) | likely | unsure."""
    if r["score"] >= float(p["links.bulk_min"]) and not r.get("doubts"):
        return "high"
    if r["score"] >= float(p["links.propose_min"]) and not r.get("doubts"):
        return "likely"
    return "unsure"


def to_json(x: Any) -> Any:
    """For a JSON file: numpy numbers as floats."""
    if isinstance(x, dict):
        return {k: to_json(v) for k, v in x.items()}
    if isinstance(x, list):
        return [to_json(v) for v in x]
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, float) and math.isnan(x):
        return None
    return x
