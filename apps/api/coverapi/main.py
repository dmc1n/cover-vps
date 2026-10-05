"""The web app's server: the API under /api and the built browser app (apps/web/dist) at /.

    COVER_DATA_DIR=data uv run cover-web          # http://127.0.0.1:8080

One process, one port, on 127.0.0.1 only: the reverse proxy (deploy/Caddyfile) serves it to
the internet over https. Users must log in (COVER_LOGIN=off turns that off for a local trial).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from coverengine import __version__
from coverengine.catalogue import KEPT, compare_files, info, revision_file, set_info
from coverengine.errors import CoverError
from coverengine.params.registry import ParamError, list_families, repo_root
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from coverapi.jobs import Jobs, JobSpec, store_upload
from coverapi.plan import plan, save_seams
from coverapi.references import register, unpack
from coverapi.store import ALLOWED, MEDIA, STEPS, UPLOAD_SUFFIXES, Store, registry_specs


class ApproveRequest(BaseModel):
    note: str = ""


class RunRequest(BaseModel):
    steps: list[str] | None = None  # default: everything after import
    trial: dict[str, Any] = {}


class ParametersRequest(BaseModel):
    values: dict[str, Any]


class InfoRequest(BaseModel):
    family: str | None = None
    category: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    notes: str | None = None


class BatchRequest(BaseModel):
    model_ids: list[str] | None = None
    family: str | None = None
    steps: list[str] | None = None
    trial: dict[str, Any] = {}


class KindRequest(BaseModel):
    kind: str  # product | cover
    run: bool = True


class AiApplyRequest(BaseModel):
    action: str
    value: float | None = None


class SeamsRequest(BaseModel):
    automatic: bool = False  # true: forget the hand-placed seams
    skirt_seams: list[list[float]] | None = None  # plan points, one per vertical skirt seam
    top_seams: list[list[list[float]]] | None = None  # plan polylines
    run: bool = True  # cut and flatten again straight away


def _named(model_id: str, name: str, revision: int | None = None) -> tuple[str, str]:
    """A download carries the model's name, not "cut.dxf": the cutting table's file is
    <model>.dxf (with -r<n> for a kept revision), the others <model>-<file> (the owner, 5 Oct)."""
    rev = f"-r{revision}" if revision is not None else ""
    stem, suffix = Path(name).stem, Path(name).suffix
    file = f"{model_id}{rev}{suffix}" if stem == "cut" else f"{model_id}{rev}-{name}"
    kind = "attachment" if suffix in (".dxf", ".pdf", ".svg", ".json") else "inline"
    return file, kind


def create_app(
    data_dir: Path, web_dir: Path | None = None, login_required: bool = False
) -> FastAPI:
    """`login_required`: users must log in (the served app, `cover-web`); off in the tests."""
    from coverapi.auth import Auth
    from coverapi.security import install, require

    store = Store(data_dir)
    store.ensure()
    # the drape after every full calculation (ADR-059); COVER_AUTO_DRAPE=off for tests
    jobs = Jobs(
        store,
        drape_after_export=os.environ.get("COVER_AUTO_DRAPE", "on") != "off",
        drape_workers=int(os.environ.get("COVER_DRAPE_WORKERS", "4")),
    )
    app = FastAPI(
        title="Cover Studio", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.store, app.state.jobs = store, jobs
    auth = Auth(store.root / "app.db")
    install(app, auth, login_required)
    from coverapi import webshop

    webshop.install(app, auth, store.root / "quotes", store.models)
    from coverapi import own_reference

    own_reference.install(app, store)  # the workshop's own reference per model (ADR-070)
    from coverapi import shop

    shop.install(app, auth, store.root, jobs, store)

    def model_or_404(model_id: str) -> Path:
        try:
            d = store.model_dir(model_id)
        except KeyError:
            raise HTTPException(404, f"no model {model_id!r}") from None
        if not d.is_dir():
            raise HTTPException(404, f"no model {model_id!r}")
        return d

    release = repo_root().name if repo_root().name.startswith("v") else "development"

    @app.get("/api/health")
    def health() -> dict[str, str]:
        # the release is the folder the app runs from (~/releases/v1.2.3, ADR-053)
        return {"status": "ok", "engine": __version__, "release": release}

    @app.get("/api/models")
    def models() -> list[dict[str, Any]]:
        return store.list_models()

    @app.post("/api/models")
    async def upload(
        file: UploadFile = File(...),  # noqa: B008 - FastAPI's way
        units: str | None = Form(None),  # noqa: B008
        up: str | None = Form(None),  # noqa: B008
        run_all: bool = Form(True),  # noqa: B008
        kind: str | None = Form(None),  # noqa: B008 - product | cover; none: ask after import
    ) -> dict[str, Any]:
        """Without `kind` only the import runs: the web app shows what the program thinks the
        file is (the furniture or the cover surface only) and the owner confirms (ADR-039)."""
        from coverengine.io.kind import confirm

        name = file.filename or "model"
        if Path(name).suffix.lower() not in UPLOAD_SUFFIXES:
            raise HTTPException(400, f"{name}: not a 3D file this program reads")
        model_id = store.new_id(name)
        path = store_upload(store, model_id, name, await file.read())
        store.model_dir(model_id).mkdir(parents=True)
        if kind:
            try:
                confirm(store.model_dir(model_id), kind)
            except CoverError as exc:
                raise HTTPException(400, str(exc)) from None
        steps = STEPS if run_all and kind else ["import"]
        job = jobs.submit(JobSpec(model_id, list(steps), {}, str(path), units or None, up or None))
        return {"model_id": model_id, "job": job}

    @app.get("/api/models/{model_id}")
    def model(model_id: str) -> dict[str, Any]:
        from coverapi.approval import state

        d = model_or_404(model_id)
        out = store.summary(model_id)
        out["job"] = jobs.latest(model_id)
        out["approval"] = state(d)
        return out

    @app.get("/api/models/{model_id}/files/{name}")
    def file(model_id: str, name: str) -> FileResponse:
        d = model_or_404(model_id)
        if name not in ALLOWED or not (d / name).is_file():
            raise HTTPException(404, f"no file {name!r}")
        suffix = Path(name).suffix
        file, kind = _named(model_id, name)
        return FileResponse(d / name, media_type=MEDIA.get(suffix, "application/octet-stream"),
                            filename=file, content_disposition_type=kind)  # fmt: skip

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

    @app.post("/api/models/{model_id}/kind")
    def set_kind(model_id: str, req: KindRequest) -> dict[str, Any]:
        """The owner confirms what the file is; then the cover is calculated."""
        from coverengine.io.kind import confirm

        d = model_or_404(model_id)
        try:
            doc = confirm(d, req.kind)
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        job = jobs.submit(JobSpec(model_id, STEPS[1:], {})) if req.run else None
        return {"kind": doc, "job": job}

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
        drawings = [u for u in batch.unpaired if u.lower().endswith(".pdf")]
        if not batch.pairs and not drawings:
            raise HTTPException(
                400, "no drawings found: a zip of PDFs, or pairs like 1.step + 1.pdf"
            )
        made = register(store, batch)
        for m in made:
            m["job"] = jobs.submit(JobSpec(m["model_id"], list(STEPS), {}, m["source"]))["id"]
        # drawings without a 3D model are kept for the analysis of the owner's covers
        # (scripts/drawings.py, ADR-043); they are not "unpaired" leftovers
        doc = {
            "id": batch_id,
            "file": file.filename,
            "pairs": made,
            "drawings_only": drawings,
            "unpaired": [u for u in batch.unpaired if u not in drawings],
        }
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

    @app.get("/api/categories")
    def categories() -> list[dict[str, Any]]:
        from coverengine.category import CATEGORIES

        return [{"group": g, "category": c, "name": f"{g} › {c}", "on_suns_site": on}
                for g, c, on in CATEGORIES]  # fmt: skip

    @app.put("/api/models/{model_id}/info")
    def model_info(model_id: str, req: InfoRequest) -> dict[str, Any]:
        from coverapi.approval import state

        d = model_or_404(model_id)
        changes = {k: v for k, v in req.model_dump().items() if k in req.model_fields_set}
        approved = state(d)
        if changes.get("status") == "production" and not (approved and approved["valid"]):
            raise HTTPException(400, "production needs an approval of the current drawing")
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
        file, kind = _named(model_id, name, number)
        return FileResponse(path, media_type=MEDIA.get(path.suffix, "application/octet-stream"),
                            filename=file, content_disposition_type=kind)  # fmt: skip

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

    @app.get("/api/models/{model_id}/approval")
    def approval_state(model_id: str) -> dict[str, Any]:
        from coverapi.approval import state

        return {"approval": state(model_or_404(model_id))}

    @app.post("/api/models/{model_id}/approve")
    def approve_model(model_id: str, req: ApproveRequest, request: Request) -> dict[str, Any]:
        from coverapi.approval import approve

        user = require(request, "approve")
        d = model_or_404(model_id)
        try:
            doc = approve(d, user.username, user.name, req.note)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        auth.log(user, "approved", {"model": model_id, "revision": doc["revision"]})
        return {"approval": doc}

    @app.delete("/api/models/{model_id}/approve")
    def withdraw_approval(model_id: str, request: Request) -> dict[str, Any]:
        from coverapi.approval import withdraw

        user = require(request, "approve")
        withdraw(model_or_404(model_id))
        auth.log(user, "approval withdrawn", {"model": model_id})
        return {"approval": None}

    @app.post("/api/models/{model_id}/approval-request")
    def ask_approval(model_id: str, request: Request) -> dict[str, Any]:
        from coverapi import mailer
        from coverapi.security import DEFAULT_PUBLIC_URL, PUBLIC_URL_KEY

        user = require(request, "edit")
        model_or_404(model_id)
        base = str(auth.setting(PUBLIC_URL_KEY, DEFAULT_PUBLIC_URL)).rstrip("/")
        sent, skipped = [], []
        for u in auth.users():
            if not (u.can_approve and u.active and u.email):
                continue
            if not mailer.configured(auth):
                skipped.append(u.username)
                continue
            try:
                mailer.send(
                    auth, u.email, f"Please approve the cover {model_id}",
                    f"Hello {u.name},\n\n{user.name} asks you to approve the definitive "
                    f"drawing of {model_id}:\n\n{base}/#/model/{model_id}\n",
                )  # fmt: skip
                sent.append(u.username)
            except Exception:  # noqa: BLE001
                skipped.append(u.username)
        auth.log(user, "approval asked", {"model": model_id, "mailed": sent})
        return {"mailed": sent, "not_mailed": skipped}

    @app.get("/api/models/{model_id}/approved/{name}")
    def approved_file(model_id: str, name: str) -> FileResponse:
        from coverapi.approval import APPROVED_DIR, STAMPED

        d = model_or_404(model_id)
        if name not in STAMPED or not (d / APPROVED_DIR / name).is_file():
            raise HTTPException(404, f"no approved {name!r}")
        return FileResponse(d / APPROVED_DIR / name, media_type="application/pdf")

    @app.get("/api/jobs/{job_id}")
    def job(job_id: str) -> dict[str, Any]:
        try:
            return jobs.get(job_id)
        except KeyError:
            raise HTTPException(404, f"no job {job_id!r}") from None

    if web_dir is not None and (web_dir / "shop.html").is_file():
        from coverapi.shop import install_pages

        install_pages(app, auth, web_dir)  # /shop/..., robots.txt, sitemap.xml, llms.txt
    if web_dir is not None and (web_dir / "index.html").is_file():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app


def default_app() -> FastAPI:
    data = Path(os.environ.get("COVER_DATA_DIR", repo_root() / "data"))
    web = Path(os.environ.get("COVER_WEB_DIR", repo_root() / "apps" / "web" / "dist"))
    login = os.environ.get("COVER_LOGIN", "on") != "off"
    return create_app(data, web, login_required=login)


def serve() -> None:
    import uvicorn

    host = os.environ.get("COVER_HOST", "127.0.0.1")
    port = int(os.environ.get("COVER_PORT", "8080"))
    uvicorn.run(default_app(), host=host, port=port)
