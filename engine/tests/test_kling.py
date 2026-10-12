"""scripts/film/kling.py with a mocked HTTP layer: no real calls, nothing paid (ADR-124)."""

import base64
import hashlib
import hmac
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from coverengine.params.registry import repo_root

KEY = "sk-test-SECRET-api-key-123"
AK, SK = "ak-test-ACCESS", "sk-test-SECRET-signing"


def load() -> Any:
    path = repo_root() / "scripts" / "film" / "kling.py"
    spec = importlib.util.spec_from_file_location("kling", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["kling"] = mod  # dataclasses look their module up
    spec.loader.exec_module(mod)
    return mod


k = load()


class FakeHttp:
    """Answers like Kling; records every call; refuses everything when `closed`."""

    def __init__(self, statuses: list[str] | None = None, closed: bool = False, legacy=False):
        self.calls: list[tuple[str, str, dict, Any]] = []
        self.statuses = list(statuses or ["succeeded"])
        self.closed = closed
        self.legacy = legacy
        self.downloads: list[str] = []
        self.n = 0

    def json(self, method, url, headers, body=None):
        if self.closed:
            raise AssertionError(f"no call expected, got {method} {url}")
        self.calls.append((method, url, headers, body))
        if method == "POST":
            self.n += 1
            if self.legacy:
                return {"code": 0, "data": {"task_id": f"T{self.n}", "task_status": "submitted"}}
            return {"code": 0, "data": {"id": f"T{self.n}", "status": "submitted"}}
        st = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        if self.legacy:
            tid = url.rsplit("/", 1)[1]
            res = {"videos": [{"url": f"https://cdn.example/{tid}.mp4"}]}
            return {
                "code": 0,
                "data": {
                    "task_id": tid,
                    "task_status": "succeed" if st == "succeeded" else st,
                    "task_result": res if st == "succeeded" else {},
                },
            }
        ids = url.split("task_ids=")[1].split(",")
        return {"code": 0, "data": [
            {"id": t, "status": st,
             "outputs": [{"type": "video", "url": f"https://cdn.example/{t}.mp4"}]
             if st == "succeeded" else [],
             "billing": [{"charge_type": "unit", "amount": "4"}] if st == "succeeded" else []}
            for t in ids]}  # fmt: skip

    def download(self, url, path):
        self.downloads.append(url)
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        return path.stat().st_size


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    frames = tmp_path / "frames"
    frames.mkdir()
    for name in ("fit-start", "fit-end", "fit-mid", "rain-start", "sew-start", "vent-start",
                 "cut-start", "villa-start"):  # fmt: skip
        for asp in ("4x5", "16x9"):
            (frames / f"{name}-{asp}.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
    data = tmp_path / "data"
    monkeypatch.setenv("COVER_DATA_DIR", str(data))
    for v in ("KLING_API_KEY", "KLING_ACCESS_KEY", "KLING_SECRET_KEY"):
        monkeypatch.delenv(v, raising=False)
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")
    return {"frames": frames, "out": tmp_path / "out", "data": data, "env": empty_env}


def args(w: dict[str, Path], *rest: str) -> list[str]:
    return ["--out", str(w["out"]), "--frames", str(w["frames"]), "--env-file", str(w["env"]),
            *rest]  # fmt: skip


def test_jwt_is_kling_s_token() -> None:
    tok = k.jwt_hs256(AK, SK, now=1_000_000)
    head, body, sig = tok.split(".")

    def dec(s: str) -> dict:
        return json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))

    assert dec(head) == {"alg": "HS256", "typ": "JWT"}
    assert dec(body) == {"iss": AK, "exp": 1_001_800, "nbf": 999_995}
    want = hmac.new(SK.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    assert base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4)) == want


