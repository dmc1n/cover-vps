"""The cover unfolded, piece by piece, with where its fabric goes (ADR-085): the data for the 3D
view's "Unfold". Computed on request and kept per cover revision (coverengine/unfold.py)."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response


def install(app: FastAPI, store: Any) -> None:
    def build(model_id: str) -> tuple[dict[str, Any], bytes]:
        from coverengine import unfold
        from coverengine.errors import CoverError
        from coverengine.params.registry import resolve_model

        try:
            d = store.model_dir(model_id)
        except KeyError:
            raise HTTPException(404, f"no model {model_id!r}") from None
        if not (d / "finished.json").is_file() or not (d / "panels.npz").is_file():
            raise HTTPException(404, "no finished pieces yet: calculate the cover first")
        params = resolve_model(d)
        try:
            return unfold.build(d, params)
        except (CoverError, ValueError) as exc:
            raise HTTPException(422, f"cannot unfold this cover: {exc}") from None

    @app.get("/api/models/{model_id}/unfold.json")
    def unfold_meta(model_id: str) -> dict[str, Any]:
        return build(model_id)[0]

    @app.get("/api/models/{model_id}/unfold.bin")
    def unfold_bin(model_id: str) -> Response:
        return Response(build(model_id)[1], media_type="application/octet-stream")
