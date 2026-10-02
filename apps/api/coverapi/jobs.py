"""Background runs: the `cover` steps as subprocesses, one job at a time (a big model takes
minutes and several GB), with each step's status and log in `jobs/<id>.json`."""

from __future__ import annotations

import json
import queue
import shutil
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from coverapi.store import STEPS, Store

LOG_TAIL = 4000  # characters of each step's output kept in the job file
# cover improve: the program adds seams; cover ai: AI advice; cover rain: the rain simulation;
# cover drape: the sewn cover falling over the furniture
EXTRA_STEPS = ["improve", "ai", "rain", "drape"]


@dataclass
class JobSpec:
    model_id: str
    steps: list[str]
    trial: dict[str, Any]
    source: str | None = None  # the uploaded file (for the import step)
    units: str | None = None
    up: str | None = None


class Jobs:
    def __init__(self, store: Store) -> None:
        self.store = store
        self._queue: queue.Queue[tuple[str, JobSpec]] = queue.Queue()
        self._thread = threading.Thread(target=self._work, daemon=True)
        self._thread.start()

    def submit(self, spec: JobSpec) -> dict[str, Any]:
        unknown = [s for s in spec.steps if s not in STEPS and s not in EXTRA_STEPS]
        if unknown:
            raise ValueError(f"unknown step(s): {', '.join(unknown)}")
        job_id = uuid.uuid4().hex[:12]
        doc = {
            "id": job_id,
            "model_id": spec.model_id,
            "status": "queued",
            "created": time.time(),
            "trial": spec.trial,
            "steps": [{"name": s, "status": "waiting", "log": ""} for s in spec.steps],
        }
        self._write(doc)
        self._queue.put((job_id, spec))
        return doc

    def get(self, job_id: str) -> dict[str, Any]:
        path = self.store.jobs / f"{job_id}.json"
        if not path.is_file() or not job_id.isalnum():
            raise KeyError(job_id)
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def latest(self, model_id: str) -> dict[str, Any] | None:
        best = None
        for path in self.store.jobs.glob("*.json"):
            doc = json.loads(path.read_text(encoding="utf-8"))
            if doc["model_id"] == model_id and (best is None or doc["created"] > best["created"]):
                best = doc
        return best

    def wait(self, job_id: str, timeout: float) -> dict[str, Any]:
        """For tests: block until the job is done."""
        end = time.time() + timeout
        while time.time() < end:
            doc = self.get(job_id)
            if doc["status"] in ("done", "failed"):
                return doc
            time.sleep(0.2)
        raise TimeoutError(job_id)

    def _write(self, doc: dict[str, Any]) -> None:
        self.store.jobs.mkdir(parents=True, exist_ok=True)
        path = self.store.jobs / f"{doc['id']}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _work(self) -> None:
        while True:
            job_id, spec = self._queue.get()
            try:
                self._run(job_id, spec)
            except Exception as exc:  # noqa: BLE001 - a job must never kill the worker
                doc = self.get(job_id)
                doc["status"], doc["error"] = "failed", str(exc)
                self._write(doc)

    def _run(self, job_id: str, spec: JobSpec) -> None:
        doc = self.get(job_id)
        doc["status"], doc["started"] = "running", time.time()
        self._write(doc)
        model_dir = self.store.model_dir(spec.model_id)
        pattern = model_dir / "pattern.json"
        if (
            "flatten" in spec.steps or "improve" in spec.steps
        ) and pattern.is_file():  # keep the last run for the diff
            shutil.copyfile(pattern, model_dir / "pattern.prev.json")
        sets = [x for k, v in sorted(spec.trial.items()) for x in ("--set", f"{k}={_yaml(v)}")]
        for step in doc["steps"]:
            name = step["name"]
            if name == "import":
                if not spec.source:
                    raise ValueError("the import step needs an uploaded file")
                args = ["import", spec.source, "--out", str(model_dir)]
                args += ["--units", spec.units] if spec.units else []
                args += ["--up", spec.up] if spec.up else []
            else:
                args = [name, str(model_dir), *sets]
            step["status"], step["started"] = "running", time.time()
            self._write(doc)
            proc = subprocess.run(
                [sys.executable, "-m", "coverengine.cli", *args],
                capture_output=True,
                text=True,
                check=False,
            )
            step["log"] = (proc.stdout + proc.stderr)[-LOG_TAIL:]
            step["finished"] = time.time()
            step["status"] = "done" if proc.returncode == 0 else "failed"
            self._write(doc)
            if proc.returncode != 0:
                doc["status"] = "failed"
                doc["error"] = _last_error(proc.stderr) or f"cover {name} failed"
                self._write(doc)
                return
        doc["status"], doc["finished"] = "done", time.time()
        self._write(doc)


def _yaml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _last_error(text: str) -> str | None:
    lines = [ln for ln in text.splitlines() if ln.startswith("error:")]
    return lines[-1].removeprefix("error:").strip() if lines else None


def store_upload(store: Store, model_id: str, filename: str, data: bytes) -> Path:
    folder = store.uploads / model_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(filename).name
    path.write_bytes(data)
    return path
