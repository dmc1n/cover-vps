"""The website's clips from real SUNS photos with Google's Gemini image model and Veo (ADR-127).

The recipe the owner approved on 13 October 2026 ("dit is stukken beter"):

1. the start frame is a real SUNS product photo (hello-suns.com), cropped to 16:9 1920 x 1080
   (`photo`);
2. the end frame is that photo with OUR cover on the furniture, made by gemini-3-pro-image from
   the photo plus our cover's render as the shape reference, everything else kept (`frame`);
3. Veo 3.1 Fast animates between them, or from the covered frame alone (`submit`, `run`).

    uv run python scripts/film/veo.py photo URL --name NAME [--center 0.5,0.55] [--zoom 1.0]
    uv run python scripts/film/veo.py frame NAME [--dry-run]          an end frame from the spec
    uv run python scripts/film/veo.py submit SHOT [--dry-run]         one Veo clip from the spec
    uv run python scripts/film/veo.py fetch [SHOT]                    poll, download finished clips
    uv run python scripts/film/veo.py run --shots a,b [--dry-run]     submit, wait, download
    uv run python scripts/film/veo.py cost                            prices, spent, the cap

The frames, shots and prompts are in veo_shots.json (docs/plans/veo-shots.md). Frames land in
out/veo/frames/ with sources.json (each SUNS photo's file name and URL: the photos belong to
the furniture brand, the owner's partner). Clips land in out/veo/<shot>/<n>.mp4 with <n>.json
beside it (prompt, parameters, operation, cost).

Money: every paid call is written to out/veo/ledger.jsonl and the studio's AI ledger (spend.py;
`--no-studio-ledger` leaves that out) BEFORE it is sent, at an estimate that errs high; a call
whose estimate would take the ledger past `--budget-eur` (default 30) is refused before anything
is sent. A Gemini image answer's own token count replaces its estimate ("billed").

Prices (ai.google.dev/gemini-api/docs/pricing, read 13 Oct 2026): Veo 3.1 Fast $0.10/s at 720p,
$0.12/s at 1080p, $0.30/s at 4K (audio included; we strip it); Veo 3.1 $0.40/s; Gemini 3 Pro
Image $0.134 an output image at 1K/2K ($120 per million output tokens), $0.0011 an input image.
The ledger uses $0.15/s for Veo Fast 1080p (the figure in the owner's brief, above the list price)
and $1 = EUR 0.95, so the cap errs safe.

Key: GEMINI_API_KEY (deploy/.env or the environment), sent only as the x-goog-api-key header,
never printed.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SPEC_FILE = Path(__file__).resolve().parent / "veo_shots.json"
BASE = "https://generativelanguage.googleapis.com/v1beta"
USD_EUR = 0.95  # deliberately high (about 0.86 in Oct 2026): the cap errs safe
# USD a second of video, by model and resolution; deliberately at or above the list price
VIDEO_USD_S = {
    "veo-3.1-fast-generate-preview": {"720p": 0.15, "1080p": 0.15, "4k": 0.30},
    "veo-3.1-generate-preview": {"720p": 0.40, "1080p": 0.40, "4k": 0.60},
}
IMAGE_USD = {"gemini-3-pro-image": 0.134, "gemini-3-pro-image-preview": 0.134}
IMAGE_IN_USD = 0.0011  # an input picture
IMAGE_OUT_USD_PER_TOKEN = 120 / 1_000_000
FRAME_SIZE = (1920, 1080)
POLL_S = 15.0
WAIT_S = 1800.0
UA = "cover-studio-film/1.0"


class VeoError(RuntimeError):
    pass


# ---- keys -----------------------------------------------------------------------------------
def read_env(path: Path) -> dict[str, str]:
    """KEY=VALUE lines of an .env file (quotes stripped); missing file: nothing."""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip().removeprefix("export ").strip()] = v.strip().strip("'\"")
    return out


def load_key(env: dict[str, str] | None = None, env_file: Path | None = None) -> str:
    src = read_env(env_file or ROOT / "deploy" / ".env")
    e = env if env is not None else dict(os.environ)
    return e.get("GEMINI_API_KEY") or src.get("GEMINI_API_KEY", "")


# ---- HTTP (the one place that talks to the network; tests replace it) -------------------------
class Http:
    def __init__(self, timeout: float = 300.0) -> None:
        self.timeout = timeout

    def json(self, method: str, url: str, headers: dict[str, str], body: Any = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            text = e.read().decode(errors="replace")
            try:
                msg = json.loads(text).get("error", {}).get("message", "")
            except json.JSONDecodeError:
                msg = text[:300]
            raise VeoError(f"HTTP {e.code} from Google: {msg}") from None

    def download(self, url: str, headers: dict[str, str], path: Path) -> int:
        req = urllib.request.Request(url, headers=headers)
        tmp = path.with_suffix(".part")
        with urllib.request.urlopen(req, timeout=600) as r, tmp.open("wb") as fh:
            while chunk := r.read(1 << 20):
                fh.write(chunk)
        tmp.replace(path)
        return path.stat().st_size

    def get(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.read()


# ---- costs ----------------------------------------------------------------------------------
def video_estimate(model: str, resolution: str, seconds: int, usd_eur: float = USD_EUR) -> dict:
    if model not in VIDEO_USD_S:
        raise VeoError(f"no price for {model}; known: {', '.join(VIDEO_USD_S)}")
    usd = VIDEO_USD_S[model][resolution] * seconds
    return {"usd": round(usd, 4), "eur": round(usd * usd_eur, 4)}


def image_estimate(model: str, n_inputs: int, usd_eur: float = USD_EUR) -> dict:
    if model not in IMAGE_USD:
        raise VeoError(f"no price for {model}; known: {', '.join(IMAGE_USD)}")
    usd = IMAGE_USD[model] + n_inputs * IMAGE_IN_USD
    return {"usd": round(usd, 4), "eur": round(usd * usd_eur, 4)}


def image_billed(usage: dict, n_inputs: int, usd_eur: float = USD_EUR) -> dict | None:
    """The cost from the answer's own token count (output tokens at $120/M), if it has one."""
    out_tokens = usage.get("candidatesTokenCount")
    if not out_tokens:
        return None
    usd = int(out_tokens) * IMAGE_OUT_USD_PER_TOKEN + n_inputs * IMAGE_IN_USD
    return {"tokens_out": int(out_tokens), "usd": round(usd, 4), "eur": round(usd * usd_eur, 4)}


