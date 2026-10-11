"""Approved drawing covers as "we already make a cover that fits" (ADR-114, the owner's decision
of 9 Oct 2026, option a): every drawing cover whose Desk status is approved or produced gets a
size card like the SUNS covers (ADR-064), with the kind of furniture it is for.

The kind, in this order (the first that says something decides, the others check it):
1. a person's word: `match.kind` in the cover's cover.json (also `match.side`, `match.chairs`);
   "none" keeps a cover out. It confirms a doubtful cover.
2. the price list (the newest uploaded list with a drawing-code column, "Type nr."): its section
   ("Corner sets", "Dining tables", ...) and item name ("Suns cover corner set left");
3. the product names the workshop's product list links to the cover (products.json, ADR-091);
4. the drawing's shape: an L is a corner sofa, a round one a round set, a sloped box a sofa (or a
   chair below LONG_SOFA_CM), a flat box as wide as a table with chairs a dining set.
Nothing says it: unknown, not offered. Two sources that disagree, sizes in the price list that
are not the cover's, a U/C or curved shape for a corner sofa, a code two covers share: doubtful,
not offered until a person confirms with `match.kind`.

Sizes follow the SUNS cards (the furniture, not the cover): the drawing's cover minus
`hull.clearance_mm` on each side and on top. A dining or round cover over table and chairs gets
the table's own size (from the price list or the product name, else the cover minus the chair
room) and its height is a ceiling (`height_max`): any table lower than the cover fits under it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from coverengine.params import EffectiveParams

MM_PER_CM = 10.0  # param-ok: units
LONG_SOFA_CM = 150.0  # param-ok: as match.LONG_SOFA_CM: a shorter "corner" is a module
CODE_TOKEN = re.compile(r"(?<![a-z0-9])[a-z]\d+[a-z]?(?![a-z0-9])")
LEFT = re.compile(r"\b(left|links)\b", re.I)
RIGHT = re.compile(r"\b(right|rechts|rightt)\b", re.I)
ROUND_WORDS = re.compile(r"Ø|\bdia\b|\bround\b|\brond\b", re.I)
WITHOUT = re.compile(r"\bw/?o\b[^,;]*?table", re.I)  # "w/o side table" names no kind
CHAIRS_WORDS = re.compile(r"chair|stoel", re.I)
NUM = re.compile(r"\d+(?:[.,]\d+)?")
TABLE_SIZE = re.compile(r"(\d{2,3})\s*[x×*]\s*(\d{2,3})")
DIAMETER = re.compile(r"Ø\s*(\d{2,3})|(\d{2,3})\s*(?:cm\s*)?Ø", re.I)
ISOFIT_EDGES = re.compile(r"back edge ([\d.]+(?: \+ [\d.]+)*)")

# words → kind, in this order; the first that matches decides (a doubt goes with some)
WORDS: tuple[tuple[re.Pattern[str], str, str | None], ...] = (
    (re.compile(r"umbrella|parasol", re.I), "none", None),
    (re.compile(r"extension", re.I), "item", "an extension piece, not a whole piece of furniture"),
    (re.compile(r"ibiza", re.I), "sofa", "Ibiza style: a corner and a sofa in one row"),
    (re.compile(r"(side|lounge|coffee)\s*tables?|bijzettafel|loungetafel", re.I), "item", None),
    (re.compile(r"tables?\b|tafel", re.I), "table", None),
    (
        re.compile(
            r"chaise\s*longue\s*set|\bCL\b|corner\s*set|lounge\s*set|hoek|l-part|moon", re.I
        ),
        "corner_sofa",
        None,
    ),  # fmt: skip
    (re.compile(r"daybed|lounger|ligbed|chaise\s*longue", re.I), "lounger", None),
    (re.compile(r"\bcorner\b", re.I), "corner", None),
    (
        re.compile(
            r"lounge\s*chair|loungechair|chair|stoel|single\s*seater|middle|hocker|"
            r"footstool|pouf",
            re.I,
        ),
        "item",
        None,
    ),  # fmt: skip
    (re.compile(r"seater|searter|sofa|bench|bank|zits", re.I), "sofa", None),
)
CURVED = re.compile(r"curved|angled", re.I)


def statuses(p: EffectiveParams) -> list[str]:
    """The Desk statuses whose drawing covers are offered (match.drawing_statuses)."""
    return [s.strip() for s in str(p["match.drawing_statuses"]).split(",") if s.strip()]


def _read(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc, dict) else {}


def norm(code: str) -> str:
    """As products_sheet.norm: "S 04" and "s4" are one code."""
    s = re.sub(r"[^a-z0-9]", "", str(code or "").lower())
    return re.sub(r"(?<![0-9])0+(?=[0-9])", "", s)


def codes(model_dir: Path) -> list[str]:
    """The drawing codes a cover answers to: the Desk's code ("cover 24 & 24B - S4 & S5" → s4,
    s5; "S10 (box)" → s10), else the folder name's."""
    text = str(_read(model_dir / "desk.json").get("code") or "")
    found = CODE_TOKEN.findall(text.lower())
    if not found:
        found = CODE_TOKEN.findall(model_dir.name.removeprefix("drawing-").replace("-", " "))
    return list(dict.fromkeys(norm(c) for c in found))


