"""Every stylesheet of the web app closes every rule it opens. An unclosed rule left by a merge
(desk.css, 9 Oct 2026) made the browser nest the rest of the studio's styles inside it, and the
studio showed unstyled pages; prettier accepts it because CSS nesting is valid syntax."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[3] / "apps" / "web" / "src"


def test_every_stylesheet_closes_its_rules() -> None:
    sheets = sorted(WEB.rglob("*.css"))
    assert sheets
    for css in sheets:
        text = re.sub(r"/\*.*?\*/", "", css.read_text(encoding="utf-8"), flags=re.S)
        depth = 0
        for line_no, line in enumerate(text.splitlines(), 1):
            depth += line.count("{") - line.count("}")
            assert depth >= 0, f"{css.name}:{line_no}: a '}}' closes nothing"
        assert depth == 0, f"{css.name}: {depth} rule(s) left open"
