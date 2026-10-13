"""Jobs a stopped server left behind (ADR-129): on start-up they are "interrupted", with the
reason, a step's leftover process group is ended, and "Run again" starts the same job anew."""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest
from coverapi import jobs as jobs_module
from coverapi.main import create_app
from fastapi.testclient import TestClient


def _dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def _job(data: Path, job_id: str, status: str, steps: list[tuple[str, str, Any]],
         owner: dict[str, Any] | None) -> None:  # fmt: skip
    doc = {
        "id": job_id, "model_id": "m", "status": status, "created": time.time(), "trial": {},
        "steps": [{"name": n, "status": s, "log": "", "pid": pid} for n, s, pid in steps],
    }  # fmt: skip
    if owner is not None:
        doc["owner"] = owner
    (data / "jobs").mkdir(parents=True, exist_ok=True)
    (data / "jobs" / f"{job_id}.json").write_text(json.dumps(doc))


def _read(data: Path, job_id: str) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((data / "jobs" / f"{job_id}.json").read_text())
    return out


def test_a_restart_marks_orphaned_jobs_interrupted_and_ends_their_step(tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / "models" / "m").mkdir(parents=True)
    # a step runner that outlived its server (own session, as the job runner starts it)
    leftover = subprocess.Popen(
        [sys.executable, "-m", "coverapi.limited", "0", "0", "timeit", "-n", "1",
         "import time; time.sleep(60)"],
        start_new_session=True,
    )  # fmt: skip
    try:
        dead = {"pid": _dead_pid(), "process": "gone"}
        _job(data, "run1", "running", [("hull", "done", None), ("cut", "running", leftover.pid),
                                       ("flatten", "waiting", None)], dead)  # fmt: skip
        _job(data, "wait1", "queued", [("hull", "waiting", None)], dead)
        _job(data, "old1", "running", [("hull", "running", None)], None)  # before ADR-129
        _job(data, "done1", "done", [("hull", "done", None)], dead)
        # a job of this very process (another app on the same data, still running it)
        _job(data, "live1", "running", [("hull", "running", None)],
             {"pid": 1, "process": jobs_module.PROCESS})  # fmt: skip
        create_app(data)
        run1 = _read(data, "run1")
        assert run1["status"] == "interrupted"
        assert "step cut" in run1["error"] and "run it again" in run1["error"]
        assert [s["status"] for s in run1["steps"]] == ["done", "interrupted", "waiting"]
        assert leftover.wait(timeout=10) != 0  # its process group was ended
        wait1 = _read(data, "wait1")
        assert wait1["status"] == "interrupted" and "before it started" in wait1["error"]
        assert _read(data, "old1")["status"] == "interrupted"
        assert _read(data, "done1")["status"] == "done"
        assert _read(data, "live1")["status"] == "running"
    finally:
        if leftover.poll() is None:
            leftover.kill()


def test_recover_never_ends_a_process_that_is_not_our_step_runner(tmp_path: Path) -> None:
    data = tmp_path / "data"
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                             start_new_session=True)  # fmt: skip
    try:
        _job(data, "j", "running", [("hull", "running", other.pid)], {"pid": _dead_pid()})
        create_app(data)
        assert _read(data, "j")["status"] == "interrupted"
        assert other.poll() is None  # a reused pid of another program is left alone
    finally:
        other.kill()


def test_run_again_starts_the_same_job_and_the_limit_is_shown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ok = tmp_path / "ok.sh"
    ok.write_text("#!/bin/sh\nexit 0\n")
    ok.chmod(0o755)
    monkeypatch.setattr(jobs_module.sys, "executable", str(ok))
    data = tmp_path / "data"
    (data / "models" / "m").mkdir(parents=True)
    _job(data, "run1", "running", [("cut", "running", None), ("flatten", "waiting", None)],
         {"pid": _dead_pid()})  # fmt: skip
    app = create_app(data)
    c = TestClient(app)
    assert c.get("/api/jobs/run1").json()["status"] == "interrupted"
    r = c.post("/api/jobs/run1/rerun")
    assert r.status_code == 200, r.text
    new = r.json()
    assert new["rerun_of"] == "run1" and new["id"] != "run1"
    assert [s["name"] for s in new["steps"]] == ["cut", "flatten"]
    assert new["timeout_s"] == jobs_module.job_limits()[0] > 0  # the studio shows it
    done = app.state.jobs.wait(new["id"], 20)
    assert done["status"] == "done"
    # only an interrupted or failed job runs again
    assert c.post(f"/api/jobs/{new['id']}/rerun").status_code == 409
    assert c.post("/api/jobs/nope/rerun").status_code == 404
