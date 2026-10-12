"""Request bodies no larger than their route needs (ADR-123).

Caddy (deploy/Caddyfile) is the outer wall; this is the inner one, so the app is safe on its own:
a request whose Content-Length is over its route's limit is answered 413 before anything reads
or parses it, and a body without a length (chunked) is counted as it arrives and stopped at the
limit. The limits come from config/defaults.yaml (limits.*, and the routes' own per-file caps
times their file counts, plus `limits.body_mb` for the form around them).
"""

from __future__ import annotations

import json
import re
from typing import Any

from coverengine.params import EffectiveParams

MIB = 1024 * 1024


def route_limits(p: EffectiveParams, max_photos: int) -> list[tuple[re.Pattern[str], int]]:
    """(path pattern, bytes) for the routes that may send more than `limits.body_mb`."""
    margin = int(float(p["limits.body_mb"]) * MIB)  # type: ignore[arg-type]
    upload = int(float(p["limits.upload_mb"]) * MIB)  # type: ignore[arg-type]
    lists = int(p["products.max_bytes"]) + margin  # type: ignore[arg-type]
    pictures = (
        int(p["desk.pictures_max"])  # type: ignore[arg-type]
        * int(float(p["desk.picture_max_mb"]) * MIB)  # type: ignore[arg-type]
        + margin
    )
    photos = max_photos * int(p["suggest.photo_max_bytes"]) + margin  # type: ignore[arg-type]
    table = [
        # logged-in uploads: 3D models, drawings, references (a zip of many)
        (r"/api/models|/api/references|/api/models/drawing|/api/models/[^/]+/(drawing|reference)",
         upload),
        # the workshop's product list, a price list (Excel, CSV or a zip)
        (r"/api/desk-products|/api/prices/import", lists),
        # pictures at the Desk and on a question; the shop's photo test (logged in)
        (r"/api/desk/[^/]+/pictures|/api/questions/[^/]+/pictures|/api/admin/shop/photo-test",
         pictures),
        # the public shop's photos
        (r"/api/shop/suggest|/api/shop/order/[^/]+/source|/api/shop/fit/[^/]+/photo", photos),
    ]  # fmt: skip
    return [(re.compile(pattern), size) for pattern, size in table]


class TooLarge(Exception):
    pass


class BodyLimit:
    """Pure ASGI middleware: 413 for a body over its route's limit, before it is parsed."""

    def __init__(self, app: Any, default: int, routes: list[tuple[re.Pattern[str], int]]) -> None:
        self.app, self.default, self.routes = app, default, routes

    def limit_for(self, path: str) -> int:
        for pattern, size in self.routes:
            if pattern.fullmatch(path):
                return size
        return self.default

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limit_for(scope.get("path", ""))
        length = next((v for k, v in scope.get("headers", []) if k == b"content-length"), None)
        if length is not None:
            try:
                n = int(length)
            except ValueError:
                await _reply(send, 400, "a wrong Content-Length")
                return
            if n > limit:
                await _reply(send, 413, f"the request is larger than {limit // MIB} MB")
                return

        seen = 0
        over = replied = False
        too_large = f"the request is larger than {limit // MIB} MB"

        async def counted() -> dict[str, Any]:
            nonlocal seen, over
            message: dict[str, Any] = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    over = True
                    raise TooLarge
            return message

        async def watched(message: dict[str, Any]) -> None:
            # once the body ran over, whatever the app makes of it (a parse error) becomes 413
            nonlocal replied
            if not over:
                await send(message)
            elif not replied and message["type"] == "http.response.start":
                replied = True
                await _reply(send, 413, too_large)

        try:
            await self.app(scope, counted, watched)
        except TooLarge:
            if not replied:
                replied = True
                await _reply(send, 413, too_large)


async def _reply(send: Any, status: int, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode()
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                            (b"connection", b"close")]})  # fmt: skip
    await send({"type": "http.response.body", "body": body})


def install(app: Any, p: EffectiveParams, max_photos: int) -> None:
    default = int(float(p["limits.body_mb"]) * MIB)  # type: ignore[arg-type]
    app.add_middleware(BodyLimit, default=default, routes=route_limits(p, max_photos))
