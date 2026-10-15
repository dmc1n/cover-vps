"""Exercise the CLI against an actual local HTTP server."""

import json
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import covers  # noqa: E402

PRICE = {"amount_eur": 849, "currency": "EUR", "vat_included": True}
MATCH = {
    "kind": "sofa",
    "your_sizes": {"width": 230, "depth": 90, "height": 85},
    "results": [
        {
            "rank": 1,
            "type": "existing",
            "code": "suns-2-seater-kota",
            "name": "Kota cover",
            "fit_pct": 98,
            "price": PRICE,
            "order_url": "https://shop.test/order",
            "why": "A good fit",
        }
    ],
    "notes": ["Measure carefully"],
    "assumed": [{"size": "front_height", "value_cm": 60, "why": "not given; our default"}],
}
KINDS = {
    "kinds": [
        {
            "kind": "sofa",
            "label": "Sofa",
            "aliases": ["couch"],
            "sizes": [{"name": "depth", "required": True, "min_cm": 10, "max_cm": 200}],
        }
    ]
}
LINK = {
    "order_url": "https://shop.test/pay",
    "expires_at": "2026-10-15T12:00:00Z",
    "what_happens_next": ["A person checks out"],
    "agent_may_pay": False,
}
ERROR = {
    "error": "missing_size",
    "message": "depth missing for kind sofa",
    "hint": 'Add "depth" ...',
    "field": "depth",
}


