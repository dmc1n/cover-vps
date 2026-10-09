"""A price list from Excel as fixed prices in the draft price set (ADR-113).

The owner, 9 October 2026: "I have a price list in Excel; these are retail prices incl. VAT.
Can I upload this Excel somewhere so you set these prices as fixed prices for the current
covers?"

On Admin → Prices & costing → Channels & price lists an admin uploads the list (.xlsx, .csv or a
.zip of them; read with the product list's careful reader, ADR-091). The program

- finds the **price column** by content: cells that read as money ("€ 1.234,95", "1234.95",
  "99,-", a number cell), with a head start for a header that says prijs / price / retail /
  verkoop / incl; and whether the prices are incl. or ex VAT (default incl., the owner's case;
  a header saying "excl" / "ex BTW" turns it to ex);
- finds the **identification columns**: those whose cells name our covers. Each row is matched
  - *exact*: a drawing cover's code ("S40", "C 23"), the order number on its drawing
    ("Cover 66"), a cover's own name or id ("SUNS-2 Seater-Kota", "2 seater kota"), a drawing
    cover's product name from the product list (products.json), an arrangement's name, the
    balloon or the frame;
  - *probable*: SUNS catalogue models named by a description, conservatively: a family and a
    type in common, the same shape, left never for right (`products_sheet.suns_for`); and the
    SUNS models the product list links to a drawing cover matched by its code;
  - *ambiguous*: the columns disagree, or a description names a family but no type; the
    candidates are offered to a person;
  - *none*: nothing matched; a person may pick the cover by hand.
  Two rows that give one cover two different prices are a *conflict*: an exact match wins over a
  probable one, otherwise the cover is left out until a person chooses;
- converts each price to what the channel stores: a channel that shows VAT (B2C) stores the
  price incl. VAT, one that does not (B2B) ex VAT. The conversion keeps six decimals so the
  price incl. VAT the shop shows equals the sheet's price to the cent; no channel rounding;
- writes the chosen fixed prices into the **draft** with the note "Imported from <file> (N
  prices)", never into a published version: the owner previews and publishes as always.

Every uploaded list is kept in the data folder (prices/imports/<stamp>-<name>).
`scripts/prices_import.py` runs the same matching from the command line.
"""

from __future__ import annotations

import copy
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from coverapi import products_sheet as ps_sheet

CONFIDENCE = ("exact", "probable")
ACCESSORY_NAMES = {"balloon": "balloon", "ballon": "balloon", "balloons": "balloon",
                   "frame": "frame", "tentframe": "frame", "frametent": "frame"}  # fmt: skip
PRICE_WORDS = re.compile(r"prijs|price|retail|verkoop|\bvk\b|incl|consument|advies|eur|€", re.I)
NOT_PRICE_WORDS = re.compile(
    r"cover|code|\bnr\b|\bno\b|number|nummer|artikel|\bart\b|\bid\b|qty|aantal|maat|size|"
    r"\bcm\b|\bmm\b|width|length|breed|lengte|hoogte|height|weight|gewicht|kg",
    re.I,
)
EX_WORDS = re.compile(r"\bexc?l?\b\.?|excl|exclusief|\bex\s*(btw|vat)|netto|\bnet\b", re.I)
INCL_WORDS = re.compile(r"\bincl|inclusief|\binc\b|bruto|gross", re.I)
MIN_RATE = 0.5  # param-ok: a price column: at least half its cells read as money
MIN_HITS = 0.1  # param-ok: an identification column names a cover in at least 10 % of rows
DECIMALS = 6  # param-ok: a converted fixed price keeps this many decimals (exact to the cent)
UPLOAD_NAME = re.compile(r"\d{8}-\d{6}-[A-Za-z0-9._-]+")
PERCENT = 100.0  # param-ok: percent to ratio


class ImportError_(ValueError):
    """Something the person can fix, said plainly."""


# ---- reading money --------------------------------------------------------------------------