def words_kind(text: str, length_cm: float) -> tuple[str | None, str | None]:
    """The kind a product name says ("table" is dining or round, by Ø), and a doubt if any."""
    t = WITHOUT.sub(" ", text)
    for rx, kind, doubt in WORDS:
        if rx.search(t):
            if kind == "table":
                return ("round_set" if ROUND_WORDS.search(t) else "dining_set"), doubt
            if kind == "corner":
                return ("corner_sofa" if length_cm >= LONG_SOFA_CM else "item"), doubt
            return kind, doubt
    return None, None


def sides(texts: list[str]) -> str | None:
    """left, right, both (a mirrored pair) or None (said nowhere)."""
    left = any(LEFT.search(t) for t in texts)
    right = any(RIGHT.search(t) for t in texts)
    return "both" if left and right else "left" if left else "right" if right else None


def shape_of(model_dir: Path, size: list[float], p: EffectiveParams) -> dict[str, Any]:
    """What the drawing's shape says: its class (L, U, round, sloped, box, curved, free) and,
    when it is clear, the kind."""
    notes = str(_read(model_dir / "cover.json").get("notes") or "")
    head = notes.split("\n")[0]
    head = head.split(": ", 1)[1] if ": " in head else head
    length, width, height = size
    shape = "unknown"
    edges = ISOFIT_EDGES.search(head)
    if edges:
        n = edges.group(1).count("+") + 1
        shape = "L" if n == 2 else "sloped" if n == 1 else "U"  # noqa: PLR2004 - two edges: an L
    elif head.startswith("L shape"):
        shape = "L"
    elif head.startswith("round"):
        shape = "round"
    elif head.startswith("sloped box") or "(sloped box)" in head:
        shape = "sloped"
    elif "(hip)" in head:
        shape = "hip"  # a sofa, a chair or a daybed: no kind of its own
    elif head.startswith("box"):
        shape = "box"
    elif head.startswith("swept") or "(swept" in head:
        shape = "curved" if '"arc"' in head else "swept"
    elif "plan-profile" in head or head.startswith("outline") or "(faces" in head:
        shape = "free"
    kind = None
    chair_cm = float(p["hull.chair_room_mm"]) / MM_PER_CM
    table_min_cm = float(p["hull.table_top_min_mm"]) / MM_PER_CM
    chair_h_cm = float(p["hull.chair_height_dining_mm"]) / MM_PER_CM
    tol = float(p["match.drawing_size_tol_cm"])
    if shape == "L":
        kind = "corner_sofa"
    elif shape == "round":
        kind = "round_set"
    elif shape == "sloped":
        kind = "sofa" if length >= LONG_SOFA_CM else "item"
    elif shape == "box" and width >= 2 * chair_cm + table_min_cm and height >= chair_h_cm - tol:
        kind = "dining_set"  # a flat top as wide as a table with chairs, at chair height
    return {"shape": shape, "kind": kind}


