"""Arrangements in the studio: furniture placed together, one cover over the whole (ADR-089).

- GET  /api/arrangements                     every arrangement (models with arrangement.json)
- GET  /api/arrangements/settings            the page's grid, turn step and default gap
- GET  /api/arrangements/outline/{model_id}  a member's footprint from above (mm, centred)
- POST /api/arrangements/snap                put one member against another's side
- POST /api/arrangements/footprints          the cover's plans to choose from before building
                                             (follow the members, one rectangle, smoothed;
                                             ADR-095), each with its outline and size
- GET  /api/arrangements/{model_id}          one arrangement (its members and places)
- POST /api/arrangements                     make or update one and build its cover (a job:
                                             import → hull → cut → flatten → export)

An arrangement is an ordinary model (`arr-<name>`): it shows in the catalogue (tag
"arrangement") and at the Desk, and its model page has the 3D, the sizes and Unfold.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field


class MemberIn(BaseModel):
    model_id: str
    x_mm: float = 0.0
    y_mm: float = 0.0
    rot_deg: float = 0.0
    mirror: bool = False


class ArrangementIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    members: list[MemberIn] = Field(min_length=1, max_length=20)
    model_id: str | None = None  # update this arrangement (else a new one, named after `name`)
    gap_mm: float = 0.0
    footprint: str | None = None  # follow | box | smooth (ADR-095); None: arrange.footprint


class FootprintsIn(BaseModel):
    members: list[MemberIn] = Field(min_length=1, max_length=20)
    gap_mm: float = 0.0


class SnapIn(BaseModel):
    members: list[MemberIn] = Field(min_length=2, max_length=20)
    i: int
    j: int
    side: str
    align: str = "back"
    gap_mm: float | None = None


def install(app: FastAPI, store: Any, jobs: Any) -> None:
    from coverengine import arrange as ar
    from coverengine.errors import CoverError
    from coverengine.params import Registry

    from coverapi.jobs import JobSpec
    from coverapi.security import require

    outlines: dict[tuple[str, float], dict[str, Any]] = {}

    def params() -> Any:
        return Registry.load(None).resolve()

    def member_ok(model_id: str) -> None:
        try:
            d = store.model_dir(model_id)
        except KeyError:
            raise HTTPException(404, f"no model {model_id!r}") from None
        if not (d / "model.glb").is_file():
            raise HTTPException(400, f"{model_id}: no imported furniture")

    @app.get("/api/arrangements")
    def list_arrangements(request: Request) -> list[dict[str, Any]]:
        require(request, "view")
        out = []
        for d in sorted(Path(store.models).glob("arr-*")):
            if (d / ar.ARRANGEMENT_JSON).is_file():
                doc = ar.read(d)
                out.append({"id": d.name, "name": doc.get("name"), "size_mm": doc.get("size_mm"),
                            "members": [m["model_id"] for m in doc.get("members", [])],
                            "stale": ar.stale(Path(store.models), doc),
                            "built": (d / "finished.json").is_file()})  # fmt: skip
        return out

    @app.get("/api/arrangements/settings")
    def settings(request: Request) -> dict[str, Any]:
        require(request, "view")
        p = params()
        keys = ("gap_mm", "grid_mm", "rotation_step_deg", "footprint")
        return {k: p[f"arrange.{k}"] for k in keys}

    @app.get("/api/arrangements/outline/{model_id}")
    def outline(model_id: str, request: Request) -> dict[str, Any]:
        require(request, "view")
        member_ok(model_id)
        glb = store.model_dir(model_id) / "model.glb"
        key = (model_id, glb.stat().st_mtime)
        if key not in outlines:
            outlines[key] = ar.outline(Path(store.models), model_id)
        return outlines[key]

    @app.post("/api/arrangements/snap")
    def snap(body: SnapIn, request: Request) -> dict[str, Any]:
        require(request, "view")
        for m in body.members:
            member_ok(m.model_id)
        members = [ar.Member(**m.model_dump()) for m in body.members]
        if not (0 <= body.i < len(members) and 0 <= body.j < len(members)) or body.i == body.j:
            raise HTTPException(400, "choose two different members")
        meshes = {m.model_id: ar.furniture(Path(store.models), m.model_id) for m in members}
        gap = float(params()["arrange.gap_mm"]) if body.gap_mm is None else body.gap_mm  # type: ignore[arg-type]
        try:
            moved = ar.snap(members, meshes, body.i, body.j, body.side, body.align, gap)
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        return {"member": moved.__dict__}

    @app.post("/api/arrangements/footprints")
    def footprints(body: FootprintsIn, request: Request) -> dict[str, Any]:
        """The plans the cover can take, seen from above, before it is built (ADR-095)."""
        require(request, "view")
        for m in body.members:
            member_ok(m.model_id)
        members = [ar.Member(**m.model_dump()) for m in body.members]
        try:
            options = ar.footprints(Path(store.models), members, body.gap_mm, params())
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        return {"default": str(params()["arrange.footprint"]), "options": options}

    @app.get("/api/arrangements/{model_id}")
    def one(model_id: str, request: Request) -> dict[str, Any]:
        require(request, "view")
        try:
            d = store.model_dir(model_id)
            doc = ar.read(d)
        except (KeyError, CoverError):
            raise HTTPException(404, f"no arrangement {model_id!r}") from None
        return {**doc, "stale": ar.stale(Path(store.models), doc)}

    @app.post("/api/arrangements")
    def build(body: ArrangementIn, request: Request) -> dict[str, Any]:
        """Make or update an arrangement and build its cover in the background."""
        user = require(request, "edit")
        for m in body.members:
            member_ok(m.model_id)
            if m.model_id.startswith("arr-"):
                raise HTTPException(400, "an arrangement cannot be a member of another one")
        if body.model_id:
            model_id = body.model_id
            if not re.fullmatch(r"arr-[a-z0-9-]+", model_id):
                raise HTTPException(400, "not an arrangement")
        else:
            model_id = ar.slug(body.name)
            n = 2
            while (Path(store.models) / model_id).exists():
                model_id, n = f"{ar.slug(body.name)}-{n}", n + 1
        d = Path(store.models) / model_id
        members = [ar.Member(**m.model_dump()) for m in body.members]
        footprint = body.footprint or str(params()["arrange.footprint"])
        if footprint not in ar.FOOTPRINTS:
            raise HTTPException(400, f"footprint: one of {', '.join(ar.FOOTPRINTS)}")
        try:
            src = ar.write(Path(store.models), model_id, body.name, members, body.gap_mm,
                           footprint)  # fmt: skip
        except CoverError as exc:
            raise HTTPException(400, str(exc)) from None
        p = params()
        cj = d / "cover.json"
        doc: dict[str, Any] = json.loads(cj.read_text()) if cj.is_file() else {"format_version": 1}
        mine = doc.setdefault("parameters", {})
        hull = mine.setdefault("hull", {})
        hull.setdefault("top", str(p["arrange.hull_top"]))
        hull.setdefault("box_pieces", int(p["arrange.box_pieces"]))  # type: ignore[call-overload]
        doc["tags"] = sorted(set(doc.get("tags") or []) | {"arrangement"})
        names = ", ".join(m.model_id for m in members)
        doc["notes"] = f"Arrangement {body.name} by {user.username}: {names}"
        doc.setdefault("status", "draft")
        cj.write_text(json.dumps(doc, indent=2) + "\n")
        steps = ["import", "hull", "cut", "flatten", "export"]
        job = jobs.submit(JobSpec(model_id, steps, {}, source=str(src), units="mm", up="z"))
        return {"model_id": model_id, "job": job, "size_mm": ar.read(d)["size_mm"],
                "footprint": footprint}  # fmt: skip
