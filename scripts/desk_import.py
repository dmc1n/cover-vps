"""Fill the drawing desk from the checks so far (ADR-079), once.

    uv run python scripts/desk_import.py --pdfs <PDF folder> [--models models]

For every drawing PDF with its models/drawing-<code>/: desk.json gets the drawing's code and
PDF (kept as it is when it exists), and check.json the latest Gemini + DeepSeek check of the
cover as it is now: a replacement's own check (out/drawings/rebuild*/), else the newest of
out/drawings/check-2026-10-06/ and out/drawings/crosscheck/. A failed check is not copied.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from drawing_features import pdfs, slug  # noqa: E402

CHECKS = ("out/drawings/check-2026-10-06", "out/drawings/crosscheck")
REBUILDS = ("out/drawings/rebuild2", "out/drawings/rebuild")


def _read(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def latest(code: str) -> dict[str, Any] | None:
    name = code.replace("&", "-").replace(" ", "-")
    for folder in CHECKS:  # the newest whole run first: it saw the covers as they are now
        for f in (Path(folder) / f"{code}.json", Path(folder) / f"{name}.json"):
            doc = _read(f)
            if doc.get("outcome") and doc["outcome"] != "check failed":
                return {**doc, "source": folder}
    for folder in REBUILDS:
        for f in Path(folder).glob("*.json"):
            doc = _read(f)
            if doc.get("code") == code and doc.get("status") == "replaced":
                return {"code": code, **doc["new_check"], "source": folder}
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdfs", type=Path, required=True)
    ap.add_argument("--models", type=Path, default=Path("models"))
    a = ap.parse_args()
    n_desk = n_check = 0
    for code, pdf in pdfs(a.pdfs).items():
        model = a.models / slug(code)
        if not (model / "cover.json").is_file():
            continue
        desk = _read(model / "desk.json")
        desk.setdefault("code", code)
        desk.setdefault("pdf", str(pdf.resolve()))
        desk.setdefault("history", [])
        (model / "desk.json").write_text(json.dumps(desk, indent=1) + "\n", encoding="utf-8")
        n_desk += 1
        c = latest(code)
        if c is not None:
            (model / "check.json").write_text(json.dumps(c, indent=1) + "\n", encoding="utf-8")
            n_check += 1
    print(f"desk.json for {n_desk} covers, check.json for {n_check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