def _size_cm(model_dir: Path) -> list[float] | None:
    m = _read(model_dir / "model.json")
    size = m.get("size_mm")
    if not size and m.get("bbox_mm"):
        lo, hi = m["bbox_mm"]
        size = [hi[i] - lo[i] for i in range(3)]
    if not size:
        return None
    return [float(x) / MM_PER_CM for x in size]


def _numbers(text: str) -> list[float]:
    return [float(x.replace(",", ".")) for x in NUM.findall(text)]


def _table_size(texts: list[str], kind: str) -> list[float] | None:
    """A table's own size written in a name: "Tables 340 x 100 cm", "Table Ø 170", "120 Ø"."""
    for t in texts:
        if kind == "round_set":
            ds = [float(a or b) for a, b in DIAMETER.findall(t)]
            if ds:
                return [max(ds)] * 2  # "170 & 180 Ø": the cover is made for the larger
        else:
            m = TABLE_SIZE.search(t)
            if m:
                return sorted([float(m.group(1)), float(m.group(2))])[::-1]
    return None


def row_kind(r: Mapping[str, Any], length_cm: float) -> tuple[str | None, str | None]:
    """A price list row's kind: its item name, else what it suits and its section; a table is
    round when any of its cells says Ø."""
    k, d = words_kind(str(r.get("item") or ""), length_cm)
    if k is None:
        k, d = words_kind(f"{r.get('suitable') or ''} {r.get('section') or ''}", length_cm)
    if k in ("dining_set", "round_set"):
        k, d = words_kind(f"table {r.get('suitable') or ''} {r.get('size') or ''}", length_cm)
    return k, d


def _check_sizes(row_size: str, cover: list[float], row: Mapping[str, Any],
                 p: EffectiveParams) -> str | None:  # fmt: skip
    """The price list's sizes against the cover's: None when they agree (the cover's own sizes,
    or a table's smaller by the chair room), else what differs."""
    nums = [x for x in _numbers(row_size) if x > 0]
    if not nums:
        return None
    tol = float(p["match.drawing_size_tol_cm"])
    if all(any(abs(c - n) <= tol for n in nums) for c in cover):
        return None
    if row_kind(row, max(cover[:2]))[0] in ("dining_set", "round_set"):
        chair = float(p["hull.chair_room_mm"]) / MM_PER_CM  # the list gives the table's size:
        w = sorted(cover[:2])[0]  # smaller than the cover by the chairs round it
        if max(cover[:2]) >= max(nums) and min(nums) <= w - 2 * chair + tol:
            return None
    return (f"price list {row_size.strip()} against the cover "
            f"{' x '.join(f'{x:g}' for x in cover)} cm")  # fmt: skip


def _families(suitable: str) -> list[str]:
    """ "Nardo/ Stockholm: 3-seater corner" → ["nardo", "stockholm"] (every line's families)."""
    out: list[str] = []
    for line in suitable.split("\n"):
        head = line.split(":")[0] if ":" in line else ""
        out += [w.strip().lower() for w in re.split(r"[/,&]| and ", head) if w.strip()]
    return [w for w in dict.fromkeys(out) if re.fullmatch(r"[a-z][a-z ]{2,30}", w)]


def _pretty_name(row: dict[str, Any] | None, labels: list[str], model_id: str) -> str:
    """The name the customer sees: the price list's item name and what it suits, else the
    product list's name, never the folder name if anything else is known."""
    if row:
        item = re.sub(r"\s+", " ", str(row.get("item") or "")).strip()
        item = re.sub(r"^suns\s+cover\b", "SUNS cover", item, flags=re.I)
        suit = re.sub(r"\s+", " ", str(row.get("suitable") or "").split("\n")[0]).strip()
        name = " – ".join(x for x in (item, suit) if x)
        if name:
            return name[:160]
    if labels:
        return " / ".join(labels)[:160]
    return model_id


