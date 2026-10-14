"""Desk remarks nobody has answered yet: a person's reject, comment, note or fit that came after
the studio's last action on that cover. Read-only. The daily round (ADR-109) runs it next to
`questions.py new`, so a rejection never waits unseen again (owner, 14 Oct 2026: Rens' round-2
rejections of 9 Oct were missed).

    COVER_DATA_DIR=~/cover-data uv run python scripts/desk_open_remarks.py [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
from coverapi import desk  # noqa: E402

STUDIO = desk.STUDIO_NAMES  # one rule with the Desk's "Waiting for us" filter (desk.remark_open)
REMARKS = desk.REMARK_ACTIONS


def open_remarks(models: Path) -> list[dict]:
    out = []
    for d in sorted(models.iterdir()):
        if not (d / "desk.json").is_file():
            continue
        st = desk.state(d)
        hist = st["history"]
        last = max([h.get("time", 0) for h in hist if h.get("by") in STUDIO] or [0])
        todo = [
            h for h in hist
            if h.get("by") not in STUDIO and h.get("action") in REMARKS
            and h.get("time", 0) > last and not h.get("undone")
        ]  # fmt: skip
        if todo:
            out.append({
                "model": d.name, "code": desk._code(d), "status": st["status"],
                "remarks": [{
                    "when": time.strftime("%Y-%m-%d %H:%M", time.localtime(h.get("time", 0))),
                    "action": h.get("action"), "by": h.get("by"), "text": h.get("text") or "",
                    "pictures": len(h.get("pictures") or []),
                } for h in todo],
            })  # fmt: skip
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    data = Path(os.environ.get("COVER_DATA_DIR", Path.home() / "cover-data")).expanduser()
    models = data / "models"
    rows = open_remarks(models)
    if args.json:
        print(json.dumps(rows, indent=1, ensure_ascii=False))
        return 0
    for r in rows:
        for m in r["remarks"]:
            pics = f" [{m['pictures']} picture(s)]" if m["pictures"] else ""
            who = f"{r['code'] or r['model']:<10} {m['when']} {m['action']:<7} {m['by']}"
            print(f"{who}: {m['text'][:120]}{pics}")
    print(f"\n{len(rows)} covers with remarks the studio has not answered yet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
