"""Do the Desk's corrections still hold? The measuring rod's groundwork (ADR-082).

    COVER_DATA_DIR=~/cover-data uv run python scripts/learned_check.py [--recalc] [--only ID]

Every correction made at the Desk left a case in <data>/learning/cases/: what must hold after it
(a piece count, no seam left where one was removed, a vent count, a setting). This checks each
"auto" case against the cover as it is now; with --recalc the cover is first calculated again
(cut, flatten, export), so a change to the program that undoes a correction shows up here.
"manual" cases (a size read wrong, a shape missing) are listed as still to do. Out: one line per
case and <data>/learning/check.json; the exit code is 1 when a case fails.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from coverengine import learned


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", type=Path, default=None, help="default: <data>/models")
    ap.add_argument("--recalc", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    base = learned.data_dir()
    if base is None:
        print("set COVER_DATA_DIR to the data folder", file=sys.stderr)
        return 2
    models = a.models or base / "models"
    cases_dir = learned.cases_dir(base)
    cases = sorted(cases_dir.glob("*.json")) if cases_dir and cases_dir.is_dir() else []
    only = set(a.only.split(",")) if a.only else None
    rows, recalced = [], set()
    for path in cases:
        case = json.loads(path.read_text(encoding="utf-8"))
        name = case.get("model", "")
        if only and name not in only:
            continue
        d = models / name
        if case.get("check") != "auto":
            # the pictures the person attached show what is meant (ADR-096)
            pics = (case.get("feedback") or {}).get("picture_paths") or []
            rows.append({"case": path.name, "model": name, "result": "to do by hand",
                         "pictures": pics})  # fmt: skip
            continue
        if not (d / "cover.json").is_file():
            rows.append({"case": path.name, "model": name, "result": "cover gone"})
            continue
        if a.recalc and name not in recalced:
            for step in ("cut", "flatten", "export"):
                subprocess.run([sys.executable, "-m", "coverengine.cli", step, str(d)],
                               capture_output=True, check=False)  # fmt: skip
            recalced.add(name)
        bad = learned.evaluate(d, case.get("expect") or {})
        rows.append({"case": path.name, "model": name, "result": "holds" if not bad else "FAILS",
                     "why": bad})  # fmt: skip
    for r in rows:
        print(f"{r['result']:14} {r['case']}  {'; '.join(r.get('why') or [])}")
        for pic in r.get("pictures") or []:
            print(f"{'':14} picture: {pic}")
    held = sum(1 for r in rows if r["result"] == "holds")
    failed = sum(1 for r in rows if r["result"] == "FAILS")
    print(f"{held} hold, {failed} fail, {len(rows) - held - failed} other, of {len(rows)} cases")
    out = base / "learning" / "check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"time": time.time(), "rows": rows}, indent=1) + "\n", "utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
