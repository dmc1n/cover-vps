"""The web app's server: the API under /api and the built browser app (apps/web/dist) at /.

    COVER_DATA_DIR=data uv run cover-web          # http://127.0.0.1:8080

One process, one port. It is meant to sit behind the Cloudflare tunnel (M6) or an SSH tunnel.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from coverengine import __version__
from coverengine.catalogue import KEPT, compare_files, info, revision_file, set_info
from coverengine.errors import CoverError
from coverengine.params.registry import ParamError, list_families, repo_root
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coverapi.jobs import Jobs, JobSpec, store_upload
from coverapi.plan import plan, save_seams
from coverapi.references import register, unpack
from coverapi.store import ALLOWED, MEDIA, STEPS, UPLOAD_SUFFIXES, Store, registry_specs


class RunRequest(BaseModel):
    steps: list[str] | None = None  # default: everything after import
    trial: dict[str, Any] = {}


class ParametersRequest(BaseModel):
    values: dict[str, Any]


class InfoRequest(BaseModel):
    family: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


class BatchRequest(BaseModel):
    model_ids: list[str] | None = None
    family: str | None = None
    steps: list[str] | None = None
    trial: dict[str, Any] = {}


class AiApplyRequest(BaseModel):
    action: str
    value: float | None = None


class SeamsRequest(BaseModel):
    automatic: bool = False  # true: forget the hand-placed seams
    skirt_seams: list[list[float]] | None = None  # plan points, one per vertical skirt seam
    top_seams: list[list[list[float]]] | None = None  # plan polylines
    run: bool = True  # cut and flatten again straight away


def create_app(data_dir: Path, web_dir: Path | None = None) -> FastAPI:
    store = Store(data_dir)
    store.ensure()
    jobs = Jobs(store)
    app = FastAPI(title="Cover pattern engine", version=__version__)
    app.state.store, app.state.jobs = store, jobs

    def model_or_404(model_id: str) -> Path:
        try:
            d = store.model_dir(model_id)
        except KeyError:
            raise HTTPException(404, f"no model {model_id!r}") from None
        if not d.is_dir():
            raise HTTPException(404, f"no model {model_id!r}")
        return d

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "engine": __version__}

    @app.get("/api/models")
    def models() -> list[dict[str, Any]]:
        return store.list_models()

    @app.post("/api/models")
    async def upload(
        file: UploadFile = File(...),  # noqa: B008 - FastAPI's way
        units: str | None = Form(None),  # noqa: B008
        up: str | None = Form(None),  # noqa: B008
        run_all: bool = Form(True),  # noqa: B008
    ) -> dict[str, Any]:
        name = file.filename or "model"
        if Path(name).suffix.lower() not in UPLOAD_SUFFIXES:
            raise HTTPException(400, f"{name}: not a 3D file this program reads")
        model_id = store.new_id(name)
        path = store_upload(store, model_id, name, await file.read())
        store.model_dir(model_id).mkdir(parents=True)
        steps = STEPS if run_all else ["import"]
        job = jobs.submit(JobSpec(model_id, list(steps), {}, str(path), units or None, up or None))
        return {"model_id": model_id, "job": job}

    @app.get("/api/models/{model_id}")
    def model(model_id: str) -> dict[str, Any]:
        model_or_404(model_id)
        out = store.summary(model_id)
        out["job"] = jobs.latest(model_id)
        return out

    @app.get("/api/models/{model_id}/files/{name}")
    def file(model_id: str, name: str) -> FileResponse:
        d = model_or_404(model_id)
        if name not in ALLOWED or not (d / name).is_file():
            raise HTTPException(404, f"no file {name!r}")
        suffix = Path(name).suffix
        return FileResponse(d / name, media_type=MEDIA.get(suffix, "application/octet-stream"))

    @app.get("/api/parameters")
    def parameters() -> list[dict[str, Any]]:
        return registry_specs()

    @app.get("/api/models/{model_id}/parameters")
    def model_parameters(model_id: str) -> dict[str, Any]:
        model_or_404(model_id)
        return store.parameters(model_id)

    @app.put("/api/models/{model_id}/parameters")
    def save_parameters(model_id: str, req: ParametersRequest) -> dict[str, Any]:
        model_or_404(model_id)
        try:
            return store.save_parameters(model_id, req.values)
        except (ParamError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from None

    @app.post("/api/models/{model_id}/run")
    def run(model_id: str, req: RunRequest) -> dict[str, Any]:
        d = model_or_404(model_id)
        if not (d / "model.json").is_file():
            raise HTTPException(400, "the model is not imported yet")
        steps = req.steps or STEPS[1:]
        try:
            store.parameters(model_id, trial=req.trial)  # check the values before queueing
            return jobs.submit(JobSpec(model_id, steps, req.trial))
        except (ParamError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/models/{model_id}/plan")
    def plan_view(model_id: str) -> dict[str, Any]:
        d = model_or_404(model_id)
        try:
            return plan(d)
        except FileNotFoundError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.put("/api/models/{model_id}/seams")
    def seams(model_id: str, req: SeamsRequest) -> dict[str, Any]:
        d = model_or_404(model_id)
        if not (d / "hull.glb").is_file():
            raise HTTPException(400, "no cover surface yet")
        if req.automatic:
            save_seams(d, None)
        else:
            if req.skirt_seams is None and req.top_seams is None:
                raise HTTPException(400, "no seams given (or set automatic)")
            save_seams(d, {"skirt_seams": req.skirt_seams, "top_seams": req.top_seams})
        job = jobs.submit(JobSpec(model_id, ["cut", "flatten", "export"], {})) if req.run else None
        return {"saved": not req.automatic, "job": job}

    @app.post("/api/models/{model_id}/ai-apply")
    def ai_apply(model_id: str, req: AiApplyRequest) -> dict[str, Any]:
        from coverengine.ai import apply_action

        d = model_or_404(model_id)
        try:
            steps = apply_action(d, req.action, req.value)
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        return jobs.submit(JobSpec(model_id, steps, {}))

    @app.post("/api/references")
    async def upload_references(file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
        """One zip of the owner's drawings with their 3D models, paired by name."""
        import time

        if not (file.filename or "").lower().endswith(".zip"):
            raise HTTPException(400, "upload one .zip with pairs like 1.step + 1.pdf")
        batch_id = time.strftime("%Y%m%d-%H%M%S")
        target = store.uploads / f"{batch_id}.zip"
        with target.open("wb") as out:  # streamed: the zip may be large
            while chunk := await file.read(1 << 20):
                out.write(chunk)
        import zipfile

        try:
            batch = unpack(store, target, batch_id)
        except zipfile.BadZipFile:
            raise HTTPException(400, "this is not a readable zip file") from None
        if not batch.pairs:
            raise HTTPException(400, "no pairs found: name the files alike, e.g. 1.step and 1.pdf")
        made = register(store, batch)
        for m in made:
            m["job"] = jobs.submit(JobSpec(m["model_id"], list(STEPS), {}, m["source"]))["id"]
        doc = {"id": batch_id, "file": file.filename, "pairs": made, "unpaired": batch.unpaired}
        import json as _json

        (store.batches / f"{batch_id}.json").write_text(_json.dumps(doc, indent=2) + "\n")
        return doc

    @app.get("/api/references")
    def references() -> list[dict[str, Any]]:
        import json as _json

        out = []
        for path in sorted(store.batches.glob("*.json"), reverse=True):
            doc = _json.loads(path.read_text())
            for m in doc["pairs"]:
                try:
                    m["status"] = jobs.get(m["job"])["status"]
                except KeyError:
                    m["status"] = "unknown"
            out.append(doc)
        return out

    @app.get("/api/models/{model_id}/sizes")
    def sizes(model_id: str) -> list[dict[str, Any]]:
        from coverapi.store import key_sizes

        return key_sizes(model_or_404(model_id))

    @app.get("/api/families")
    def families() -> list[str]:
        return list_families()

    @app.put("/api/models/{model_id}/info")
    def model_info(model_id: str, req: InfoRequest) -> dict[str, Any]:
        d = model_or_404(model_id)
        changes = {k: v for k, v in req.model_dump().items() if k in req.model_fields_set}
        try:
            return set_info(d, changes)
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/models/{model_id}/compare")
    def compare_revisions(model_id: str, a: int, b: int) -> dict[str, Any]:
        d = model_or_404(model_id)
        out = compare_files(
            revision_file(d, a, "pattern.json"), revision_file(d, b, "pattern.json")
        )
        if out is None:
            raise HTTPException(404, "no such revisions")
        return out

    @app.get("/api/models/{model_id}/revisions/{number}/{name}")
    def revision(model_id: str, number: int, name: str) -> FileResponse:
        d = model_or_404(model_id)
        if name not in KEPT:
            raise HTTPException(404, f"no file {name!r}")
        path = revision_file(d, number, name)
        if not path.is_file():
            raise HTTPException(404, f"revision {number} has no {name}")
        return FileResponse(path, media_type=MEDIA.get(path.suffix, "application/octet-stream"))

    @app.post("/api/batch")
    def batch(req: BatchRequest) -> dict[str, Any]:
        ids = req.model_ids or [m["id"] for m in store.list_models()]
        if req.family:
            ids = [i for i in ids if info(store.model_dir(i))["family"] == req.family]
        ids = [i for i in ids if (store.model_dir(i) / "model.json").is_file()]
        if not ids:
            raise HTTPException(400, "no models match")
        steps = req.steps or STEPS[1:]
        try:
            for i in ids:
                store.parameters(i, trial=req.trial)
            return {"jobs": [jobs.submit(JobSpec(i, steps, req.trial)) for i in ids]}
        except (ParamError, ValueError) as exc:
            raise HTTPException(400, str(exc)) from None

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str) -> dict[str, Any]:
        try:
            return jobs.get(job_id)
        except KeyError:
            raise HTTPException(404, f"no job {job_id!r}") from None

    if web_dir is not None and (web_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


def default_app() -> FastAPI:
    data = Path(os.environ.get("COVER_DATA_DIR", repo_root() / "data"))
    web = Path(os.environ.get("COVER_WEB_DIR", repo_root() / "apps" / "web" / "dist"))
    return create_app(data, web)


def serve() -> None:
    import uvicorn

    host = os.environ.get("COVER_HOST", "127.0.0.1")
    port = int(os.environ.get("COVER_PORT", "8080"))
    uvicorn.run(default_app(), host=host, port=port)
