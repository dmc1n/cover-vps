"""The stamped PDFs of a Desk approval, and the old "definitive drawing" approvals as history.

Since ADR-128 (owner, 13 Oct 2026, question 83: "a) only the Desk") the Desk's approval is the
only approval. On a Desk approval the size drawing and the cutting list are stamped
"APPROVED <name> <date> revision <n>" on every page into approved/ (`prepare` writes the stamped
copies beside their final names, `commit` moves them in with os.replace, so a reader never sees
half a PDF and a refused approval leaves the old copies alone). The stamped copies are served
only while the Desk approval that made them still holds (desk.stamped_ok).

The separate approval of ADR-047 (approval.json, "Approve the definitive drawing" on the cover
page) is retired: its routes answer 410 and point at the Desk. Existing approval.json files stay
readable as history (`legacy`); scripts/desk_definitive.py turns a definitive approval that still
matches its cut file into a Desk approval with a history note, so no cover silently loses its DXF.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

FILES = ("cut.dxf", "cut.svg", "cutting-list.pdf", "sizes.pdf", "finished.json")
APPROVAL_JSON = "approval.json"
APPROVED_DIR = "approved"
STAMPED = ("sizes.pdf", "cutting-list.pdf")
STAMP_RGB = (0.31, 0.48, 0.23)  # S2DIO olive green


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint(model_dir: Path) -> dict[str, str]:
    return {f: _sha(model_dir / f) for f in FILES if (model_dir / f).is_file()}


def legacy(model_dir: Path) -> dict[str, Any] | None:
    """The old definitive approval (approval.json), read-only history: who, when, which revision,
    and whether its cut file is still the one on disk (`valid`)."""
    path = model_dir / APPROVAL_JSON
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    cut = (doc.get("files") or {}).get("cut.dxf")
    now = model_dir / "cut.dxf"
    doc["valid"] = bool(cut) and now.is_file() and cut == _sha(now)
    doc["legacy"] = True
    return doc


def stamp_text(name: str, when: float, revision: int | None) -> str:
    stamp = time.strftime("%d %b %Y %H:%M", time.localtime(when))
    return f"APPROVED  {name}  {stamp}  revision {revision if revision is not None else '-'}"


def prepare(model_dir: Path, name: str, when: float, revision: int | None) -> dict[str, Any]:
    """Stamped copies of the PDFs that exist, written to temporary files in approved/. A PDF
    without pages refuses the approval (ValueError) before anything is recorded; a PDF that does
    not exist is listed in `missing` (an arrangement or an order cover may have no size drawing
    yet). `commit` moves them in; `discard` removes them."""
    import pymupdf

    try:
        from coverengine.export.drawing import ensure_sizes

        ensure_sizes(model_dir)  # the size drawing is made when it is needed (ADR-080)
    except Exception:  # noqa: BLE001 - no pattern to draw from: no size drawing to stamp
        pass
    text = stamp_text(name, when, revision)
    out = model_dir / APPROVED_DIR
    ready: list[tuple[Path, Path]] = []
    missing: list[str] = []
    try:
        for f in STAMPED:
            src = model_dir / f
            if not src.is_file():
                missing.append(f)
                continue
            with pymupdf.open(src) as pdf:
                if not pdf.page_count:
                    raise ValueError(f"nothing to approve yet: {f} has no pages; regenerate it")
                for i in range(pdf.page_count):
                    page = pdf[i]
                    r = page.rect
                    box = pymupdf.Rect(r.x1 - 330, r.y0 + 12, r.x1 - 12, r.y0 + 34)
                    page.draw_rect(box, color=STAMP_RGB, width=1.2)
                    page.insert_textbox(box, text, fontsize=9, fontname="helv",
                                        color=STAMP_RGB, align=1)  # fmt: skip
                out.mkdir(exist_ok=True)
                tmp = out / f".{f}.{os.getpid()}.{time.monotonic_ns()}.tmp"
                pdf.save(tmp, garbage=3, deflate=True)
            ready.append((tmp, out / f))
    except Exception:
        discard({"ready": ready})
        raise
    return {"ready": ready, "missing": missing, "text": text}


def commit(prepared: dict[str, Any]) -> dict[str, str]:
    """Move the stamped copies in (atomic per file); their fingerprints, for the Desk."""
    done = {}
    for tmp, final in prepared["ready"]:
        os.replace(tmp, final)
        done[final.name] = _sha(final)[:20]
    return done


def discard(prepared: dict[str, Any]) -> None:
    for tmp, _ in prepared.get("ready", []):
        Path(tmp).unlink(missing_ok=True)
