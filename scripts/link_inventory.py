"""The model catalogue's files, Desk statuses and drawing links to 3D models.

    COVER_DATA_DIR=~/cover-data uv run python scripts/link_inventory.py
        [--models DIR] [--json OUT.json]

Prints counts by folder prefix and the links recorded in drawings' products.json.
Reads only; nothing in the models changes. Optional JSON output goes through the
staging guard. Unreadable JSON counts as missing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from coverengine.staging import guard_staging_output

GROUPS = ("drawing", "suns", "bbq", "arr", "other")
FILES = (
    "cover.json",
    "model.json",
    "hull.json",
    "cover.png",
    "reference.png",
    "reference.pdf",
    "products.json",
    "drawings.json",
    "product.jpg",
)
MISSING = object()
COVER_LABEL = re.compile(r"cover\s*\d+\w?", re.IGNORECASE)


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return MISSING


def inventory(models: Path) -> dict[str, Any]:
    groups = {
        group: {
            "folders": 0,
            **dict.fromkeys(FILES, 0),
            "no_cover": 0,
            "desk_status": {},
        }
        for group in GROUPS
    }
    links = dict.fromkeys(
        (
            "drawings_with_linked",
            "drawings_with_only_suggested",
            "drawings_with_neither",
            "linked_pairs",
            "suggested_pairs",
            "products_with_multiple_labels",
        ),
        0,
    )
    for folder in sorted(models.iterdir()):
        if not folder.is_dir():
            continue
        group = next((g for g in GROUPS[:-1] if folder.name.startswith(f"{g}-")), "other")
        counts = groups[group]
        counts["folders"] += 1
        docs = {}
        for filename in FILES:
            path = folder / filename
            if filename.endswith(".json"):
                doc = read_json(path)
                docs[filename] = doc
                counts[filename] += int(doc is not MISSING)
            else:
                counts[filename] += int(path.is_file())
        cover = docs["cover.json"]
        if isinstance(cover, dict) and cover.get("no_cover") is True:
            counts["no_cover"] += 1
        desk = read_json(folder / "desk.json")
        status = desk.get("status") if isinstance(desk, dict) else None
        status = status if isinstance(status, str) else "none"
        statuses = counts["desk_status"]
        statuses[status] = statuses.get(status, 0) + 1

        products = docs["products.json"]
        if group != "drawing" or products is MISSING:
            continue
        products = products if isinstance(products, dict) else {}
        suns = products.get("suns")
        suns = suns if isinstance(suns, dict) else {}
        linked = suns.get("linked")
        suggested = suns.get("suggested")
        linked = linked if isinstance(linked, list) else []
        suggested = suggested if isinstance(suggested, list) else []
        if linked:
            links["drawings_with_linked"] += 1
        elif suggested:
            links["drawings_with_only_suggested"] += 1
        else:
            links["drawings_with_neither"] += 1
        links["linked_pairs"] += len(linked)
        links["suggested_pairs"] += len(suggested)
        labels = products.get("labels")
        if isinstance(labels, list):
            product_labels = [
                label
                for label in labels
                if isinstance(label, str) and not COVER_LABEL.fullmatch(label)
            ]
            links["products_with_multiple_labels"] += int(len(product_labels) > 1)
    return {"groups": groups, "sheet_links": links}


def print_inventory(result: dict[str, Any]) -> None:
    groups = result["groups"]

    def row(label: str, values: list[int | str]) -> None:
        print(f"{label:32}" + "".join(f"{value:>10}" for value in values))

    row("Catalogue", list(GROUPS))
    print("-" * 82)
    for key in ("folders", *FILES, "no_cover"):
        row(key, [groups[group][key] for group in GROUPS])
    statuses = sorted({status for group in GROUPS for status in groups[group]["desk_status"]})
    for status in statuses:
        row(f"Desk: {status}", [groups[group]["desk_status"].get(status, 0) for group in GROUPS])
    print("\nSheet links (drawings with readable products.json)")
    for key, count in result["sheet_links"].items():
        print(f"  {key.replace('_', ' '):36} {count:>8}")


def main() -> None:
    data = Path(os.environ.get("COVER_DATA_DIR", "~/cover-data")).expanduser()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--models", default=str(data / "models"))
    parser.add_argument("--json", type=Path, metavar="OUT.json")
    args = parser.parse_args()
    models = Path(args.models).expanduser()
    result = inventory(models)
    print_inventory(result)
    if args.json is not None:
        out = args.json.expanduser()
        guard_staging_output(out.parent)
        guard_staging_output(out, src=models)
        out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
