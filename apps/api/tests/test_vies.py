import json
from io import BytesIO
from urllib.error import URLError

import pytest
from coverapi import vies


@pytest.mark.parametrize(
    ("country", "number", "expected"),
    [
        ("de", " de 123.456.789 ", ("DE", "123456789")),
        ("GR", "GR 123.456", ("EL", "123456")),
        ("el", "EL123456", ("EL", "123456")),
    ],
)
def test_normalise(country, number, expected):
    assert vies.normalise(country, number) == expected


def test_http_request_and_result(monkeypatch):
    def post(request, timeout):
        assert request.full_url == vies.URL
        assert request.method == "POST" and timeout == 10
        assert json.loads(request.data) == {"countryCode": "EL", "vatNumber": "123456"}
        return BytesIO(
            b'{"isValid":true,"name":"Dealer","address":"Athens","requestIdentifier":"ref"}'
        )

    monkeypatch.setattr(vies, "urlopen", post)
    result = vies.check("GR", "EL 123.456")
    assert result["valid"] is True and result["name"] == "Dealer"
    assert result["address"] == "Athens" and result["request_id"] == "ref"
    assert result["checked"] > 0 and result["error"] is None


def test_transport_failure(monkeypatch):
    def down(*args, **kwargs):
        raise URLError("offline")

    monkeypatch.setattr(vies, "urlopen", down)
    result = vies.check("DE", "123")
    assert result["valid"] is None and "offline" in result["error"]


@pytest.mark.parametrize(
    ("country", "valid", "previous", "override", "expected"),
    [
        ("DE", True, False, None, True),
        ("NL", True, True, None, False),
        ("DE", False, True, None, False),
        ("DE", None, True, None, True),
        ("DE", None, False, None, False),
        ("DE", True, True, False, False),
        ("DE", False, False, True, True),
    ],
)
def test_stored_vat_treatment(tmp_path, monkeypatch, country, valid, previous, override, expected):
    from coverapi.b2b import Store, _check_vies

    def post(*args, **kwargs):
        response = {"userError": "MS_UNAVAILABLE"} if valid is None else {"isValid": valid}
        return BytesIO(json.dumps(response).encode())

    monkeypatch.setattr(vies, "urlopen", post)
    store = Store(tmp_path / "app.db")
    cid = store.add_company(
        {"name": "Dealer", "country": country, "vat_number": "123", "reverse_charge": previous},
        "active",
    )
    changes = {} if override is None else {"reverse_charge": override}
    _check_vies(store.company(cid), changes)
    company = store.change_company(cid, changes)
    assert company["reverse_charge"] is expected
    assert company["vies"]["valid"] is valid
    if valid is None:
        assert company["vies"]["error"] == "MS_UNAVAILABLE"
    if override is not None:
        assert company["vies"]["manual_override"] is override
    # The additive migration can be run again without losing the stored check.
    assert Store(store.path).company(cid)["vies"] == company["vies"]


@pytest.mark.parametrize(
    "response",
    [
        b'{"isValid":false,"userError":"MS_UNAVAILABLE"}',
        b'{"isValid":false,"actionSucceed":false}',
        b'{"errorWrappers":[{"error":"TIMEOUT"}]}',
        b"not json",
        b"{}",
    ],
)
def test_service_errors_are_indeterminate(monkeypatch, response):
    monkeypatch.setattr(vies, "urlopen", lambda *a, **kw: BytesIO(response))
    result = vies.check("DE", "123")
    assert result["valid"] is None and result["error"]
