"""The website's clips from our own stills with Kling image-to-video (ADR-124).

Our Blender frames (kling_frames.py) decide the cover, its colour and the light; Kling only
adds the motion: the cover settling, the rain running off, a slow camera. One shot a call or a
list; the shots, their frames and prompts are in kling_shots.json (docs/plans/kling-shots.md).

    uv run python scripts/film/kling.py submit SHOT [--aspect 4x5|16x9] [--model kling-3.0]
        [--mode pro|std] [--duration 5] [--dry-run]
    uv run python scripts/film/kling.py status [SHOT]          what Kling says about our tasks
    uv run python scripts/film/kling.py fetch [SHOT]           download the finished clips
    uv run python scripts/film/kling.py run --shots fit,rain [--dry-run]   submit, wait, fetch
    uv run python scripts/film/kling.py cost                   spent, budget, a clip's estimate

Each clip lands in out/kling/<shot>/<n>.mp4 with <n>.json beside it (the prompt, the
parameters, the task, the cost). Every submit is written to out/kling/ledger.jsonl and to the
studio's AI ledger (spend.py, `--no-studio-ledger` leaves that out) before it is sent; a submit
whose estimate would take the ledger past `--budget-eur` (default 50) is refused before
anything is sent. `--dry-run` prints the request (the key masked, the pictures summarised) and
sends nothing.

Keys (deploy/.env or the environment), never printed:
- KLING_API_KEY: `Authorization: Bearer <key>`, the current API (/image-to-video/<model>,
  /tasks); the negative prompt goes into the prompt text as "Avoid: ...", the only way that API
  takes one.
- KLING_ACCESS_KEY + KLING_SECRET_KEY: a JWT (HS256, iss = access key, exp 30 min, nbf 5 s
  back) for the legacy API, which per Kling's docs is the only one that takes it
  (/v1/videos/image2video with model_name, image, image_tail, negative_prompt, mode).

Prices (kling.ai/document-api/pricing/base/video, read 12 Oct 2026): units a second, one unit
$0.14 at list price; a resource package can be cheaper, so the ledger errs high.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SHOTS_FILE = Path(__file__).resolve().parent / "kling_shots.json"
BASE = "https://api-singapore.klingai.com"
USD_PER_UNIT = 0.14  # list price of one unit (Kling's pricing page, Oct 2026)
USD_EUR = 0.95  # deliberately high (the rate was ~0.86 in Oct 2026): the cap errs safe
# units a second without native audio: (720p, 1080p)
UNITS_PER_S = {
    "kling-3.0": (0.6, 0.8),
    "kling-3.0-omni": (0.6, 0.8),
    "kling-3.0-turbo": (0.8, 1.0),  # always with native audio
    "kling-2.6": (0.3, 0.5),
    "kling-2.5-turbo": (0.3, 0.5),
}
# which models take a last frame, and at which resolution (the capability map)
LAST_FRAME = {"kling-3.0": None, "kling-3.0-omni": None, "kling-2.6": "1080p",
              "kling-2.5-turbo": "1080p"}  # fmt: skip
# the legacy API's model_name for each (pricing as the matching version)
LEGACY_NAME = {"kling-2.5-turbo": "kling-v2-5-turbo", "kling-2.6": "kling-v2-6",
               "kling-3.0": "kling-v3", "kling-3.0-omni": "kling-v3-omni"}  # fmt: skip
MODE_RES = {"std": "720p", "pro": "1080p"}
JWT_LIFE_S = 1800
POLL_S = 15.0
WAIT_S = 1800.0
DONE = {"succeeded", "failed"}


class KlingError(RuntimeError):
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
        k = k.strip().removeprefix("export ").strip()
        out[k] = v.strip().strip("'\"")
    return out


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def jwt_hs256(access: str, secret: str, now: float | None = None) -> str:
    """Kling's token: header {alg HS256, typ JWT}, payload {iss, exp +30 min, nbf -5 s}."""
    t = int(now if now is not None else time.time())
    head = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64url(
        json.dumps(
            {"iss": access, "exp": t + JWT_LIFE_S, "nbf": t - 5}, separators=(",", ":")
        ).encode()
    )
    sig = hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()
    return f"{head}.{body}.{_b64url(sig)}"


