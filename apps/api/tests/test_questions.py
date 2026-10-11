"""Questions at the Desk (ADR-109): the approvers answer, the owner marks final and processed,
the import adds nothing twice, the mails come as digests."""

import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from coverapi import questions as Q
from coverapi.main import create_app
from fastapi.testclient import TestClient
from PIL import Image

REPO = Path(__file__).resolve().parents[3]
USERS = (
    ("rick", "Rick", "admin"),
    ("rens", "Rens de Vries", "editor"),
    ("wouter", "Wouter Bekkers", "viewer"),  # an approver with only a viewer's role
    ("vera", "Vera", "editor"),  # not an approver
    ("vic", "Vic", "viewer"),
)


def _secret(user: str) -> str:
    return f"a-long-secret-for-{user[::-1]}-9"


@pytest.fixture()
def app(tmp_path: Path) -> Any:
    a = create_app(tmp_path / "data", login_required=True)
    auth = a.state.auth
    for user, name, role in USERS:
        u = auth.add_user(user, name, role, f"{user}@example.com", False)
        auth.set_password(auth.invite(u.id), _secret(user))
    d = tmp_path / "data" / "models" / "drawing-s38"
    d.mkdir(parents=True)
    (d / "cover.json").write_text(json.dumps({"format_version": 1, "model_id": "drawing-s38"}))
    return a


def login(app: Any, user: str) -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"username": user, "password": _secret(user)})
    assert r.status_code == 200, r.text
    return c


def _add(app: Any, **extra: Any) -> int:
    spec = {
        "title": "S38: vorm?",
        "text": "Wat is er mis met de vorm?",
        "topic": "shape",
        "options": ["Trekkoord-opening toevoegen", "Laten zoals het is"],
        "models": ["drawing-s38", "drawing-s39"],
        **extra,
    }
    r = login(app, "rick").post("/api/questions", json=spec)
    assert r.status_code == 200, r.text
    return int(r.json()["id"])


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (200, 30, 30)).save(buf, "PNG")
    return buf.getvalue()


def test_who_reads_and_who_answers(app: Any) -> None:
    qid = _add(app)
    assert TestClient(app).get("/api/questions").status_code == 401
    for user in ("vic", "vera"):  # everyone logged in reads, read-only
        c = login(app, user)
        q = c.get("/api/questions").json()["items"][0]
        assert q["can_answer"] is False
        r = c.post(f"/api/questions/{qid}/answer", json={"choice": 0})
        assert r.status_code == 403
        files = [("files", ("a.png", _png(), "image/png"))]
        assert c.post(f"/api/questions/{qid}/pictures", files=files).status_code == 403
    for user in ("rens", "wouter", "rick"):  # the approvers (a viewer too) and admins
        c = login(app, user)
        assert c.get(f"/api/questions/{qid}").json()["can_answer"] is True
        r = c.post(f"/api/questions/{qid}/answer", json={"choice": 1, "comment": user})
        assert r.status_code == 200, r.text
    q = login(app, "vic").get(f"/api/questions/{qid}").json()
    assert q["status"] == "answered" and len(q["answers"]) == 3
    assert q["models"][0] == {"id": "drawing-s38", "code": "S38", "picture": False}
    # only the owner or an admin adds questions
    assert (
        login(app, "rens").post("/api/questions", json={"title": "x", "text": "y"}).status_code
        == 403
    )


def test_a_question_for_some_people_only(app: Any) -> None:
    qid = _add(app, answerers="vera")
    assert (
        login(app, "rens").post(f"/api/questions/{qid}/answer", json={"choice": 0}).status_code
        == 403
    )
    assert (
        login(app, "vera").post(f"/api/questions/{qid}/answer", json={"choice": 0}).status_code
        == 200
    )
    assert (
        login(app, "rick").post(f"/api/questions/{qid}/answer", json={"choice": 0}).status_code
        == 200
    )  # admin


def test_answering(app: Any) -> None:
    qid = _add(app)
    rens = login(app, "rens")
    url = f"/api/questions/{qid}/answer"
    assert rens.post(url, json={}).status_code == 400  # nothing chosen, nothing said
    assert rens.post(url, json={"choice": 5}).status_code == 400  # no such option
    assert rens.post(url, json={"choice": -1}).status_code == 400  # anders without words
    assert rens.get("/api/questions/count").json() == {"open": 1, "for_you": 1}
    r = rens.post(url, json={"choice": -1, "other": "Rand 2 cm hoger", "comment": "zie foto"})
    assert r.status_code == 200
    a = r.json()["answers"][0]
    assert (a["choice"], a["other"], a["name"]) == (-1, "Rand 2 cm hoger", "Rens de Vries")
    assert rens.get("/api/questions/count").json() == {"open": 0, "for_you": 0}
    # a second answer by the same person replaces the first; the first stays in the trail
    r = rens.post(url, json={"choice": 0})
    assert [x["choice"] for x in r.json()["answers"]] == [0]
    since = login(app, "rick").get("/api/questions/answers?since=0").json()["answers"]
    assert [(x["chosen"], x["replaced"]) for x in since] == [
        ("anders: Rand 2 cm hoger", True),
        ("Trekkoord-opening toevoegen", False),
    ]
    assert login(app, "rens").get("/api/questions/answers?since=0").status_code == 403
    # a comment alone is an answer too
    assert login(app, "wouter").post(url, json={"comment": "weet ik niet"}).status_code == 200


