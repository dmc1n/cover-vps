"""Grandfather earlier drawing approvals. Default is a read-only dry run.

    uv run python scripts/desk_fingerprints.py --dry-run
    uv run python scripts/desk_fingerprints.py --apply

Uses COVER_DATA_DIR/models, or --models. Does not approve historical cuts with different bytes.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from coverapi import desk  # noqa: E402


def migrate(models: Path, *, apply: bool = False) -> list[str]:
    changed = []
    for d in sorted(models.glob("drawing-*")):
        if not d.is_dir():
            continue
        with desk._lock:
            doc = desk._read(d / "desk.json")
            if desk.grandfather_fingerprint(d, doc):
                changed.append(d.name)
                if apply:
                    desk._write(d / "desk.json", doc)
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--models", type=Path, default=None)
    args = parser.parse_args(argv)
    models = (
        args.models
        or Path(os.environ.get("COVER_DATA_DIR", str(Path.home() / "cover-data"))).expanduser()
        / "models"
    )
    if not models.is_dir():
        parser.error(f"no models folder: {models}")
    changed = migrate(models, apply=args.apply)
    for name in changed:
        print(name)
    print(f"{'Recorded' if args.apply else 'Would record'} {len(changed)} fingerprints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