def parse_price(value: Any) -> float | None:
    """A price as the sheet writes it: 1234.95, "€ 1.234,95", "1,234.95", "99,-", "EUR 249".
    None when the cell is no price (text, a code, empty, zero or less)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return round(float(value), 2) if value > 0 else None
    s = str(value).strip()
    s = re.sub(r"(?i)€|\beur(o|os)?\b|\bincl\.?|\bexcl?\.?|\bbtw\b|\bvat\b", "", s)
    s = re.sub(r"\s|'", "", s)
    s = re.sub(r"[,.]-+$", "", s)  # "99,-"
    if not re.fullmatch(r"\d[\d.,]*", s):
        return None
    s = s.rstrip(".,")
    if "," in s and "." in s:
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s or "." in s:
        sep = "," if "," in s else "."
        parts = s.split(sep)
        grouped = 1 <= len(parts[0]) <= 3 and all(len(p) == 3 for p in parts[1:])  # noqa: PLR2004
        if grouped and (len(parts) > 2 or len(parts[1]) == 3):  # noqa: PLR2004 - "1.234"
            s = "".join(parts)
        elif len(parts) == 2:  # noqa: PLR2004 - one separator: the decimals
            s = f"{parts[0]}.{parts[1]}"
        else:
            return None
    try:
        v = float(s)
    except ValueError:
        return None
    return round(v, 2) if v > 0 else None


def _money_like(v: str) -> bool:
    return bool(re.search(r"€|eur|[.,]\d{1,2}\b|[.,]-", v, re.I))


def _sequential(vals: list[str]) -> bool:
    """1, 2, 3 …: a row number, not a price."""
    try:
        nums = [int(v) for v in vals]
    except ValueError:
        return False
    return len(nums) > 2 and all(b - a == 1 for a, b in zip(nums, nums[1:], strict=False))  # noqa: PLR2004


def price_columns(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every column that could hold the prices, best first, with its score and why."""
    out: dict[str, dict[str, Any]] = {}
    for t in tables:
        for col in t["header"]:
            vals = [str(r.get(col) or "") for r in t["rows"] if str(r.get(col) or "").strip()]
            if not vals:
                continue
            ok = [v for v in vals if parse_price(v) is not None]
            rate = len(ok) / len(vals)
            if rate < MIN_RATE:
                continue
            score = rate
            if PRICE_WORDS.search(col):
                score += 1.0
            if INCL_WORDS.search(col):
                score += 0.25  # param-ok: two price columns: incl. first (the owner's case)
            if NOT_PRICE_WORDS.search(col) and not PRICE_WORDS.search(col):
                score -= 1.0
            if _sequential(vals):
                score -= 1.0
            if any(_money_like(v) for v in ok) or any("." in v for v in ok):
                score += 0.25  # param-ok: cents or a euro sign: money
            prev = out.get(col)
            if prev is None or score > prev["score"]:
                out[col] = {"column": col, "score": round(score, 2), "rate": round(rate, 2)}
    return sorted(out.values(), key=lambda c: -c["score"])


def vat_hint(column: str | None) -> bool | None:
    """What the price column's header says: True incl. VAT, False ex VAT, None nothing."""
    if not column:
        return None
    if INCL_WORDS.search(column):
        return True
    if EX_WORDS.search(column):
        return False
    return None


# ---- what we sell ---------------------------------------------------------------------------


def catalogue(models: Path) -> dict[str, dict[str, Any]]:
    """Every cover a price can belong to: id → {name, kind, code, calculated, labels}; and the
    balloon and the frame."""
    from coverapi.desk import _code
    from coverapi.prices import _name, model_kind

    out: dict[str, dict[str, Any]] = {}
    for d in sorted(models.glob("*")) if models.is_dir() else []:
        if not (d / "cover.json").is_file():
            continue
        kind = model_kind(d.name)
        base = _name(d)
        code = _code(d) if kind == "drawing" else ""
        labels = ps_sheet.product_labels(d) if kind == "drawing" else []
        words = [x for x in labels if not re.fullmatch(r"(?i)cover\s*\d+\w?", x.strip())]
        out[d.name] = {
            "id": d.name,
            "name": f"{code} · {words[0]}"[:90] if code and words else base,
            "base": base,
            "kind": kind,
            "code": code,
            "calculated": (d / "finished.json").is_file(),
            "labels": labels,
        }
    for code in ("balloon", "frame"):
        out[code] = {"id": code, "name": code.capitalize(), "base": code, "kind": "accessory",
                     "code": "",
                     "calculated": True, "labels": []}  # fmt: skip
    return out


