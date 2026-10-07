"""Start from a photo or a link (ADR-086): safe fetching, what a page says, the AI's answer
checked against the configurator, limits. The AI and the web are faked: no paid call, no
network in a test."""

import io
import json
from pathlib import Path
from typing import Any

import pytest
from coverapi import shop_suggest as sg
from coverapi.main import create_app
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture(autouse=True)
def no_web_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may search the web for real (Google's search costs money): nothing found."""
    monkeypatch.setattr(sg, "search_comparable", lambda *a, **k: [])


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    return create_app(tmp_path / "data")


def _png() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (40, 30), (120, 110, 90)).save(b, "PNG")
    return b.getvalue()


class _Resp:
    def __init__(self, status: int, headers: dict[str, str], body: bytes = b"") -> None:
        self.status, self._h, self._b = status, headers, body

    def getheader(self, k: str) -> str | None:
        return self._h.get(k)

    def read(self, n: int = -1) -> bytes:
        return self._b if n < 0 else self._b[:n]

    def close(self) -> None:
        pass


def _web(monkeypatch: pytest.MonkeyPatch, hosts: dict[str, str], pages: dict[str, Any]) -> None:
    """Fake DNS (host -> address) and fake answers (url path on host -> response)."""

    def getaddrinfo(host: str, port: int, *a: Any, **k: Any) -> list[Any]:
        if host not in hosts:
            raise OSError("no such host")
        return [(2, 1, 6, "", (hosts[host], port))]

    def request(scheme: str, host: str, port: int, path: str, ip: str, timeout: float) -> Any:
        assert ip == hosts[host]  # the connection goes to the checked address
        return pages[f"{host}{path}"]

    monkeypatch.setattr(sg.socket, "getaddrinfo", getaddrinfo)
    monkeypatch.setattr(sg, "_request", request)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "http://"])
def test_only_web_links(url: str) -> None:
    with pytest.raises(sg.SuggestError):
        sg.fetch(url, sg.PAGE_TYPES, 5, 1000)


