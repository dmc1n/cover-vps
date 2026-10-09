"""The drawing covers' size cards for review (ADR-114): which approved drawing cover the shop
offers as an existing cover, as which kind, decided how, with which sizes, and which are in doubt.

    COVER_DATA_DIR=~/cover-data uv run python scripts/matchcards.py [--out out/matchcards]
        [--models DIR] [--prices DIR]

Writes review.json (everything), review.csv (one row per drawing cover) and listing.json (the
price list as read, with the rows it could not place). Reads only; nothing in the models changes.
A doubtful cover is confirmed or corrected with `"match": {"kind": "...", "side": "...",
"chairs": true}` in its cover.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from coverapi.match_list import listing as read_listing
from coverengine import match_drawings as md
from coverengine.params import Registry


def main() -> None:
    data = Path(os.environ.get("COVER_DATA_DIR", "~/cover-data")).expanduser()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default="out/matchcards")
    ap.add_argument("--models", default=str(data / "models"))
    ap.add_argument("--prices", default=str(data / "prices" / "imports"))
    a = ap.parse_args()
    models, out = Path(a.models), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    p = Registry.load(None).resolve()
    lst = read_listing(Path(a.prices))
    shared = md.owners(models, p)
    reviews = [r for d in sorted(models.glob("drawing-*")) if (r := md.review(d, p, lst, shared))]
    by_code: dict[str, list[dict[str, Any]]] = {}
    for r in reviews:
        for c in r["codes"]:
            by_code.setdefault(c, []).append(r)
    unplaced = list((lst or {}).get("unplaced") or [])
    for _code, rows in sorted(((lst or {}).get("rows") or {}).items()):
        for row in rows:
            k, _ = md.row_kind(row, 0.0)
            covers = by_code.get(row["code"], [])
            used = [r["model_id"] for r in covers for x in r["price_list"]
                    if x["row"] == row["row"] and x["used"]]  # fmt: skip
            why = None
            if not covers:
                why = "no drawing cover with this code"
            elif k in (None, "none"):
                why = "not furniture the configurator covers" if k else "the row names no kind"
            elif not used:
                why = "its sizes are not those of " + ", ".join(r["model_id"] for r in covers)
            elif not any(r["status"] in md.statuses(p) for r in covers):
                why = "the cover is not approved yet: " + ", ".join(
                    f"{r['model_id']} ({r['status']})" for r in covers
                )
            if why:
                unplaced.append({**row, "why": why})
    (out / "review.json").write_text(json.dumps(reviews, indent=1, ensure_ascii=False))
    (out / "listing.json").write_text(json.dumps(
        {"source": (lst or {}).get("source"), "unplaced": unplaced,
         "rows": (lst or {}).get("rows")}, indent=1, ensure_ascii=False))  # fmt: skip
    cols = ["model_id", "codes", "status", "offered", "why_not", "kind", "category", "how",
            "shape", "side", "chairs", "size_cm", "height_max", "cover_cm", "name", "families",
            "doubts"]  # fmt: skip
    with (out / "review.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in reviews:
            w.writerow([" | ".join(map(str, v)) if isinstance(v, list) else v
                        for v in (r[c] for c in cols)])  # fmt: skip
    offered = [r for r in reviews if r["offered"]]
    statuses = md.statuses(p)
    doubtful = [r for r in reviews if r["status"] in statuses and not r["offered"]]
    print(f"price list: {(lst or {}).get('source')}")
    print(f"drawing covers: {len(reviews)}, approved or produced: "
          f"{sum(r['status'] in statuses for r in reviews)}, offered: {len(offered)}")  # fmt: skip
    for k, n in sorted(Counter(r["kind"] for r in offered).items()):
        print(f"  {k}: {n}")
    print(f"not offered although approved ({len(doubtful)}):")
    for r in doubtful:
        print(
            f"  {r['model_id']:34} {r['kind'] or '-':12} {r['why_not']}: {'; '.join(r['doubts'])}"
        )
    print(f"price list rows not placed: {len(unplaced)}")
    for u in unplaced:
        print(f"  {u.get('code') or ''} row {u.get('row')} under the header: {u['why']}"
              f" ({u.get('item') or u.get('cells')})")  # fmt: skip
    print(f"written: {out}/review.json, review.csv, listing.json")


if __name__ == "__main__":
    main()
