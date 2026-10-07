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

REAL_GEMINI = sg.gemini  # the tests of the calls themselves fake the network under them
REAL_REVERSE = sg.reverse_search


@pytest.fixture(autouse=True)
def no_web_search(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may call the AI or search the web for real (both cost money): the photo is not
    identified, nothing is found, nothing compared; any other paid call fails the test."""

    def paid(*a: Any, **k: Any) -> Any:
        raise AssertionError("a test made a paid AI call")

    monkeypatch.setattr(sg, "gemini", paid)
    monkeypatch.setattr(sg, "reverse_search", lambda *a, **k: {"pages": [], "labels": []})
    monkeypatch.setattr(sg, "identify", lambda *a, **k: {})
    monkeypatch.setattr(sg, "search_comparable", lambda *a, **k: [])
    monkeypatch.setattr(sg, "compare", lambda *a, **k: {})


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

    def fake_ask(
        params: Any, photos: list[bytes], facts: Any, lang: str, hint: Any = None
    ) -> dict[str, Any]:
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

    def refuse(url: str, kinds: Any, *a: Any, **k: Any) -> Any:
        if kinds == sg.IMAGE_TYPES:  # its picture comes from a CDN that serves robots
            return url, _png()
        raise sg.SuggestError("the page answered 429")  # shops refuse robots

    monkeypatch.setattr(sg, "fetch", refuse)
    found[0]["image"] = "https://cdn.example/rotunde.jpg"
    monkeypatch.setattr(sg, "compare", lambda *a, **k: {
        0: {"same": False, "similarity": 0.8, "why": "same shape, other brand"}})  # fmt: skip
    seen: dict[str, Any] = {}

    def fake_ask(
        params: Any, photos: list[bytes], facts: Any, lang: str, hint: Any = None
    ) -> dict[str, Any]:
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


def _photo_flow(monkeypatch: pytest.MonkeyPatch, ident: dict[str, Any],
                runs: dict[bool, list[dict[str, Any]]],
                scores: dict[int, dict[str, Any]]) -> dict[str, Any]:  # fmt: skip
    """A photo alone with faked identify, searches (by brand / by look), web and comparison."""
    seen: dict[str, Any] = {"searches": []}
    monkeypatch.setattr(sg, "identify", lambda *a, **k: ident)

    def search(params: Any, png: bytes, idt: Any = None, brand: bool = False) -> Any:
        seen["searches"].append(brand)
        return runs.get(brand, [])

    monkeypatch.setattr(sg, "search_comparable", search)
    monkeypatch.setattr(sg, "fetch", lambda url, kinds, *a, **k: (
        (url, _png()) if kinds == sg.IMAGE_TYPES else (_ for _ in ()).throw(
            sg.SuggestError("the page answered 403"))))  # fmt: skip

    def cmp(params: Any, png: bytes, cands: list[dict[str, Any]]) -> Any:
        seen["candidates"] = [c["title"] for c in cands]
        return scores

    monkeypatch.setattr(sg, "compare", cmp)

    def fake_ask(params: Any, photos: Any, facts: Any, lang: str, hint: Any = None) -> Any:
        seen.update(facts=facts, hint=hint)
        fields = {"length_cm": {"value": 231, "source": "page", "confidence": 0.9}} if facts else {
            "length_cm": {"value": 220, "source": "photo", "confidence": 0.4}}  # fmt: skip
        return {"product": "sofa", "summary": "a sofa", "fields": fields}

    monkeypatch.setattr(sg, "ask", fake_ask)
    return seen


def _post_photo(app: Any) -> dict[str, Any]:
    photo = [("photos", ("s.png", _png(), "image/png"))]
    r = TestClient(app).post("/api/shop/suggest", files=photo)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _page(title: str, brand: str = "", same: bool = False) -> dict[str, Any]:
    slug = title.lower().replace(" ", "-")
    return {"url": f"https://shop.example/{slug}", "title": title, "brand": brand, "same": same,
            "image": f"https://cdn.example/{slug}.jpg",
            "sizes_cm": {"length": 231, "depth": 85, "height": 90}}  # fmt: skip


def test_a_recognised_brand_and_model_is_searched_and_shown(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner, 7 Oct 2026: recognising the brand and model is wanted. The brand's own search
    runs beside the search by look; the comparison of pictures confirms it; the proposal names
    it ("Recognised: ...") and its sizes are the basis, still to check."""
    ident = {"kind": "sofa", "type": "3-seater sofa", "brand": "SUNS", "model": "Tosca",
             "brand_confidence": 0.9, "queries": ["outdoor sofa rope back"]}  # fmt: skip
    runs = {True: [_page("SUNS Tosca 3-seater sofa", "SUNS", True)],
            False: [_page("Kettal Cala 3-seater"), _page("Tribu Vis a Vis")]}  # fmt: skip
    scores = {0: {"same": True, "similarity": 0.95, "why": "identical"},
              1: {"same": False, "similarity": 0.6, "why": "other arms"},
              2: {"same": False, "similarity": 0.3, "why": "other shape"}}  # fmt: skip
    seen = _photo_flow(monkeypatch, ident, runs, scores)
    r = TestClient(app).post("/api/shop/suggest", data={"lang": "nl"},
                             files=[("photos", ("s.png", _png(), "image/png"))])  # fmt: skip
    assert r.status_code == 200, r.text
    out = r.json()
    assert sorted(seen["searches"]) == [False, True]  # by brand and by look
    assert seen["candidates"][0] == "SUNS Tosca 3-seater sofa"  # results taken in turns
    assert out["recognised"]["title"] == "SUNS Tosca 3-seater sofa"
    assert out["recognised"]["brand"] == "SUNS" and out["comparable"] is None
    assert "the same product" in seen["facts"]["relation"]
    assert seen["hint"]["type"] == "3-seater sofa"  # the first look goes with the question
    assert "recognised" in out["flags"]["length_cm"] and "length_cm" in out["check"]


def test_a_wrong_brand_guess_and_unlike_products_are_not_taken_over(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner's photo, 7 Oct 2026: what it "recognised" made no sense. A product the
    comparison finds unlike the photo is never the basis: the photo's own estimates instead."""
    ident = {"kind": "sofa", "brand": "Talenti", "model": "Leaf", "brand_confidence": 0.8}
    runs = {True: [_page("Talenti Leaf 3 seater sofa", "Talenti", True)],
            False: [_page("Jardin curved corner set")]}  # fmt: skip
    scores = {0: {"same": False, "similarity": 0.35, "why": "straight, thin legs"},
              1: {"same": False, "similarity": 0.5, "why": "other modules"}}  # fmt: skip
    seen = _photo_flow(monkeypatch, ident, runs, scores)
    r = TestClient(app).post("/api/shop/suggest",
                             files=[("photos", ("s.png", _png(), "image/png"))])  # fmt: skip
    out = r.json()
    assert out["recognised"] is None and out["comparable"] is None and seen["facts"] is None
    assert out["flags"]["length_cm"] == ["estimate"]


def test_a_page_without_a_picture_counts_only_with_the_recognised_name(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    ident = {"brand": "SUNS", "model": "Tosca", "brand_confidence": 0.9}
    page = _page("SUNS Tosca 3-seater sofa", "SUNS", True) | {"image": ""}
    other = _page("Some sofa", "", True) | {"image": ""}
    seen = _photo_flow(monkeypatch, ident, {True: [page], False: [other]}, {})
    out = _post_photo(app)
    assert out["recognised"]["title"] == "SUNS Tosca 3-seater sofa"
    assert seen["facts"]["product"]["sizes"]["length"] == 231
    low = {**ident, "brand_confidence": 0.5}  # not sure enough of the brand: not recognised
    seen = _photo_flow(monkeypatch, low, {True: [page], False: [other]}, {})
    out = _post_photo(app)
    assert out["recognised"] is None and seen["facts"] is None


class _Reply:
    def __init__(self, doc: dict[str, Any]) -> None:
        self._b = json.dumps(doc).encode()

    def read(self) -> bytes:
        return self._b

    def __enter__(self) -> "_Reply":
        return self

    def __exit__(self, *a: Any) -> None:
        pass


def test_every_gemini_call_and_each_search_query_is_in_the_ledger(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The costs (ADR-078): tokens per call, and Google's fee per search query the model ran."""
    import urllib.request

    import coverengine.ai
    from coverengine.params import Registry

    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(coverengine.ai, "_key", lambda provider: "test-key")
    reply = {"usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 200},
             "candidates": [{"content": {"parts": [{"text": '{"pages": []}'}]},
                             "groundingMetadata": {"webSearchQueries": ["a", "b", "c"],
                             "groundingChunks": [{"web": {"uri": "https://x.example/p",
                                                          "title": "x.example"}}]}}]}  # fmt: skip
    sent: list[Any] = []

    def urlopen(req: Any, timeout: float = 0) -> _Reply:
        sent.append(json.loads(req.data))
        return _Reply(reply)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    p = Registry.load(None).resolve()
    got = REAL_GEMINI(p, [{"text": "hi"}], "suggest search", 5, search=True)
    assert got["queries"] == ["a", "b", "c"] and got["links"][0]["url"] == "https://x.example/p"
    assert sent[0]["tools"] == [{"google_search": {}}]
    rows = [json.loads(x) for f in (tmp_path / "usage").glob("*.jsonl")
            for x in f.read_text().splitlines()]  # fmt: skip
    fee = [r for r in rows if r["model"].endswith(" search")]
    per_query = float(p["suggest.search_query_eur"])  # type: ignore[arg-type]
    assert len(rows) == 2 and fee[0]["eur"] == pytest.approx(3 * per_query)
    REAL_GEMINI(p, [{"text": "hi"}], "suggest compare", 5)  # no search: JSON, no fee
    assert sent[1]["generationConfig"]["responseMimeType"] == "application/json"
    assert "tools" not in sent[1]


def test_the_search_by_image_when_switched_on_comes_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """ADR-092: Google's search by image (off until the owner gives a key). Its pages showing the
    very picture come first and its best guess of the name is the first query."""
    from coverengine.params import Registry

    ident = {"kind": "sofa", "queries": ["outdoor sofa rope back"]}
    seen = _photo_flow(monkeypatch, ident, {False: [_page("Kettal Cala 3-seater")]}, {
        0: {"same": True, "similarity": 0.97, "why": "the same picture"},
        1: {"same": False, "similarity": 0.5, "why": "other arms"}})  # fmt: skip
    queries: list[Any] = []
    search = sg.search_comparable

    def spy(p: Any, png: bytes, idt: Any = None, brand: bool = False) -> Any:
        queries.append(list((idt or {}).get("queries") or []))
        return search(p, png, idt, brand)

    monkeypatch.setattr(sg, "search_comparable", spy)
    monkeypatch.setattr(sg, "reverse_search", lambda *a, **k: {
        "labels": ["suns tosca sofa"],
        "pages": [_page("Tosca 3-zits bank", "SUNS", True)]})  # fmt: skip
    off = Registry.load(None).resolve(trial={"suggest.reverse_search": False})
    assert sg._reverse(off, _png()) == {"pages": [], "labels": []}  # switched off
    on = Registry.load(None).resolve(trial={"suggest.reverse_search": True})
    out = sg.find_comparable(on, _png(), 5, 1000, 1000)
    assert seen["candidates"][0] == "Tosca 3-zits bank"
    assert queries[0][0] == "suns tosca sofa"
    assert out["recognised"]["name"] == "SUNS Tosca 3-zits bank"


def test_the_search_by_image_reads_google_s_answer_and_records_its_fee(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import urllib.request

    import coverengine.ai
    from coverengine.params import Registry

    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(coverengine.ai, "_key", lambda provider: "test-key")
    web = {"bestGuessLabels": [{"label": "suns tosca"}], "pagesWithMatchingImages": [
        {"url": "https://hello-suns.com/tosca", "pageTitle": "<b>Tosca</b> sofa",
         "fullMatchingImages": [{"url": "https://hello-suns.com/tosca.jpg"}]},
        {"url": "https://pins.example/1", "pageTitle": "a pin",
         "partialMatchingImages": [{"url": "https://pins.example/1.jpg"}]}]}  # fmt: skip
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=0: _Reply(
        {"responses": [{"webDetection": web}]}))  # fmt: skip
    p = Registry.load(None).resolve()
    got = REAL_REVERSE(p, _png())
    assert got["labels"] == ["suns tosca"]
    first = {"url": "https://hello-suns.com/tosca", "title": "Tosca sofa",
             "image": "https://hello-suns.com/tosca.jpg", "same": True}  # fmt: skip
    assert got["pages"][0] == first
    assert got["pages"][1]["same"] is False
    rows = [json.loads(x) for f in (tmp_path / "usage").glob("*.jsonl")
            for x in f.read_text().splitlines()]  # fmt: skip
    assert rows[0]["eur"] == pytest.approx(float(p["suggest.reverse_eur"]))


def test_a_cut_out_picture_gets_a_white_background() -> None:
    """A webshop's product picture with a see-through background: white, never black."""
    import io

    from coverapi.shop_suggest import photo_png
    from PIL import Image

    im = Image.new("RGBA", (40, 40), (0, 0, 0, 0))
    im.paste((200, 30, 30, 255), (10, 10, 30, 30))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    out = Image.open(io.BytesIO(photo_png(buf.getvalue()))).convert("RGB")
    assert out.getpixel((1, 1)) == (255, 255, 255)
    assert out.getpixel((20, 20)) == (200, 30, 30)
