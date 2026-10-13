"""scripts/release.sh --switch and scripts/rollback.sh (ADR-053, ADR-129) with stand-in sudo,
systemctl and curl: a failed restart or health check switches back to the release before, by
itself, and says so; the first install of the service file is left to a person (only
`sudo systemctl restart cover-web` works without a password) and nothing is changed."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"

FAKE_SUDO = """#!/bin/bash
echo "sudo $*" >> "$FAKE_LOG"
if [ "$*" != "-n systemctl restart cover-web" ]; then
  echo "sudo: a password is required" >&2; exit 1
fi
live=$(basename "$(readlink "$COVER_RELEASES/current")")
case " $FAKE_RESTART_FAILS " in *" $live "*) exit 1;; esac
exit 0
"""
FAKE_SYSTEMCTL = """#!/bin/bash
echo "systemctl $*" >> "$FAKE_LOG"
[ "$1" = show ] && echo "$FAKE_WORKDIR"
exit 0
"""
FAKE_CURL = """#!/bin/bash
live=$(basename "$(readlink "$COVER_RELEASES/current")")
case " $FAKE_UNHEALTHY " in *" $live "*) exit 22;; esac
echo "{\\"status\\":\\"ok\\",\\"engine\\":\\"1\\",\\"release\\":\\"$live\\"}"
"""


@pytest.fixture()
def rig(tmp_path: Path) -> dict[str, object]:
    rel = tmp_path / "releases"
    for v in ("v1.0.0", "v1.1.0"):
        (rel / v / ".venv").mkdir(parents=True)
    (rel / "current").symlink_to(rel / "v1.0.0")
    (rel / "history.log").write_text("2026-10-01 10:00:00 v1.0.0 live (before: )\n")
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for name, text in (("sudo", FAKE_SUDO), ("systemctl", FAKE_SYSTEMCTL), ("curl", FAKE_CURL),
                       ("sleep", "#!/bin/sh\nexit 0\n")):  # fmt: skip
        (bin_ / name).write_text(text)
        (bin_ / name).chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_}:{os.environ['PATH']}",
        "COVER_RELEASES": str(rel),
        "COVER_HEALTH_TRIES": "3",
        "FAKE_LOG": str(tmp_path / "calls.log"),
        "FAKE_WORKDIR": str(rel / "current"),
        "FAKE_RESTART_FAILS": "",
        "FAKE_UNHEALTHY": "",
    }
    return {"rel": rel, "env": env, "log": tmp_path / "calls.log"}


def _run(rig: dict[str, object], *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    script = "rollback.sh" if args and args[0] == "rollback" else "release.sh"
    argv = list(args[1:]) if script == "rollback.sh" else ["--switch", *args]
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *argv], env={**rig["env"], **env},  # type: ignore[dict-item]
        capture_output=True, text=True, timeout=60, check=False,
    )  # fmt: skip


def _live(rig: dict[str, object]) -> str:
    return os.readlink(rig["rel"] / "current").rsplit("/", 1)[-1]  # type: ignore[operator]


def test_a_good_switch_goes_live(rig: dict[str, object]) -> None:
    r = _run(rig, "v1.1.0")
    assert r.returncode == 0, r.stderr
    assert _live(rig) == "v1.1.0" and "v1.1.0 is live" in r.stdout
    assert "v1.1.0 live (before: v1.0.0)" in (rig["rel"] / "history.log").read_text()  # type: ignore[operator]


@pytest.mark.parametrize(
    ("env", "why"),
    [({"FAKE_RESTART_FAILS": "v1.1.0"}, "the restart failed"),
     ({"FAKE_UNHEALTHY": "v1.1.0"}, "does not answer as v1.1.0")],
)  # fmt: skip
def test_a_failed_restart_or_health_check_switches_back_by_itself(
    rig: dict[str, object], env: dict[str, str], why: str
) -> None:
    r = _run(rig, "v1.1.0", **env)
    assert r.returncode == 1
    assert why in r.stderr and "switched back to v1.0.0 automatically" in r.stderr
    assert _live(rig) == "v1.0.0"
    hist = (rig["rel"] / "history.log").read_text()  # type: ignore[operator]
    assert "v1.1.0 FAILED" in hist and "switched back to v1.0.0" in hist
    # only the password-free command was used
    calls = rig["log"].read_text().splitlines()  # type: ignore[attr-defined]
    assert {c for c in calls if c.startswith("sudo")} == {"sudo -n systemctl restart cover-web"}


def test_when_the_release_before_fails_too_it_says_so(rig: dict[str, object]) -> None:
    r = _run(rig, "v1.1.0", FAKE_UNHEALTHY="v1.0.0 v1.1.0")
    assert r.returncode == 1 and "does not answer either" in r.stderr
    assert _live(rig) == "v1.0.0"


def test_the_first_install_needs_a_person_and_changes_nothing(rig: dict[str, object]) -> None:
    r = _run(rig, "v1.1.0", FAKE_WORKDIR="/home/dev/cover-pattern-engine")
    assert r.returncode == 2
    assert "needs a person" in r.stderr and "sudo systemctl daemon-reload" in r.stderr
    assert _live(rig) == "v1.0.0"
    assert not rig["log"].read_text().count("sudo")  # type: ignore[attr-defined]


def test_rollback_goes_back_and_a_failed_rollback_returns_to_the_live_one(
    rig: dict[str, object],
) -> None:
    assert _run(rig, "v1.1.0").returncode == 0
    r = _run(rig, "rollback", FAKE_UNHEALTHY="v1.0.0")  # the one before is broken now
    assert r.returncode == 1 and "switched back to v1.1.0 automatically" in r.stderr
    assert _live(rig) == "v1.1.0"
    r = _run(rig, "rollback")
    assert r.returncode == 0 and _live(rig) == "v1.0.0"
