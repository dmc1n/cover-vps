"""Free plan shapes (kidney, lens, blob) built from the drawing's own lines; the AI only checks.

    uv run python scripts/drawing_outline.py out/drawings/outline --pdfs <PDF folder>
        [--only S45] [--no-build] [--no-ai]

The program decides the shape itself (ADR-072): coverengine/drawing_vectors.py takes the closed
outline from the PDF's vector lines and scales it by the written circumference or length; two
written sizes that disagree are reported, not chosen between silently. The cover is built as
models/drawing-<code>/ (shape "outline"). Then two AIs check it and each other
(coverengine/crosscheck.py): Gemini compares the pictures, DeepSeek the words and numbers; the
outcome is a check for a person, it never changes the shape. Results:
<out>/outline.json, one entry per drawing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coverengine import crosscheck  # noqa: E402
from coverengine.drawing_vectors import outline_shape  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--pdfs", type=Path, required=True)
    ap.add_argument("--only")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--no-ai", action="store_true")
    a = ap.parse_args()
    pdfs = {re.sub(r"^cover \d+ - ", "", p.stem): p for p in sorted(a.pdfs.glob("*.pdf"))}
    codes = a.only.split(",") if a.only else list(pdfs)
    a.out.mkdir(parents=True, exist_ok=True)
    results = []
    for code in codes:
        pdf = pdfs.get(code)
        if pdf is None:
            continue
        read = outline_shape(pdf)
        if read is None:
            continue  # no closed free outline on this drawing
        res: dict[str, Any] = {"code": code, **read}
        if "error" in read:
            res["status"] = "outline found, " + read["error"]
        elif not a.no_build:
            from drawing_cover import make  # the same builder as every drawing

            model = make(code, "outline", read["shape"], Path("models"),
                         note="outline read from the drawing's lines")  # fmt: skip
            res["model"] = model.name
            res["status"] = "built" + (", sizes disagree" if read["conflicts"] else "")
            if not a.no_ai:
                try:
                    facts = {k: read[k] for k in ("scaled_by", "conflicts", "plan_cm", "sizes")}
                    res["ai_check"] = crosscheck.run(pdf, model, facts)
                except Exception as exc:  # noqa: BLE001 - the check is advice, never a stop
                    res["ai_check"] = {"error": str(exc)}
        shape = res.get("shape") or {}
        res["shape"] = {**shape, "outline_cm": f"{len(shape.get('outline_cm', []))} points"}
        print(code, res.get("status"), json.dumps(res.get("conflicts")),
              json.dumps(res.get("ai_check"))[:400], flush=True)  # fmt: skip
        if shape:
            (a.out / f"{code}.shape.json").write_text(json.dumps(shape))
        results.append(res)
    (a.out / "outline.json").write_text(json.dumps(results, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