# ---- the ledger ------------------------------------------------------------------------------
class Ledger:
    """out/veo/ledger.jsonl: one line per paid call (its estimate, written before sending) and
    per bill seen in an answer. Spent = per call its bill when known, else its estimate."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def rows(self) -> list[dict]:
        if not self.path.is_file():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    def add(self, row: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": round(time.time(), 1), **row}) + "\n")

    def spent_eur(self) -> float:
        per: dict[str, float] = {}
        for r in self.rows():
            if r.get("event") in ("call", "billed"):
                per[str(r.get("id"))] = float(r.get("eur", 0))
        return round(sum(per.values()), 4)


def studio_record(model: str, eur: float, what: str) -> None:
    """The studio's AI ledger (coverengine.spend, <data>/usage/ai-YYYY-MM.jsonl), if present."""
    try:
        from coverengine import spend
    except ImportError:
        return
    spend.record_eur(model, eur, what)


# ---- pictures -------------------------------------------------------------------------------
def mime(path: Path) -> str:
    s = path.suffix.lower()
    if s == ".png":
        return "image/png"
    if s in (".jpg", ".jpeg"):
        return "image/jpeg"
    if s == ".webp":
        return "image/webp"
    raise VeoError(f"{path.name}: give a .png, .jpg or .webp")


def b64(path: Path) -> str:
    if not path.is_file():
        raise VeoError(f"picture missing: {path}")
    return base64.b64encode(path.read_bytes()).decode()


