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
                                             import → hull → cut → flatten → export); a change
                                             to one at the Desk reopens its approval (ADR-115)
- POST /api/arrangements/{model_id}/send     send a built one to the Desk: ready for approval
                                             (ADR-115); the approvers get it in their digest

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

    from coverapi import desk
    from coverapi.jobs import JobSpec
    from coverapi.security import require

    outlines: dict[tuple[str, float], dict[str, Any]] = {}
    learning = Path(store.root) / "learning"

    def desk_of(d: Path) -> dict[str, Any]:
        """Where the arrangement stands at the Desk (ADR-115), for the page."""
        desk.reopen_if_changed(d, learning)
        st = desk.state(d)
        keep = ("sent", "approved", "rejected", "produced")
        last = st["history"][-1] if st["history"] else None
        short = ("by", "time", "reasons", "text")  # not the fingerprints an approval keeps
        return {
            "status": st["status"],
            **{k: {f: st[k][f] for f in short if f in st[k]} if st.get(k) else None for k in keep},
            "at_desk": (d / "desk.json").is_file() and st["status"] != "new",
            "dxf_ok": desk.dxf_allowed(d, params()),
            "last": last and {k: last.get(k) for k in ("action", "by", "time", "text")},
        }

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
                            "built": (d / "finished.json").is_file(),
                            "desk": desk_of(d)})  # fmt: skip
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
        return {**doc, "stale": ar.stale(Path(store.models), doc), "desk": desk_of(d),
                "built": (d / "finished.json").is_file()}  # fmt: skip

    @app.post("/api/arrangements/{model_id}/send")
    def send(model_id: str, request: Request) -> dict[str, Any]:
        """Send a built arrangement to the Desk: ready for approval by Rens or Wout (ADR-115).
        Whoever may build one may send it; the approvers hear of it in their daily digest."""
        user = require(request, "edit")
        if not re.fullmatch(r"arr-[a-z0-9-]+", model_id):
            raise HTTPException(400, "not an arrangement")
        try:
            d = Path(store.model_dir(model_id))
        except KeyError:
            raise HTTPException(404, f"no arrangement {model_id!r}") from None
        if not (d / ar.ARRANGEMENT_JSON).is_file():
            raise HTTPException(404, f"no arrangement {model_id!r}")
        job = jobs.latest(model_id)
        if job and job.get("status") in ("queued", "running"):
            raise HTTPException(409, "the cover is still being built: send it when it is ready")
        desk.send_arrangement(d, user, learning)
        return {"model_id": model_id, "desk": desk_of(d)}

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
        old = ar.read(d) if (d / ar.ARRANGEMENT_JSON).is_file() else None
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
        if old is not None:  # at the Desk: a change reopens its approval, never silently
            desk.arrangement_changed(d, changes(old, ar.read(d), Path(store.models)), user,
                                     learning)  # fmt: skip
        job = jobs.submit(JobSpec(model_id, steps, {}, source=str(src), units="mm", up="z"))
        return {"model_id": model_id, "job": job, "size_mm": ar.read(d)["size_mm"],
                "footprint": footprint, "desk": desk_of(d)}  # fmt: skip


def changes(old: dict[str, Any], new: dict[str, Any], models: Path) -> list[str]:
    """What a rebuild changes in an arrangement, in words for the Desk's history (ADR-115):
    members, places, the plan, the gap, or a member's own furniture changed since."""
    from coverengine import arrange as ar

    a, b = ar.placement(old), ar.placement(new)
    out = []
    ids_a = [m["model_id"] for m in a["members"]]
    ids_b = [m["model_id"] for m in b["members"]]
    if ids_a != ids_b:
        out.append(f"members {', '.join(ids_a)} → {', '.join(ids_b)}")
    elif a["members"] != b["members"]:
        moved = [m["model_id"] for m, n in zip(a["members"], b["members"], strict=True) if m != n]
        out.append(f"place of {', '.join(moved)}")
    if a["footprint"] != b["footprint"]:  # None: built before ADR-095, the default plan
        out.append(f"plan {a['footprint'] or 'default'} → {b['footprint']}")
    if a["gap_mm"] != b["gap_mm"]:
        out.append(f"gap {a['gap_mm']:g} → {b['gap_mm']:g} mm")
    versions = {m["model_id"]: (m.get("version") or {}).get("model_glb")
                for m in old.get("members") or []}  # fmt: skip
    rebuilt = sorted(
        m["model_id"]
        for m in new.get("members") or []
        if m["model_id"] in versions
        and versions[m["model_id"]] != (m.get("version") or {}).get("model_glb")
    )
    if rebuilt:
        out.append(f"furniture of {', '.join(rebuilt)} changed")
    # a new name alone changes nothing to cut; should the rebuilt cut file differ all the
    # same, its fingerprint reopens the approval (desk.reopen_if_changed)
    return out