@dataclass
class Auth:
    """Which key we have; `header()` makes the Authorization value. Its repr hides the key."""

    api_key: str = field(default="", repr=False)
    access: str = field(default="", repr=False)
    secret: str = field(default="", repr=False)

    @classmethod
    def load(cls, env: dict[str, str] | None = None, env_file: Path | None = None) -> Auth:
        src = dict(read_env(env_file or ROOT / "deploy" / ".env"))
        src.update({k: v for k, v in (env if env is not None else os.environ).items()
                    if k.startswith("KLING_")})  # fmt: skip
        return cls(
            src.get("KLING_API_KEY", ""), src.get("KLING_ACCESS_KEY", ""),
            src.get("KLING_SECRET_KEY", ""),
        )  # fmt: skip

    @property
    def kind(self) -> str:
        if self.api_key:
            return "api_key"
        if self.access and self.secret:
            return "jwt"
        return "none"

    def api(self, want: str = "auto") -> str:
        """new (path-versioned, API key) or legacy (model_name, JWT)."""
        if want != "auto":
            return want
        return "legacy" if self.kind == "jwt" else "new"

    def header(self, now: float | None = None) -> str:
        if self.api_key:
            return f"Bearer {self.api_key}"
        if self.access and self.secret:
            return f"Bearer {jwt_hs256(self.access, self.secret, now)}"
        raise KlingError("no Kling key: set KLING_API_KEY, or KLING_ACCESS_KEY and "
                         "KLING_SECRET_KEY, in deploy/.env")  # fmt: skip


# ---- HTTP (the one place that talks to the network; tests replace it) -------------------------
class Http:
    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    def json(self, method: str, url: str, headers: dict[str, str], body: Any = None) -> dict:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode() or "{}") | {"_http": e.code}
            except json.JSONDecodeError:
                raise KlingError(f"HTTP {e.code} from Kling") from None

    def download(self, url: str, path: Path) -> int:
        # no Authorization here: the result's URL is a signed CDN link, the key stays with Kling
        req = urllib.request.Request(url, headers={"User-Agent": "cover-studio-film/1.0"})
        tmp = path.with_suffix(".part")
        with urllib.request.urlopen(req, timeout=300) as r, tmp.open("wb") as fh:
            while chunk := r.read(1 << 20):
                fh.write(chunk)
        tmp.replace(path)
        return path.stat().st_size


# ---- shots, requests, costs ----------------------------------------------------------------
def load_shots(path: Path = SHOTS_FILE) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def frames_dir(spec: dict[str, Any], override: Path | None = None) -> Path:
    return (override or Path(os.path.expanduser(spec["frames_dir"]))).resolve()


def shot_frames(spec: dict, name: str, aspect: str, fdir: Path) -> tuple[Path, Path | None]:
    s = spec["shots"][name]
    first = fdir / s["first"].format(aspect=aspect)
    last = fdir / s["last"].format(aspect=aspect) if s.get("last") else None
    return first, last


def estimate(model: str, resolution: str, seconds: int, usd_eur: float = USD_EUR) -> dict:
    if model not in UNITS_PER_S:
        raise KlingError(f"no price for {model}; known: {', '.join(UNITS_PER_S)}")
    units = UNITS_PER_S[model][1 if resolution == "1080p" else 0] * seconds
    usd = units * USD_PER_UNIT
    return {"units": round(units, 3), "usd": round(usd, 4), "eur": round(usd * usd_eur, 4)}


def image_b64(path: Path) -> str:
    if not path.is_file():
        raise KlingError(f"frame missing: {path} (render it with kling_frames.py)")
    if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
        raise KlingError(f"{path.name}: Kling takes .jpg, .jpeg or .png")
    if path.stat().st_size > 50_000_000:
        raise KlingError(f"{path.name}: over Kling's 50 MB")
    return base64.b64encode(path.read_bytes()).decode()  # plain base64, no data: prefix


