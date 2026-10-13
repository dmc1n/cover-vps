"""scripts/film/veo.py with a fake HTTP layer: no real calls, nothing paid (ADR-127)."""

import base64
import importlib.util
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from coverengine.params.registry import repo_root
from PIL import Image

KEY = "AIza-test-SECRET-gemini-key-123"


def load() -> Any:
    path = repo_root() / "scripts" / "film" / "veo.py"
    spec = importlib.util.spec_from_file_location("veo", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["veo"] = mod  # dataclasses look their module up
    spec.loader.exec_module(mod)
    return mod


v = load()


def png(w: int = 64, h: int = 36, colour=(200, 180, 140)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), colour).save(buf, "PNG")
    return buf.getvalue()


class FakeHttp:
    """Answers like Google; records every call; refuses everything when `closed`."""

    def __init__(self, polls: int = 1, closed: bool = False, fail: bool = False) -> None:
        self.calls: list[tuple[str, str, dict, Any]] = []
        self.polls = polls
        self.closed = closed
        self.fail = fail
        self.downloads: list[tuple[str, dict]] = []
        self.n = 0

    def json(self, method, url, headers, body=None):
        if self.closed:
            raise AssertionError(f"no call expected, got {method} {url}")
        self.calls.append((method, url, headers, body))
        if url.endswith(":generateContent"):
            data = base64.b64encode(png(275, 154)).decode()
            return {"candidates": [{"content": {"parts": [{"inlineData": {
                "mimeType": "image/png", "data": data}}]}}],
                "usageMetadata": {"candidatesTokenCount": 1290}}  # fmt: skip
        if url.endswith(":predictLongRunning"):
            self.n += 1
            return {"name": f"models/veo/operations/op{self.n}"}
        self.polls -= 1
        if self.polls > 0:
            return {"name": url.rsplit("/", 1)[1], "done": False}
        if self.fail:
            return {"done": True, "error": {"code": 3, "message": "blocked"}}
        return {"done": True, "response": {"generateVideoResponse": {"generatedSamples": [
            {"video": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/x:download"}}
        ]}}}  # fmt: skip

    def download(self, url, headers, path):
        self.downloads.append((url, headers))
        path.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        return path.stat().st_size

    def get(self, url):
        self.calls.append(("GET", url, {}, None))
        return png(400, 300)


SPEC = {
    "defaults": {"model": "veo-3.1-fast-generate-preview", "image_model": "gemini-3-pro-image",
                 "duration": 8, "resolution": "1080p", "aspect": "16:9",
                 "negative": "hands, text"},
    "frames": {"sofa-end": {"photo": "sofa-start.png", "refs": ["refs/cover.png"],
                            "prompt": "Put our cover on the sofa."}},
    "shots": {
        "fit": {"media_key": "fit", "first": "sofa-start.png", "last": "sofa-end.png",
                "prompt": "A cover settles."},
        "rain": {"media_key": "runoff", "first": "sofa-end.png", "prompt": "Rain."},
        "villa": {"media_key": "villa", "first": "sofa-end.png", "prompt": "Golden hour."},
    },
}  # fmt: skip


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    frames = tmp_path / "out" / "frames"
    (frames / "refs").mkdir(parents=True)
    for name in ("sofa-start.png", "sofa-end.png", "refs/cover.png"):
        (frames / name).write_bytes(png())
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(SPEC))
    data = tmp_path / "data"
    monkeypatch.setenv("COVER_DATA_DIR", str(data))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(v, "POLL_S", 0.0)
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")
    return {"out": tmp_path / "out", "frames": frames, "spec": spec, "data": data,
            "env": empty_env}  # fmt: skip


def args(w: dict[str, Path], *rest: str) -> list[str]:
    return ["--out", str(w["out"]), "--spec", str(w["spec"]), "--env-file", str(w["env"]),
            *rest]  # fmt: skip


def ledger(w: dict[str, Path]) -> list[dict]:
    p = w["out"] / "ledger.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.is_file() else []


def test_key_from_env_file(tmp_path: Path) -> None:
    f = tmp_path / ".env"
    f.write_text(f"# x\nexport GEMINI_API_KEY='{KEY}'\nOTHER=1\n")
    assert v.load_key({}, f) == KEY
    assert v.load_key({"GEMINI_API_KEY": "env-wins"}, f) == "env-wins"
    assert v.load_key({}, tmp_path / "missing.env") == ""


def test_estimates() -> None:
    assert v.video_estimate("veo-3.1-fast-generate-preview", "1080p", 8, 1.0) == {
        "usd": 1.2, "eur": 1.2}  # fmt: skip
    assert v.video_estimate("veo-3.1-generate-preview", "1080p", 8, 1.0)["usd"] == 3.2
    e = v.image_estimate("gemini-3-pro-image", 2, 1.0)
    assert e["usd"] == pytest.approx(0.1362)
    b = v.image_billed({"candidatesTokenCount": 1120}, 2, 1.0)
    assert b is not None and b["usd"] == pytest.approx(0.1366, abs=1e-4)
    assert v.image_billed({}, 2) is None
    with pytest.raises(v.VeoError):
        v.video_estimate("veo-9", "1080p", 8)


