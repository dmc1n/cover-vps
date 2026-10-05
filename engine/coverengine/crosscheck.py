"""Two AIs check the program's cover against the drawing, and each other (ADR-072).

The program decides the shape itself; the AIs only check. Gemini (ai.vision_*) looks: the
drawing's pages next to the program's picture of the cover. DeepSeek (ai.*) reads: every word
and number on the drawing against the cover's measured sizes, and Gemini's verdict. When the
two disagree, Gemini gets DeepSeek's points once to confirm or correct its view. The outcome is
"agreed: same", "agreed: different" or "person to check"; it never changes the cover.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from coverengine.ai import ask_parts
from coverengine.params import EffectiveParams, Registry

DPI = 110  # param-ok: the drawing as a picture for the check
WORKSHOP = """How this workshop works: every cover is open at the bottom (it slides over the
furniture);
an "air pocket" on a drawing is an air vent, made as an opening with a hood and a membrane (the
pieces vent-hood and vent-membrane, one each per vent; the picture does not show them); fabric,
colour, elastic, grommets and tie downs are finishing, not part of this check. "plan" sizes are
the top seen from above (its outline length, its longest straight distance, its area); piece
areas are fabric, a different thing. Judge the shape and the sizes."""
LOOK = (
    """You check a cover workshop's work. The first pictures are the technical drawing of a
cover; the last picture is the cover the program built from it. Compare the SHAPE: the outline
seen from above, the top (flat, domed, sloped), the sides, the height, the seams, the openings
and features written on the drawing.
"""
    + WORKSHOP
    + """
Answer JSON only:
{"same": true|false, "score": 0-100, "differences": ["..."], "summary": "..."}"""
)
READ = (
    """You check a cover workshop's work by the numbers. You get every word and number on a
technical drawing of a cover, the sizes the program measured on the cover it built from it, and
a colleague's verdict from comparing the pictures. Check that every size and feature on the
drawing (heights, lengths, circumferences, diameters, counts such as air pockets, openings) is
in the program's cover, within 1 cm or 1 %. Note sizes on the drawing that contradict each
other: say which one the cover follows and that a person must confirm it, but do not count it
as the program's mistake. Then say whether you agree with the colleague.
"""
    + WORKSHOP
    + """
Answer JSON only:
{"same": true|false, "score": 0-100, "agree_with_colleague": true|false,
 "differences": ["..."], "summary": "..."}"""
)
SECOND = """A colleague checked the same cover by its numbers and wrote the following. Look at
the pictures again with these points in mind and give your final verdict, same JSON form."""


def _png(data: bytes) -> dict[str, Any]:
    b = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b}"}}


def measured(model: Path) -> dict[str, Any]:
    """The cover's own sizes for the reading check: every piece and its openings."""
    doc = json.loads((model / "finished.json").read_text())
    return {
        "pieces": [
            {k: p.get(k) for k in ("name", "quantity", "net_mm", "size_mm", "area_m2", "note")}
            for p in doc.get("pieces", [])
        ],
        "warnings": doc.get("warnings", []),
    }


def vision_params() -> EffectiveParams:
    base = Registry.load(None).resolve()
    return Registry.load(None).resolve(trial={
        "ai.provider": str(base["ai.vision_provider"]), "ai.model": str(base["ai.vision_model"]),
        "ai.base_url": str(base["ai.vision_base_url"]), "ai.timeout_s": 600})  # fmt: skip


def run(pdf: Path, model: Path, facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Both checks and their outcome. `facts`: what the program read off the drawing itself
    (the outline's sizes, written sizes that disagree), passed to the reading check."""
    import pymupdf

    doc = pymupdf.open(pdf)
    text = "\n".join(p.get_text() for p in doc.pages())
    pictures = [_png(p.get_pixmap(dpi=DPI).tobytes("png")) for p in doc.pages()]
    look_parts: list[dict[str, Any]] = [
        {"type": "text", "text": "The drawing, then the program's cover."},
        *pictures,
        _png((model / "cover.png").read_bytes()),
        {"type": "text", "text": "The program's pieces: " + json.dumps(measured(model)["pieces"])},
    ]
    vision = vision_params()
    out: dict[str, Any] = {}
    look = ask_parts(vision, LOOK, look_parts)
    look.pop("_usage", None)
    out["gemini"] = look
    reading = {"drawing_text": text, "program_read": facts or {},
               "program_cover": measured(model), "colleague_verdict": look}  # fmt: skip
    read = ask_parts(Registry.load(None).resolve(), READ, json.dumps(reading, default=str))
    read.pop("_usage", None)
    out["deepseek"] = read
    if bool(look.get("same")) != bool(read.get("same")):
        second = SECOND + "\n" + json.dumps(read)
        again = ask_parts(vision, LOOK, [*look_parts, {"type": "text", "text": json.dumps(look)},
                                         {"type": "text", "text": second}])  # fmt: skip
        again.pop("_usage", None)
        out["gemini_second"] = again
        look = again
    if bool(look.get("same")) == bool(read.get("same")):
        out["outcome"] = "agreed: same" if look.get("same") else "agreed: different"
    else:
        out["outcome"] = "person to check"
    return out
