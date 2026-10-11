"""Validate staging paths before creating, deleting or overwriting any output."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def guard_staging_output(dst: Path, src: Path | None = None) -> None:
    """Reject overlapping source/live trees, including symlink aliases.

    Validate the output root as well as each model destination before any writes.
    Existing output symlinks are checked too: file copies may follow them.
    """
    target = dst.expanduser().resolve()
    protected = [REPO_ROOT / "models", Path.home() / "cover-data/models"]
    if src is not None:
        protected.append(src.expanduser())
    roots = [p.resolve() for p in protected]

    def check(path: Path) -> None:
        for root in roots:
            if path.is_relative_to(root) or root.is_relative_to(path):
                raise ValueError(
                    f"Unsafe staging output {dst}: {path} overlaps protected tree {root}"
                )

    check(target)
    if target.is_dir():
        for path in target.rglob("*"):
            if path.is_symlink():
                check(path.resolve())