@dataclass
class Job:
    shot: str
    aspect: str
    model: str
    mode: str
    duration: int
    prompt: str
    negative: str
    first: Path
    last: Path | None
    api: str  # new | legacy

    @property
    def resolution(self) -> str:
        return MODE_RES[self.mode]

    def check(self) -> None:
        if self.model not in UNITS_PER_S:
            raise KlingError(f"unknown model {self.model}")
        if self.last is not None:
            if self.model not in LAST_FRAME:
                raise KlingError(f"{self.model} takes no last frame; use kling-3.0")
            need = LAST_FRAME[self.model]
            if need and self.resolution != need:
                raise KlingError(f"{self.model} with a last frame only at {need} (--mode pro)")
        if self.api == "new" and self.model == "kling-3.0-turbo" and self.duration < 3:
            raise KlingError("kling-3.0-turbo: 3 to 15 s")
        if self.model in ("kling-2.6", "kling-2.5-turbo") and self.duration not in (5, 10):
            raise KlingError(f"{self.model}: 5 or 10 s")

    def text(self) -> str:
        """The new API has no negative field; Kling says the prompt may carry both."""
        if self.api == "new" and self.negative:
            return f"{self.prompt} Avoid: {self.negative}."
        return self.prompt

    def request(self, images: dict[str, str] | None = None) -> tuple[str, str, dict]:
        """(method, path, body). `images` maps first/last to their base64 (dry runs pass a
        summary instead)."""
        im = images or {}
        if self.api == "new":
            contents: list[dict[str, str]] = [
                {"type": "prompt", "text": self.text()},
                {"type": "first_frame", "url": im["first"]},
            ]
            if self.last is not None:
                contents.append({"type": "last_frame", "url": im["last"]})
            settings: dict[str, Any] = {"resolution": self.resolution, "duration": self.duration}
            if self.model.startswith("kling-3.0"):
                settings |= {"multi_shot": False, "audio": "off"}
            if self.model == "kling-3.0-turbo":
                settings.pop("audio")
                settings.pop("multi_shot")
            body = {"contents": contents, "settings": settings,
                    "options": {"watermark_info": {"enabled": False}}}  # fmt: skip
            return "POST", f"/image-to-video/{self.model}", body
        body = {
            "model_name": LEGACY_NAME.get(self.model, self.model),
            "image": im["first"],
            "prompt": self.prompt,
            "negative_prompt": self.negative,
            "mode": self.mode,
            "duration": str(self.duration),
        }
        if self.last is not None:
            body["image_tail"] = im["last"]
        return "POST", "/v1/videos/image2video", body


IMAGE_FIELDS = ("url", "image", "image_tail")


def masked(body: Any) -> Any:
    """A request for printing: the pictures' base64 summarised."""
    if isinstance(body, dict):
        return {k: (f"<base64, {len(v) * 3 // 4 / 1e6:.2f} MB>"
                    if k in IMAGE_FIELDS and isinstance(v, str) and len(v) > 300 else masked(v))
                for k, v in body.items()}  # fmt: skip
    if isinstance(body, list):
        return [masked(v) for v in body]
    return body


# ---- the ledger ------------------------------------------------------------------------------
class Ledger:
    """out/kling/ledger.jsonl: one line per submit (the estimate) and per bill seen in a task's
    answer. Spent = per task its bill when known, else its estimate (a failed task keeps its
    estimate unless Kling bills it at 0: the cap errs safe)."""

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
            key = f"{r.get('shot')}#{r.get('n')}:{r.get('task')}"
            if r.get("event") == "submit" and key not in per:
                per[key] = float(r.get("eur", 0))
            elif r.get("event") == "billed":
                per[key] = float(r.get("eur", 0))
        return round(sum(per.values()), 4)

    def billed(self, task: str, shot: str, n: int) -> bool:
        return any(r.get("event") == "billed" and r.get("task") == task and r.get("shot") == shot
                   and r.get("n") == n for r in self.rows())  # fmt: skip


def studio_record(model: str, eur: float, what: str) -> None:
    """The studio's AI ledger (coverengine.spend, <data>/usage/ai-YYYY-MM.jsonl), if present."""
    try:
        from coverengine import spend
    except ImportError:
        return
    spend.record_eur(model, eur, what)


# ---- the client ------------------------------------------------------------------------------
def norm_status(s: str) -> str:
    return {"succeed": "succeeded", "success": "succeeded"}.get(s, s or "unknown")


