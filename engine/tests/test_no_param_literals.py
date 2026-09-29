"""No numeric literal in engine code may duplicate a registered default (ADR-015, ADR-017).

Exempt: 0, 1, 2, -1 (indices, halves, pairs) and lines marked `# param-ok: <reason>`.
The parameter registry itself (coverengine/params/) is not scanned.
"""

import ast
import re
from pathlib import Path

from coverengine.params import Registry

ENGINE = Path(__file__).resolve().parents[1] / "coverengine"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXEMPT = {0.0, 1.0, 2.0, -1.0}
PARAM_OK = re.compile(r"#\s*param-ok:\s*\S")


def _numeric_literals(tree: ast.AST) -> list[tuple[int, float]]:
    found: list[tuple[int, float]] = []
    negated: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.USub)
            and isinstance(node.operand, ast.Constant)
            and type(node.operand.value) in (int, float)
        ):
            negated.add(id(node.operand))
            found.append((node.lineno, -float(node.operand.value)))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and type(node.value) in (int, float)
            and id(node) not in negated
        ):
            found.append((node.lineno, float(node.value)))
    return found


def scan(path: Path, defaults: dict[float, list[str]]) -> list[str]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    problems = []
    for lineno, value in _numeric_literals(ast.parse(source, str(path))):
        if value in EXEMPT or value not in defaults:
            continue
        if PARAM_OK.search(lines[lineno - 1]):
            continue
        keys = ", ".join(defaults[value])
        problems.append(f"{path}:{lineno}: literal {value:g} duplicates default {keys}")
    return problems


def test_engine_has_no_default_literals() -> None:
    defaults = Registry.load().numeric_defaults()
    files = [p for p in sorted(ENGINE.rglob("*.py")) if "params" not in p.relative_to(ENGINE).parts]
    assert files
    problems = [msg for f in files for msg in scan(f, defaults)]
    assert not problems, "use the parameter registry instead:\n" + "\n".join(problems)


def test_scanner_catches_violations() -> None:
    reg = Registry.from_text("hull:\n  clearance_mm: 10\n  hem_height_mm: -50\nfeatures: 2\n")
    problems = scan(FIXTURES / "literal_violation.py", reg.numeric_defaults())
    lines = sorted(int(p.split(":")[1]) for p in problems)
    assert lines == [4, 5, 6], problems