def test_auth_from_env_file_and_hidden(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text(f"# x\nKLING_ACCESS_KEY={AK}\nexport KLING_SECRET_KEY='{SK}'\nOTHER=1\n")
    a = k.Auth.load({}, f)
    assert a.kind == "jwt" and a.api() == "legacy"
    assert AK not in repr(a) and SK not in repr(a)
    assert a.header().startswith("Bearer ") and len(a.header().split(".")) == 3
    b = k.Auth.load({"KLING_API_KEY": KEY}, f)  # the API key wins
    assert b.kind == "api_key" and b.api() == "new" and b.header() == f"Bearer {KEY}"
    assert k.Auth.load({}, tmp_path / "missing.env").kind == "none"


def test_estimate() -> None:
    e = k.estimate("kling-3.0", "1080p", 5, usd_eur=1.0)
    assert e == {"units": 4.0, "usd": 0.56, "eur": 0.56}
    assert k.estimate("kling-2.5-turbo", "720p", 5, usd_eur=1.0)["units"] == 1.5


def test_dry_run_sends_nothing_and_prints_no_key(world, capsys) -> None:
    http = FakeHttp(closed=True)
    rc = k.main(args(world, "--dry-run", "submit", "fit"), http=http,
                env={"KLING_API_KEY": KEY})  # fmt: skip
    out = capsys.readouterr().out
    assert rc == 0
    assert KEY not in out and "Bearer ***" in out
    assert "/image-to-video/kling-3.0" in out and "last_frame" in out
    assert "Avoid: hands" in out
    assert not world["out"].exists()  # nothing written, not even the ledger
    assert not world["data"].exists()


def test_dry_run_works_without_a_key(world, capsys) -> None:
    rc = k.main(args(world, "run", "--shots", "rain,villa", "--dry-run"), http=FakeHttp(
        closed=True), env={})  # fmt: skip
    assert rc == 0
    out = capsys.readouterr().out
    assert "(no key yet)" in out and "villa-start-16x9.png" in out


def test_submit_new_api(world, capsys) -> None:
    http = FakeHttp()
    rc = k.main(args(world, "submit", "fit"), http=http, env={"KLING_API_KEY": KEY})
    assert rc == 0
    (method, url, headers, body), = http.calls  # fmt: skip
    assert (method, url) == ("POST", k.BASE + "/image-to-video/kling-3.0")
    assert headers["Authorization"] == f"Bearer {KEY}"
    types = [c["type"] for c in body["contents"]]
    assert types == ["prompt", "first_frame", "last_frame"]
    assert body["contents"][1]["url"] == base64.b64encode(
        (world["frames"] / "fit-start-4x5.png").read_bytes()).decode()  # fmt: skip
    assert body["settings"] == {"resolution": "1080p", "duration": 5, "multi_shot": False,
                                "audio": "off"}  # fmt: skip
    rec = json.loads((world["out"] / "fit" / "1.json").read_text())
    assert rec["task"] == "T1" and rec["media_key"] == "fit" and rec["prompt"]
    led = [json.loads(x) for x in (world["out"] / "ledger.jsonl").read_text().splitlines()]
    assert led[0]["event"] == "submit" and led[0]["units"] == 4.0
    studio = list((world["data"] / "usage").glob("ai-*.jsonl"))
    assert studio and "kling fit 4x5 #1" in studio[0].read_text()
    assert KEY not in capsys.readouterr().out


def test_budget_refuses_before_sending(world, capsys) -> None:
    http = FakeHttp(closed=True)
    rc = k.main(args(world, "--budget-eur", "0.4", "submit", "sew"), http=http,
                env={"KLING_API_KEY": KEY})  # fmt: skip
    assert rc == 2
    assert "refused" in capsys.readouterr().err
    assert not (world["out"] / "sew").exists()
    # a run checks the whole list first: 3 clips at ~€0.53 do not fit in €1.2
    rc = k.main(args(world, "--budget-eur", "1.2", "run", "--shots", "sew,vent,cut"),
                http=http, env={"KLING_API_KEY": KEY})  # fmt: skip
    assert rc == 2 and http.calls == []


def test_budget_counts_what_was_spent(world) -> None:
    env = {"KLING_API_KEY": KEY}
    assert k.main(args(world, "--budget-eur", "1.1", "submit", "sew"), http=FakeHttp(),
                  env=env) == 0  # fmt: skip
    http = FakeHttp()
    assert k.main(args(world, "--budget-eur", "1.1", "submit", "vent"), http=http,
                  env=env) == 0  # fmt: skip
    http = FakeHttp(closed=True)
    assert k.main(args(world, "--budget-eur", "1.1", "submit", "cut"), http=http, env=env) == 2


def test_run_polls_downloads_and_bills(world, capsys) -> None:
    http = FakeHttp(statuses=["processing", "processing", "succeeded"])
    env = {"KLING_API_KEY": KEY}
    a = args(world, "--no-studio-ledger", "run", "--shots", "sew,vent")
    ctx_calls: list[float] = []
    orig = k.run

    def quick(ctx, jobs, **kw):
        return orig(ctx, jobs, poll_s=0.0, sleep=ctx_calls.append)

    k.run = quick
    try:
        assert k.main(a, http=http, env=env) == 0
    finally:
        k.run = orig
    assert (world["out"] / "sew" / "1.mp4").is_file() and (
        world["out"] / "vent" / "1.mp4"
    ).is_file()
    assert sorted(http.downloads) == ["https://cdn.example/T1.mp4", "https://cdn.example/T2.mp4"]
    rec = json.loads((world["out"] / "sew" / "1.json").read_text())
    assert rec["status"] == "succeeded" and rec["billed"]["units"] == 4.0
    rows = [json.loads(x) for x in (world["out"] / "ledger.jsonl").read_text().splitlines()]
    assert [r["event"] for r in rows].count("billed") == 2
    assert not (world["data"] / "usage").exists()  # --no-studio-ledger
    # status afterwards asks nothing more (all done) and bills nothing twice
    http2 = FakeHttp(closed=True)
    assert k.main(args(world, "status"), http=http2, env=env) == 0
    rows2 = (world["out"] / "ledger.jsonl").read_text().splitlines()
    assert len(rows2) == len(rows)
    assert KEY not in capsys.readouterr().out


def test_legacy_api_with_jwt(world, capsys) -> None:
    http = FakeHttp(legacy=True)
    env = {"KLING_ACCESS_KEY": AK, "KLING_SECRET_KEY": SK}
    assert k.main(args(world, "submit", "fit", "--model", "kling-2.5-turbo"), http=http,
                  env=env) == 0  # fmt: skip
    method, url, headers, body = http.calls[0]
    assert url == k.BASE + "/v1/videos/image2video"
    assert body["model_name"] == "kling-v2-5-turbo" and body["mode"] == "pro"
    assert body["duration"] == "5" and body["image_tail"] and "hands" in body["negative_prompt"]
    assert "Avoid:" not in body["prompt"]
    tok = headers["Authorization"].removeprefix("Bearer ")
    assert len(tok.split(".")) == 3 and SK not in tok
    assert k.main(args(world, "fetch"), http=http, env=env) == 0
    assert http.calls[-1][1] == k.BASE + "/v1/videos/image2video/T1"
    assert (world["out"] / "fit" / "1.mp4").is_file()
    out = capsys.readouterr().out
    assert AK not in out and SK not in out


def test_last_frame_rules(world) -> None:
    rc = k.main(args(world, "--dry-run", "submit", "fit", "--model", "kling-2.5-turbo",
                     "--mode", "std"), http=FakeHttp(closed=True), env={})  # fmt: skip
    assert rc == 2  # first + last frame on 2.5 Turbo only at 1080p
    rc = k.main(args(world, "--dry-run", "submit", "fit", "--model", "kling-3.0-turbo"),
                http=FakeHttp(closed=True), env={})  # fmt: skip
    assert rc == 2  # 3.0 Turbo takes no last frame


def test_kling_error_is_reported_not_raised(world, capsys) -> None:
    class Refusing(FakeHttp):
        def json(self, method, url, headers, body=None):
            return {"code": 1102, "message": "Resource pack exhausted"}

    rc = k.main(args(world, "submit", "sew"), http=Refusing(), env={"KLING_API_KEY": KEY})
    assert rc == 2 and "1102" in capsys.readouterr().err
    rec = json.loads((world["out"] / "sew" / "1.json").read_text())
    assert rec["status"] == "not sent"
    assert not (world["out"] / "ledger.jsonl").exists()  # nothing billed for a refused call


def test_shots_file_and_the_plan_agree() -> None:
    spec = k.load_shots()
    plan = (repo_root() / "docs" / "plans" / "kling-shots.md").read_text()
    plan_flat = " ".join(plan.split())
    for name, s in spec["shots"].items():
        assert s["media_key"] in {"cut", "sew", "vent", "fit", "runoff", "range", "villa"}
        assert "{aspect}" in s["first"]
        assert " ".join(s["prompt"].split()) in plan_flat, f"{name}'s prompt not in the plan"
    assert " ".join(spec["defaults"]["negative"].split()) in plan_flat