def test_the_owner_marks_final_and_processed(app: Any) -> None:
    qid = _add(app)
    rens, rick = login(app, "rens"), login(app, "rick")
    aid = rens.post(f"/api/questions/{qid}/answer", json={"choice": 0}).json()["answers"][0]["id"]
    assert rens.post(f"/api/questions/{qid}/final", json={"answer_id": aid}).status_code == 403
    r = rick.post(f"/api/questions/{qid}/final", json={"answer_id": aid})
    assert r.status_code == 200 and r.json()["final_answer"] == aid
    assert rick.post(f"/api/questions/{qid}/final", json={"answer_id": 999}).status_code == 404
    assert rens.post(f"/api/questions/{qid}/done", json={"note": "x"}).status_code == 403
    assert rick.post(f"/api/questions/{qid}/done", json={"note": " "}).status_code == 400
    r = rick.post(f"/api/questions/{qid}/done", json={"note": "Trekkoord toegevoegd op S38/S39"})
    q = r.json()
    assert q["status"] == "processed" and q["processed"]["note"].startswith("Trekkoord")
    assert q["processed"]["by"] == "Rick"
    seen = rens.get(f"/api/questions/{qid}").json()
    assert seen["processed"]["note"] and seen["can_answer"] is False
    assert rens.post(f"/api/questions/{qid}/answer", json={"choice": 1}).status_code == 409
    assert rick.post(f"/api/questions/{qid}/reopen").json()["status"] == "answered"
    # every step is in the audit trail
    import sqlite3

    with sqlite3.connect(app.state.auth.path) as db:
        acts = [
            r[0]
            for r in db.execute(
                "SELECT action FROM question_log WHERE question_id=? ORDER BY id", (qid,)
            )
        ]
    assert acts == ["add", "answer", "final", "processed", "reopen"]


def test_pictures_with_an_answer(app: Any, tmp_path: Path) -> None:
    qid = _add(app)
    rens = login(app, "rens")
    files = [("files", ("shot.png", _png(), "image/png"))]
    r = rens.post(f"/api/questions/{qid}/pictures", files=files)
    assert r.status_code == 200, r.text
    name = r.json()["pictures"][0]
    assert (tmp_path / "data" / "questions" / str(qid) / name).is_file()
    bad = rens.post(f"/api/questions/{qid}/answer", json={"choice": 0, "pictures": ["x.png"]})
    assert bad.status_code == 400
    r = rens.post(f"/api/questions/{qid}/answer", json={"choice": 0, "pictures": [name]})
    assert r.json()["answers"][0]["pictures"] == [name]
    got = login(app, "vic").get(f"/api/questions/{qid}/pictures/{name}")
    assert got.status_code == 200 and got.headers["content-type"] == "image/png"
    assert login(app, "vic").get(f"/api/questions/{qid}/pictures/..%2Fapp.db").status_code == 404
    svg = [("files", ("a.svg", b"<svg/>", "image/svg+xml"))]
    assert rens.post(f"/api/questions/{qid}/pictures", files=svg).status_code == 400


def test_digests_not_a_mail_per_click(app: Any) -> None:
    auth = app.state.auth
    from coverengine.params import Registry

    params = Registry.load(None).resolve()
    mails: list[tuple[str, str, str]] = []

    def send(to: str, subject: str, text: str) -> None:
        mails.append((to, subject, text))

    q1, q2 = _add(app), _add(app, title="Tweede vraag")
    Q.question_mails(auth, params, "https://studio", send)
    to = sorted(m[0] for m in mails)
    assert to == ["rens@example.com", "rick@example.com", "wouter@example.com"]  # one each
    assert "/#/questions/" in mails[0][2] and "Tweede vraag" in mails[0][2]
    mails.clear()
    _add(app, title="Derde")
    login(app, "rens").post(f"/api/questions/{q1}/answer", json={"choice": 0})
    login(app, "wouter").post(f"/api/questions/{q2}/answer", json={"choice": 1})
    Q.question_mails(auth, params, "https://studio", send)
    # the new question waits for tomorrow's digest; the answers go to Rick in one mail
    assert [m[0] for m in mails] == ["rick@example.com"]
    assert "2 new answers" in mails[0][1]
    mails.clear()
    login(app, "rens").post(f"/api/questions/{q2}/answer", json={"choice": 0})
    Q.question_mails(auth, params, "https://studio", send)
    assert mails == []  # within answer_digest_hours: no second mail


