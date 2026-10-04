"""The customer's furniture in 3D from rough sizes (ADR-062): a recognisable model under the
cover in the shop's configurator, and the support for the rain check. Sizes in cm in, mesh in mm
out (Z up, on the ground, centred on x and y like the cover from `drawn.scene`).
"""

from __future__ import annotations

from typing import Any

import trimesh


def _join(meshes: Any) -> trimesh.Trimesh:
    m = trimesh.util.concatenate(list(meshes))
    assert isinstance(m, trimesh.Trimesh)
    return m


MM_PER_CM = 10.0  # param-ok: unit conversion
# proportions of a generic piece of furniture (display only)
LEG_CM = 6.0  # param-ok: display
TOP_CM = 4.0  # param-ok: display
SEAT_W_CM = 46.0  # param-ok: display: a dining chair's width
SEAT_D_CM = 45.0  # param-ok: display
SEAT_H_CM = 46.0  # param-ok: display
CHAIR_BACK_CM = 90.0  # param-ok: display
ARM_CM = 14.0  # param-ok: display
BACK_CM = 18.0  # param-ok: display
LOUNGER_BACK_CM = 52.0  # param-ok: display: the raised back of a lounger
HALF = 0.5  # param-ok: the middle of a place
CHAIR_BACK_THICK_CM = 4.5  # param-ok: display
CHAIR_GAP_CM = 4.5  # param-ok: display


def _box(x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> trimesh.Trimesh:
    b = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
    b.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
    return b


def build(product: str, v: dict[str, Any]) -> trimesh.Trimesh:
    """The furniture as one mesh (mm), centred on the origin in plan."""
    cm = MM_PER_CM
    parts: list[trimesh.Trimesh] = []
    if product in ("dining_set", "round_set"):
        h = float(v["table_height_cm"])
        if product == "round_set":
            r = float(v["table_diameter_cm"]) / 2
            top = trimesh.creation.cylinder(radius=r * cm, height=TOP_CM * cm, sections=64)
            top.apply_translation((0, 0, (h - TOP_CM / 2) * cm))
            parts += [top, _box(-LEG_CM, -LEG_CM, 0, LEG_CM, LEG_CM, h - TOP_CM).apply_scale(cm)]
            lx, wy = r, r
        else:
            lx = float(v["table_length_cm"]) / 2
            wy = float(v["table_width_cm"]) / 2
            parts.append(_box(-lx, -wy, h - TOP_CM, lx, wy, h).apply_scale(cm))
            for sx in (-1, 1):
                for sy in (-1, 1):
                    x, y = sx * (lx - 2 * LEG_CM), sy * (wy - 2 * LEG_CM)
                    parts.append(
                        _box(
                            x - LEG_CM / 2,
                            y - LEG_CM / 2,
                            0,
                            x + LEG_CM / 2,
                            y + LEG_CM / 2,
                            h - TOP_CM,
                        ).apply_scale(cm)  # fmt: skip
                    )
        if v.get("chairs", True):
            n = max(1, int(2 * lx // (SEAT_W_CM + 14)))  # param-ok: chairs per long side
            xs = [-lx + (i + HALF) * 2 * lx / n for i in range(n)]
            for sy in (-1, 1):
                for x in xs:
                    y0 = sy * (wy + CHAIR_GAP_CM)  # the chair just pulled up
                    y1 = y0 + sy * SEAT_D_CM
                    ya, yb = min(y0, y1), max(y0, y1)
                    parts.append(
                        _box(
                            x - SEAT_W_CM / 2, ya, 0, x + SEAT_W_CM / 2, yb, SEAT_H_CM
                        ).apply_scale(cm)
                    )
                    back = yb - CHAIR_BACK_THICK_CM if sy > 0 else ya
                    parts.append(
                        _box(
                            x - SEAT_W_CM / 2,
                            back,
                            SEAT_H_CM,
                            x + SEAT_W_CM / 2,
                            back + CHAIR_BACK_THICK_CM,
                            CHAIR_BACK_CM,
                        ).apply_scale(cm)  # fmt: skip
                    )
    elif product == "sofa":
        L, D = float(v["length_cm"]), float(v["depth_cm"])
        hb, hf = float(v["back_height_cm"]), float(v["front_height_cm"])
        seat = hf * 0.7  # param-ok: display: the seat below the arms
        parts += [
            _box(-L / 2, -D / 2, 0, L / 2, D / 2, seat),
            _box(-L / 2, D / 2 - BACK_CM, 0, L / 2, D / 2, hb),
            _box(-L / 2, -D / 2, 0, -L / 2 + ARM_CM, D / 2, hf),
            _box(L / 2 - ARM_CM, -D / 2, 0, L / 2, D / 2, hf),
        ]
        parts = [p.apply_scale(cm) for p in parts]
    elif product == "corner_sofa":
        X, Y = float(v["long_side_cm"]), float(v["short_side_cm"])
        D = float(v["depth_cm"])
        hb, hf = float(v["back_height_cm"]), float(v["front_height_cm"])
        seat = hf * 0.7  # param-ok: display
        # the outside corner at (-X/2, +Y/2): the long arm along the back, the short one on the left
        x0, y1 = -X / 2, Y / 2
        parts += [
            _box(x0, y1 - D, 0, X / 2, y1, seat),
            _box(x0, -Y / 2, 0, x0 + D, y1, seat),
            _box(x0, y1 - BACK_CM, 0, X / 2, y1, hb),
            _box(x0, -Y / 2, 0, x0 + BACK_CM, y1, hb),
            _box(X / 2 - ARM_CM, y1 - D, 0, X / 2, y1, hf),
            _box(x0, -Y / 2, 0, x0 + D, -Y / 2 + ARM_CM, hf),
        ]
        parts = [p.apply_scale(cm) for p in parts]
    elif product == "lounger":
        L, W, H = (
            float(v["length_cm"]),
            float(v["width_cm"]),
            float(v["height_cm"]),
        )  # param-ok  # noqa: E501
        parts += [_box(-L / 2, -W / 2, 0, L / 2, W / 2, H * 0.6),  # param-ok: display
                  _box(L / 2 - LOUNGER_BACK_CM, -W / 2, 0, L / 2, W / 2, H)]  # fmt: skip
        parts = [p.apply_scale(cm) for p in parts]
    else:
        L, W, H = (
            float(v["length_cm"]),
            float(v["width_cm"]),
            float(v["height_cm"]),
        )  # param-ok  # noqa: E501
        parts.append(_box(-L / 2, -W / 2, 0, L / 2, W / 2, H).apply_scale(cm))
    return _join(parts)
