"""The colours of the pieces in every picture of a cover (3D view, cover.png, catalogue): calm
tones from the SUNS and S2DIO house styles, far enough apart to tell neighbouring pieces apart.
"""

from __future__ import annotations

# RGB 0-1, in an order where neighbours differ in both hue and lightness.
PIECES: list[tuple[float, float, float]] = [
    (0.639, 0.557, 0.431),  # sand (SUNS #a38e6e)
    (0.522, 0.533, 0.435),  # sage (S2DIO #85886f)
    (0.784, 0.722, 0.604),  # wheat
    (0.361, 0.400, 0.329),  # olive
    (0.722, 0.506, 0.384),  # clay
    (0.663, 0.675, 0.612),  # sage soft (S2DIO #a9ac9c)
    (0.471, 0.420, 0.353),  # umber
    (0.831, 0.851, 0.800),  # mist (SUNS #d4d9cc)
    (0.549, 0.388, 0.306),  # rust
    (0.443, 0.522, 0.525),  # slate
    (0.894, 0.859, 0.776),  # cream stone
    (0.290, 0.318, 0.263),  # deep olive
]


def piece(i: int) -> tuple[float, float, float]:
    return PIECES[i % len(PIECES)]