@pytest.fixture
def api() -> Iterator[tuple[str, list[dict[str, object]]]]:
    requests: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.respond()

        def do_POST(self) -> None:
            self.respond()

        def log_message(self, format: str, *args: object) -> None:
            pass

        def respond(self) -> None:
            body = json.loads(
                self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}"
            )
            requests.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": body,
                }
            )
            status = 200
            data = {}
            if body.get("kind") == "limited":
                status, data = 429, {"error": "rate_limit", "message": "Too many requests"}
            elif self.path == "/match":
                status, data = (200, MATCH) if "depth" in body else (400, ERROR)
            elif self.path == "/kinds":
                data = KINDS
            elif self.path == "/order-link":
                data = LINK
            elif self.path == "/quote":
                data = {"price": PRICE, "cover_sizes": {"width": 235}, "lead_time": "2 weeks"}
            elif self.path == "/covers/suns-2-seater-kota":
                data = {"name": "Kota", "code": "suns-2-seater-kota", "price": PRICE}
            else:
                status, data = 404, {"error": "not_found"}
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("RateLimit-Remaining", "9")
            if status == 429:
                self.send_header("Retry-After", "120")
            self.end_headers()
            self.wfile.write(json.dumps(data).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_find(api: tuple[str, list[dict[str, object]]], capsys: pytest.CaptureFixture[str]) -> None:
    url, requests = api
    assert (
        covers.main(
            [
                "find",
                "--api",
                url,
                "--kind",
                "sofa",
                "--width",
                "230",
                "--depth",
                "90",
                "--height",
                "85",
                "--size",
                "extra=12.5",
                "--no-chairs",
            ]
        )
        == 0
    )
    assert requests[0]["body"] == {
        "kind": "sofa",
        "width": 230,
        "depth": 90,
        "height": 85,
        "extra": 12.5,
        "chairs": False,
    }
    out = capsys.readouterr().out
    for expected in ("suns-2-seater-kota", "98%", "EUR 849.00 incl. VAT", covers.CLOSING):
        assert expected in out


def test_json_key_env(
    api: tuple[str, list[dict[str, object]]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url, requests = api
    monkeypatch.setenv("COVERS_API", url)
    monkeypatch.setenv("COVERS_API_KEY", "secret-partner")
    assert covers.main(["find", "--kind", "sofa", "--depth", "90", "--json"]) == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out) == MATCH
    assert "secret-partner" not in captured.out + captured.err
    assert requests[0]["headers"]["X-Api-Key"] == "secret-partner"
    assert requests[0]["headers"]["User-Agent"] == "s2dio-covers-cli/1.0"


@pytest.mark.parametrize("as_json", [False, True])
def test_error(
    api: tuple[str, list[dict[str, object]]], capsys: pytest.CaptureFixture[str], as_json: bool
) -> None:
    url, _ = api
    argv = ["--api", url, "find", "--kind", "sofa"] + (["--json"] if as_json else [])
    assert covers.main(argv) == 2
    captured = capsys.readouterr()
    if as_json:
        assert json.loads(captured.out) == ERROR
        assert not captured.err
    else:
        assert 'hint: Add "depth"' in captured.err


def test_rate_limit(
    api: tuple[str, list[dict[str, object]]], capsys: pytest.CaptureFixture[str]
) -> None:
    url, _ = api
    assert covers.main(["find", "--api", url, "--kind", "limited"]) == 3
    assert "retry after 120" in capsys.readouterr().err


def test_link(api: tuple[str, list[dict[str, object]]], capsys: pytest.CaptureFixture[str]) -> None:
    url, requests = api
    assert covers.main(["--api", url, "link", "--kind", "sofa", "--no-vents"]) == 0
    out = capsys.readouterr().out
    assert LINK["order_url"] in out
    assert LINK["expires_at"] in out
    assert covers.CLOSING in out
    assert requests[0]["body"]["vents"] is False


def test_kinds_alias(
    api: tuple[str, list[dict[str, object]]], capsys: pytest.CaptureFixture[str]
) -> None:
    url, _ = api
    assert covers.main(["kinds", "--api", url, "--kind", "couch"]) == 0
    assert "sofa — Sofa" in capsys.readouterr().out
    assert covers.main(["kinds", "--api", url, "--kind", "unknown"]) == 2
    assert "kinds: sofa" in capsys.readouterr().err


def test_cover_and_quote(
    api: tuple[str, list[dict[str, object]]], capsys: pytest.CaptureFixture[str]
) -> None:
    url, _ = api
    assert covers.main(["cover", "suns-2-seater-kota", "--api", url]) == 0
    assert "Kota (suns-2-seater-kota)" in capsys.readouterr().out
    assert covers.main(["quote", "--kind", "sofa", "--api", url]) == 0
    assert "EUR 849.00 incl. VAT" in capsys.readouterr().out


def test_call(api: tuple[str, list[dict[str, object]]]) -> None:
    url, _ = api
    status, headers, data = covers.call("POST", "/match", {"kind": "sofa"}, api=url, key=None)
    assert status == 400
    assert data == ERROR
    assert headers["RateLimit-Remaining"] == "9"


def test_global_overrides(
    api: tuple[str, list[dict[str, object]]], capsys: pytest.CaptureFixture[str]
) -> None:
    url, requests = api
    assert (
        covers.main(
            [
                "--api",
                "http://invalid",
                "--key",
                "old",
                "--json",
                "kinds",
                "--api",
                url,
                "--key",
                "new",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == KINDS
    assert requests[0]["headers"]["X-Api-Key"] == "new"


def test_socket_free_request(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: list[tuple[str, str, covers.Json | None, str, str | None]] = []

    def fake_call(
        method: str,
        path: str,
        body: covers.Json | None = None,
        *,
        api: str,
        key: str | None,
    ) -> tuple[int, dict[str, str], covers.Json]:
        seen.append((method, path, body, api, key))
        return 200, {}, MATCH

    monkeypatch.setattr(covers, "call", fake_call)
    assert (
        covers.main(
            [
                "--api",
                "https://test",
                "--key",
                "private",
                "find",
                "--kind",
                "sofa",
                "--width",
                "230",
                "--depth",
                "90",
                "--height",
                "85",
                "--no-chairs",
                "--size",
                "extra=true",
                "--json",
            ]
        )
        == 0
    )
    assert seen == [
        (
            "POST",
            "/match",
            {
                "kind": "sofa",
                "width": 230.0,
                "depth": 90.0,
                "height": 85.0,
                "chairs": False,
                "extra": True,
            },
            "https://test",
            "private",
        )
    ]
    assert json.loads(capsys.readouterr().out) == MATCH


def test_size_values() -> None:
    assert covers.size_pair("front-height=60") == ("front_height", 60.0)
    assert covers.size_pair("chairs=false") == ("chairs", False)
    for value in ("missing", "=12", "width=nan", "depth=inf", "width=abc"):
        with pytest.raises(covers.argparse.ArgumentTypeError):
            covers.size_pair(value)


@pytest.fixture()
def real_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Serve the real anonymous API on an operating-system-selected local port."""
    import socket
    import time

    import uvicorn
    from coverapi import shop_suggest
    from coverapi.main import create_app

    monkeypatch.setenv("COVER_AUTO_DRAPE", "off")
    monkeypatch.setenv("COVER_MAIL_WORKER", "off")
    monkeypatch.delenv("COVERS_API_KEY", raising=False)

    def no_external(*args: object, **kwargs: object) -> None:
        pytest.fail("The CLI integration test attempted an AI or external web call")

    monkeypatch.setattr(shop_suggest, "run_suggestion", no_external)
    import urllib.request
    from urllib.parse import urlsplit

    urlopen = urllib.request.urlopen

    def local_only(request: urllib.request.Request, *args: object, **kwargs: object) -> object:
        if urlsplit(request.full_url).hostname != "127.0.0.1":
            no_external()
        return urlopen(request, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", local_only)
    a = create_app(tmp_path / "data", login_required=True)
    a.state.auth.set_setting("shop", {"agent_api_enabled": True})
    d = a.state.store.models / "suns-2-seater-kota"
    d.mkdir(parents=True)
    (d / "cover.json").write_text(
        json.dumps(
            {
                "notes": "SUNS: SUNS-2 Seater-Kota",
                "category": "Lounge › Sofasets",
            }
        )
    )
    (d / "model.json").write_text(json.dumps({"size_mm": [2300, 900, 850]}))
    (d / "product.jpg").write_bytes(b"\xff\xd8\xfftest")
    server = uvicorn.Server(uvicorn.Config(a, host="127.0.0.1", port=0, log_level="error"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, "uvicorn did not start"
        yield f"http://127.0.0.1:{port}/api/v2"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive(), "uvicorn did not stop"


def test_real_agent_api(real_api: str, capsys: pytest.CaptureFixture[str]) -> None:
    """The CLI finds real catalogue and custom covers and reads the real measuring kinds."""
    args = [
        "find",
        "--api",
        real_api,
        "--kind",
        "sofa",
        "--width",
        "230",
        "--depth",
        "90",
        "--height",
        "85",
    ]
    assert covers.main(args) == 0
    output = capsys.readouterr().out
    assert "suns-2-seater-kota" in output and "made to measure" in output.lower()
    assert covers.main([*args, "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["results"][0]["code"] == "suns-2-seater-kota"
    assert covers.main(["kinds", "--api", real_api, "--kind", "sofa"]) == 0
    output = capsys.readouterr().out
    assert "sofa" in output and "depth" in output and "width" in output