def name_keys(cat: dict[str, dict[str, Any]]) -> ps_sheet.Keys:
    """Every exact way a cover may be named → its ids: its name, its id with and without the
    prefix, "SUNS" left off, an arrangement's name, a drawing cover's product names."""
    from coverengine.match import _pretty

    keys: ps_sheet.Keys = {}

    def add(text: str, mid: str) -> None:
        k = ps_sheet.norm(text)
        if len(k) > 2 and mid not in keys.setdefault(k, []):  # noqa: PLR2004 - no "c1"-like noise
            keys[k].append(mid)

    for mid, c in cat.items():
        if c["kind"] == "accessory":
            continue
        bare = re.sub(r"^(suns|drawing|arr)-", "", mid)
        for text in (c["base"], mid, bare, _pretty(c["base"])):
            add(text, mid)
            add(re.sub(r"(?i)^suns\b", "", text), mid)
            add(re.sub(r"(?i)^arrangement\b", "", text), mid)
        for label in c["labels"]:
            if not re.fullmatch(r"(?i)cover\s*\d+\w?", label.strip()):  # "Cover 105": the code's
                add(label, mid)
    return keys


# ---- matching -------------------------------------------------------------------------------


class Matcher:
    """Names in a row → covers."""

    def __init__(self, models: Path, data_dir: Path) -> None:
        from coverengine import quote as q

        self.cat = catalogue(models)
        self.codes = ps_sheet.drawing_keys(models, data_dir)
        self.names = name_keys(self.cat)
        self.suns = ps_sheet.suns_index(models)
        self.configurator = {ps_sheet.norm(v["label"]) for v in q.PRODUCTS.values()} | {
            ps_sheet.norm(k) for k in q.PRODUCTS
        }
        self.products: dict[str, dict[str, Any]] = {}
        for mid in self.cat:
            if mid.startswith("drawing-"):
                self.products[mid] = ps_sheet._doc(models / mid / ps_sheet.PRODUCTS_JSON)

    def exact(self, value: str) -> tuple[list[str], str]:
        """Covers this cell names exactly, and how."""
        k = ps_sheet.norm(value)
        if not k:
            return [], ""
        if k in ACCESSORY_NAMES:
            return [ACCESSORY_NAMES[k]], "accessory"
        ids = [m for m in ps_sheet.match(value, self.codes) if m in self.cat]
        if ids:
            return ids, "code"
        ids = [m for m in self.names.get(k, []) if m in self.cat]
        if ids:
            return ids, "name"
        return [], ""

    def fuzzy(self, value: str) -> dict[str, list[str]]:
        if not re.search(r"[A-Za-z]{3}", value or ""):
            return {"linked": [], "suggested": []}
        return ps_sheet.suns_for(value, self.suns)

    def linked_suns(self, drawing: str) -> list[str]:
        """The SUNS models the product list links to this drawing cover, when the cover
        carries one product only (one code on two products links both, which says nothing)."""
        doc = self.products.get(drawing) or {}
        labels = [x for x in doc.get("labels") or []
                  if not re.fullmatch(r"(?i)cover\s*\d+\w?", str(x).strip())]  # fmt: skip
        if len(labels) > 1:
            return []
        return [m for m in (doc.get("suns") or {}).get("linked") or [] if m in self.cat]

    def is_configurator(self, value: str) -> bool:
        return ps_sheet.norm(value) in self.configurator


def id_columns(tables: list[dict[str, Any]], m: Matcher, price_col: str | None) -> list[str]:
    """The columns whose cells name our covers, best first."""
    hits: dict[str, int] = {}
    rows = 0
    for t in tables:
        rows += len(t["rows"])
        for col in t["header"]:
            if col == price_col:
                continue
            n = 0
            for r in t["rows"]:
                v = str(r.get(col) or "")
                if v and (m.exact(v)[0] or m.fuzzy(v)["linked"]):
                    n += 1
            hits[col] = hits.get(col, 0) + n
    need = max(1, int(rows * MIN_HITS))
    return [c for c, n in sorted(hits.items(), key=lambda kv: -kv[1]) if n >= need]


def _label(row: dict[str, Any], header: list[str], price_col: str) -> str:
    cells = [str(row.get(c) or "").strip() for c in header if c != price_col]
    return " · ".join(c for c in cells if c)[:120]


