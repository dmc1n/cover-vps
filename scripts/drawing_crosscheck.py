"""Gemini and DeepSeek check built drawing covers against their drawings, and each other.

    uv run python scripts/drawing_crosscheck.py out/drawings/crosscheck --pdfs <PDF folder>
        [--only S44,S47] [--workers 3]

For every models/drawing-<code>/ with a PDF: coverengine/crosscheck.run (ADR-072). Out:
<out>/<code>.json and crosscheck.csv (code, outcome, both scores, the differences).
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from coverengine import crosscheck


def slug(code: str) -> str:
    return "drawing-" + re.sub(r"[^a-z0-9]+", "-", code.lower()).strip("-")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--pdfs", type=Path, required=True)
    ap.add_argument("--only")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    pdfs = {re.sub(r"^cover \d+ - ", "", p.stem): p for p in sorted(a.pdfs.glob("*.pdf"))}
    codes = a.only.split(",") if a.only else list(pdfs)
    jobs = [(c, pdfs[c], Path("models") / slug(c)) for c in codes if c in pdfs]
    jobs = [
        j for j in jobs if (j[2] / "cover.png").is_file() and (j[2] / "finished.json").is_file()
    ]
    a.out.mkdir(parents=True, exist_ok=True)

    def one(job: tuple[str, Path, Path]) -> dict[str, Any]:
        code, pdf, model = job
        try:
            res = {"code": code, **crosscheck.run(pdf, model)}
        except Exception as exc:  # noqa: BLE001 - one drawing must not stop the others
            res = {"code": code, "outcome": "check failed", "error": str(exc)}
        (a.out / f"{code}.json").write_text(json.dumps(res, indent=1))
        print(code, res["outcome"], flush=True)
        return res

    with ThreadPoolExecutor(max_workers=a.workers) as pool:
        rows = list(pool.map(one, jobs))
    with (a.out / "crosscheck.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["code", "outcome", "gemini", "deepseek", "tokens_in", "tokens_out",
                    "differences"])  # fmt: skip
        for r in rows:
            g = r.get("gemini_second") or r.get("gemini") or {}
            d = r.get("deepseek") or {}
            diff = (g.get("differences") or []) + (d.get("differences") or [])
            t = r.get("tokens") or {}
            t_in = sum(x.get("in", 0) for x in t.values())
            t_out = sum(x.get("out", 0) for x in t.values())
            w.writerow([r["code"], r["outcome"], g.get("score"), d.get("score"), t_in, t_out,
                        " | ".join(diff)])  # fmt: skip
    t_in = sum(x.get("in", 0) for r in rows for x in (r.get("tokens") or {}).values())
    t_out = sum(x.get("out", 0) for r in rows for x in (r.get("tokens") or {}).values())
    print(f"{len(rows)} covers checked; tokens in {t_in}, out {t_out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
