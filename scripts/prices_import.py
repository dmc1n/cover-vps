"""A price list from Excel matched to our covers, and (with --apply) put in the draft price set
(ADR-113). The same matching as Admin → Prices & costing → Import prices (Excel).

    COVER_DATA_DIR=~/cover-data uv run python scripts/prices_import.py FILE \
        [--channel b2c|b2b] [--incl-vat | --ex-vat] [--price-column NAME] \
        [--id-column NAME ...] [--json OUT.json] [--dry-run | --apply]

Without --apply nothing is written (--dry-run is the default and says so): the report is printed
as a table, and as JSON with --json. With --apply the matched prices go into the DRAFT with the
note "Imported from <file> (N prices)" and the file is kept in prices/imports/; publish on the
page (Preview changes → Publish). Nothing is ever published from here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from coverapi import prices  # noqa: E402
from coverapi import prices_import as pim  # noqa: E402
from coverapi.auth import Auth  # noqa: E402

LABEL = 44  # characters of a row's label in the table
NAME = 40  # characters of a cover's name in the table


def data_dir() -> Path:
    return Path(os.environ.get("COVER_DATA_DIR", Path.home() / "cover-data")).expanduser()


def money(x: float | None) -> str:
    return "-" if x is None else f"{x:,.2f}"


def mark(tg: dict[str, Any]) -> str:
    """Why a matched cover gets no price from this row."""
    if tg.get("chosen"):
        return ""
    if tg.get("conflict"):
        return " (conflict)"
    if "same_as" in tg:
        return " (same price above)"
    if tg.get("dropped"):
        return " (dropped)"
    return " (no price)"


def table(rep: dict[str, Any]) -> str:
    vat = "incl." if rep["incl_vat"] else "ex"
    unit = "incl. VAT" if rep["channel_shows_vat"] else "ex VAT"
    lines = [
        f"Price list {rep['file']}: prices {vat} VAT in column {rep['price_column']!r}, "
        f"covers named in {', '.join(repr(c) for c in rep['id_columns'])}",
        f"Channel {rep['channel']} ({rep['channel_name']}) stores fixed prices {unit}, "
        f"VAT {rep['vat_pct']:g} %",
        "",
        f"{'row':>4}  {'status':<9} {'given':>10} {'stored':>12} {'incl.VAT':>10} "
        f"{'now incl':>10}  {'cover':<{NAME}}  label",
    ]
    for row in rep["rows"]:
        label = row["label"][:LABEL]
        if not row["targets"]:
            cands = ", ".join(c["id"] for c in row["candidates"][:4])
            extra = "; ".join(x for x in (row["note"], cands) if x)
            lines.append(
                f"{row['line']:>4}  {row['status']:<9} {money(row['price_given']):>10} "
                f"{'':>12} {'':>10} {'':>10}  {'-':<{NAME}}  {label}"
                + (f"  [{extra}]" if extra else "")
            )
            continue
        for i, tg in enumerate(row["targets"]):
            now = (tg.get("current") or {}).get("incl")
            lines.append(
                f"{row['line'] if i == 0 else '':>4}  "
                f"{(row['status'] if i == 0 else tg['confidence']):<9} "
                f"{money(row['price_given']) if i == 0 else '':>10} "
                f"{(format(tg['stored'], '.10g') if 'stored' in tg else '-'):>12} "
                f"{money(tg.get('shown_incl')):>10} {money(now):>10}  "
                f"{(tg['id'] + mark(tg))[:NAME]:<{NAME}}  {label if i == 0 else ''}"
            )
            if i == 0 and row["note"]:
                lines.append(f"{'':>4}  {'':<9} {row['note']}")
    c = rep["counts"]
    lines += ["", "rows: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())),
              f"covers with a price chosen: {rep['chosen']}"]  # fmt: skip
    for cf in rep["conflicts"]:
        rows = "; ".join(f"row {r['line']} {money(r['price_given'])}" for r in cf["rows"])
        lines.append(f"conflict {cf['id']}: {rows} (left out; choose on the page)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("file", type=Path)
    ap.add_argument("--channel", default="b2c")
    vat = ap.add_mutually_exclusive_group()
    vat.add_argument("--incl-vat", dest="incl", action="store_const", const=True, default=None)
    vat.add_argument("--ex-vat", dest="incl", action="store_const", const=False)
    ap.add_argument("--price-column")
    ap.add_argument("--id-column", action="append", dest="id_columns")
    ap.add_argument("--json", type=Path, help="write the report as JSON here ('-' = stdout)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="only report (the default)")
    mode.add_argument("--apply", action="store_true", help="put the chosen prices in the draft")
    ap.add_argument("--by", default="cli", help="who imports (for the draft and the audit log)")
    args = ap.parse_args(argv)

    from coverengine.params import Registry

    root = data_dir()
    auth = Auth(root / "app.db")
    prices.ensure_table(auth)
    p = Registry.load(None).resolve()
    data = args.file.read_bytes()
    try:
        tables = pim.read(args.file.name, data, int(p["products.max_files"]),  # type: ignore[arg-type]
                          int(p["products.max_bytes"]))  # type: ignore[arg-type]  # fmt: skip
        facts = prices.Facts(root / "models")
        rep = pim.analyse(tables, pim.Matcher(root / "models", root), prices.current(auth),
                          args.channel, args.incl, args.price_column, args.id_columns,
                          facts.get)  # fmt: skip
    except (pim.ImportError_, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rep["file"] = args.file.name
    slim = {k: v for k, v in rep.items() if k != "covers"}
    if args.json:
        text = json.dumps(slim, indent=1, ensure_ascii=False)
        if str(args.json) == "-":
            print(text)
        else:
            args.json.write_text(text + "\n", encoding="utf-8")
    if str(args.json) != "-":
        print(table(rep))
    if not args.apply:
        print("\ndry run: nothing written (use --apply to put these prices in the draft)")
        return 0
    chosen = pim.choose(rep)
    if not chosen:
        print("no prices chosen; nothing written", file=sys.stderr)
        return 1
    kept = pim.keep(root / "prices" / "imports", args.file.name, data)
    out = prices.import_draft(auth, rep, chosen, args.file.name, args.by)
    print(
        f"\nput {out['count']} prices in the draft — {out['note']}; kept as prices/imports/{kept}"
    )
    print("Not published: open Admin → Prices & costing, Preview changes, then Publish.")
    if out["errors"]:
        print("the draft has errors: " + "; ".join(out["errors"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
