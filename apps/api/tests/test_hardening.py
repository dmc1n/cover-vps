"""The security fixes of 12 Oct 2026 (ADR-123), each with the hole it closes."""

import io
import json
import re
import sqlite3
import struct
import subprocess
import sys
import time
import zipfile
import zlib
from pathlib import Path
from typing import Any

import pytest
from coverapi.main import create_app
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[3]
PASSWORDS = {"rick": "a-long-admin-password", "vera": "a-long-viewer-password"}


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    a = create_app(tmp_path / "data", login_required=True)
    auth = a.state.auth
    for name, role in (("rick", "admin"), ("vera", "viewer")):
        u = auth.add_user(name, name.title(), role, f"{name}@example.com", name == "rick")
        auth.set_password(auth.invite(u.id), PASSWORDS[name])
    return a


def login(app: Any, user: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user, "password": PASSWORDS[user]})
    assert r.status_code == 200, r.text
    return c


def png_header_only(width: int, height: int) -> bytes:
    """A tiny PNG that claims a huge size (a decompression bomb's header)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))  # fmt: skip

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" * 64)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


# ---- 1. server-only settings ------------------------------------------------------------------


def test_server_only_settings_are_refused_per_model_and_per_trial(tmp_path: Path) -> None:
    from coverengine.testshapes import write_all

    write_all(tmp_path / "shapes")
    a = create_app(tmp_path / "data")
    c = TestClient(a)
    d = a.state.store.models / "m"
    d.mkdir(parents=True)
    (d / "model.json").write_text("{}")
    for key, value in (("ai.base_url", "https://evil.example"), ("spend.budget_eur_month", 1e9),
                       ("suggest.visitor_eur_day", 100.0), ("limits.body_mb", 9999)):  # fmt: skip
        r = c.put("/api/models/m/parameters", json={"values": {key: value}})
        assert r.status_code == 400 and "server only" in r.text, (key, r.text)
        r = c.post("/api/models/m/run", json={"steps": ["hull"], "trial": {key: value}})
        assert r.status_code == 400, (key, r.text)
    assert not (d / "cover.json").exists()
    specs = {s["key"]: s for s in c.get("/api/parameters").json()}
    assert specs["ai.base_url"]["server_only"] and not specs["hull.clearance_mm"]["server_only"]
    ok = c.put("/api/models/m/parameters", json={"values": {"hull.clearance_mm": 12}})
    assert ok.status_code == 200


# ---- 3. request sizes -------------------------------------------------------------------------


def test_a_body_over_its_routes_limit_is_refused_before_it_is_read(app: Any) -> None:
    c = TestClient(app)
    big = b"x" * (2 * 1024 * 1024 + 10)  # over limits.body_mb
    r = c.post("/api/auth/login", content=big, headers={"content-type": "application/json"})
    assert r.status_code == 413
    # a body without a length (chunked) is counted as it comes
    r = c.post("/api/auth/login", content=iter([big[:1_000_000]] * 3),
               headers={"content-type": "application/json"})  # fmt: skip
    assert r.status_code == 413
    # the photo route allows more (3 photos), and a model upload more still
    from coverapi.bodylimit import BodyLimit

    mw = next(m for m in app.user_middleware if m.cls is BodyLimit)
    limiter = BodyLimit(None, **mw.kwargs)
    small = limiter.limit_for("/api/auth/login")
    assert limiter.limit_for("/api/shop/suggest") > small
    assert limiter.limit_for("/api/shop/fit/abc/photo") > small
    assert limiter.limit_for("/api/models") > limiter.limit_for("/api/shop/suggest")
    assert limiter.limit_for("/api/models/x/drawing") == limiter.limit_for("/api/models")
    assert limiter.limit_for("/api/models/x/parameters") == small


def test_the_caddyfile_and_the_app_name_the_same_upload_routes(app: Any) -> None:
    """Every route that takes a file is large in Caddy and in the app; nothing else is."""
    from coverapi.bodylimit import BodyLimit
    from fastapi.routing import APIRoute

    text = (REPO / "deploy" / "Caddyfile").read_text()
    upload = re.search(r"@upload path (.+)", text)
    photos = re.search(r"@photos path (.+)", text)
    assert upload and photos
    caddy = upload.group(1).split() + photos.group(1).split()
    assert f"not path {upload.group(1)}" in text and f"not path {photos.group(1)}" in text
    mw = next(m for m in app.user_middleware if m.cls is BodyLimit)
    limiter = BodyLimit(None, **mw.kwargs)
    takes_files = set()
    for r in app.routes:
        if not isinstance(r, APIRoute) or not ({"POST", "PUT"} & r.methods):
            continue
        fields = r.dependant.body_params
        if any("UploadFile" in str(f.field_info.annotation) for f in fields) or r.path in (
            "/api/shop/fit/{token}/photo",
        ):
            takes_files.add(re.sub(r"\{[^}]+\}", "*", r.path))
    assert takes_files and takes_files <= set(caddy), takes_files - set(caddy)
    for path in caddy:
        assert limiter.limit_for(path.replace("*", "x")) > limiter.default, path


# ---- 4. decompression bombs -------------------------------------------------------------------


def test_a_tiny_png_claiming_a_huge_size_is_refused_before_decoding() -> None:
    from coverapi.shop_suggest import SuggestError, photo_png
    from coverengine.safeimage import TooLargeImage, open_image

    bomb = png_header_only(60000, 60000)  # 3600 megapixels in a few bytes
    assert len(bomb) < 200
    with pytest.raises(SuggestError, match="too large"):
        photo_png(bomb)
    with pytest.raises(TooLargeImage):
        open_image(bomb, 40_000_000)


def test_a_large_jpeg_is_decoded_at_a_reduced_scale() -> None:
    from coverengine.safeimage import open_image
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (8000, 6000), "white").save(buf, "JPEG", quality=50)  # 48 MP
    im = open_image(buf.getvalue(), 40_000_000, draft_edge=1600)
    assert max(im.size) >= 1600 and im.size[0] * im.size[1] <= 40_000_000
    im = open_image(buf.getvalue(), 40_000_000)  # no edge asked: halved, under the cap
    assert im.size == (4000, 3000)


def test_only_web_picture_formats_reach_a_decoder() -> None:
    """A TIFF (or JPEG 2000) is refused before Pillow decodes it: their decoders carried the
    critical advisories of Oct 2026; JPEG, PNG, WebP, AVIF and GIF still open."""
    from coverengine.safeimage import open_image
    from PIL import Image, UnidentifiedImageError

    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, "TIFF")
    with pytest.raises(UnidentifiedImageError):
        open_image(buf.getvalue(), 40_000_000)
    for fmt in ("JPEG", "PNG", "WEBP", "GIF"):
        buf = io.BytesIO()
        Image.new("RGB", (40, 30), "white").save(buf, fmt)
        assert open_image(buf.getvalue(), 40_000_000).size == (40, 30)


def test_a_desk_picture_bomb_is_refused(tmp_path: Path) -> None:
    from coverapi.desk import save_picture
    from coverengine.params import Registry
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        save_picture(tmp_path, png_header_only(60000, 60000), Registry.load(None).resolve())
    assert exc.value.status_code in (400, 413)
    assert not list(tmp_path.rglob("*.png"))


def test_a_pdf_with_too_many_pages_or_a_giant_page_is_refused() -> None:
    import pymupdf
    from coverengine.safeimage import TooLargeImage, check_upload_pdf

    doc = pymupdf.open()
    doc.new_page(width=595, height=842)
    assert check_upload_pdf(doc.tobytes()) == 1
    many = pymupdf.open()
    for _ in range(60):
        many.new_page()
    with pytest.raises(TooLargeImage, match="pages"):
        check_upload_pdf(many.tobytes())
    giant = pymupdf.open()
    giant.new_page(width=14400, height=14400)  # 200 x 200 inches
    with pytest.raises(TooLargeImage, match="too large"):
        check_upload_pdf(giant.tobytes())


# ---- 5. the old webshop API -------------------------------------------------------------------
# (test_security.test_the_webshop_api_keys_limits_and_requests)


def test_the_old_webshop_api_is_behind_the_website_gate(app: Any) -> None:
    from coverapi.shop import SHOP_SETTING

    app.state.auth.set_setting(SHOP_SETTING, {"website_link": {"closed": True}})
    r = TestClient(app).get("/api/public/v1/options")
    assert r.status_code == 403 and "shop is at" in r.text
    assert login(app, "rick").get("/api/public/v1/options").status_code == 200


# ---- 6. old proposals, and who a limit counts -------------------------------------------------


def test_old_proposals_go_unless_an_order_names_them(tmp_path: Path) -> None:
    sys.path.insert(0, str(REPO / "scripts"))
    import quotes_clean

    data = tmp_path / "data"
    create_app(data)  # the database with its tables
    q = data / "shop_quotes"
    q.mkdir(exist_ok=True)
    old, kept, new = "a" * 16, "b" * 16, "c" * 16
    for qid in (old, kept, new):
        for name in (f"{qid}.json", f"{qid}.glb", f"{qid}-balloons.glb"):
            (q / name).write_text("{}")
    (q / "README.txt").write_text("not a proposal")
    month = 86400 * 61
    for f in q.iterdir():
        if not f.name.startswith(new):
            import os

            os.utime(f, (time.time() - month, time.time() - month))
    with sqlite3.connect(data / "app.db") as db:
        db.execute("INSERT INTO orders (created, token, status, email, data, total_eur, updated) "
                   "VALUES (?, 'tok', 'paid', 'a@b.c', ?, 1, ?)",
                   (time.time(), json.dumps({"customer": {"quote_id": kept}}),
                    time.time()))  # fmt: skip
    would = quotes_clean.clean(data, 60, dry_run=True)
    assert sorted(f.name for f in would) == sorted(
        [f"{old}.json", f"{old}.glb", f"{old}-balloons.glb"])  # fmt: skip
    assert all(f.exists() for f in would)  # a dry run removes nothing
    gone = quotes_clean.clean(data, 60, dry_run=False)
    assert len(gone) == 3 and not any(f.exists() for f in gone)
    assert (q / f"{kept}.json").exists() and (q / f"{new}.glb").exists()
    assert (q / "README.txt").exists()
    out = subprocess.run(["bash", "-n", str(REPO / "scripts" / "housekeeping.sh")], check=False)
    assert out.returncode == 0


def test_an_ipv6_visitor_counts_as_its_network_and_all_visitors_have_a_cap() -> None:
    from coverapi.ratelimit import GlobalCap, visitor_key

    assert visitor_key("2001:db8:1:2:aaaa::1") == visitor_key("2001:db8:1:2:bbbb::9")
    assert visitor_key("2001:db8:1:2::1") != visitor_key("2001:db8:1:3::1")
    assert visitor_key("203.0.113.5") == "203.0.113.5"
    assert visitor_key("::ffff:203.0.113.5") == "203.0.113.5"
    assert visitor_key("unknown") == "unknown"
    cap = GlobalCap(3)
    assert [cap.hit(100.0) for _ in range(4)] == [True, True, True, False]
    assert cap.hit(161.0)  # a minute later


def test_proposals_from_everyone_together_are_capped(app: Any) -> None:
    from coverapi.ratelimit import GlobalCap

    app.state.quote_cap = GlobalCap(2)
    c = TestClient(app)
    codes = [c.post("/api/shop/quote", json={"product": "item"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


# ---- 7. the login code fails closed -----------------------------------------------------------


def test_with_the_code_on_and_no_mail_server_a_password_is_not_enough(
    app: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coverapi import mailer, users_cli

    auth = app.state.auth
    auth.set_setting("two_factor", True)
    monkeypatch.setattr(mailer, "configured", lambda a: False)
    r = TestClient(app).post("/api/auth/login",
                             json={"username": "rick", "password": PASSWORDS["rick"]})  # fmt: skip
    assert r.status_code == 503 and "cover-users" in r.json()["detail"]
    # the way in on the server: cover-users two-factor off (or invite)
    monkeypatch.setenv("COVER_DATA_DIR", str(auth.path.parent))
    monkeypatch.setattr(sys, "argv", ["cover-users", "two-factor", "off"])
    assert users_cli.main() == 0
    assert login(app, "rick")


# ---- 8. codes and links: revoked, used once ---------------------------------------------------


def test_a_password_change_reset_or_disable_ends_the_open_login_codes(app: Any) -> None:
    from coverapi.auth import AuthError

    auth = app.state.auth
    vera = next(u for u in auth.users() if u.username == "vera")
    for revoke in (
        lambda: auth.change_password(vera.id, PASSWORDS["vera"], PASSWORDS["vera"]),
        lambda: auth.invite(vera.id),
        lambda: auth.update_user(vera.id, {"active": False}),
    ):
        cid, code = auth.challenge(vera, "x")
        revoke()
        with pytest.raises(AuthError, match="expired"):
            auth.verify(cid, code, "x")
        auth.update_user(vera.id, {"active": True})
        auth.set_password(auth.invite(vera.id), PASSWORDS["vera"])


def test_a_login_code_and_a_link_are_used_once(app: Any) -> None:
    from coverapi.auth import AuthError

    auth = app.state.auth
    vera = next(u for u in auth.users() if u.username == "vera")
    cid, code = auth.challenge(vera, "x")
    auth.verify(cid, code, "x")
    with pytest.raises(AuthError):
        auth.verify(cid, code, "x")
    token = auth.invite(vera.id)
    auth.set_password(token, "a-new-long-password-1")
    with pytest.raises(AuthError, match="no longer valid"):
        auth.set_password(token, "a-new-long-password-2")
    # wrong codes: each try counted before the comparison; the fifth ends it
    cid, code = auth.challenge(vera, "x")
    for _ in range(5):
        with pytest.raises(AuthError):
            auth.verify(cid, "x" + code, "x")
    with pytest.raises(AuthError, match="too many"):
        auth.verify(cid, code, "x")


def test_login_codes_are_limited_per_hour(app: Any) -> None:
    from coverapi.auth import AuthError, login_limits

    auth = app.state.auth
    vera = next(u for u in auth.users() if u.username == "vera")
    for _ in range(login_limits()[1]):
        auth.challenge(vera, "x")
    with pytest.raises(AuthError) as exc:
        auth.challenge(vera, "x")
    assert exc.value.status == 429


# ---- 10. logins, approvers, Mollie ------------------------------------------------------------


def test_wrong_passwords_lock_one_account_and_address_and_an_unknown_name_alike(app: Any) -> None:
    from coverapi.auth import AuthError

    auth = app.state.auth

    def answer(user: str, pw: str, address: str) -> int:
        try:
            auth.check_login(user, pw, address)
        except AuthError as exc:
            return exc.status
        return 200

    known = [answer("vera", "wrong", "203.0.113.1") for _ in range(6)]
    unknown = [answer("nobody", "wrong", "203.0.113.2") for _ in range(6)]
    assert known == unknown == [401] * 5 + [429]
    assert answer("vera", PASSWORDS["vera"], "203.0.113.1") == 429  # that address waits
    assert answer("vera", PASSWORDS["vera"], "198.51.100.1") == 200  # the real person does not
    # the lock grows: one more wrong one after the lock doubles it
    from coverapi.auth import LOCK_MINUTES, lock_seconds

    assert lock_seconds(5) == LOCK_MINUTES * 60 and lock_seconds(6) == LOCK_MINUTES * 120


def test_a_display_name_does_not_make_an_approver() -> None:
    from coverapi.auth import User
    from coverapi.desk import approver
    from coverapi.questions import _matches

    params = {"desk.approvers": "rens,rick"}
    fake = User(9, "mallory", "Rens Fake", None, "editor", False, True)
    real = User(8, "rens", "Rens", None, "editor", False, True)
    assert not approver(fake, params) and approver(real, params)
    assert not _matches(fake, {"rens"}) and _matches(real, {"rens"})


def test_a_mollie_payment_must_be_this_orders() -> None:
    from coverapi.shop import payment_mismatch

    pay = {"amount": {"value": "129.95", "currency": "EUR"}, "metadata": {"order": 7},
           "mode": "live"}  # fmt: skip
    assert payment_mismatch(pay, 7, 129.95, "live") is None
    assert "amount" in str(payment_mismatch(pay, 7, 130.00, "live"))
    assert "currency" in str(payment_mismatch({**pay, "amount": {"value": "129.95",
                                                                 "currency": "USD"}}, 7, 129.95,
                                              "live"))  # fmt: skip
    assert "order" in str(payment_mismatch(pay, 8, 129.95, "live"))
    assert "test" in str(payment_mismatch({**pay, "mode": "test"}, 7, 129.95, "live"))


# ---- 9. parsers: zips, sheets, jobs -----------------------------------------------------------


def test_a_reference_zip_with_too_many_files_or_too_much_inside_is_refused(
    app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coverapi import references

    def zipped(n: int, size: int) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            for i in range(n):
                z.writestr(f"{i}.stl", b"\0" * size)
        return buf.getvalue()

    c = login(app, "rick")
    monkeypatch.setattr(references, "zip_limits", lambda: (3, 10_000))
    r = c.post("/api/references", files={"file": ("a.zip", zipped(4, 10), "application/zip")})
    assert r.status_code == 413 and "files" in r.text
    r = c.post("/api/references", files={"file": ("b.zip", zipped(2, 20_000), "application/zip")})
    assert r.status_code == 413 and "unpacks" in r.text
    store = app.state.store
    assert not [p for p in store.uploads.iterdir() if p.is_dir()]  # nothing half unpacked left


def test_a_sheet_that_claims_too_many_rows_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    from coverapi import products_sheet

    monkeypatch.setattr(products_sheet, "sheet_limits", lambda: (5, 1000))
    text = "code,name\n" + "".join(f"S{i},x\n" for i in range(10))
    with pytest.raises(products_sheet.SheetError, match="too large"):
        products_sheet.read_sheets("list.csv", text.encode())
    assert products_sheet.read_sheets("list.csv", b"code,name\nS1,x\n")


def test_a_job_step_has_a_time_and_memory_limit(
    app: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # the launcher: a step over its memory fails, the caller goes on
    hog = [sys.executable, "-m", "coverapi.limited", "300", "0", "json.tool", "--help"]
    assert subprocess.run(hog, capture_output=True, check=False).returncode == 0
    eat = "from coverapi.limited import apply; apply(200, 0); b = bytearray(400 * 2**20)"
    over = [sys.executable, "-c", eat]
    r = subprocess.run(over, capture_output=True, text=True, check=False)
    assert r.returncode != 0 and "MemoryError" in r.stderr
    # the job runner: a step that runs too long is stopped and the job says why
    from coverapi import jobs as jobs_module

    slow = tmp_path / "slow.sh"
    slow.write_text("#!/bin/sh\nsleep 30\n")
    slow.chmod(0o755)
    monkeypatch.setattr(jobs_module, "job_limits", lambda: (1, 0, 0))
    monkeypatch.setattr(jobs_module.sys, "executable", str(slow))
    d = app.state.store.models / "m"
    d.mkdir(parents=True)
    job = app.state.jobs.submit(jobs_module.JobSpec("m", ["hull"], {}))
    done = app.state.jobs.wait(job["id"], 20)
    assert done["status"] == "failed" and "longer than 1 s" in done["error"]


def test_a_page_over_the_pixel_cap_renders_smaller_not_fails() -> None:
    """Codex, 12 Oct: a fractional resolution must not break the render (PyMuPDF's dpi= takes
    whole numbers)."""
    import pymupdf
    from coverengine.safeimage import render_page

    doc = pymupdf.open()
    page = doc.new_page(width=7200, height=7200)  # 100 x 100 inches: 121 MP at 110 dpi
    pix = render_page(page, 110, 4_000_000)
    assert 0 < pix.width * pix.height <= 4_000_000 * 1.01
    small = doc.new_page(width=595, height=842)
    assert render_page(small, 110, 4_000_000).width == small.get_pixmap(dpi=110).width


def test_an_xlsx_that_unpacks_to_too_much_is_refused_before_it_is_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex, 12 Oct: openpyxl reads the shared strings whole; the zip's sizes are checked first."""
    from coverapi import products_sheet
    from coverengine.params import Registry

    base = Registry.load(None).resolve()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/sharedStrings.xml", b"<sst>" + b"A" * (3 * 1024 * 1024) + b"</sst>")
    data = buf.getvalue()
    assert len(data) < 100_000  # small on the wire

    class Small:
        def __getitem__(self, key: str) -> object:
            return 1 if key == "limits.sheet_max_unpacked_mb" else base[key]

    monkeypatch.setattr(Registry, "resolve", lambda self, **k: Small())
    with pytest.raises(products_sheet.SheetError, match="unpacks to too much"):
        products_sheet.read_sheets("prices.xlsx", data)
