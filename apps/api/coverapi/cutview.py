"""The Cutting file view (ADR-147): the cutting table's cut.dxf drawn on the server, for the Desk
card and the cover page, while the DXF itself stays behind the Desk's approval gate.

- `GET /api/models/{id}/cutview[?revision=n]`: what the viewer needs besides the drawing: the
  sheet, each piece's name, box, corners and edge lengths, the layers' counts, whether this cut
  file is approved and so whether the drawing carries the watermark. Never an outline.
- `GET /api/models/{id}/cutview.svg[?revision=n]`: the drawing (SVG, never the DXF's bytes),
  with "PREVIEW – NOT FOR CUTTING" across it unless the Desk approved this very cut file.
- `GET /api/models/{id}/cutview/diff?a=<n>&b=<n|current>`: what changed between two revisions'
  cutting files, piece by piece.

Who: admins, the Desk's approvers and editors; the workshop login only where it may download
the DXF anyway (an approved cover, `desk.dxf_allowed`); viewers never. The drawing is made from
the bytes whose fingerprint decides the watermark, and cached by that fingerprint (ADR-120).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

from coverengine.catalogue import revision_file, revisions
from coverengine.export import cutview as cv
from fastapi import FastAPI, HTTPException, Request, Response

from coverapi import desk

CACHE_DIR = "cutview-cache"
_render_slots = threading.BoundedSemaphore(2)  # at most two drawings made at a time
_key_locks: dict[str, threading.Lock] = {}
_key_guard = threading.Lock()
SVG_HEADERS = {
    "Cache-Control": "private, no-cache",
    "X-Content-Type-Options": "nosniff",
    # opened on its own, the drawing runs nothing and loads nothing
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
}


def _params() -> Any:
    from coverengine.params import Registry

    return Registry.load(None).resolve()


def _settings(params: Any) -> tuple[str, str, float, float, float]:
    return (str(params["export.cut_layer"]), str(params["export.pen_layer"]),
            float(params["desk.preview_flatten_mm"]), float(params["desk.preview_corner_deg"]),
            float(params["desk.preview_min_edge_mm"]))  # fmt: skip


def may_view(user: Any, params: Any) -> bool:
    """Admins, the Desk's approvers and editors see every cover's cutting file; the workshop
    login is checked per cover (`workshop_may`); viewers never."""
    if getattr(user, "role", None) == desk.WORKSHOP_ROLE:
        return False
    return bool(desk.approver(user, params) or user.may("edit"))


def approved_for(d: Path, fp: str, revision: int | None) -> bool:
    """Whether the Desk approved this cut file: the current one while the approval holds (the
    same fingerprint, an arrangement's placement unchanged), a kept revision's when its
    fingerprint was approved at some time (ADR-120, ADR-128)."""
    st = desk.state(d)
    if revision is not None:
        return fp in st.get("approved_fingerprints", [])
    ok = st.get("approved") or {}
    return (st["status"] in desk.DONE and ok.get("cut") == fp
            and not desk._changed_since_approval(d, st))  # fmt: skip


def _source(d: Path, revision: int | None) -> Path:
    if revision is None:
        path = d / "cut.dxf"
        if not path.is_file():
            raise HTTPException(404, "no cutting file yet: build the cover first")
        return path
    if revision < 1 or not any(r.get("number") == revision for r in revisions(d)):
        raise HTTPException(404, f"no revision {revision}")
    path = revision_file(d, revision, "cut.dxf")
    if not path.is_file():
        raise HTTPException(404, f"revision {revision} has no cutting file")
    return path


class Rendered:
    def __init__(self, svg: str, meta: dict[str, Any]) -> None:
        self.svg, self.meta = svg, meta


def _lock_for(key: str) -> threading.Lock:
    with _key_guard:
        return _key_locks.setdefault(key, threading.Lock())


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _prune(folder: Path, keep: int) -> None:
    files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for meta in files[: max(len(files) - keep, 0)]:
        meta.unlink(missing_ok=True)
        meta.with_suffix(".svg").unlink(missing_ok=True)


def rendered(root: Path, data: bytes, params: Any) -> Rendered:
    """The drawing and meta of these DXF bytes, from the cache when made before: the key is the
    bytes' fingerprint, the renderer's version and the settings it drew with."""
    import hashlib

    settings = _settings(params)
    tag = hashlib.sha256(json.dumps(settings).encode()).hexdigest()[:8]
    key = f"{cv.fingerprint(data)}-v{cv.VERSION}-{tag}"
    folder = root / CACHE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    svg_path, meta_path = folder / f"{key}.svg", folder / f"{key}.json"
    with _lock_for(key):
        if svg_path.is_file() and meta_path.is_file():
            try:
                return Rendered(svg_path.read_text(encoding="utf-8"),
                                json.loads(meta_path.read_text(encoding="utf-8")))  # fmt: skip
            except (OSError, ValueError):
                pass  # a damaged cache entry: draw it again
        with _render_slots:
            try:
                svg, meta = cv.render(data, *settings)
            except Exception as exc:  # noqa: BLE001 - an unreadable DXF is the user's answer
                raise HTTPException(422, f"the cutting file could not be read: {exc}") from None
        _write_atomic(svg_path, svg)
        _write_atomic(meta_path, json.dumps(meta, separators=(",", ":")))
        _prune(folder, int(params["desk.preview_cache_keep"]))
        return Rendered(svg, meta)


def install(app: FastAPI, store: Any) -> None:
    from coverapi.security import current_user

    def folder(model_id: str) -> Path:
        try:
            d = Path(store.model_dir(model_id))
        except KeyError:
            raise HTTPException(404, f"no model {model_id!r}") from None
        if not d.is_dir():
            raise HTTPException(404, f"no model {model_id!r}")
        return d

    def load(model_id: str, revision: int | None, request: Request) -> tuple[Path, Rendered, bool]:
        """The cover's cutting file (current or a revision) drawn, after the rights: refused
        before a byte is read for a viewer, and for the workshop login where it may not
        download this DXF."""
        user = current_user(request)
        params = _params()
        d = folder(model_id)
        workshop = getattr(user, "role", None) == desk.WORKSHOP_ROLE
        if not workshop and not may_view(user, params):
            raise HTTPException(403, "the cutting file is shown to editors, approvers and admins")
        path = _source(d, revision)
        if path.stat().st_size > float(params["desk.preview_max_mb"]) * 1024 * 1024:
            raise HTTPException(413, "this cutting file is too large to draw in the browser")
        data = path.read_bytes()  # once: the fingerprint, the drawing and the watermark agree
        fp = cv.fingerprint(data)
        approved = approved_for(d, fp, revision)
        if workshop and not (approved or not desk.gated(d, params)):
            raise HTTPException(403, "the workshop sees the cutting file once the Desk approved it")
        return d, rendered(store.root, data, params), approved

    def meta_of(model_id: str, revision: int | None, r: Rendered, approved: bool,
                d: Path) -> dict[str, Any]:  # fmt: skip
        out = cv.public(r.meta)
        out.update({
            "model_id": model_id,
            "revision": revision,
            "approved": approved,
            "watermark": not approved,
            "watermark_text": None if approved else cv.WATERMARK,
            "band_mm": 0.0 if approved else cv.band_mm(r.meta),
        })  # fmt: skip
        if revision is None:
            out["downloadable"] = desk.dxf_allowed(d, _params())
        return out

    @app.get("/api/models/{model_id}/cutview")
    def cutview_meta(model_id: str, request: Request, revision: int | None = None) -> Any:
        d, r, approved = load(model_id, revision, request)
        return meta_of(model_id, revision, r, approved, d)

    @app.get("/api/models/{model_id}/cutview.svg")
    def cutview_svg(model_id: str, request: Request, revision: int | None = None) -> Response:
        d, r, approved = load(model_id, revision, request)
        rev = f"r{revision}" if revision is not None else "current"
        if approved:
            body = cv.clean(r.svg)
        else:
            note = f"{model_id} {rev} {r.meta['fingerprint']} – not approved at the Desk"
            body = cv.watermarked(r.svg, r.meta, note)
        name = f"{model_id}-{rev}-{'approved' if approved else 'PREVIEW'}.svg"
        return Response(body, media_type="image/svg+xml", headers={
            **SVG_HEADERS, "Content-Disposition": f'inline; filename="{name}"',
            "X-Cutview-Watermark": "0" if approved else "1",
        })  # fmt: skip

    @app.get("/api/models/{model_id}/cutview/diff")
    def cutview_diff(model_id: str, request: Request, a: int, b: str = "current") -> Any:
        """a: the older revision; b: a revision's number or "current"."""
        if b == "current":
            rb: int | None = None
        else:
            try:
                rb = int(b)
            except ValueError:
                raise HTTPException(400, "b is a revision's number or 'current'") from None
        _, ra, _ = load(model_id, a, request)
        _, rbb, _ = load(model_id, rb, request)
        out = cv.compare(ra.meta, rbb.meta, float(_params()["desk.preview_changed_mm"]))
        out.update({"model_id": model_id, "from": a, "to": rb})
        return out
