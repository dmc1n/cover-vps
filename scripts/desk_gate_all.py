"""Migrate previously ungated covers to the Desk (ADR-128), dry-run by default.

Only the main session runs --apply on live data, after a dry run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from coverapi import gate_migrate as migration  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--models", type=Path)
    parser.add_argument("--db", type=Path)
    parser.add_argument("--only", default="")
    parser.add_argument("--by", default="Claude")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    root = Path(os.environ.get("COVER_DATA_DIR", str(Path.home() / "cover-data"))).expanduser()
    models = args.models or root / "models"
    if not models.is_dir():
        parser.error(f"no models folder: {models}")
    rows = migration.plan_gate_all(models, args.db or models.parent / "app.db")
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    if only:
        rows = [r for r in rows if r.model_id in only]
    for row in rows:
        if args.verbose or row.action not in ("already gated", "keep"):
            print(f"{row.action:<16} {row.model_id:<40} {row.reason}")
    for action, count in sorted(Counter(r.action for r in rows).items()):
        print(f"{action}: {count}")
    for reason, count in sorted(Counter(r.reason for r in rows).items()):
        print(f"{reason}: {count}")
    if args.json:
        args.json.write_text(json.dumps([asdict(r) for r in rows], indent=2) + "\n")
    if args.apply:
        print(f"applied: {migration.apply_gate_all(models, rows, args.by)}")
    else:
        n = sum(r.action == "grandfather" for r in rows)
        m = sum(r.action == "send" for r in rows)
        print(
            f"dry run: {n} would be grandfathered, {m} would be sent to the Desk; "
            "run again with --apply"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
