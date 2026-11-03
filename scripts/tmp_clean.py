"""Clean-up of the agents' scratch, the release scratch, pytest's temp folders and merged git
worktrees (ADR-153); scripts/housekeeping.sh runs it nightly.

    uv run python scripts/tmp_clean.py [--dry-run] [--days 7] [--root DIR ...] [--repo DIR]

Scratch roots (default ~/cover-data/tmp-agents, ~/cover-data/tmp-release and
/tmp/pytest-of-<user>): every entry directly in a root is a workspace. A workspace is left
alone when anything in it changed in the last --days days, when any folder in it holds a *.pid
file whose process is alive, or when it starts with a dot (sandbox mount points). Otherwise it
is removed whole, except its reports: report.md, summary.md, *.txt and *.json at its top
level stay, everything else in it (the big stage/, base/, work/ copies) goes. Loose files
directly in a root follow the same rules; their reports stay too. Nothing outside a root is
touched: symbolic links are removed as links, never followed; a root that is itself a link
is skipped.

Worktrees under <repo>/.claude/worktrees: removed with `git worktree remove` (never --force)
when the branch (or a detached HEAD) is merged into main, nothing is uncommitted or untracked,
it is not locked and nothing in it changed for --days days; then `git branch -d` (never -D).

Prints every removal and the space freed; --dry-run only prints, and reads nothing but sizes.
"""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

DAYS = 7
REPORT_NAMES = {"report.md", "summary.md"}
REPORT_SUFFIXES = {".txt", ".json"}
SKIP_WALK = {"node_modules", ".venv"}  # links or caches in worktrees: not their own changes


def default_roots() -> list[Path]:
    data = Path(os.environ.get("COVER_DATA_DIR", Path.home() / "cover-data"))
    return [
        data / "tmp-agents",
        data / "tmp-release",
        Path("/tmp") / f"pytest-of-{getpass.getuser()}",  # noqa: S108 - pytest's own place
    ]


@dataclass
class Result:
    removed: list[tuple[str, int]] = field(default_factory=list)
    kept: list[tuple[str, str]] = field(default_factory=list)

    @property
    def freed(self) -> int:
        return sum(n for _, n in self.removed)


def _entries(path: Path) -> Iterator[os.DirEntry[str]]:
    try:
        with os.scandir(path) as it:
            yield from it
    except OSError:
        return


def size(path: Path) -> int:
    """Bytes its removal frees: symbolic links count as links, and a file with more hard links
    (a .venv's packages share the uv cache's) counts nothing, its data stays on disk."""
    try:
        st = path.lstat()
    except OSError:
        return 0
    is_dir = path.is_dir() and not path.is_symlink()
    if not is_dir and st.st_nlink > 1:
        return 0
    total = st.st_blocks * 512
    if is_dir:
        for e in _entries(path):
            total += size(Path(e.path))
    return total


def changed_since(path: Path, cutoff: float, skip: set[str] | None = None) -> bool:
    """True as soon as anything in the tree changed after `cutoff` (stops at the first)."""
    try:
        if path.lstat().st_mtime > cutoff:
            return True
    except OSError:
        return False
    if path.is_dir() and not path.is_symlink():
        for e in _entries(path):
            if skip and e.name in skip:
                continue
            if changed_since(Path(e.path), cutoff, skip):
                return True
    return False


def pid_alive(pid_file: Path) -> bool:
    try:
        pid = int(pid_file.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return False
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)  # signal 0: only asks whether it exists
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # someone else's process, but alive
    return True


def live_pids(path: Path) -> list[Path]:
    """Every *.pid file in the tree whose process is still alive."""
    if path.is_symlink():
        return []
    if path.is_file():
        return [path] if path.suffix == ".pid" and pid_alive(path) else []
    out: list[Path] = []
    for e in _entries(path):
        out += live_pids(Path(e.path))
    return out


def is_report(name: str) -> bool:
    return name in REPORT_NAMES or Path(name).suffix in REPORT_SUFFIXES


def _remove(path: Path, root: Path, dry_run: bool, res: Result, why: str) -> None:
    # never outside the root: the parent is the real root (or below it), the entry itself is
    # removed as what it is (a link stays a link)
    real_parent = path.parent.resolve()
    if real_parent != root and root not in real_parent.parents:
        res.kept.append((str(path), "outside the root"))
        return
    n = size(path)
    if not dry_run:
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError as exc:
            res.kept.append((str(path), f"could not remove: {exc}"))
            return
    res.removed.append((f"{path} ({why})", n))