def match_row(row: dict[str, Any], cols: list[str], m: Matcher) -> dict[str, Any]:
    """One row's covers: targets (exact / probable) or candidates (ambiguous), and why."""
    exact_sets: list[tuple[str, list[str], str]] = []
    probable: dict[str, str] = {}
    suggested: dict[str, str] = {}
    configurator = False
    for col in cols:
        v = str(row.get(col) or "").strip()
        if not v:
            continue
        ids, how = m.exact(v)
        if ids:
            exact_sets.append((col, ids, how))
            continue
        f = m.fuzzy(v)
        for mid in f["linked"]:
            probable.setdefault(mid, f"family and type in “{v[:60]}”")
        for mid in f["suggested"]:
            suggested.setdefault(mid, f"family only in “{v[:60]}”")
        configurator = configurator or m.is_configurator(v)
    exact: dict[str, str] = {}
    disagree = False
    for col, ids, how in exact_sets:
        if exact and not set(ids) & set(exact):
            disagree = True
        for mid in ids:
            exact.setdefault(mid, f"{how} in {col}: “{str(row.get(col))[:60]}”")
    if disagree:
        cand = {**exact, **probable}
        return {"status": "ambiguous", "targets": [], "note": "the columns name different covers",
                "candidates": [{"id": k, "why": w} for k, w in cand.items()]}  # fmt: skip
    targets = [{"id": k, "confidence": "exact", "why": w} for k, w in exact.items()]
    if exact and not probable:
        for d in [k for k in exact if k.startswith("drawing-")]:
            for mid in m.linked_suns(d):
                probable.setdefault(mid, f"linked to {m.cat[d]['code'] or d} in the product list")
    targets += [{"id": k, "confidence": "probable", "why": w}
                for k, w in probable.items() if k not in exact]  # fmt: skip
    if targets:
        return {"status": "exact" if exact else "probable", "targets": targets, "candidates": [],
                "note": ""}  # fmt: skip
    if suggested:
        return {"status": "ambiguous", "targets": [], "note": "a family but no type: which cover?",
                "candidates": [{"id": k, "why": w} for k, w in suggested.items()]}  # fmt: skip
    note = ("a configurator product: its price follows from the sizes, not a fixed price"
            if configurator else "")  # fmt: skip
    return {"status": "none", "targets": [], "candidates": [], "note": note}


# ---- prices per channel ---------------------------------------------------------------------


def stored_price(given: float, incl_vat: bool, ch: dict[str, Any]) -> float:
    """What the channel's fixed price holds for a price given incl. or ex VAT: a channel that
    shows VAT stores it incl., otherwise ex. Exact: the shown price incl. VAT is the given one."""
    vat = float(ch["vat_pct"]) / PERCENT
    if bool(ch["show_vat"]) == incl_vat:
        return given
    return round(given / (1 + vat), DECIMALS) if incl_vat else round(given * (1 + vat), DECIMALS)


def incl_ex(stored: float, ch: dict[str, Any]) -> tuple[float, float]:
    """A stored fixed price as (incl. VAT, ex VAT), to the cent, as the costing shows it."""
    vat = float(ch["vat_pct"]) / PERCENT
    if ch["show_vat"]:
        return round(stored, 2), round(stored / (1 + vat), 2)
    return round(stored * (1 + vat), 2), round(stored, 2)


def current_price(
    mid: str,
    ps: dict[str, Any],
    channel: str,
    facts: Callable[[str], dict[str, Any] | None] | None,
) -> dict[str, Any] | None:
    """The price this cover has now in the channel: {incl, ex, fixed}; None when it has none
    (no calculated cover and no fixed price)."""
    from coverengine import costing

    ch = ps["channels"][channel]
    fixed = (ch.get("fixed") or {}).get(mid)
    if mid in costing.ACCESSORIES:
        p = costing.accessory_price(ps, mid, channel)
        return {"incl": p["gross_eur"], "ex": p["net_eur"], "fixed": p["fixed"]}
    f = facts(mid) if facts else None
    if f is not None:
        c = costing.costing(f, ps, mid)["channels"][channel]
        return {"incl": c["gross_eur"], "ex": c["net_eur"], "fixed": c["fixed"]}
    if fixed:
        incl, ex = incl_ex(float(fixed), ch)
        return {"incl": incl, "ex": ex, "fixed": True}
    return None


# ---- the whole list -------------------------------------------------------------------------


