"""The studio's colour tokens (Studio 2.0 "A · iOS light", ADR-130) keep their contrast, light and
dark: every text pair at least 4.5:1 (WCAG AA), a field's border and an icon tile at least 3:1
against what is around them (WCAG 1.4.11; the first studio's input borders were 1.7:1)."""

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[3] / "apps" / "web" / "src" / "studio.css"

# text on its background
TEXT = [
    ("ink", "bg"), ("ink", "surface"), ("ink", "stone"), ("ink-2", "surface"),
    ("muted", "bg"), ("muted", "surface"), ("muted", "sunken"), ("muted", "stone"),
    ("accent", "bg"), ("accent", "surface"), ("accent", "accent-soft"),
    ("on-primary", "primary"), ("on-primary", "primary-hover"),
    ("head-ink", "head"), ("head-dim", "head"), ("head-ink", "head-field"),
    ("head-dim", "head-field"),
    ("ok", "ok-soft"), ("ok", "surface"), ("wait", "wait-soft"), ("wait", "surface"),
    ("bad", "bad-soft"), ("bad", "surface"), ("warn", "warn-soft"), ("warn", "surface"),
    ("made", "made-soft"), ("made", "surface"), ("info", "info-soft"),
]  # fmt: skip
# shapes: a field's border, the focus ring, white figures on a count, white glyphs on a tile
SHAPE = [
    ("line-strong", "surface"), ("line-strong", "bg"), ("line-strong", "sunken"),
    ("line-strong", "stone"), ("line-strong", "head"), ("focus", "surface"), ("focus", "bg"),
    # the Cutting file's lines and marks on the drawing's stage (ADR-147)
    ("cv-cut", "stage"), ("cv-pen", "stage"), ("cv-other", "stage"), ("cv-pick", "stage"),
    ("cv-mark-add", "stage"), ("cv-mark-del", "stage"), ("cv-mark-size", "stage"),
    ("cv-mark-pen", "stage"),
]  # fmt: skip
WHITE_ON = ["count", "count-mine"]
TILES = ["tile-blue", "tile-orange", "tile-green", "tile-teal", "tile-indigo", "tile-purple",
         "tile-grey"]  # fmt: skip


def _block(text: str, start: str) -> dict[str, str]:
    i = text.index(start)
    body = text[text.index("{", i) + 1 : text.index("}", i)]
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", body))


def _lum(h: str) -> float:
    def ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def ratio(a: str, b: str) -> float:
    x, y = _lum(a), _lum(b)
    return (max(x, y) + 0.05) / (min(x, y) + 0.05)


def themes() -> dict[str, dict[str, str]]:
    text = CSS.read_text(encoding="utf-8")
    light = _block(text, ":root {")
    dark = {**light, **_block(text, ':root[data-theme="dark"] {')}
    media = {**light, **_block(text, ':root:not([data-theme="light"]) {')}
    return {"light": light, "dark": dark, "dark (computer)": media}


def test_text_pairs_meet_aa() -> None:
    bad = [
        f"{name}: {fg} on {bg} {ratio(t[fg], t[bg]):.2f}"
        for name, t in themes().items()
        for fg, bg in TEXT
        if ratio(t[fg], t[bg]) < 4.5
    ]
    assert not bad, bad


def test_fields_and_shapes_meet_3_to_1() -> None:
    bad = []
    for name, t in themes().items():
        bad += [f"{name}: {a} on {b}" for a, b in SHAPE if ratio(t[a], t[b]) < 3]
        bad += [f"{name}: white on {c}" for c in WHITE_ON if ratio("#ffffff", t[c]) < 4.5]
        bad += [f"{name}: white on {c}" for c in TILES if c in t and ratio("#ffffff", t[c]) < 3]
    assert not bad, bad


def test_both_themes_set_the_same_tokens() -> None:
    t = themes()
    colours = {k for k in t["light"] if not k.startswith("tile-")}
    text = CSS.read_text(encoding="utf-8")
    dark = _block(text, ':root[data-theme="dark"] {')
    media = _block(text, ':root:not([data-theme="light"]) {')
    assert dark == media, "the two dark blocks differ"
    missing = colours - set(dark) - {"tile"}
    assert not missing, f"no dark value for {sorted(missing)}"
