"""Single-stroke font for pen text (labels drawn as lines, not outlined TrueType glyphs).

Glyphs live on a 4 x 6 grid (cap height 6). Each glyph is a string of strokes separated by
`;`, each stroke a list of `x,y` grid points. Zero is slashed so it never reads as the letter O.
Lower case is drawn as upper case. The font is ours, so there is no licence to track.
"""

from __future__ import annotations

from functools import cache

Point = tuple[float, float]

GRID_HEIGHT = 6.0
GLYPH_WIDTH = 4.0
ADVANCE = 6.0  # glyph width plus spacing, in grid units

_GLYPHS: dict[str, str] = {
    "A": "0,0 0,4 2,6 4,4 4,0; 0,3 4,3",
    "B": "0,0 0,6 3,6 4,5 4,4 3,3 0,3; 3,3 4,2 4,1 3,0 0,0",
    "C": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1",
    "D": "0,0 0,6 2,6 4,4 4,2 2,0 0,0",
    "E": "4,6 0,6 0,0 4,0; 0,3 3,3",
    "F": "4,6 0,6 0,0; 0,3 3,3",
    "G": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1 4,3 2,3",
    "H": "0,0 0,6; 4,0 4,6; 0,3 4,3",
    "I": "1,6 3,6; 2,6 2,0; 1,0 3,0",
    "J": "4,6 4,1 3,0 1,0 0,1",
    "K": "0,0 0,6; 4,6 0,2; 1,3 4,0",
    "L": "0,6 0,0 4,0",
    "M": "0,0 0,6 2,3 4,6 4,0",
    "N": "0,0 0,6 4,0 4,6",
    "O": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0",
    "P": "0,0 0,6 3,6 4,5 4,4 3,3 0,3",
    "Q": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0; 2,2 4,0",
    "R": "0,0 0,6 3,6 4,5 4,4 3,3 0,3; 2,3 4,0",
    "S": "4,5 3,6 1,6 0,5 0,4 1,3 3,3 4,2 4,1 3,0 1,0 0,1",
    "T": "0,6 4,6; 2,6 2,0",
    "U": "0,6 0,1 1,0 3,0 4,1 4,6",
    "V": "0,6 2,0 4,6",
    "W": "0,6 1,0 2,3 3,0 4,6",
    "X": "0,0 4,6; 0,6 4,0",
    "Y": "0,6 2,3 4,6; 2,3 2,0",
    "Z": "0,6 4,6 0,0 4,0",
    "0": "1,0 0,1 0,5 1,6 3,6 4,5 4,1 3,0 1,0; 0,1 4,5",
    "1": "1,5 2,6 2,0; 1,0 3,0",
    "2": "0,5 1,6 3,6 4,5 4,4 0,0 4,0",
    "3": "0,5 1,6 3,6 4,5 4,4 3,3 4,2 4,1 3,0 1,0 0,1; 1,3 3,3",
    "4": "3,0 3,6 0,2 4,2",
    "5": "4,6 0,6 0,3 3,3 4,2 4,1 3,0 0,0",
    "6": "4,5 3,6 1,6 0,5 0,1 1,0 3,0 4,1 4,2 3,3 0,3",
    "7": "0,6 4,6 1,0",
    "8": "1,3 0,4 0,5 1,6 3,6 4,5 4,4 3,3 1,3 0,2 0,1 1,0 3,0 4,1 4,2 3,3",
    "9": "0,1 1,0 3,0 4,1 4,5 3,6 1,6 0,5 0,4 1,3 4,3",
    " ": "",
    ".": "2,0 2,0.5",
    ",": "2,1 1,-1",
    "-": "1,3 3,3",
    "+": "2,1 2,5; 0,3 4,3",
    "=": "1,2 3,2; 1,4 3,4",
    "/": "0,0 4,6",
    ":": "2,1 2,1.5; 2,4 2,4.5",
    "(": "3,6 1,4 1,2 3,0",
    ")": "1,6 3,4 3,2 1,0",
    ">": "1,5 3,3 1,1",
    "<": "3,5 1,3 3,1",
}


@cache
def glyph(char: str) -> tuple[tuple[Point, ...], ...]:
    key = char.upper()
    if key not in _GLYPHS:
        raise ValueError(f"stroke font has no glyph for {char!r}")
    strokes = []
    for stroke in _GLYPHS[key].split(";"):
        pts = tuple((float(x), float(y)) for x, y in (p.split(",") for p in stroke.split() if p))
        if pts:
            strokes.append(pts)
    return tuple(strokes)


def supported(char: str) -> bool:
    return char.upper() in _GLYPHS


def text_strokes(text: str, insert: Point, height: float) -> list[list[Point]]:
    """Polylines drawing `text` with its baseline starting at `insert`, cap height `height`."""
    scale = height / GRID_HEIGHT
    x0, y0 = insert
    out: list[list[Point]] = []
    for i, char in enumerate(text):
        ox = x0 + i * ADVANCE * scale
        for stroke in glyph(char):
            out.append([(ox + x * scale, y0 + y * scale) for x, y in stroke])
    return out


def text_width(text: str, height: float) -> float:
    scale = height / GRID_HEIGHT
    if not text:
        return 0.0
    return (len(text) * ADVANCE - (ADVANCE - GLYPH_WIDTH)) * scale