def _seed_results(root: Path) -> str:
    rows_a = [
        {
            "model": "drawing-c1",
            "status": "doubt",
            "question_nl": "Vents op de binnenwanden?",
            "options_nl": ["a) ja (features.vent_inner_walls: true)", "b) nee"],
        },
        {
            "model": "drawing-c2",
            "status": "doubt",
            "question_nl": "Vents op de binnenwanden?",
            "options_nl": ["a) ja (features.vent_inner_walls: true)", "b) nee"],
        },
        {
            "model": "drawing-r1",
            "status": "doubt",
            "question_nl": "R1: vents bovenin?",
            "options_nl": ["bovenin", "onderin"],
            "compare": "out/rejections/A/compare/r1.png",
        },
        {"model": "suns-x", "status": "fixed", "answer_nl": "klaar"},
    ]
    rows_g = [
        {
            "model": "drawing-s38",
            "status": "doubt",
            "question_nl": "S38/S39: wat is mis?",
            "options_nl": ["opening", "laten"],
            "answer_nl": "vorm klopt",
        },
        {
            "model": "drawing-s39",
            "status": "doubt",
            "question_nl": "S39: zelfde vraag als S38.",
            "options_nl": ["zoals S38", "vragen"],
        },
    ]
    for group, rows in (("A", rows_a), ("G", rows_g)):
        d = root / "wt" / "out" / "rejections" / group
        d.mkdir(parents=True)
        (d / "results.json").write_text(json.dumps(rows))
    (root / "wt" / "out" / "rejections" / "A" / "compare").mkdir()
    (root / "wt" / "out" / "rejections" / "A" / "compare" / "r1.png").write_bytes(_png())
    return str(root / "wt" / "out" / "rejections" / "*" / "results.json")


def _cli() -> Any:
    spec = importlib.util.spec_from_file_location(
        "questions_cli", REPO / "scripts" / "questions.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["questions_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_the_import_adds_nothing_twice(
    app: Any, tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path / "data"))
    cli = _cli()
    import questions_seed as seed

    pattern = _seed_results(tmp_path)
    assert cli.main(["import", "--results", pattern]) == 0
    items = login(app, "vic").get("/api/questions").json()["items"]
    n = len(seed.FROM_QUESTIONS_MD) + 2  # the inner-wall vents (answered) left out; S39 joins S38
    assert len(items) == n
    s38 = next(q for q in items if q["key"] == "doubt:drawing-s38")
    assert [m["id"] for m in s38["models"]] == ["drawing-s38", "drawing-s39"]
    assert s38["text"] == "S38/S39: wat is mis?" and "vorm klopt" in s38["context"]
    r1 = next(q for q in items if q["key"] == "doubt:drawing-r1")
    assert len(r1["pictures"]) == 1 and [m["id"] for m in r1["models"]] == [
        "drawing-r1",
        "drawing-r2",
        "drawing-r3",
    ]
    assert not any("binnenwand" in q["text"] for q in items)
    assert all(2 <= len(q["options"]) <= 5 for q in items)
    assert cli.main(["import", "--results", pattern]) == 0
    assert len(login(app, "vic").get("/api/questions").json()["items"]) == n
    assert f"0 added, {n} there already" in capsys.readouterr().out


def test_the_cli_fetches_new_answers_and_marks_done(
    app: Any, tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    monkeypatch.setenv("COVER_DATA_DIR", str(tmp_path / "data"))
    cli = _cli()
    qid = _add(app)
    login(app, "rens").post(f"/api/questions/{qid}/answer", json={"choice": 1, "comment": "ok"})
    capsys.readouterr()
    assert cli.main(["new", "--json"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert [a["chosen"] for a in got["answers"]] == ["Laten zoals het is"]
    assert cli.main(["ack"]) == 0
    capsys.readouterr()
    assert cli.main(["new"]) == 0
    assert capsys.readouterr().out.startswith("0 answers since")
    assert cli.main(["done", str(qid), "Gelaten zoals het is"]) == 0
    q = login(app, "rens").get(f"/api/questions/{qid}").json()
    assert q["status"] == "processed" and q["processed"]["note"] == "Gelaten zoals het is"
    assert cli.main(["done", "999", "x"]) == 1
