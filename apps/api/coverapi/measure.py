"""Measuring on the 3D cover (ADR-111): what the viewer's Measure tool snaps to, the distance
along the fabric between two points, and the check list's points (coverengine/measure.py).
The check list itself is the file `checklist.pdf` (made when it is opened)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


class Between(BaseModel):
    a: list[float] = Field(min_length=3, max_length=3)  # mm, Z up (the engine's coordinates)
    b: list[float] = Field(min_length=3, max_length=3)


def install(app: FastAPI, store: Any) -> None:
    def folder(model_id: str) -> Path:
        try:
            d = Path(store.model_dir(model_id))
        except KeyError:
            raise HTTPException(404, f"no model {model_id!r}") from None
        if not (d / "panels.npz").is_file() or not (d / "panels.json").is_file():
            raise HTTPException(404, "no pieces yet: calculate the cover first")
        return d

    @app.get("/api/models/{model_id}/measure.json")
    def snaps(model_id: str) -> dict[str, Any]:
        """Seams, free edges and vents to snap to (mm, Z up)."""
        import json

        from coverengine.finish.vents3d import ensure_vents
        from coverengine.measure import snap_doc

        d = folder(model_id)
        out = snap_doc(d)
        path = ensure_vents(d)
        doc = json.loads(path.read_text(encoding="utf-8")) if path else {}
        out["vents"] = doc.get("vents", [])
        return out

    @app.post("/api/models/{model_id}/measure/geodesic")
    def along(model_id: str, req: Between) -> dict[str, Any]:
        """The straight distance, the height difference and the distance along the fabric."""
        from coverengine.measure import geodesic

        return geodesic(folder(model_id), req.a, req.b)

    @app.get("/api/models/{model_id}/checkpoints")
    def checkpoints(model_id: str) -> dict[str, Any]:
        """The numbers to check on a sewn cover (the check list's), with their keys."""
        from coverengine.measure import check_points

        d = folder(model_id)
        if not (d / "pattern.json").is_file():
            raise HTTPException(404, "no flat pieces yet: calculate the cover first")
        return check_points(d)
