"""Put the arrangements (arr-*) at the Desk as "ready for approval" (ADR-115).

The owner, 9 October 2026: "set the arrangements ready in the Desk; that must be the workflow,
so that Rens or Wout approve them." New arrangements are sent from the Arrangements page; this
puts the ones made before into the same state, once:

    COVER_DATA_DIR=~/cover-data uv run python scripts/desk_arrangements.py            # dry run
    COVER_DATA_DIR=~/cover-data uv run python scripts/desk_arrangements.py --apply    # write

Per arrangement with a built cover (finished.json and cut.dxf):

- new, or waiting without a record of who sent it  -> ai-checked ("ready for approval"), `sent`
  (by --by, now; not yet announced, so the approvers' next digest lists it) and a history entry
  "sent to the Desk". The existing desk.json and its history are kept; nothing is removed.
- already sent and waiting, approved, produced or rejected -> left as it is (a rejected one goes
  back to the Desk when it is changed and built again on the Arrangements page).
- not built -> skipped.

Only the main session runs it on live data, dry run first.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from coverapi import desk  # noqa: E402

NOTE = "put at the Desk for approval with the arrangements made before (ADR-115)"


def data_dir() -> Path:
    return Path(os.environ.get("COVER_DATA_DIR", Path.home() / "cover-data")).expanduser()


def plan(models: Path, only: set[str] | None = None) -> list[tuple[Path, str, str]]:
    """(folder, what to do, why) per arrangement: "send" or "keep" or "skip"."""
    out = []
    for d in sorted(models.glob(desk.ARRANGEMENT_PREFIX + "*")):
        if only and d.name not in only:
            continue
        if not desk.is_arrangement(d) or not (d / "cover.json").is_file():
            continue
        if not ((d / "finished.json").is_file() and (d / "cut.dxf").is_file()):
            out.append((d, "skip", "no cover built yet"))
            continue
        st = desk.state(d)
        s = st["status"]
        if s in desk.DONE:
            who = (st.get("approved") or st.get("produced") or {}).get("by", "?")
            out.append((d, "keep", f"{s} (by {who})"))
        elif s == "rejected":
            out.append((d, "keep", "rejected: goes back when it is changed and built again"))
        elif s == desk.WAITING and st.get("sent"):
            out.append((d, "keep", f"already waiting (sent by {st['sent'].get('by')})"))
        else:
            out.append((d, "send", f"{s} -> ready for approval"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write desk.json (default: dry run)")
    ap.add_argument("--by", default="Claude", help="who sent them, in the history")
    ap.add_argument("--only", default="", help="these arrangements only (ids, comma separated)")
    args = ap.parse_args(argv)
    root = data_dir()
    models = root / "models"
    if not models.is_dir():
        print(f"no models folder in {root}")
        return 1
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    rows = plan(models, only)
    user = SimpleNamespace(name=args.by, username=args.by)
    sent = 0
    for d, what, why in rows:
        code = desk._code(d)
        print(f"{what:<5} {d.name:<40} {code[:40]:<40} {why}")
        if what == "send" and args.apply:
            desk.send_arrangement(d, user, root / "learning", NOTE)
            sent += 1
    n = sum(1 for _, w, _ in rows if w == "send")
    if args.apply:
        print(f"\n{sent} sent to the Desk; {len(rows) - sent} left as they were")
    else:
        print(f"\ndry run: {n} would be sent to the Desk; run again with --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
