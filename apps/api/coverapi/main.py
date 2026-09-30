"""The web app's server: the API under /api and the built browser app (apps/web/dist) at /.

    COVER_DATA_DIR=data uv run cover-web          # http://127.0.0.1:8080

One process, one port. It is meant to sit behind the Cloudflare tunnel (M6) or an SSH tunnel.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from coverengine import __version__
from coverengine.params.registry import ParamError, repo_root
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coverapi.jobs import Jobs, JobSpec, store_upload
from coverapi.plan import plan, save_seams
from coverapi.store import ALLOWED, MEDIA, STEPS, UPLOAD_SUFFIXES, Store, registry_specs


class RunRequest(BaseModel):
    steps: list[str] | None = None  # default: everything after import
    trial: dict[str, Any] = {}


class ParametersRequest(BaseModel):
    values: dict[str, Any]


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