def read(name: str, data: bytes, max_files: int, max_bytes: int) -> list[dict[str, Any]]:
    """The tables in an .xlsx, a .csv or a .zip of them (the product list's careful reader)."""
    if name.lower().endswith(".zip"):
        files, _pdfs = ps_sheet.unpack(data, max_files, max_bytes)
        if not files:
            raise ImportError_("the zip holds no .xlsx or .csv")
    else:
        files = [(name, data)]
    tables: list[dict[str, Any]] = []
    errors = []
    for fname, raw in files:
        try:
            tables += ps_sheet.read_sheets(fname, raw)
        except ps_sheet.SheetError as exc:
            errors.append(str(exc))
    if not tables:
        raise ImportError_("; ".join(errors) or "the list holds no table with a header row")
    return tables


def analyse(
    tables: list[dict[str, Any]],
    m: Matcher,
    ps: dict[str, Any],
    channel: str,
    incl_vat: bool | None = None,
    price_column: str | None = None,
    columns: list[str] | None = None,
    facts: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """The matching report: every row, its covers and prices, the conflicts, what is chosen."""
    if channel not in ps["channels"]:
        raise ImportError_(f"no price list {channel!r}; one of {', '.join(ps['channels'])}")
    every = list(dict.fromkeys(c for t in tables for c in t["header"]))
    found = price_columns(tables)
    pcol = price_column or (found[0]["column"] if found else None)
    if pcol is None:
        raise ImportError_("no column holds prices (€ 1.234,95 or 1234.95): choose the column")
    if pcol not in every:
        raise ImportError_(f"there is no column {pcol!r}")
    hint = vat_hint(pcol)
    incl = incl_vat if incl_vat is not None else (hint if hint is not None else True)
    cols = [c for c in (columns or []) if c in every and c != pcol] or id_columns(tables, m, pcol)
    if not cols:
        raise ImportError_("no column names our covers (S40, Cover 66, a SUNS name): choose one")
    ch = ps["channels"][channel]
    rows: list[dict[str, Any]] = []
    for t in tables:
        if pcol not in t["header"]:
            continue
        for i, r in enumerate(t["rows"], start=1):
            raw = str(r.get(pcol) or "").strip()
            given = parse_price(raw)
            label = _label(r, t["header"], pcol)
            if not label and given is None:
                continue
            res = match_row(r, cols, m)
            if given is None:
                res = {**res, "status": "no_price", "note": "no price in this row" if not raw
                       else f"“{raw}” is not a price"}  # fmt: skip
            rows.append({"index": len(rows), "sheet": t["name"], "line": i, "label": label,
                         "cells": {c: r.get(c, "") for c in cols}, "price_raw": raw,
                         "price_given": given, **res})  # fmt: skip
    # one cover, two prices: exact wins over probable; otherwise a person chooses
    claims: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for row in rows:
        if row["status"] in ("exact", "probable"):
            for tg in row["targets"]:
                claims.setdefault(tg["id"], []).append((row, tg))
    conflicts = []
    for mid, cl in claims.items():
        if len({row["price_given"] for row, _ in cl}) <= 1:
            for _row, tg in cl[1:]:
                tg["same_as"] = cl[0][0]["index"]  # the same price twice: the first row sets it
            continue
        ex = [(row, tg) for row, tg in cl if tg["confidence"] == "exact"]
        if len({row["price_given"] for row, _ in ex}) == 1 and len(ex) < len(cl):
            for _row, tg in cl:
                if tg["confidence"] != "exact":
                    tg["dropped"] = f"row {ex[0][0]['line']} names it exactly"
            continue
        for _row, tg in cl:
            tg["conflict"] = True
        conflicts.append({"id": mid, "name": m.cat[mid]["name"],
                          "rows": [{"index": row["index"], "line": row["line"],
                                    "label": row["label"], "price_given": row["price_given"]}
                                   for row, _ in cl]})  # fmt: skip
    for row in rows:
        for tg in row["targets"]:
            c = m.cat[tg["id"]]
            tg |= {"name": c["name"], "kind": c["kind"], "code": c["code"],
                   "calculated": c["calculated"]}  # fmt: skip
            if row["price_given"] is not None:
                stored = stored_price(row["price_given"], incl, ch)
                tg["stored"] = stored
                tg["shown_incl"], tg["shown_ex"] = incl_ex(stored, ch)
            tg["current"] = current_price(tg["id"], ps, channel, facts)
            tg["chosen"] = row["price_given"] is not None and not (
                tg.get("conflict") or tg.get("dropped") or "same_as" in tg
            )
        for cd in row["candidates"]:
            c = m.cat[cd["id"]]
            cd |= {"name": c["name"], "kind": c["kind"], "code": c["code"]}
    count: dict[str, int] = {}
    for row in rows:
        count[row["status"]] = count.get(row["status"], 0) + 1
    chosen = {tg["id"] for row in rows for tg in row["targets"] if tg.get("chosen")}
    return {
        "channel": channel,
        "channel_name": ch.get("name", channel),
        "channel_shows_vat": bool(ch["show_vat"]),
        "vat_pct": float(ch["vat_pct"]),
        "incl_vat": incl,
        "vat_hint": hint,
        "price_column": pcol,
        "price_columns": [c["column"] for c in found],
        "id_columns": cols,
        "columns": every,
        "rows": rows,
        "counts": count,
        "conflicts": conflicts,
        "chosen": len(chosen),
        "covers": [
            {"id": c["id"], "name": c["name"], "kind": c["kind"], "code": c["code"]}
            for c in m.cat.values()
        ],  # fmt: skip
    }


def choose(
    report: dict[str, Any],
    exclude: list[str] | None = None,
    picks: list[dict[str, Any]] | None = None,
    known: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """The fixed prices to write: id → {stored, given, line, label}. The report's chosen
    targets, without the `exclude`d ids; then each pick {index: row, id: cover} (a row's price
    for a cover a person chose: an unmatched or ambiguous row, or one side of a conflict)."""
    out: dict[str, dict[str, Any]] = {}
    skip = set(exclude or [])
    for row in report["rows"]:
        for tg in row["targets"]:
            if tg.get("chosen") and tg["id"] not in skip and "stored" in tg:
                out[tg["id"]] = {"stored": tg["stored"], "given": row["price_given"],
                                 "line": row["line"], "label": row["label"]}  # fmt: skip
    rows = {r["index"]: r for r in report["rows"]}
    ch = {"vat_pct": report["vat_pct"], "show_vat": report["channel_shows_vat"]}
    for p in picks or []:
        try:
            row = rows[int(p.get("index"))]  # type: ignore[arg-type]
        except (KeyError, TypeError, ValueError):
            raise ImportError_(f"no row {p.get('index')!r} in this list") from None
        mid = str(p.get("id") or "")
        if known is not None and mid not in known:
            raise ImportError_(f"no cover {mid!r}")
        if row["price_given"] is None:
            raise ImportError_(f"row {row['line']} has no price")
        out[mid] = {"stored": stored_price(row["price_given"], report["incl_vat"], ch),
                    "given": row["price_given"], "line": row["line"],
                    "label": row["label"]}  # fmt: skip
    return out


def into_draft(
    base: dict[str, Any], channel: str, prices: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """A copy of the price set with these fixed prices in the channel."""
    out = copy.deepcopy(base)
    fixed = out["channels"][channel].setdefault("fixed", {})
    for mid, p in prices.items():
        fixed[mid] = p["stored"]
    return out


def note_for(filename: str, n: int, channel: str) -> str:
    return f"Imported from {filename} ({n} prices, {channel.upper()})"


def keep(folder: Path, name: str, data: bytes) -> str:
    """The uploaded list kept for reference: prices/imports/<stamp>-<name>."""
    folder.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)[-120:] or "prices.xlsx"
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = folder / f"{stamp}-{safe}"
    n = 1
    while path.exists():
        n += 1
        path = folder / f"{stamp}-copy{n}_{safe}"
    path.write_bytes(data)
    return path.name


def kept(folder: Path, upload: str) -> Path:
    """A kept upload by its name, never outside the folder."""
    if not UPLOAD_NAME.fullmatch(upload or ""):
        raise ImportError_("unknown upload; upload the list again")
    path = folder / upload
    if not path.is_file():
        raise ImportError_("unknown upload; upload the list again")
    return path


def original_name(upload: str) -> str:
    """'20261009-101500-prijslijst.xlsx' → 'prijslijst.xlsx'."""
    return re.sub(r"^\d{8}-\d{6}-(copy\d+_)?", "", upload)