def crop_16x9(data: bytes, center: tuple[float, float] = (0.5, 0.5), zoom: float = 1.0,
              size: tuple[int, int] = FRAME_SIZE) -> bytes:  # fmt: skip
    """The largest 16:9 window (smaller by `zoom`) around `center` (fractions), scaled to
    `size`, as PNG."""
    from PIL import Image

    im = Image.open(io.BytesIO(data)).convert("RGB")
    w, h = im.size
    tw, th = size
    cw = min(w, h * tw / th) / max(zoom, 1.0)
    ch = cw * th / tw
    cx = min(max(center[0] * w, cw / 2), w - cw / 2)
    cy = min(max(center[1] * h, ch / 2), h - ch / 2)
    box = (round(cx - cw / 2), round(cy - ch / 2), round(cx + cw / 2), round(cy + ch / 2))
    out = im.crop(box).resize(size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def fit_frame(data: bytes, size: tuple[int, int] = FRAME_SIZE) -> bytes:
    """Gemini's picture (1376 x 768 at 1K, 2752 x 1536 at 2K: not exactly 16:9) to `size`."""
    return crop_16x9(data, size=size)


# ---- the spec --------------------------------------------------------------------------------
def load_spec(path: Path = SPEC_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve(p: str, base: Path) -> Path:
    q = Path(os.path.expanduser(p))
    return q if q.is_absolute() else (base / q)


@dataclass
class Ctx:
    out: Path
    frames: Path
    budget_eur: float
    usd_eur: float
    studio_ledger: bool
    dry_run: bool
    key: str
    http: Http
    spec: dict

    @property
    def ledger(self) -> Ledger:
        return Ledger(self.out / "ledger.jsonl")

    def headers(self) -> dict[str, str]:
        if not self.key:
            raise VeoError("no GEMINI_API_KEY (deploy/.env or the environment)")
        return {"x-goog-api-key": self.key, "Content-Type": "application/json"}

    def check_budget(self, eur: float, what: str) -> float:
        spent = self.ledger.spent_eur()
        print(f"{what}: ~EUR {eur:.2f}; spent EUR {spent:.2f} of EUR {self.budget_eur:.2f}")
        if spent + eur > self.budget_eur + 1e-9:
            raise VeoError(
                f"refused: EUR {spent:.2f} spent + EUR {eur:.2f} would pass the budget of "
                f"EUR {self.budget_eur:.2f} (--budget-eur)"
            )
        return spent

    def charge(self, cid: str, model: str, est: dict, what: str, **extra: Any) -> None:
        """Written before the call is sent: a crash after it still leaves the cost."""
        self.ledger.add({"event": "call", "id": cid, "model": model, "what": what, **est,
                         **extra})  # fmt: skip
        if self.studio_ledger:
            studio_record(model, est["eur"], what)


def masked(body: Any) -> Any:
    """A request for printing: base64 pictures summarised."""
    if isinstance(body, dict):
        return {k: (f"<base64, {len(v) * 3 // 4 / 1e6:.2f} MB>"
                    if k in ("data", "bytesBase64Encoded") and isinstance(v, str) and len(v) > 300
                    else masked(v)) for k, v in body.items()}  # fmt: skip
    if isinstance(body, list):
        return [masked(v) for v in body]
    return body


def show_request(ctx: Ctx, method: str, url: str, body: Any) -> None:
    hdr = {"x-goog-api-key": "***" if ctx.key else "(no key yet)",
           "Content-Type": "application/json"}  # fmt: skip
    print(json.dumps({"method": method, "url": url, "headers": hdr, "body": masked(body)},
                     indent=2))  # fmt: skip
    print("  dry run: nothing sent, nothing written")


# ---- photo: a SUNS photo as a 16:9 start frame ----------------------------------------------
def photo(ctx: Ctx, url: str, name: str, center: tuple[float, float], zoom: float) -> Path:
    """Download a SUNS photo (free, no ledger), crop it to 16:9 and note its source."""
    ctx.frames.mkdir(parents=True, exist_ok=True)
    raw = ctx.http.get(url)
    orig = ctx.frames / "originals" / url.rsplit("/", 1)[1]
    orig.parent.mkdir(exist_ok=True)
    orig.write_bytes(raw)
    out = ctx.frames / f"{name}.png"
    out.write_bytes(crop_16x9(raw, center, zoom))
    note_source(ctx.frames, out.name, {"kind": "SUNS photo, cropped to 16:9", "file":
                                       orig.name, "url": url, "center": list(center),
                                       "zoom": zoom})  # fmt: skip
    print(f"{out} (from {orig.name})")
    return out


def note_source(frames: Path, name: str, info: dict) -> None:
    p = frames / "sources.json"
    data = json.loads(p.read_text()) if p.is_file() else {}
    data[name] = info
    p.write_text(json.dumps(data, indent=2, sort_keys=True))


# ---- frame: our cover onto the photo with the Gemini image model ------------------------------
def frame_request(ctx: Ctx, name: str, dry: bool = False) -> tuple[str, dict, list[Path], dict]:
    f = ctx.spec["frames"][name]
    d = ctx.spec.get("defaults", {})
    model = f.get("model") or d.get("image_model", "gemini-3-pro-image")
    pics = [resolve(f["photo"], ctx.frames)] + [resolve(r, ctx.frames) for r in f.get("refs", [])]
    parts: list[dict] = []
    for p in pics:
        if dry and not p.is_file():
            print(f"  note: picture missing: {p}")
            parts.append({"inlineData": {"mimeType": "image/png", "data": f"<base64 of {p}>"}})
        else:
            parts.append({"inlineData": {"mimeType": mime(p), "data": b64(p)}})
    parts.append({"text": f["prompt"]})
    cfg: dict[str, Any] = {"aspectRatio": f.get("aspect", "16:9")}
    if f.get("image_size", d.get("image_size")):
        cfg["imageSize"] = f.get("image_size", d.get("image_size"))
    body = {"contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": cfg}}  # fmt: skip
    return model, body, pics, f


def make_frame(ctx: Ctx, name: str) -> Path | None:
    if name not in ctx.spec.get("frames", {}):
        raise VeoError(f"unknown frame {name}; known: {', '.join(ctx.spec.get('frames', {}))}")
    model, body, pics, f = frame_request(ctx, name, dry=ctx.dry_run)
    est = image_estimate(model, len(pics), ctx.usd_eur)
    ctx.check_budget(est["eur"], f"frame {name} ({model}, {len(pics)} pictures in)")
    url = f"{BASE}/models/{model}:generateContent"
    if ctx.dry_run:
        show_request(ctx, "POST", url, body)
        return None
    headers = ctx.headers()
    ctx.frames.mkdir(parents=True, exist_ok=True)
    n = 1 + max((int(p.stem.rsplit("-v", 1)[1]) for p in ctx.frames.glob(f"{name}-v*.png")
                 if p.stem.rsplit("-v", 1)[1].isdigit()), default=0)  # fmt: skip
    cid = f"frame:{name}:v{n}:{int(time.time())}"
    ctx.charge(cid, model, est, f"veo frame {name} v{n}")
    r = ctx.http.json("POST", url, headers, body)
    billed = image_billed(r.get("usageMetadata") or {}, len(pics), ctx.usd_eur)
    if billed:
        ctx.ledger.add({"event": "billed", "id": cid, "model": model, **billed})
        if ctx.studio_ledger and abs(billed["eur"] - est["eur"]) > 1e-6:
            studio_record(model, round(billed["eur"] - est["eur"], 4),
                          f"veo frame {name} v{n} (bill minus estimate)")  # fmt: skip
    img = None
    for c in r.get("candidates") or []:
        for p in (c.get("content") or {}).get("parts") or []:
            if "inlineData" in p:
                img = base64.b64decode(p["inlineData"]["data"])
                break
        if img:
            break
    if img is None:
        reason = [(c.get("finishReason"), c.get("finishMessage")) for c in r.get("candidates", [])]
        raise VeoError(f"no picture in the answer: {reason or list(r)}")
    raw = ctx.frames / f"{name}-v{n}-raw.png"
    raw.write_bytes(img)
    out = ctx.frames / f"{name}-v{n}.png"
    out.write_bytes(fit_frame(img))
    note_source(ctx.frames, out.name, {"kind": f"made by {model} from the photo and our cover",
                                       "photo": f["photo"], "refs": f.get("refs", []),
                                       "prompt": f["prompt"], "cost": billed or est})  # fmt: skip
    print(f"  {out}")
    return out


# ---- submit / fetch: Veo ---------------------------------------------------------------------
@dataclass
class Job:
    shot: str
    model: str
    prompt: str
    negative: str
    first: Path
    last: Path | None
    duration: int
    resolution: str
    aspect: str
    media_key: str

    def body(self, images: dict[str, Any]) -> dict:
        inst: dict[str, Any] = {"prompt": self.prompt, "image": images["first"]}
        if self.last is not None:
            inst["lastFrame"] = images["last"]
        params: dict[str, Any] = {"aspectRatio": self.aspect, "durationSeconds": self.duration,
                                  "resolution": self.resolution}  # fmt: skip
        if self.negative:
            params["negativePrompt"] = self.negative
        return {"instances": [inst], "parameters": params}


def make_job(ctx: Ctx, shot: str) -> Job:
    shots = ctx.spec.get("shots", {})
    if shot not in shots:
        raise VeoError(f"unknown shot {shot}; known: {', '.join(shots)}")
    s, d = shots[shot], ctx.spec.get("defaults", {})
    job = Job(
        shot=shot, model=s.get("model") or d.get("model", "veo-3.1-fast-generate-preview"),
        prompt=s["prompt"], negative=s.get("negative", d.get("negative", "")),
        first=resolve(s["first"], ctx.frames),
        last=resolve(s["last"], ctx.frames) if s.get("last") else None,
        duration=int(s.get("duration") or d.get("duration", 8)),
        resolution=s.get("resolution") or d.get("resolution", "1080p"),
        aspect=s.get("aspect") or d.get("aspect", "16:9"), media_key=s.get("media_key", shot),
    )  # fmt: skip
    if job.resolution == "1080p" and job.duration != 8:
        raise VeoError("Veo 3.1 gives 1080p only at 8 seconds")
    if job.duration not in (4, 6, 8):
        raise VeoError("Veo 3.1: 4, 6 or 8 seconds")
    return job


def next_n(folder: Path) -> int:
    return max((int(p.stem) for p in folder.glob("*.json") if p.stem.isdigit()), default=0) + 1


def submit(ctx: Ctx, job: Job) -> dict | None:
    est = video_estimate(job.model, job.resolution, job.duration, ctx.usd_eur)
    ctx.check_budget(est["eur"], f"{job.shot}: {job.model} {job.resolution} {job.duration} s")
    url = f"{BASE}/models/{job.model}:predictLongRunning"
    if ctx.dry_run:
        imgs = {"first": {"bytesBase64Encoded": f"<base64 of {job.first}>",
                          "mimeType": "image/png"}}  # fmt: skip
        if job.last is not None:
            imgs["last"] = {"bytesBase64Encoded": f"<base64 of {job.last}>",
                            "mimeType": "image/png"}  # fmt: skip
        for k, p in (("first", job.first), ("last", job.last)):
            if p is not None and not p.is_file():
                print(f"  note: {k} frame missing: {p}")
        show_request(ctx, "POST", url, job.body(imgs))
        return None
    headers = ctx.headers()
    images = {"first": {"bytesBase64Encoded": b64(job.first), "mimeType": mime(job.first)}}
    if job.last is not None:
        images["last"] = {"bytesBase64Encoded": b64(job.last), "mimeType": mime(job.last)}
    folder = ctx.out / job.shot
    folder.mkdir(parents=True, exist_ok=True)
    n = next_n(folder)
    rec: dict[str, Any] = {
        "n": n, "shot": job.shot, "media_key": job.media_key, "model": job.model,
        "prompt": job.prompt, "negative": job.negative, "first": str(job.first),
        "last": str(job.last) if job.last else None, "duration": job.duration,
        "resolution": job.resolution, "aspect": job.aspect, "estimate": est,
        "status": "sending", "submitted": time.strftime("%Y-%m-%d %H:%M:%S"),
    }  # fmt: skip
    (folder / f"{n}.json").write_text(json.dumps(rec, indent=2))
    cid = f"video:{job.shot}#{n}"
    ctx.charge(cid, job.model, est, f"veo {job.shot} #{n}")
    try:
        op = ctx.http.json("POST", url, headers, job.body(images))
    except Exception:
        rec["status"] = "not sent"
        (folder / f"{n}.json").write_text(json.dumps(rec, indent=2))
        raise
    if not op.get("name"):
        raise VeoError(f"no operation in Google's answer: {sorted(op)}")
    rec |= {"operation": op["name"], "status": "running"}
    (folder / f"{n}.json").write_text(json.dumps(rec, indent=2))
    print(f"  operation {op['name']} -> {folder / f'{n}.json'}")
    return rec


def records(out: Path, shot: str | None = None) -> list[tuple[Path, dict]]:
    found = []
    for p in sorted(out.glob(f"{shot or '*'}/*.json")):
        if p.stem.isdigit():
            found.append((p, json.loads(p.read_text())))
    return found


def refresh(ctx: Ctx, shot: str | None = None, only: set[str] | None = None) -> list[dict]:
    """Ask Google about every running operation; download finished clips."""
    headers = ctx.headers()
    rows = []
    for path, r in records(ctx.out, shot):
        if only is not None and r.get("operation") not in only:
            continue
        if r.get("status") == "running" and r.get("operation"):
            op = ctx.http.json("GET", f"{BASE}/{r['operation']}", headers)
            if op.get("done"):
                if "error" in op:
                    r |= {"status": "failed", "message": str(op["error"].get("message", ""))}
                else:
                    resp = (op.get("response") or {}).get("generateVideoResponse") or {}
                    samples = resp.get("generatedSamples") or []
                    if samples:
                        r |= {"status": "succeeded", "uri": samples[0]["video"]["uri"]}
                    else:
                        why = resp.get("raiMediaFilteredReasons") or resp
                        r |= {"status": "failed", "message": f"no video: {why}"}
        if r.get("status") == "succeeded" and r.get("uri") and not r.get("file"):
            mp4 = path.with_suffix(".mp4")
            size = ctx.http.download(r["uri"], {"x-goog-api-key": ctx.key}, mp4)
            r["file"] = str(mp4)
            print(f"  {r['shot']} #{r['n']}: {mp4} ({size / 1e6:.1f} MB)")
        path.write_text(json.dumps(r, indent=2))
        rows.append(r)
    return rows


def show(rows: list[dict], ctx: Ctx) -> None:
    for r in rows:
        print(f"{r['shot']:>16} #{r['n']:<3} {r.get('status', ''):<10} "
              f"{r.get('file') or r.get('message') or r.get('operation', '')}")  # fmt: skip
    print(f"spent EUR {ctx.ledger.spent_eur():.2f} of EUR {ctx.budget_eur:.2f}")


def run(ctx: Ctx, jobs: list[Job], wait_s: float | None = None, poll_s: float | None = None,
        sleep=time.sleep) -> list[dict]:  # fmt: skip
    wait_s = WAIT_S if wait_s is None else wait_s
    poll_s = POLL_S if poll_s is None else poll_s
    total = sum(video_estimate(j.model, j.resolution, j.duration, ctx.usd_eur)["eur"]
                for j in jobs)  # fmt: skip
    spent = ctx.ledger.spent_eur()
    if spent + total > ctx.budget_eur + 1e-9:
        raise VeoError(
            f"refused: these {len(jobs)} clips (~EUR {total:.2f}) on top of EUR "
            f"{spent:.2f} spent would pass the budget of EUR {ctx.budget_eur:.2f}"
        )
    sent = [r for j in jobs if (r := submit(ctx, j))]
    if ctx.dry_run or not sent:
        return []
    ops = {r["operation"] for r in sent}
    t0 = time.monotonic()
    while True:
        rows = refresh(ctx, only=ops)
        if all(r.get("status") in ("succeeded", "failed") for r in rows):
            break
        if time.monotonic() - t0 > wait_s:
            print("still running; `veo.py fetch` later picks them up")
            break
        sleep(poll_s)
    show(rows, ctx)
    return rows


# ---- main ------------------------------------------------------------------------------------
def main(argv: list[str] | None = None, http: Http | None = None,
         env: dict[str, str] | None = None) -> int:  # fmt: skip
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path("out/veo"))
    ap.add_argument("--frames", type=Path, default=None, help="default: <out>/frames")
    ap.add_argument("--spec", type=Path, default=SPEC_FILE)
    ap.add_argument("--budget-eur", type=float, default=30.0)
    ap.add_argument("--usd-eur", type=float, default=USD_EUR)
    ap.add_argument("--env-file", type=Path, default=None)
    ap.add_argument("--no-studio-ledger", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("photo")
    p.add_argument("url")
    p.add_argument("--name", required=True)
    p.add_argument("--center", default="0.5,0.5")
    p.add_argument("--zoom", type=float, default=1.0)
    p = sub.add_parser("frame")
    p.add_argument("names", help="one frame or a,b,c")
    p.add_argument("--dry-run", action="store_true", dest="dry_sub")
    p = sub.add_parser("submit")
    p.add_argument("shot")
    p.add_argument("--dry-run", action="store_true", dest="dry_sub")
    p = sub.add_parser("run")
    p.add_argument("--shots", required=True)
    p.add_argument("--dry-run", action="store_true", dest="dry_sub")
    sub.add_parser("fetch").add_argument("shot", nargs="?")
    sub.add_parser("cost")
    a = ap.parse_args(argv)
    dry = a.dry_run or getattr(a, "dry_sub", False)
    ctx = Ctx(out=a.out, frames=a.frames or a.out / "frames", budget_eur=a.budget_eur,
              usd_eur=a.usd_eur, studio_ledger=not a.no_studio_ledger, dry_run=dry,
              key=load_key(env, a.env_file), http=http or Http(),
              spec=load_spec(a.spec))  # fmt: skip
    try:
        if a.cmd == "cost":
            for m, by in VIDEO_USD_S.items():
                for res in by:
                    e = video_estimate(m, res, 8, a.usd_eur)
                    print(f"{m:>32} {res:>5} 8 s: ${e['usd']:.2f}, ~EUR {e['eur']:.2f}")
            for m in IMAGE_USD:
                e = image_estimate(m, 2, a.usd_eur)
                print(f"{m:>32} one picture from 2: ${e['usd']:.3f}, ~EUR {e['eur']:.3f}")
            print(f"spent EUR {ctx.ledger.spent_eur():.2f} of EUR {a.budget_eur:.2f}")
            return 0
        if a.cmd == "photo":
            cx, cy = (float(v) for v in a.center.split(","))
            photo(ctx, a.url, a.name, (cx, cy), a.zoom)
            return 0
        if a.cmd == "frame":
            for name in [x for x in a.names.split(",") if x]:
                make_frame(ctx, name)
            return 0
        if a.cmd in ("submit", "run"):
            names = [a.shot] if a.cmd == "submit" else [s for s in a.shots.split(",") if s]
            jobs = [make_job(ctx, n) for n in names]
            if not ctx.key and not dry:
                raise VeoError("no GEMINI_API_KEY yet (deploy/.env); --dry-run shows the request")
            if a.cmd == "submit":
                submit(ctx, jobs[0])
            else:
                run(ctx, jobs)
            return 0
        show(refresh(ctx, a.shot), ctx)
        return 0
    except VeoError as e:
        print(f"veo: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