@pytest.mark.parametrize(
    "ip", ["127.0.0.1", "10.0.0.5", "192.168.1.2", "169.254.169.254", "::1", "::ffff:10.0.0.1"]
)
def test_a_private_or_metadata_address_is_refused(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    _web(monkeypatch, {"shop.example": ip}, {})
    with pytest.raises(sg.SuggestError, match="public"):
        sg.fetch("https://shop.example/lounger", sg.PAGE_TYPES, 5, 1000)


def test_a_redirect_to_a_private_address_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    _web(monkeypatch, {"shop.example": "93.184.216.34", "inside.example": "10.1.2.3"},
         {"shop.example/a": _Resp(302, {"Location": "http://inside.example/admin"})})  # fmt: skip
    with pytest.raises(sg.SuggestError, match="public"):
        sg.fetch("https://shop.example/a", sg.PAGE_TYPES, 5, 1000)


def test_too_many_redirects_too_large_or_not_a_page(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = {f"shop.example/{i}": _Resp(301, {"Location": f"/{i + 1}"}) for i in range(10)}
    loop["shop.example/big"] = _Resp(200, {"Content-Type": "text/html"}, b"x" * 2000)
    loop["shop.example/pdf"] = _Resp(200, {"Content-Type": "application/pdf"}, b"%PDF")
    _web(monkeypatch, {"shop.example": "93.184.216.34"}, loop)
    with pytest.raises(sg.SuggestError, match="redirects"):
        sg.fetch("https://shop.example/0", sg.PAGE_TYPES, 5, 1000)
    with pytest.raises(sg.SuggestError, match="large"):
        sg.fetch("https://shop.example/big", sg.PAGE_TYPES, 5, 1000)
    with pytest.raises(sg.SuggestError, match="not a web page"):
        sg.fetch("https://shop.example/pdf", sg.PAGE_TYPES, 5, 1000)


PAGE = b"""<html><head><title>Ligbed Bora | Tuinshop</title>
<meta property="og:image" content="/img/bora.jpg">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product",
 "name":"Ligbed Bora","width":{"@type":"QuantitativeValue","value":75,"unitText":"cm"},
 "depth":{"value":198,"unitCode":"CMT"},"height":"36 cm"}</script></head>
<body><h1>Ligbed Bora</h1><p>Afmetingen: 198 x 75 x 36 cm, hoofdeinde 82 cm hoog.</p>
<script>var x = 1;</script></body></html>"""


def test_a_page_s_written_sizes_are_read() -> None:
    f = sg.page_facts(PAGE, "https://shop.example/bora")
    assert (
        f["title"].startswith("Ligbed Bora") and f["image"] == "https://shop.example/img/bora.jpg"
    )
    assert f["product"]["sizes"]["width"] == "75 cm" and f["product"]["sizes"]["height"] == "36 cm"
    assert any("198 x 75 x 36" in s for s in f["sizes_text"])
    assert not any("var x" in s for s in f["sizes_text"])  # scripts are not text


def test_the_ai_answer_is_checked_against_the_configurator() -> None:
    ans = {"product": "lounger", "summary": "A sun lounger.",
           "fields": {"length_cm": {"value": 198, "source": "page", "confidence": 0.95},
                      "width_cm": {"value": 300, "source": "page", "confidence": 0.9},
                      "height_cm": {"value": 36, "source": "photo",
                                    "confidence": 0.4}}}  # fmt: skip
    p = sg.proposal(ans)
    assert p["sizes"]["length_cm"] == 198 and p["flags"]["length_cm"] == []  # from the page
    assert p["flags"]["width_cm"] == ["clipped"] and p["sizes"]["width_cm"] <= 120  # out of range
    assert p["flags"]["height_cm"] == ["estimate"]  # from a picture: to measure
    assert set(p["check"]) == {"width_cm", "height_cm"}
    with pytest.raises(sg.SuggestError):
        sg.proposal({"product": "spaceship"})


def test_a_link_gives_a_proposal_from_the_page(app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _web(monkeypatch, {"shop.example": "93.184.216.34"}, {
        "shop.example/bora": _Resp(200, {"Content-Type": "text/html; charset=utf-8"}, PAGE),
        "shop.example/img/bora.jpg": _Resp(200, {"Content-Type": "image/png"},
                                           _png())})  # fmt: skip
    seen: dict[str, Any] = {}

    def fake_ask(params: Any, photos: list[bytes], facts: Any, lang: str) -> dict[str, Any]:
        seen.update(photos=len(photos), facts=facts, lang=lang)
        return {"product": "lounger", "summary": "Een ligbed van 198 × 75 cm.",
                "fields": {"length_cm": {"value": 198, "source": "page", "confidence": 0.95},
                           "width_cm": {"value": 75, "source": "page", "confidence": 0.95},
                           "height_cm": {"value": 36, "source": "page",
                                         "confidence": 0.9}}}  # fmt: skip

    monkeypatch.setattr(sg, "ask", fake_ask)
    r = TestClient(app).post("/api/shop/suggest", data={"url": "shop.example/bora", "lang": "nl"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["product"] == "lounger" and out["sizes"]["length_cm"] == 198 and out["check"] == []
    assert seen["photos"] == 1 and "Ligbed Bora" in json.dumps(
        seen["facts"]
    )  # the page's image too
    assert out["source"]["url"] == "https://shop.example/bora"


def test_a_photo_gives_estimates_and_the_limits_hold(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sg, "ask", lambda *a, **k: {
        "product": "item", "fields": {"length_cm": {"value": 60, "source": "photo",
                                                    "confidence": 0.5}}})  # fmt: skip
    c = TestClient(app)
    r = c.post("/api/shop/suggest", files=[("photos", ("a.png", _png(), "image/png"))])
    assert r.status_code == 200, r.text
    assert r.json()["flags"]["length_cm"] == ["estimate"] and "width_cm" in r.json()["check"]
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 20
    r = c.post("/api/shop/suggest", files=[("photos", ("a.heic", heic, "image/heic"))])
    assert r.status_code == 400 and "HEIC" in r.json()["detail"]
    many = [("photos", (f"{i}.png", _png(), "image/png")) for i in range(4)]
    assert c.post("/api/shop/suggest", files=many).status_code == 400
    codes = [c.post("/api/shop/suggest", files=[("photos", ("a.png", _png(), "image/png"))])
             .status_code for _ in range(12)]  # fmt: skip
    assert 429 in codes  # suggest.per_hour


def test_the_month_s_budget_stops_it_kindly(app: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from coverengine.errors import CoverError

    def broke(*a: Any, **k: Any) -> Any:
        raise CoverError("the AI budget for this month is used up")

    monkeypatch.setattr(sg, "ask", broke)
    r = TestClient(app).post("/api/shop/suggest",
                             files=[("photos", ("a.png", _png(), "image/png"))])  # fmt: skip
    assert r.status_code == 503 and "by hand" in r.json()["detail"]


def test_a_flat_lounger_asks_nothing_about_a_headrest_a_raised_one_does() -> None:
    """The lounger's headrest is an option (owner, 7 Oct 2026): its sizes are only checked when
    the AI saw one."""
    from coverapi.shop_suggest import proposal

    page = {"source": "page", "confidence": 0.9}
    flat = proposal({"product": "lounger", "fields": {
        "length_cm": {"value": 198, **page}, "width_cm": {"value": 70, **page},
        "height_cm": {"value": 35, **page}}})  # fmt: skip
    assert flat["check"] == [] and flat["sizes"]["headrest"] is False
    raised = proposal({"product": "lounger", "fields": {
        "length_cm": {"value": 198, **page}, "width_cm": {"value": 70, **page},
        "height_cm": {"value": 35, **page}, "headrest": {"value": True, **page}}})  # fmt: skip
    assert set(raised["check"]) == {"headrest_height_cm", "headrest_length_cm"}


def test_a_photo_alone_starts_from_a_comparable_product_found_on_the_web(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner, 7 Oct 2026: a photo alone gave only estimates; now a comparable product found
    by the web search gives written sizes as the basis, always marked "comparable"."""
    found = [{"url": "https://shop.example/curved-sofa", "title": "Curved Sofa Rotunde",
              "sizes_cm": {"length": 448, "depth": 115, "height": 76}}]  # fmt: skip
    monkeypatch.setattr(sg, "search_comparable", lambda *a, **k: found)

    def refuse(*a: Any, **k: Any) -> Any:
        raise sg.SuggestError("the page answered 429")  # shops refuse robots

    monkeypatch.setattr(sg, "fetch", refuse)
    seen: dict[str, Any] = {}

    def fake_ask(params: Any, photos: list[bytes], facts: Any, lang: str) -> dict[str, Any]:
        seen["facts"] = facts
        return {"product": "sofa", "summary": "a curved sofa", "fields": {
            "length_cm": {"value": 448, "source": "page", "confidence": 0.9},
            "depth_cm": {"value": 115, "source": "page", "confidence": 0.9}}}  # fmt: skip

    monkeypatch.setattr(sg, "ask", fake_ask)
    r = TestClient(app).post("/api/shop/suggest", data={"lang": "nl"},
                             files=[("photos", ("sofa.png", _png(), "image/png"))])  # fmt: skip
    assert r.status_code == 200, r.text
    out = r.json()
    assert seen["facts"]["product"]["sizes"]["length"] == 448  # the search's sizes were the basis
    assert out["comparable"]["title"] == "Curved Sofa Rotunde"
    assert "comparable" in out["flags"]["length_cm"] and "length_cm" in out["check"]