def review(model_dir: Path, p: EffectiveParams, listing: Mapping[str, Any] | None = None,
           shared: Mapping[str, list[str]] | None = None) -> dict[str, Any] | None:  # fmt: skip
    """Everything decided about one drawing cover, offered or not, and why."""
    size = _size_cm(model_dir)
    if size is None:
        return None
    cover = _read(model_dir / "cover.json")
    desk = _read(model_dir / "desk.json")
    status = desk.get("status")
    offer = statuses(p)
    labels = [str(x) for x in (_read(model_dir / "products.json").get("labels") or [])
              if not re.fullmatch(r"(?i)cover\s*\d+\w?", str(x).strip())]  # fmt: skip
    mine = codes(model_dir)
    rows = [r for c in mine for r in ((listing or {}).get("rows") or {}).get(c, [])]
    clearance = float(p["hull.clearance_mm"]) / MM_PER_CM
    x, y, h = size
    plan = sorted([x, y])[::-1]
    shape = shape_of(model_dir, plan + [h], p)
    doubts: list[str] = []
    how: list[str] = []
    # the kind per source
    list_kinds: list[str] = []
    table: list[float] | None = None
    used = []
    for r in rows:
        bad = _check_sizes(str(r.get("size") or ""), [x, y, h], r, p)
        if bad:  # a row about another product (D6 in the list is the Blocchi hocker): not used
            doubts.append(f"{r['code']}: {bad}")
            continue
        used.append(r)
        k, d = row_kind(r, plan[0])
        if k:
            list_kinds.append(k)
        if d:
            doubts.append(d)
    label_kinds = []
    for t in labels:
        k, d = words_kind(t, plan[0])
        if k:
            label_kinds.append(k)
            if d and d not in doubts:
                doubts.append(d)
    m = cover.get("match")
    override: dict[str, Any] = m if isinstance(m, dict) else {}
    kind: str | None = None
    if override.get("kind"):
        kind = str(override["kind"])
        how.append("a person's word (cover.json match.kind)")
    elif list_kinds:
        kind = list_kinds[0]
        how.append("price list " + ", ".join(f"{r['code']} ({r.get('section') or '-'}: "
                                              f"{r.get('item') or r.get('suitable')})"
                                              for r in used))  # fmt: skip
    elif label_kinds:
        kind = label_kinds[0]
        how.append("product list: " + " / ".join(labels))
    elif shape["kind"]:
        kind = shape["kind"]
        how.append(f"the drawing's shape ({shape['shape']})")
    else:
        how.append("nothing says what it is for")
    # the others check it
    if len(set(list_kinds)) > 1:
        doubts.append("the price list's rows say " + " and ".join(sorted(set(list_kinds))))
    if len(set(label_kinds)) > 1:
        doubts.append("the product names say " + " and ".join(sorted(set(label_kinds))))
    for src, ks in (("the price list", list_kinds), ("the product names", label_kinds),
                    ("the shape", [shape["kind"]] if shape["kind"] else [])):  # fmt: skip
        if kind and kind != "none" and ks and kind not in ks and not override.get("kind"):
            doubts.append(f"{src} {'say' if src.endswith('s') else 'says'} {ks[0]}")
    if kind == "corner_sofa" and shape["shape"] == "U":
        doubts.append("a U or C shape: the configurator asks for an L")
    if shape["shape"] == "curved" or any(CURVED.search(t) for t in labels + [
            str(r.get("suitable") or "") for r in used]):  # fmt: skip
        doubts.append("a curved or angled shape: the sizes do not compare to a straight one")
    if kind in ("sofa", "corner_sofa", "item", "lounger") and shape["shape"] in ("swept", "free"):
        if not any("curved" in d or "Ibiza" in d for d in doubts):
            doubts.append(f"a free shape ({shape['shape']}): its box size may mislead")
    # the side of an L: price list, then product names, then the plan (an L longer along x is
    # the left one, as every drawing named left or right shows)
    # (the item name only: "suitable for" names the modules' hands, "2-seater left, corner, ...")
    side_list = sides([str(r.get("item") or "") for r in used])
    side_labels = sides(labels)
    tol = float(p["match.drawing_size_tol_cm"])
    side_plan = ("left" if x > y + tol else "right" if y > x + tol else None) \
        if shape["shape"] == "L" else None  # fmt: skip
    side = override.get("side") or side_list or side_labels or side_plan
    if kind == "corner_sofa" and not override.get("side"):
        said = [s for s in (side_list, side_labels, side_plan) if s and s != "both"]
        if len(set(said)) > 1:
            doubts.append(f"left or right: price list {side_list}, product names "
                          f"{side_labels}, plan {side_plan}")  # fmt: skip
    if side == "both":
        how.append("a mirrored pair: fits either hand")
        side = None
    if kind != "corner_sofa":
        side = None if kind not in ("sofa", "item", "lounger") else side
    # sizes: the furniture under the cover, as the SUNS cards
    chairs: bool | None = None
    height_max = False
    if kind in ("dining_set", "round_set"):
        chair = float(p["hull.chair_room_mm"]) / MM_PER_CM
        texts = [str(r.get("suitable") or "") + " " + str(r.get("size") or "") for r in used]
        table = _table_size(texts + labels, kind)
        if "chairs" in override:
            chairs = bool(override["chairs"])
        elif any(CHAIRS_WORDS.search(str(r.get("suitable") or "")) for r in used):
            chairs = True
        else:
            chairs = plan[1] - (table[1] if table else plan[1]) >= 2 * chair - tol or (
                table is None and plan[1] >= 2 * chair + float(p["hull.table_top_min_mm"])
                / MM_PER_CM)  # fmt: skip
        if table is None:  # the cover minus the chair room (and the clearance)
            table = [plan[0] - 2 * clearance - (2 * chair if chairs and kind == "round_set"
                                                else 0),
                     plan[1] - 2 * clearance - (2 * chair if chairs else 0)]  # fmt: skip
            how.append("table size from the cover minus the chair room")
            if kind == "round_set":
                table = [min(table)] * 2
        furniture = [*table, h - clearance]
        height_max = bool(chairs)
    else:
        furniture = [plan[0] - 2 * clearance, plan[1] - 2 * clearance, h - clearance]
    # a code two covers share (S10 box and plain): which one to sell is a person's choice
    for c in mine:
        others = [o for o in (shared or {}).get(c, []) if o != model_dir.name]
        if others:
            doubts.append(f"code {c.upper()} is also {', '.join(others)}")
    row = used[0] if used else None
    families = list(dict.fromkeys(f for r in used for f in _families(str(r.get("suitable") or ""))))
    unknown = kind in (None, "none")
    doubtful = bool(doubts) and not override.get("kind")
    in_status = status in offer
    return {
        "model_id": model_dir.name,
        "codes": [c.upper() for c in mine],
        "status": status,
        "name": _pretty_name(row, labels, model_dir.name),
        "category": str(cover.get("category") or "").split(" › ")[-1],
        "kind": None if unknown else kind,
        "how": "; ".join(how),
        "shape": shape["shape"],
        "size_cm": [round(v, 1) for v in sorted(furniture[:2])[::-1] + [furniture[2]]],
        "cover_cm": [round(v, 1) for v in plan + [h]],
        "height_max": height_max,
        "side": side,
        "chairs": chairs,
        "families": families,
        "price_list": [{"code": r["code"], "section": r.get("section"), "item": r.get("item"),
                        "suitable": r.get("suitable"), "size": r.get("size"),
                        "row": r.get("row"), "used": r in used} for r in rows],  # fmt: skip
        "labels": labels,
        "doubts": list(dict.fromkeys(doubts)),
        "confirmed": bool(override.get("kind")),
        "offered": in_status and not unknown and not doubtful,
        "why_not": (None if in_status and not unknown and not doubtful else
                    f"Desk status {status}" if not in_status else
                    "kind unknown" if unknown else "doubtful: confirm with match.kind"),
    }  # fmt: skip


def owners(models: Path, p: EffectiveParams) -> dict[str, list[str]]:
    """Per code the drawing covers with an offered Desk status that answer to it."""
    offer = statuses(p)
    out: dict[str, list[str]] = {}
    for d in sorted(models.glob("drawing-*")):
        if _read(d / "desk.json").get("status") in offer:
            for c in codes(d):
                out.setdefault(c, []).append(d.name)
    return out
