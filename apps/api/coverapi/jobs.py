"""Background runs: the `cover` steps as subprocesses, one job at a time (a big model takes
minutes and several GB), with each step's status and log in `jobs/<id>.json`.

The drape (about 40 minutes with Style3D) has a queue of its own, so it never holds up the other
models; after a calculation that ends with `export`, the drape follows by itself and its result
is kept with the model (ADR-059)."""

from __future__ import annotations

import contextlib
import json
import os
import queue
import shutil
import signal
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
# cover drawing-build: route A, a drawing read and built as a cover (ADR-081)
EXTRA_STEPS = ["improve", "ai", "rain", "drape", "drawing-build", "drawing-ai"]
LONG_STEPS = {"drape"}  # a job of only these runs in the second queue
DRAPE_WORKERS = 4  # drapes side by side (one core each; the server has 8)


CACHED = ("hull", "cut", "flatten", "export")  # steps that skip themselves when unchanged


@dataclass
class JobSpec:
    model_id: str
    steps: list[str]
    trial: dict[str, Any]
    source: str | None = None  # the uploaded file (for the import step)
    units: str | None = None
    up: str | None = None
    force: bool = False  # calculate even the steps whose inputs did not change (ADR-080)


class Jobs:
    def __init__(
        self, store: Store, drape_after_export: bool = True, drape_workers: int = DRAPE_WORKERS
    ) -> None:
        self.store = store
        self.drape_after_export = drape_after_export
        self._queue: queue.Queue[tuple[str, JobSpec]] = queue.Queue()
        self._long: queue.Queue[tuple[str, JobSpec]] = queue.Queue()
        threading.Thread(target=self._work, args=(self._queue,), daemon=True).start()
        # Style3D works on one CPU core, so several drapes can run side by side
        for _ in range(max(1, drape_workers)):
            threading.Thread(target=self._work, args=(self._long,), daemon=True).start()

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
        long = bool(spec.steps) and set(spec.steps) <= LONG_STEPS
        (self._long if long else self._queue).put((job_id, spec))
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

    def _work(self, q: queue.Queue[tuple[str, JobSpec]]) -> None:
        while True:
            job_id, spec = q.get()
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
                if spec.force and name in CACHED:
                    args.append("--force")
            step["status"], step["started"] = "running", time.time()
            self._write(doc)
            timeout_s, as_mb, cpu_s = job_limits()
            # limits.job_* (ADR-123): one runaway step ends, not the server; its own process
            # group, so a step's helpers end with it
            proc = subprocess.Popen(
                [sys.executable, "-m", "coverapi.limited", str(as_mb), str(cpu_s),
                 "coverengine.cli", *args],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                start_new_session=True,
            )  # fmt: skip
            try:
                out, err = proc.communicate(timeout=timeout_s or None)
                code = proc.returncode
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)
                out, err = proc.communicate()
                err += f"\nerror: took longer than {timeout_s} s (limits.job_timeout_s)"
                code = -1
            step["log"] = (out + err)[-LOG_TAIL:]
            step["finished"] = time.time()
            step["status"] = "done" if code == 0 else "failed"
            self._write(doc)
            if code != 0:
                doc["status"] = "failed"
                doc["error"] = _last_error(err) or _killed(code) or f"cover {name} failed"
                self._write(doc)
                return
        doc["status"], doc["finished"] = "done", time.time()
        self._write(doc)
        # a model calculated to the end gets its drape (and the rain on it), kept with the model;
        # not after a trial run, which is not saved
        if self.drape_after_export and "export" in spec.steps and not spec.trial:
            self.submit(JobSpec(spec.model_id, ["drape"], {}))


def job_limits() -> tuple[int, int, int]:
    """(wall seconds, address space MiB, CPU seconds) for one step; 0: no limit."""
    from coverengine.params import Registry

    p = Registry.load(None).resolve()
    timeout = int(p["limits.job_timeout_s"])  # type: ignore[arg-type]
    # CPU time: the wall time on every core; a backstop for a step that spins without end
    return timeout, int(p["limits.job_memory_mb"]), timeout * (os.cpu_count() or 1)  # type: ignore[arg-type]


def _killed(code: int) -> str | None:
    """A step ended by a signal: say which limit it likely met."""
    if code in (-signal.SIGXCPU, -signal.SIGKILL):
        return "the step was stopped: it used more CPU time than limits.job_timeout_s allows"
    if code == -signal.SIGSEGV:
        return "the step crashed (perhaps out of memory: limits.job_memory_mb)"
    return None


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
