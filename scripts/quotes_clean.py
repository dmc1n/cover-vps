"""Old price proposals off the disk (ADR-123; run daily by scripts/housekeeping.sh).

Every proposal the shop makes is kept as <qid>.json plus its 3D scenes (<qid>.glb,
<qid>-<support>.glb) in cover-data/shop_quotes (the consumer shop), b2b_quotes (the B2B shop)
and quotes (the old webshop API). A visitor who asks for many prices fills the disk. A proposal
older than `limits.quotes_keep_days` is removed unless an order or a request names it: a B2C
order keeps its own copy of the proposal (orders.data "quote"), but its files stay too.

    COVER_DATA_DIR=~/cover-data uv run python scripts/quotes_clean.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import time
from pathlib import Path

DIRS = ("shop_quotes", "b2b_quotes", "quotes")
NAME = re.compile(r"([0-9a-f]{16})(-[a-z]+)?\.(json|glb)")
DAY_S = 86400


def referenced(db_path: Path) -> set[str]:
    """Every proposal id an order or a request names."""
    out: set[str] = set()
    if not db_path.is_file():
        return out
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "orders" in tables:
            for (data,) in db.execute("SELECT data FROM orders"):
                try:
                    doc = json.loads(data or "{}")
                except json.JSONDecodeError:
                    continue
                qid = (doc.get("customer") or {}).get("quote_id")
                if qid:
                    out.add(str(qid))
        if "b2b_orders" in tables:
            for (lines,) in db.execute("SELECT lines FROM b2b_orders"):
                try:
                    rows = json.loads(lines or "[]")
                except json.JSONDecodeError:
                    continue
                out |= {str(r["quote_id"]) for r in rows
                        if isinstance(r, dict) and r.get("quote_id")}  # fmt: skip
        if "requests" in tables:
            out |= {str(r[0]) for r in db.execute("SELECT quote_id FROM requests")}
    finally:
        db.close()
    return out


def clean(data: Path, keep_days: float, dry_run: bool, now: float | None = None) -> list[Path]:
    """The files removed (or that would be, with `dry_run`)."""
    cutoff = (now or time.time()) - keep_days * DAY_S
    keep = referenced(data / "app.db")
    gone: list[Path] = []
    for name in DIRS:
        folder = data / name
        if not folder.is_dir():
            continue
        for f in sorted(folder.iterdir()):
            m = NAME.fullmatch(f.name)
            if not m or not f.is_file() or m.group(1) in keep:
                continue
            if f.stat().st_mtime >= cutoff:
                continue
            if not dry_run:
                f.unlink()
            gone.append(f)
    return gone


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="only say what would go")
    data = os.environ.get("COVER_DATA_DIR", str(Path.home() / "cover-data"))
    ap.add_argument("--data", default=data)
    a = ap.parse_args()
    from coverengine.params import Registry

    days = float(Registry.load(None).resolve()["limits.quotes_keep_days"])  # type: ignore[arg-type]
    gone = clean(Path(a.data), days, a.dry_run)
    size = sum(f.stat().st_size for f in gone) if a.dry_run else None
    verb = "would remove" if a.dry_run else "removed"
    extra = f" ({size / 1e6:.0f} MB)" if size is not None else ""
    print(f"proposals older than {days:g} days: {verb} {len(gone)} files{extra}")


if __name__ == "__main__":
    main()
