"""The website's Worker (apps/site, ADR-066, ADR-103) in `make test`: its own tests run with
node's test runner (no Cloudflare, no network): the security headers on every answer, no studio
route through the shop's domain, the preview never indexed."""

import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[2] / "site"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_worker_tests_pass() -> None:
    r = subprocess.run(
        ["node", "--test", "test/worker.test.ts"],  # noqa: S607 - node from PATH
        cwd=SITE,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