class Kling:
    def __init__(self, auth: Auth, http: Http | None = None, base: str = BASE,
                 api: str = "auto") -> None:  # fmt: skip
        self.auth, self.http, self.base = auth, http or Http(), base.rstrip("/")
        self.api = auth.api(api)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": self.auth.header(), "Content-Type": "application/json"}

    def _call(self, method: str, path: str, body: Any = None) -> dict:
        r = self.http.json(method, self.base + path, self._headers(), body)
        if r.get("code", 0) != 0:
            raise KlingError(f"Kling {r.get('code')}: {r.get('message', '')}")
        return r

    def create(self, job: Job, images: dict[str, str]) -> str:
        method, path, body = job.request(images)
        r = self._call(method, path, body)
        d = r.get("data") or {}
        task = d.get("id") or d.get("task_id")
        if not task:
            raise KlingError(f"no task id in Kling's answer: {sorted(d)}")
        return str(task)

    def query(self, tasks: list[str]) -> dict[str, dict]:
        """task id -> {status, url, message, units (billed, or None)}."""
        out: dict[str, dict] = {}
        if not tasks:
            return out
        if self.api == "new":
            r = self._call("GET", "/tasks?task_ids=" + ",".join(tasks))
            data = r.get("data") or []
            for t in data if isinstance(data, list) else [data]:
                vids = [o for o in t.get("outputs") or [] if o.get("type") == "video"]
                units = None
                for b in t.get("billing") or []:
                    if b.get("charge_type") == "unit":
                        units = (units or 0.0) + float(b.get("amount") or 0)
                out[str(t.get("id"))] = {
                    "status": norm_status(t.get("status", "")),
                    "url": vids[0].get("url") if vids else None,
                    "message": t.get("message", ""),
                    "units": units,
                }
            return out
        for task in tasks:
            r = self._call("GET", f"/v1/videos/image2video/{task}")
            d = r.get("data") or {}
            vids = (d.get("task_result") or {}).get("videos") or []
            out[task] = {
                "status": norm_status(d.get("task_status", "")),
                "url": vids[0].get("url") if vids else None,
                "message": d.get("task_status_msg", ""),
                "units": None,
            }
        return out


# ---- the work --------------------------------------------------------------------------------
@dataclass
class Ctx:
    out: Path
    budget_eur: float
    usd_eur: float
    studio_ledger: bool
    dry_run: bool
    client: Kling | None
    spec: dict
    fdir: Path

    @property
    def ledger(self) -> Ledger:
        return Ledger(self.out / "ledger.jsonl")


def make_job(ctx: Ctx, shot: str, aspect: str | None, model: str | None, mode: str | None,
             duration: int | None, api: str) -> Job:  # fmt: skip
    if shot not in ctx.spec["shots"]:
        raise KlingError(f"unknown shot {shot}; known: {', '.join(ctx.spec['shots'])}")
    s = ctx.spec["shots"][shot]
    d = ctx.spec.get("defaults", {})
    asp = aspect or s.get("aspect") or d.get("aspect", "4x5")
    first, last = shot_frames(ctx.spec, shot, asp, ctx.fdir)
    job = Job(
        shot=shot, aspect=asp, model=model or s.get("model") or d.get("model", "kling-3.0"),
        mode=mode or s.get("mode") or d.get("mode", "pro"),
        duration=int(duration or s.get("duration") or d.get("duration", 5)),
        prompt=s["prompt"], negative=s.get("negative") or d.get("negative", ""),
        first=first, last=last, api=api,
    )  # fmt: skip
    job.check()
    return job


def next_n(folder: Path) -> int:
    ns = [int(p.stem) for p in folder.glob("*.json") if p.stem.isdigit()]
    return max(ns, default=0) + 1


