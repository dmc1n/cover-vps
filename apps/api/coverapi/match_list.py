"""The price list as the main source of what each drawing cover is for (ADR-114).

The owner's retail list ("SUNS Covers", uploaded through Import prices, ADR-113, kept in
prices/imports/) has a row per cover with its drawing code ("Type nr."), the item name
("Suns cover corner set left"), what it suits ("Kota/ Aspen/ Evora: 3-seater, corner, 2-seater")
and its size. Rows with one text only are headings: a section ("Corner sets", "Dining tables")
or a family ("Kota / Aspen/ Evora"); a heading with a colon continues the row above ("Memphis/
Tondo: 2-seater left, ..."). "#VALUE!" cells are ignored.

`listing(folder)` reads the newest kept list that has a drawing-code column, once per file
change, as {"source", "stamp", "rows": {code: [row, ...]}, "unplaced": [...]}; the engine's
match_drawings decides the kind from it.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any

from coverengine.match_drawings import norm

from coverapi import products_sheet as ps_sheet

CODE = re.compile(r"[A-Za-z]\d{1,3}[A-Za-z]?")
SECTION = re.compile(r"\b(sets|tables|items|umbrellas|loungers|chairs|beds|daybeds)\b", re.I)
MIN_CODES = 10  # param-ok: a list with fewer coded rows is not the price list of the covers
ERROR_CELL = re.compile(r"^#[A-Z/0!?]+[!?]?$")  # Excel's #VALUE!, #N/A, #REF!


def _col(header: list[str], rx: str) -> str | None:
    return next((h for h in header if re.search(rx, h, re.I)), None)


def _code_column(table: dict[str, Any]) -> str | None:
    named = _col(table["header"], r"type\s*n|\bcode\b|drawing")
    counts = {h: sum(bool(CODE.fullmatch(str(r.get(h) or "").strip())) for r in table["rows"])
              for h in table["header"]}  # fmt: skip
    best = max(counts, key=lambda h: counts[h]) if counts else None
    col = named if named and counts.get(named, 0) >= MIN_CODES else best
    return col if col and counts.get(col, 0) >= MIN_CODES else None


def parse(tables: list[dict[str, Any]], source: str = "") -> dict[str, Any]:
    rows: dict[str, list[dict[str, Any]]] = {}
    unplaced: list[dict[str, Any]] = []
    for t in tables:
        code_col = _code_column(t)
        if code_col is None:
            continue
        h = t["header"]
        item_col = _col(h, r"item\s*name|omschrijving|description")
        suit_col = _col(h, r"suitable|geschikt")
        size_col = _col(h, r"\bsize\b|maat|afmeting")
        section = family = None
        last: dict[str, Any] | None = None
        for i, r in enumerate(t["rows"], start=1):
            cells = {k: str(v).strip() for k, v in r.items()
                     if str(v or "").strip() and not ERROR_CELL.match(str(v).strip())}  # fmt: skip
            code = cells.get(code_col, "")
            if not CODE.fullmatch(code):
                texts = list(cells.values())
                if len(texts) == 1:
                    one = texts[0]
                    if ":" in one and last is not None:
                        last["suitable"] = f"{last['suitable']}\n{one}".strip()
                    elif SECTION.search(one):
                        section, family = one, None
                    else:
                        family = one
                elif texts:
                    unplaced.append({"sheet": t["name"], "row": i, "cells": cells,
                                     "why": "no drawing code"})  # fmt: skip
                continue
            last = {"code": code.upper(), "sheet": t["name"], "row": i, "section": section,
                    "family": family, "item": cells.get(item_col or "", ""),
                    "suitable": cells.get(suit_col or "", ""),
                    "size": cells.get(size_col or "", "")}  # fmt: skip
            rows.setdefault(norm(code), []).append(last)
    return {"source": source, "rows": rows, "unplaced": unplaced}


_lock = threading.Lock()
_cache: dict[str, Any] = {}


def newest(folder: Path) -> list[Path]:
    """The kept price lists, newest first (their names start with the upload's time)."""
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.iterdir() if p.is_file()
                   and p.suffix.lower() in (".xlsx", ".xlsm", ".csv")),
                  key=lambda p: p.name, reverse=True)  # fmt: skip


def listing(folder: Path) -> dict[str, Any] | None:
    """The newest kept list with a drawing-code column, parsed (None: there is none)."""
    files = newest(folder)
    stamp = "|".join(f"{p.name}:{p.stat().st_mtime}" for p in files)
    with _lock:
        if _cache.get("stamp") == stamp and _cache.get("folder") == str(folder):
            out: dict[str, Any] | None = _cache["listing"]
            return out
    found = None
    for p in files:
        try:
            tables = ps_sheet.read_sheets(p.name, p.read_bytes())
        except (ps_sheet.SheetError, OSError):
            continue
        doc = parse(tables, p.name)
        if doc["rows"]:
            doc["stamp"] = f"{p.name}:{p.stat().st_mtime}"
            found = doc
            break
    with _lock:
        _cache.update(stamp=stamp, folder=str(folder), listing=found)
    return found


STOCK_MODEL = r"^(suns|drawing)-[a-z0-9-]{1,120}$"  # a cover of our range: SUNS or drawing


def for_data(data: Path) -> dict[str, Any] | None:
    """The price list kept in this data folder (prices/imports/), parsed."""
    return listing(data / "prices" / "imports")
