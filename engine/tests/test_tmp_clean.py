"""The nightly scratch clean-up (ADR-153, scripts/tmp_clean.py): a temp tree with old and new
workspaces, live and dead pid files, reports and a link out of the root; and merged, unmerged,
dirty, locked and recent git worktrees. Checks exactly what stays and what goes."""

import importlib.util
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/tmp_clean.py"
NOW = time.time()
OLD = NOW - 30 * 86400
DAY = 86400


@pytest.fixture(scope="module")
def tc() -> Any:
    spec = importlib.util.spec_from_file_location("tmp_clean_test", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # its dataclass looks itself up there
    spec.loader.exec_module(mod)
    return mod


def age(path: Path, when: float = OLD) -> None:
    """Set the whole tree's times (deepest first, so a folder's own time sticks)."""
    if path.is_dir() and not path.is_symlink():
        for c in path.iterdir():
            age(c, when)
    os.utime(path, (when, when), follow_symlinks=False)


def write(path: Path, text: str = "x" * 5000) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def dead_pid() -> int:
    p = subprocess.Popen(["true"])
    p.wait()
    return p.pid


def build(tmp: Path) -> tuple[Path, Path]:
    root, outside = tmp / "tmp-agents", tmp / "outside"
    write(outside / "precious.bin")
    # an old workspace with reports: the reports stay, the copies go
    ws = root / "drape-run"
    write(ws / "report.md")
    write(ws / "summary.md")
    write(ws / "scores.json")
    write(ws / "notes.txt")
    write(ws / "run.log")
    write(ws / "stage" / "model" / "cut.dxf")
    write(ws / "base" / "a.glb")
    write(ws / "work" / "deep" / "b.glb")
    write(ws / "nested" / "report.md")  # not at the top level: goes with its folder
    # an old workspace without reports: goes whole
    write(root / "scratch" / "big.bin")
    # an old workspace whose process still runs (the pid file deep inside)
    write(root / "live-run" / "work" / "job.pid", str(os.getpid()))
    write(root / "live-run" / "work" / "big.bin")
    # an old workspace with a dead pid: goes
    write(root / "dead-run" / "job.pid", str(dead_pid()))
    # a workspace with one file changed yesterday: stays whole
    write(root / "recent-run" / "stage" / "old.bin")
    write(root / "recent-run" / "stage" / "new.bin")
    # loose files in the root
    write(root / "old.log")
    write(root / "review1.txt")  # a report: stays
    write(root / "mcp.pid", str(os.getpid()))  # live: it and its namesakes stay
    write(root / "mcp.log")
    write(root / "uv-123.lock", "")
    write(root / ".codex" / "x")  # hidden: a sandbox's mount point
    (root / "escape").symlink_to(outside)  # a link out of the root: removed as a link only
    (root / "dangling").symlink_to(tmp / "nowhere")
    age(root)
    age(outside)
    os.utime(root / "recent-run" / "stage" / "new.bin", (NOW - DAY, NOW - DAY))
    write(root / "fresh" / "x.bin")  # made today
    return root, outside


def names(paths: list[tuple[str, Any]], root: Path) -> set[str]:
    return {str(Path(p.split(" (")[0]).relative_to(root)) for p, _ in paths}


def test_what_stays_and_what_goes(tc: Any, tmp_path: Path) -> None:
    root, outside = build(tmp_path)
    expect_gone = {
        "drape-run/run.log", "drape-run/stage", "drape-run/base", "drape-run/work",
        "drape-run/nested", "scratch", "dead-run", "old.log", "uv-123.lock", "escape", "dangling",
    }  # fmt: skip
    # a dry run says what would go and touches nothing
    dry = tc.run([root], None, 7, dry_run=True, now=NOW)
    assert names(dry.removed, root) == expect_gone
    assert dry.freed > 0
    assert (root / "scratch").is_dir() and (root / "drape-run" / "stage").is_dir()
    res = tc.run([root], None, 7, dry_run=False, now=NOW)
    assert names(res.removed, root) == expect_gone
    left = {str(p.relative_to(root)) for p in root.rglob("*")}
    for kept in (
        "drape-run/report.md", "drape-run/summary.md", "drape-run/scores.json",
        "drape-run/notes.txt", "live-run/work/job.pid", "live-run/work/big.bin",
        "recent-run/stage/old.bin", "recent-run/stage/new.bin", "review1.txt", "mcp.pid",
        "mcp.log", ".codex/x", "fresh/x.bin",
    ):  # fmt: skip
        assert kept in left, kept
    for gone in expect_gone:
        assert gone not in left, gone
    assert set(os.listdir(root / "drape-run")) == {
        "report.md",
        "summary.md",
        "scores.json",
        "notes.txt",
    }
    assert (outside / "precious.bin").is_file()  # the link went, never its target
    # a second night: only the reports are left, nothing more goes
    age(root / "drape-run")
    assert tc.run([root], None, 7, dry_run=False, now=NOW).removed == []


def test_a_root_that_is_a_link_or_missing_is_skipped(tc: Any, tmp_path: Path) -> None:
    real = tmp_path / "real"
    write(real / "ws" / "big.bin")
    age(real)
    (tmp_path / "linked").symlink_to(real)
    res = tc.run([tmp_path / "linked", tmp_path / "missing"], None, 7, False, now=NOW)
    assert res.removed == [] and (real / "ws" / "big.bin").is_file()


# ---- git worktrees ---------------------------------------------------------------------------


def git(cwd: Path, *args: str, when: float = OLD) -> str:
    env = {**os.environ, "GIT_AUTHOR_DATE": f"@{int(when)}", "GIT_COMMITTER_DATE": f"@{int(when)}",
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@x"}  # fmt: skip
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(k, None)
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_merged_unchanged_worktrees_go_never_forced(tc: Any, tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    write(repo / "a.txt", "a")
    write(repo / ".gitignore", "out/\n")
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "a")
    wts = repo / ".claude" / "worktrees"

    def add(name: str, commit: bool = False) -> Path:
        path = wts / name
        git(repo, "worktree", "add", "-q", "-b", name, str(path))
        if commit:
            write(path / f"{name}.txt", name)
            git(path, "add", ".")
            git(path, "commit", "-qm", name)
        return path

    merged = add("merged", commit=True)
    write(merged / "out" / "stage" / "big.bin")  # ignored copies go with the worktree
    git(repo, "merge", "-q", "--ff-only", "merged")
    add("unmerged", commit=True)
    dirty = add("dirty")
    write(dirty / "untracked.txt", "u")
    locked = add("locked")
    git(repo, "worktree", "lock", str(locked))
    add("recent")
    elsewhere = tmp_path / "release"  # a worktree outside .claude/worktrees: never touched
    git(repo, "worktree", "add", "-q", "--detach", str(elsewhere))
    for p in (wts, elsewhere):
        age(p)
    os.utime(wts / "recent" / "a.txt", (NOW - DAY, NOW - DAY))

    dry = tc.run([], repo, 7, dry_run=True, now=NOW)
    assert [w.split(" (")[0] for w, _ in dry.removed] == ["worktree merged [merged]"]
    assert merged.is_dir()
    why = dict(dry.kept)
    assert why["worktree unmerged [unmerged]"] == "not merged into main"
    assert why["worktree dirty [dirty]"] == "uncommitted or untracked changes"
    assert why["worktree locked [locked]"] == "locked"
    assert why["worktree recent [recent]"] == "changed in the last days"

    res = tc.run([], repo, 7, dry_run=False, now=NOW)
    assert [w.split(" (")[0] for w, _ in res.removed] == ["worktree merged [merged]"]
    assert not merged.exists()
    branches = git(repo, "branch", "--format=%(refname:short)").split()
    assert "merged" not in branches and "unmerged" in branches and "dirty" in branches
    for p in ("unmerged", "dirty", "locked", "recent"):
        assert (wts / p).is_dir()
    assert (dirty / "untracked.txt").is_file() and elsewhere.is_dir()