def submit(ctx: Ctx, job: Job) -> dict | None:
    """Check the budget, print or send, write the clip's record and the ledgers."""
    est = estimate(job.model, job.resolution, job.duration, ctx.usd_eur)
    spent = ctx.ledger.spent_eur()
    print(
        f"{job.shot} {job.aspect}: {job.model} {job.resolution} {job.duration} s, "
        f"~{est['units']} units, ~€{est['eur']:.2f}; spent €{spent:.2f} of €{ctx.budget_eur:.2f}"
    )
    if spent + est["eur"] > ctx.budget_eur + 1e-9:
        raise KlingError(
            f"refused: €{spent:.2f} spent + €{est['eur']:.2f} would pass the budget of "
            f"€{ctx.budget_eur:.2f} (--budget-eur)"
        )
    if ctx.dry_run:
        imgs = {"first": f"<base64 of {job.first}>"}
        if job.last is not None:
            imgs["last"] = f"<base64 of {job.last}>"
        for k, p in (("first", job.first), ("last", job.last)):
            if p is not None and not p.is_file():
                print(f"  note: {k} frame missing: {p}")
        method, path, body = job.request(imgs)
        api_kind = ctx.client.auth.kind if ctx.client else "none"
        print(json.dumps({"method": method, "url": BASE + path,
                          "headers": {"Authorization": "Bearer ***" if api_kind != "none"
                                      else "(no key yet)", "Content-Type": "application/json"},
                          "body": masked(body)}, indent=2))  # fmt: skip
        print("  dry run: nothing sent, nothing written")
        return None
    assert ctx.client is not None
    images = {"first": image_b64(job.first)}
    if job.last is not None:
        images["last"] = image_b64(job.last)
    folder = ctx.out / job.shot
    folder.mkdir(parents=True, exist_ok=True)
    n = next_n(folder)
    record = {
        "n": n, "shot": job.shot, "aspect": job.aspect, "media_key":
        ctx.spec["shots"][job.shot].get("media_key", job.shot), "model": job.model,
        "mode": job.mode, "resolution": job.resolution, "duration": job.duration,
        "api": job.api, "prompt": job.prompt, "negative": job.negative, "sent_text": job.text(),
        "first": str(job.first), "last": str(job.last) if job.last else None,
        "estimate": est, "status": "sending", "submitted": time.strftime("%Y-%m-%d %H:%M:%S"),
    }  # fmt: skip
    # written before sending: a crash after the call still leaves the cost on the ledger
    (folder / f"{n}.json").write_text(json.dumps(record, indent=2))
    try:
        task = ctx.client.create(job, images)
    except Exception:
        record["status"] = "not sent"
        (folder / f"{n}.json").write_text(json.dumps(record, indent=2))
        raise
    record |= {"task": task, "status": "submitted"}
    (folder / f"{n}.json").write_text(json.dumps(record, indent=2))
    ctx.ledger.add({"event": "submit", "task": task, "shot": job.shot, "n": n,
                    "aspect": job.aspect, "model": job.model, "resolution": job.resolution,
                    "duration": job.duration, **est})  # fmt: skip
    if ctx.studio_ledger:
        studio_record(job.model, est["eur"], f"kling {job.shot} {job.aspect} #{n}")
    print(f"  task {task} → {folder / f'{n}.json'}")
    return record


def records(out: Path, shot: str | None = None) -> list[tuple[Path, dict]]:
    out_ = []
    for p in sorted(out.glob(f"{shot or '*'}/*.json")):
        if p.stem.isdigit():
            out_.append((p, json.loads(p.read_text())))
    return out_


def refresh(ctx: Ctx, shot: str | None = None, download: bool = False) -> list[dict]:
    """Ask Kling about every open task; with `download`, fetch finished clips."""
    assert ctx.client is not None
    recs = records(ctx.out, shot)
    open_ = [r["task"] for _, r in recs if r.get("task") and (
        r.get("status") not in DONE or (download and r.get("status") == "succeeded"
                                        and not r.get("file")))]  # fmt: skip
    answers = ctx.client.query(open_) if open_ else {}
    rows = []
    for path, r in recs:
        a = answers.get(r.get("task", ""))
        if a:
            r["status"] = a["status"]
            if a.get("message"):
                r["message"] = a["message"]
            if a.get("url"):
                r["url"] = a["url"]
            if a.get("units") is not None and not ctx.ledger.billed(r["task"], r["shot"], r["n"]):
                units = float(a["units"])
                eur = round(units * USD_PER_UNIT * ctx.usd_eur, 4)
                r["billed"] = {"units": units, "eur": eur}
                ctx.ledger.add({"event": "billed", "task": r["task"], "shot": r["shot"],
                                "n": r["n"], "units": units, "eur": eur})  # fmt: skip
        if download and r.get("status") == "succeeded" and r.get("url") and not r.get("file"):
            mp4 = path.with_suffix(".mp4")
            size = ctx.client.http.download(r["url"], mp4)
            r["file"] = str(mp4)
            print(f"  {r['shot']} #{r['n']}: {mp4} ({size / 1e6:.1f} MB)")
        path.write_text(json.dumps(r, indent=2))
        rows.append(r)
    return rows


def show(rows: list[dict], ctx: Ctx) -> None:
    for r in rows:
        print(f"{r['shot']:>6} #{r['n']:<3} {r.get('aspect', ''):>5} {r.get('status', ''):<10} "
              f"{r.get('task', '-'):<22} {r.get('file') or r.get('message') or ''}")  # fmt: skip
    print(f"spent €{ctx.ledger.spent_eur():.2f} of €{ctx.budget_eur:.2f}")