def test_crop_is_16x9_full_hd() -> None:
    out = Image.open(io.BytesIO(v.crop_16x9(png(400, 300), (0.5, 0.2))))
    assert out.size == (1920, 1080)
    out = Image.open(io.BytesIO(v.fit_frame(png(1376, 768))))
    assert out.size == (1920, 1080)


def test_dry_run_sends_nothing_and_prints_no_key(world, capsys) -> None:
    http = FakeHttp(closed=True)
    env = {"GEMINI_API_KEY": KEY}
    assert v.main(args(world, "--dry-run", "submit", "fit"), http=http, env=env) == 0
    assert v.main(args(world, "frame", "sofa-end", "--dry-run"), http=http, env=env) == 0
    out = capsys.readouterr().out
    assert KEY not in out and '"x-goog-api-key": "***"' in out
    assert ":predictLongRunning" in out and "lastFrame" in out and ":generateContent" in out
    assert not (world["out"] / "ledger.jsonl").exists()
    assert not (world["out"] / "fit").exists()
    assert not world["data"].exists()


def test_dry_run_works_without_a_key(world, capsys) -> None:
    rc = v.main(args(world, "run", "--shots", "rain,villa", "--dry-run"),
                http=FakeHttp(closed=True), env={})  # fmt: skip
    assert rc == 0
    out = capsys.readouterr().out
    assert "(no key yet)" in out and "lastFrame" not in out


def test_frame_writes_picture_ledgers_and_source(world, capsys) -> None:
    http = FakeHttp()
    rc = v.main(args(world, "frame", "sofa-end"), http=http, env={"GEMINI_API_KEY": KEY})
    assert rc == 0
    (method, url, headers, body), = http.calls  # fmt: skip
    assert url == v.BASE + "/models/gemini-3-pro-image:generateContent"
    assert headers["x-goog-api-key"] == KEY
    parts = body["contents"][0]["parts"]
    assert [("inlineData" in p) for p in parts] == [True, True, False]
    assert parts[-1]["text"] == "Put our cover on the sofa."
    assert body["generationConfig"] == {"responseModalities": ["IMAGE"],
                                        "imageConfig": {"aspectRatio": "16:9"}}  # fmt: skip
    out = world["frames"] / "sofa-end-v1.png"
    assert Image.open(out).size == (1920, 1080)
    assert (world["frames"] / "sofa-end-v1-raw.png").is_file()
    src = json.loads((world["frames"] / "sources.json").read_text())
    assert src["sofa-end-v1.png"]["photo"] == "sofa-start.png"
    rows = ledger(world)
    assert [r["event"] for r in rows] == ["call", "billed"]
    assert rows[1]["tokens_out"] == 1290
    studio = list((world["data"] / "usage").glob("ai-*.jsonl"))
    assert studio and "veo frame sofa-end v1" in studio[0].read_text()
    # the second take is v2, the first stays
    assert v.main(args(world, "frame", "sofa-end"), http=FakeHttp(),
                  env={"GEMINI_API_KEY": KEY}) == 0  # fmt: skip
    assert (world["frames"] / "sofa-end-v2.png").is_file() and out.is_file()
    assert KEY not in capsys.readouterr().out


def test_run_submits_polls_and_downloads_with_the_key_header(world, capsys) -> None:
    http = FakeHttp(polls=2)
    rc = v.main(args(world, "run", "--shots", "fit"), http=http, env={"GEMINI_API_KEY": KEY})
    assert rc == 0
    post = http.calls[0]
    assert post[1] == v.BASE + "/models/veo-3.1-fast-generate-preview:predictLongRunning"
    inst, params = post[3]["instances"][0], post[3]["parameters"]
    assert inst["prompt"] == "A cover settles."
    assert inst["image"]["mimeType"] == "image/png"
    assert inst["image"]["bytesBase64Encoded"] == base64.b64encode(
        (world["frames"] / "sofa-start.png").read_bytes()).decode()  # fmt: skip
    assert "lastFrame" in inst
    assert params == {"aspectRatio": "16:9", "durationSeconds": 8, "resolution": "1080p",
                      "negativePrompt": "hands, text"}  # fmt: skip
    assert [c[1].rsplit("/", 1)[1] for c in http.calls[1:]] == ["op1", "op1"]
    (url, headers), = http.downloads  # fmt: skip
    assert headers == {"x-goog-api-key": KEY}
    rec = json.loads((world["out"] / "fit" / "1.json").read_text())
    assert rec["status"] == "succeeded" and rec["file"].endswith("fit/1.mp4")
    assert rec["media_key"] == "fit" and rec["estimate"]["eur"] > 0
    assert (world["out"] / "fit" / "1.mp4").is_file()
    assert ledger(world)[0]["id"] == "video:fit#1"
    assert KEY not in capsys.readouterr().out


