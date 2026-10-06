"""Approving the definitive drawing of a cover (ADR-047).

Only users with `can_approve` may approve. An approval belongs to one revision: it records who,
when, the revision number and a fingerprint (sha256) of the production files (cut.dxf,
cut.svg, cutting-list.pdf, sizes.pdf, finished.json). Approved copies of the two PDFs are
stamped with the approver's name and the date (approved/sizes.pdf, approved/cutting-list.pdf).
When the cover is calculated again and the files change, the approval no longer matches and the
cover shows as "changed after approval": it must be approved again. An editor can ask the
approvers for an approval; they get a mail.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from coverengine.catalogue import revisions, set_info

FILES = ("cut.dxf", "cut.svg", "cutting-list.pdf", "sizes.pdf", "finished.json")
APPROVAL_JSON = "approval.json"
APPROVED_DIR = "approved"
STAMPED = ("sizes.pdf", "cutting-list.pdf")
STAMP_RGB = (0.31, 0.48, 0.23)  # S2DIO olive green


def fingerprint(model_dir: Path) -> dict[str, str]:
    return {
        f: hashlib.sha256((model_dir / f).read_bytes()).hexdigest()
        for f in FILES
        if (model_dir / f).is_file()
    }


def state(model_dir: Path) -> dict[str, Any] | None:
    """The approval and whether it still matches the files."""
    path = model_dir / APPROVAL_JSON
    if not path.is_file():
        return None
    doc: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    doc["valid"] = doc.get("files") == fingerprint(model_dir)
    return doc


def approve(model_dir: Path, username: str, name: str, note: str = "") -> dict[str, Any]:
    from coverengine.export.drawing import ensure_sizes

    ensure_sizes(model_dir)  # the size drawing is made when it is needed (ADR-080)
    missing = [
        f for f in ("cut.dxf", "cutting-list.pdf", "sizes.pdf") if not (model_dir / f).is_file()
    ]
    if missing:
        raise ValueError(f"nothing to approve yet: {', '.join(missing)} missing")
    revs = revisions(model_dir)
    doc = {
        "approved_by": username,
        "name": name,
        "time": round(time.time()),
        "revision": revs[-1]["number"] if revs else None,
        "note": note,
        "files": fingerprint(model_dir),
    }
    (model_dir / APPROVAL_JSON).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    stamp(model_dir, doc)
    set_info(model_dir, {"status": "production"})
    return {**doc, "valid": True}


def withdraw(model_dir: Path) -> None:
    (model_dir / APPROVAL_JSON).unlink(missing_ok=True)
    for f in STAMPED:
        (model_dir / APPROVED_DIR / f).unlink(missing_ok=True)
    set_info(model_dir, {"status": "checked"})


def stamp(model_dir: Path, doc: dict[str, Any]) -> None:
    """Copies of the PDFs with 'APPROVED by <name>, <date>, revision <n>' on every page."""
    import pymupdf

    out = model_dir / APPROVED_DIR
    out.mkdir(exist_ok=True)
    when = time.strftime("%d %b %Y %H:%M", time.localtime(doc["time"]))
    text = f"APPROVED  {doc['name']}  {when}  revision {doc['revision']}"
    for f in STAMPED:
        pdf = pymupdf.open(model_dir / f)
        for i in range(pdf.page_count):
            page = pdf[i]
            r = page.rect
            box = pymupdf.Rect(r.x1 - 330, r.y0 + 12, r.x1 - 12, r.y0 + 34)
            page.draw_rect(box, color=STAMP_RGB, width=1.2)
            page.insert_textbox(box, text, fontsize=9, fontname="helv", color=STAMP_RGB,
                                align=1)  # fmt: skip
        pdf.save(out / f, garbage=3, deflate=True)