def run(ctx: Ctx, jobs: list[Job], wait_s: float = WAIT_S, poll_s: float = POLL_S,
        sleep=time.sleep) -> list[dict]:  # fmt: skip
    total = sum(estimate(j.model, j.resolution, j.duration, ctx.usd_eur)["eur"] for j in jobs)
    spent = ctx.ledger.spent_eur()
    if spent + total > ctx.budget_eur + 1e-9:
        raise KlingError(
            f"refused: these {len(jobs)} clips (~€{total:.2f}) on top of €"
            f"{spent:.2f} spent would pass the budget of €{ctx.budget_eur:.2f}"
        )
    sent = [r for j in jobs if (r := submit(ctx, j))]
    if ctx.dry_run or not sent:
        return []
    tasks = {r["task"] for r in sent}
    t0 = time.monotonic()
    while True:
        rows = [r for r in refresh(ctx, download=True) if r.get("task") in tasks]
        if all(r.get("status") in DONE for r in rows):
            break
        if time.monotonic() - t0 > wait_s:
            print("still running; `kling.py fetch` later picks them up")
            break
        sleep(poll_s)
    show(rows, ctx)
    return rows


def main(argv: list[str] | None = None, http: Http | None = None,
         env: dict[str, str] | None = None) -> int:  # fmt: skip
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=Path("out/kling"))
    ap.add_argument("--frames", type=Path, default=None, help="the stills' folder")
    ap.add_argument("--shots-file", type=Path, default=SHOTS_FILE)
    ap.add_argument("--budget-eur", type=float, default=50.0)
    ap.add_argument("--usd-eur", type=float, default=USD_EUR)
    ap.add_argument("--api", choices=("auto", "new", "legacy"), default="auto")
    ap.add_argument("--env-file", type=Path, default=None)
    ap.add_argument("--no-studio-ledger", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("submit", "run"):
        p = sub.add_parser(name)
        if name == "submit":
            p.add_argument("shot")
        else:
            p.add_argument("--shots", required=True)
        p.add_argument("--aspect", choices=("4x5", "16x9", "both"), default=None)
        p.add_argument("--model", choices=sorted(UNITS_PER_S), default=None)
        p.add_argument("--mode", choices=("std", "pro"), default=None)
        p.add_argument("--duration", type=int, default=None)
        p.add_argument("--dry-run", action="store_true", dest="dry_run_sub")
    for name in ("status", "fetch"):
        sub.add_parser(name).add_argument("shot", nargs="?")
    sub.add_parser("cost")
    a = ap.parse_args(argv)
    dry = a.dry_run or getattr(a, "dry_run_sub", False)
    spec = load_shots(a.shots_file)
    auth = Auth.load(env, a.env_file)
    api = auth.api(a.api)
    client = Kling(auth, http, api=a.api) if auth.kind != "none" else None
    ctx = Ctx(a.out, a.budget_eur, a.usd_eur, not a.no_studio_ledger, dry, client, spec,
              frames_dir(spec, a.frames))  # fmt: skip
    try:
        if a.cmd == "cost":
            d = spec.get("defaults", {})
            for m in sorted(UNITS_PER_S):
                for mode in ("std", "pro"):
                    e = estimate(m, MODE_RES[mode], int(d.get("duration", 5)), a.usd_eur)
                    print(f"{m:>16} {mode} {MODE_RES[mode]}: {e['units']} units, "
                          f"${e['usd']:.2f}, ~€{e['eur']:.2f}")  # fmt: skip
            print(f"spent €{ctx.ledger.spent_eur():.2f} of €{a.budget_eur:.2f}")
            return 0
        if a.cmd in ("submit", "run"):
            names = [a.shot] if a.cmd == "submit" else [s for s in a.shots.split(",") if s]
            jobs = []
            for n in names:
                default = spec["shots"].get(n, {}).get("aspect")
                aspects = ["4x5", "16x9"] if a.aspect == "both" else [a.aspect or default]
                jobs += [make_job(ctx, n, asp, a.model, a.mode, a.duration, api)
                         for asp in aspects]  # fmt: skip
            if client is None and not dry:
                raise KlingError("no Kling key yet (deploy/.env); --dry-run shows the request")
            if a.cmd == "submit":
                for j in jobs:
                    submit(ctx, j)
            else:
                run(ctx, jobs)
            return 0
        if client is None:
            raise KlingError("no Kling key yet (deploy/.env)")
        rows = refresh(ctx, a.shot, download=a.cmd == "fetch")
        show(rows, ctx)
        return 0
    except KlingError as e:
        print(f"kling: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
