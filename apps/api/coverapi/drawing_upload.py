"""Route A in the web app: upload a drawing (PDF) and the program builds its cover (ADR-081).

- POST /api/models/drawing: a new drawing cover. The PDF is kept as the model's reference.pdf
  (as every drawing cover has); `cover drawing-build` runs as a background job: the program
  reads the drawing itself and, when sure, builds and calculates the cover. When it is not
  sure the cover is marked "needs a person" with the reasons, and the Desk puts it at the top.
- POST /api/models/{id}/drawing: build an existing drawing cover again from its drawing (a new
  revision; reference/, desk.json and revisions/ are kept). A new PDF may come with it.
- GET /api/models/{id}/drawing: what the program read (drawing_read.json).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile

MAX_BYTES = 50 * 1024 * 1024  # param-ok: a drawing PDF
STEP = "drawing-build"


def code_of(filename: str) -> str:
    """The drawing's code from its file name: "cover 111 - S45.pdf" -> "S45"."""
    stem = Path(filename).stem
    return re.sub(r"^cover [\d &]+ - ", "", stem, flags=re.I).strip() or "drawing"


def _desk_note(d: Path, code: str, by: str) -> None:
    """The Desk's state for a cover the program is building: new, with the drawing's code."""
    path = d / "desk.json"
    doc: dict[str, Any] = json.loads(path.read_text()) if path.is_file() else {}
    doc.setdefault("status", "new")
    doc.setdefault("history", [])
    doc["code"] = code
    doc["history"].append({"action": "drawing uploaded", "by": by, "time": time.time()})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def install(app: FastAPI, store: Any, jobs: Any) -> None:
    from coverapi.jobs import JobSpec
    from coverapi.security import require

    def _save_pdf(d: Path, data: bytes) -> None:
        if len(data) > MAX_BYTES:
            raise HTTPException(400, "the drawing is larger than 50 MB")
        if not data.startswith(b"%PDF"):
            raise HTTPException(400, "not a PDF")
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "reference.pdf.tmp"
        tmp.write_bytes(data)
        tmp.replace(d / "reference.pdf")

    @app.post("/api/models/drawing")
    async def upload_drawing(
        request: Request,
        file: UploadFile = File(...),  # noqa: B008 - FastAPI's way
        code: str | None = Form(None),  # noqa: B008
    ) -> dict[str, Any]:
        user = require(request, "edit")
        name = file.filename or "drawing.pdf"
        if Path(name).suffix.lower() != ".pdf":
            raise HTTPException(400, f"{name}: a drawing is a PDF")
        code = (code or code_of(name)).strip()
        model_id = store.new_id("drawing-" + code)
        d = store.model_dir(model_id)
        _save_pdf(d, await file.read())
        _desk_note(d, code, user.username)
        job = jobs.submit(JobSpec(model_id, [STEP], {}))
        return {"model_id": model_id, "code": code, "job": job}

    @app.post("/api/models/{model_id}/drawing")
    async def rebuild_drawing(
        model_id: str,
        request: Request,
        file: UploadFile | None = File(None),  # noqa: B008
    ) -> dict[str, Any]:
        user = require(request, "edit")
        try:
            d = store.model_dir(model_id)
        except KeyError:
            raise HTTPException(404, f"no model {model_id!r}") from None
        if file is not None:
            _save_pdf(d, await file.read())
        if not (d / "reference.pdf").is_file():
            raise HTTPException(400, "this model has no drawing: upload one")
        _desk_note(d, json.loads((d / "desk.json").read_text()).get("code")
                   if (d / "desk.json").is_file() else model_id, user.username)  # fmt: skip
        return {"model_id": model_id, "job": jobs.submit(JobSpec(model_id, [STEP], {}))}

    @app.get("/api/models/{model_id}/drawing")
    def drawing_read(model_id: str) -> dict[str, Any]:
        try:
            d = store.model_dir(model_id)
        except KeyError:
            raise HTTPException(404, f"no model {model_id!r}") from None
        path = d / "drawing_read.json"
        if not path.is_file():
            raise HTTPException(404, "not read yet")
        doc: dict[str, Any] = json.loads(path.read_text())
        job = jobs.latest(model_id)
        doc["job"] = job and {k: job.get(k) for k in ("id", "status", "error")}
        return doc