def clean_root(root: Path, cutoff: float, dry_run: bool, res: Result) -> None:
    if root.is_symlink() or not root.is_dir():
        if root.is_symlink():
            res.kept.append((str(root), "the root is a link: skipped"))
        return
    root = root.resolve()
    live_stems = {p.stem for p in live_pids_shallow(root)}
    for e in sorted(_entries(root), key=lambda e: e.name):
        path = Path(e.path)
        if e.name.startswith("."):
            res.kept.append((str(path), "hidden"))
            continue
        if changed_since(path, cutoff):
            res.kept.append((str(path), "changed in the last days"))
            continue
        if e.is_dir(follow_symlinks=False):
            alive = live_pids(path)
            if alive:
                res.kept.append((str(path), f"a live process: {alive[0].name}"))
                continue
            reports = [c for c in _entries(path) if c.is_file(follow_symlinks=False)
                       and is_report(c.name)]  # fmt: skip
            if not reports:
                _remove(path, root, dry_run, res, "old workspace")
                continue
            for c in sorted(_entries(path), key=lambda c: c.name):
                if c.is_file(follow_symlinks=False) and is_report(c.name):
                    continue
                _remove(Path(c.path), root, dry_run, res, "old, reports kept")
            continue
        # a loose file or link directly in the root
        if Path(e.name).stem in live_stems:
            res.kept.append((str(path), "belongs to a live process"))
            continue
        if e.is_file(follow_symlinks=False) and is_report(e.name):
            res.kept.append((str(path), "report"))
            continue
        _remove(path, root, dry_run, res, "old file")


def live_pids_shallow(root: Path) -> list[Path]:
    return [Path(e.path) for e in _entries(root)
            if e.name.endswith(".pid") and e.is_file(follow_symlinks=False)
            and pid_alive(Path(e.path))]  # fmt: skip


# ---- git worktrees ---------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def worktrees(repo: Path) -> list[dict[str, str]]:
    out = _git(repo, "worktree", "list", "--porcelain").stdout
    items: list[dict[str, str]] = []
    for block in out.strip().split("\n\n"):
        item: dict[str, str] = {}
        for line in block.splitlines():
            k, _, v = line.partition(" ")
            item[k] = v
        if "worktree" in item:
            items.append(item)
    return items


def clean_worktrees(
    repo: Path, cutoff: float, dry_run: bool, res: Result, main: str = "main"
) -> None:
    base = (repo / ".claude" / "worktrees").resolve()
    if not base.is_dir():
        return
    for wt in worktrees(repo):
        path = Path(wt["worktree"])
        if base not in path.resolve().parents:
            continue  # only the agents' worktrees: never the main checkout or a release
        branch = wt.get("branch", "").removeprefix("refs/heads/")
        name = f"worktree {path.name}" + (f" [{branch}]" if branch else " (detached)")
        if "locked" in wt:
            res.kept.append((name, "locked"))
            continue
        if "prunable" in wt or not path.is_dir():
            res.kept.append((name, "folder missing: git worktree prune"))
            continue
        head = wt.get("HEAD", "")
        if _git(repo, "merge-base", "--is-ancestor", head, main).returncode != 0:
            res.kept.append((name, f"not merged into {main}"))
            continue
        # --no-optional-locks: a dry run does not even refresh the worktree's index
        status = _git(path, "--no-optional-locks", "status", "--porcelain",
                      "--untracked-files=normal")  # fmt: skip
        if status.returncode != 0 or status.stdout.strip():
            res.kept.append((name, "uncommitted or untracked changes"))
            continue
        tip = _git(repo, "log", "-1", "--format=%ct", head).stdout.strip()
        if (tip and float(tip) > cutoff) or changed_since(path, cutoff, SKIP_WALK):
            res.kept.append((name, "changed in the last days"))
            continue
        n = size(path)
        if dry_run:
            res.removed.append((f"{name} (merged, unchanged)", n))
            continue
        r = _git(repo, "worktree", "remove", str(path))
        if r.returncode != 0:
            res.kept.append((name, f"git worktree remove refused: {r.stderr.strip()}"))
            continue
        res.removed.append((f"{name} (merged, unchanged)", n))
        if branch:
            d = _git(repo, "branch", "-d", branch)
            if d.returncode != 0:
                res.kept.append((f"branch {branch}", f"git branch -d refused: {d.stderr.strip()}"))


# ---- main ------------------------------------------------------------------------------------


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def run(roots: list[Path], repo: Path | None, days: float, dry_run: bool,
        now: float | None = None) -> Result:  # fmt: skip
    cutoff = (now if now is not None else time.time()) - days * 86400
    res = Result()
    for root in roots:
        clean_root(root, cutoff, dry_run, res)
    if repo is not None:
        clean_worktrees(repo, cutoff, dry_run, res)
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry-run", action="store_true", help="only print what would go")
    ap.add_argument("--days", type=float, default=DAYS)
    ap.add_argument("--root", action="append", type=Path, help="a scratch root (repeatable)")
    ap.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--no-worktrees", action="store_true")
    ap.add_argument("--verbose", action="store_true", help="also say what stays and why")
    a = ap.parse_args(argv)
    roots = a.root or default_roots()
    res = run(roots, None if a.no_worktrees else a.repo, a.days, a.dry_run)
    verb = "would remove" if a.dry_run else "removed"
    for what, n in res.removed:
        print(f"{verb}: {what}, {human(n)}")
    for what, why in res.kept:
        if a.verbose or why.startswith(("could not", "git ")):
            print(f"kept: {what}: {why}")
    print(f"clean-up: {len(res.removed)} {verb}, {human(res.freed)} "
          f"{'would be ' if a.dry_run else ''}freed")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