def test_a_shot_without_last_frame_sends_none(world) -> None:
    http = FakeHttp()
    assert v.main(args(world, "submit", "rain"), http=http, env={"GEMINI_API_KEY": KEY}) == 0
    assert "lastFrame" not in http.calls[0][3]["instances"][0]
    rec = json.loads((world["out"] / "rain" / "1.json").read_text())
    assert rec["status"] == "running" and rec["operation"] == "models/veo/operations/op1"
    # fetch picks it up later
    assert v.main(args(world, "fetch"), http=http, env={"GEMINI_API_KEY": KEY}) == 0
    rec = json.loads((world["out"] / "rain" / "1.json").read_text())
    assert rec["status"] == "succeeded" and (world["out"] / "rain" / "1.mp4").is_file()


def test_a_failed_operation_is_recorded(world) -> None:
    http = FakeHttp(fail=True)
    assert v.main(args(world, "run", "--shots", "rain"), http=http,
                  env={"GEMINI_API_KEY": KEY}) == 0  # fmt: skip
    rec = json.loads((world["out"] / "rain" / "1.json").read_text())
    assert rec["status"] == "failed" and rec["message"] == "blocked"
    assert http.downloads == []


def test_budget_refuses_before_sending(world, capsys) -> None:
    env = {"GEMINI_API_KEY": KEY}
    http = FakeHttp(closed=True)
    assert v.main(args(world, "--budget-eur", "1.0", "submit", "fit"), http=http, env=env) == 2
    assert "refused" in capsys.readouterr().err
    assert not (world["out"] / "fit").exists() and ledger(world) == []
    # a run checks the whole list first: 2 clips at ~EUR 1.14 do not fit in EUR 2
    assert v.main(args(world, "--budget-eur", "2", "run", "--shots", "rain,villa"), http=http,
                  env=env) == 2  # fmt: skip
    assert http.calls == []


def test_budget_counts_frames_and_clips(world) -> None:
    env = {"GEMINI_API_KEY": KEY}
    a = args(world, "--budget-eur", "1.35")
    assert v.main([*a, "frame", "sofa-end"], http=FakeHttp(), env=env) == 0
    assert v.main([*a, "submit", "rain"], http=FakeHttp(), env=env) == 0
    spent = v.Ledger(world["out"] / "ledger.jsonl").spent_eur()
    assert 1.2 < spent < 1.35  # the frame's bill + the clip's estimate
    assert v.main([*a, "frame", "sofa-end"], http=FakeHttp(closed=True), env=env) == 2


def test_no_key_is_refused_without_a_call(world, capsys) -> None:
    assert v.main(args(world, "submit", "fit"), http=FakeHttp(closed=True), env={}) == 2
    assert "GEMINI_API_KEY" in capsys.readouterr().err


def test_veo_rules() -> None:
    ctx_spec = {"defaults": {}, "shots": {"x": {"first": "a.png", "prompt": "p",
                                                "duration": 6}}}  # fmt: skip
    ctx = v.Ctx(out=Path("o"), frames=Path("f"), budget_eur=1, usd_eur=1, studio_ledger=False,
                dry_run=True, key="", http=FakeHttp(closed=True), spec=ctx_spec)  # fmt: skip
    with pytest.raises(v.VeoError, match="1080p only at 8"):
        v.make_job(ctx, "x")


def test_photo_crops_and_notes_the_source(world) -> None:
    url = "https://hello-suns.com/app/uploads/2025/01/Some-SUNS-Mood.jpg"
    http = FakeHttp()
    assert v.main(args(world, "photo", url, "--name", "x-start", "--center", "0.5,0.4"),
                  http=http, env={}) == 0  # fmt: skip
    assert Image.open(world["frames"] / "x-start.png").size == (1920, 1080)
    assert (world["frames"] / "originals" / "Some-SUNS-Mood.jpg").is_file()
    src = json.loads((world["frames"] / "sources.json").read_text())
    assert src["x-start.png"]["url"] == url
    assert ledger(world) == []  # a photo download costs nothing


def test_the_repository_spec_is_sound() -> None:
    spec = v.load_spec()
    assert spec["defaults"]["model"] in v.VIDEO_USD_S
    assert spec["defaults"]["image_model"] in v.IMAGE_USD
    for name, s in spec["shots"].items():
        assert s["prompt"] and s["first"] and s["media_key"], name
    for name, f in spec["frames"].items():
        assert f["photo"] and f["prompt"], name
