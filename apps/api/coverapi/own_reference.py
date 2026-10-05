"""The workshop's own reference per model, compared and learned from (ADR-070).

On a model's page a colleague uploads what the workshop knows to be right: a 3D model of the
cover and/or a PDF (its drawing or pattern). It is kept in models/<id>/reference/ and compared
with the program's cover in the background (coverengine/compare.py): the surface's deviation in
mm with a coloured 3D view, the PDF's sizes found or not, the AI's list of differences and the
lessons it proposes. A person accepts a lesson; accepted lessons go to the data folder's
learning/lessons.json (they last across releases) and from there into every AI prompt. Every
comparison is logged in learning/references.jsonl, the material the program learns from.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

SURFACE_SUFFIXES = {".step", ".stp", ".iges", ".igs", ".stl", ".obj", ".ply", ".glb"}
MAX_BYTES = 200 * 1024 * 1024  # param-ok: a large STEP file


def install(app: FastAPI, store: Any) -> None:
    from coverapi.security import require

    running: set[str] = set()
    lock = threading.Lock()
    learning = store.root / "learning"

    def folder(model_id: str) -> Path:
        try:
            d = store.model_dir(model_id)
        except KeyError:
            raise HTTPException(404, f"no model {model_id!r}") from None
        if not d.is_dir():
            raise HTTPException(404, f"no model {model_id!r}")
        return Path(d) / "reference"

    def state(model_id: str) -> dict[str, Any]:
        ref = folder(model_id)
        doc = (
            json.loads((ref / "compare.json").read_text())
            if (ref / "compare.json").is_file()
            else {}
        )
        files = (
            sorted(p.name for p in ref.glob("*") if p.stem in ("surface", "drawing"))
            if ref.is_dir()
            else []
        )
        return {"files": files, "compare": doc, "running": model_id in running,
                "has_view": (ref / "compare.glb").is_file()}  # fmt: skip

    def compare(model_id: str, kind: str, path: Path, by: str) -> None:
        from coverengine import compare as cmp
        from coverengine.params import Registry

        ref = path.parent
        try:
            params = Registry.load(None).resolve()
            model_dir = ref.parent
            if kind == "surface":
                res = cmp.surface(model_dir, path, params)
            else:
                res = cmp.drawing(model_dir, path, params, use_ai=True)
        except Exception as exc:  # noqa: BLE001 - shown on the page, never a crash
            res = {"kind": kind, "reference": path.name, "error": str(exc)}
        res["time"], res["by"] = time.time(), by
        with lock:
            doc = (
                json.loads((ref / "compare.json").read_text())
                if (ref / "compare.json").is_file()
                else {}
            )
            doc[kind] = res
            (ref / "compare.json").write_text(json.dumps(doc, indent=1))
            learning.mkdir(parents=True, exist_ok=True)
            with (learning / "references.jsonl").open("a") as fh:
                fh.write(json.dumps({"model": model_id, **res}) + "\n")
            running.discard(model_id)

    @app.get("/api/models/{model_id}/reference")
    def get_reference(model_id: str) -> dict[str, Any]:
        return state(model_id)

    @app.post("/api/models/{model_id}/reference")
    async def put_reference(
        model_id: str,
        request: Request,
        file: UploadFile = File(...),  # noqa: B008
    ) -> dict[str, Any]:
        user = require(request, "edit")
        name = file.filename or ""
        suffix = Path(name).suffix.lower()
        if suffix == ".pdf":
            kind = "drawing"
        elif suffix in SURFACE_SUFFIXES:
            kind = "surface"
        else:
            raise HTTPException(400, "a 3D model of the cover (STEP, STL, OBJ, GLB...) or a PDF")
        data = await file.read()
        if len(data) > MAX_BYTES:
            raise HTTPException(400, "the file is larger than 200 MB")
        ref = folder(model_id)
        ref.mkdir(parents=True, exist_ok=True)
        for old in ref.glob(f"{kind}.*"):
            old.unlink()
        path = ref / f"{kind}{suffix}"
        path.write_bytes(data)
        (ref / f"{kind}.source.json").write_text(json.dumps(
            {"name": name, "by": user.username, "time": time.time()}))  # fmt: skip
        running.add(model_id)
        threading.Thread(target=compare, args=(model_id, kind, path, user.username),
                         daemon=True).start()  # fmt: skip
        return state(model_id)

    @app.get("/api/models/{model_id}/reference/compare.glb")
    def compare_view(model_id: str) -> FileResponse:
        path = folder(model_id) / "compare.glb"
        if not path.is_file():
            raise HTTPException(404, "no comparison in 3D yet")
        return FileResponse(path, media_type="model/gltf-binary")

    @app.get("/api/models/{model_id}/reference/{kind}")
    def reference_file(model_id: str, kind: str) -> FileResponse:
        hits = [p for p in folder(model_id).glob(f"{kind}.*") if not p.name.endswith(".json")]
        if kind not in ("surface", "drawing") or not hits:
            raise HTTPException(404, "no such reference")
        return FileResponse(hits[0], filename=f"{model_id}-reference-{hits[0].name}")

    @app.post("/api/models/{model_id}/reference/lessons/{index}")
    def accept_lesson(model_id: str, index: int, request: Request) -> dict[str, Any]:
        """A proposed lesson, accepted by a person: from now on in every AI prompt."""
        user = require(request, "edit")
        doc = state(model_id)["compare"].get("drawing") or {}
        proposed = (doc.get("ai") or {}).get("lessons") or []
        if not 0 <= index < len(proposed):
            raise HTTPException(404, "no such lesson")
        lesson = {**proposed[index], "model_id": model_id, "from": "reference",
                  "accepted_by": user.username, "time": time.time()}  # fmt: skip
        learning.mkdir(parents=True, exist_ok=True)
        path = learning / "lessons.json"
        kept = json.loads(path.read_text()) if path.is_file() else []
        if not any(k.get("rule") == lesson.get("rule") for k in kept):
            kept.append(lesson)
            path.write_text(json.dumps(kept, indent=1))
        return {"accepted": lesson, "lessons": len(kept)}
