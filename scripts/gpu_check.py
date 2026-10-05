"""The control check on GPUs (ADR-069): drop the covers over their furniture, many at once.

    uv run python scripts/gpu_check.py <model dirs ...> [--models DIR --prefix drawing-]
        [--out out/gpu-check] [--batch 12] [--no-ai]

This server prepares every cover's cloth (its flat pieces), Modal runs the Style3D falls side by
side (one NVIDIA L4 each, billed per second), and here each one is measured, written (drape.*),
rained on and judged by the audit's drape check (folds, sag, water) and, unless --no-ai, by the
AI. Out: <out>/check.json and check.csv, one row per cover: passed or not, and why.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from coverengine import audit, drape, drape_gpu
from coverengine.params import Registry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*", type=Path)
    ap.add_argument("--models-dir", type=Path, default=Path("models"))
    ap.add_argument("--prefix", default="")
    ap.add_argument("--out", type=Path, default=Path("out/gpu-check"))
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--no-ai", action="store_true")
    a = ap.parse_args()
    dirs = list(a.models) or sorted(
        d for d in a.models_dir.glob(f"{a.prefix}*") if (d / "panels.npz").is_file()
    )
    params = Registry.load(None).resolve()
    a.out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    t0 = time.time()

    def prepare(d: Path) -> tuple[Path, Any, Any] | dict[str, Any]:
        try:
            return d, drape.cloth(d, params), drape._colliders(d)
        except Exception as exc:  # noqa: BLE001 - report it, go on with the others
            return {"model": d.name, "passed": False, "detail": f"not prepared: {exc}"}

    for i in range(0, len(dirs), a.batch):
        part = dirs[i : i + a.batch]
        with ThreadPoolExecutor(max_workers=4) as pool:
            ready = list(pool.map(prepare, part))
        rows += [r for r in ready if isinstance(r, dict)]
        jobs = [r for r in ready if not isinstance(r, dict)]
        if not jobs:
            continue
        print(f"{len(jobs)} cover(s) to the GPUs ...", flush=True)
        results = drape_gpu.run_many([(c, ms) for _, c, ms in jobs], params, print)
        for (d, c, ms), (frames, extra) in zip(jobs, results, strict=True):
            try:
                rep = drape.finish(d, c, ms, frames, extra, params, print, use_ai=not a.no_ai,
                                   t0=time.time() - float(extra.get("gpu_s", 0)))  # fmt: skip
                chk = audit.drape_checks(d, params)
                ok = bool(chk and chk[0]["ok"])
                detail = chk[0]["detail"] if chk else ""
                rows.append({"model": d.name, "passed": ok, "detail": detail,
                             "folds_pct": rep.get("fold_share_pct"),
                             "sag_cm": round(float(rep.get("max_sag_mm", 0)) / 10, 1),
                             "stretch_pct": rep.get("max_stretch_pct"),
                             "pond_l": (rep.get("wet") or {}).get("pond_volume_l"),
                             "gpu_s": extra.get("gpu_s")})  # fmt: skip
                print(f"{d.name}: {'passed' if ok else 'CHECK'} - {rows[-1]['detail']}", flush=True)
            except Exception as exc:  # noqa: BLE001
                rows.append({"model": d.name, "passed": False, "detail": f"failed after: {exc}"})
    (a.out / "check.json").write_text(json.dumps(rows, indent=1))
    keys = ["model", "passed", "folds_pct", "sag_cm", "stretch_pct", "pond_l", "gpu_s", "detail"]
    with (a.out / "check.csv").open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    good = sum(1 for r in rows if r["passed"])
    print(f"{good}/{len(rows)} passed in {time.time() - t0:.0f} s -> {a.out}/check.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
