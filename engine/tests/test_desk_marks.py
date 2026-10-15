"""scripts/desk_marks.py draws the cover's current vents on a Desk picture (ADR-138): Rens marked
C27 and S32 on 14 Oct 2026 on the vents of 9 Oct (the Desk's 3D was cached), which shows only when
the current vents are put next to his marks."""

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
from coverengine.params.registry import repo_root


def _module():
    path = repo_root() / "scripts" / "desk_marks.py"
    spec = importlib.util.spec_from_file_location("desk_marks", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["desk_marks"] = mod
    spec.loader.exec_module(mod)
    return mod


def _vent(number: int, x: float, normal: tuple[float, float]) -> dict:
    n = np.array([*normal, 0.0])
    side = np.array([-normal[1], normal[0], 0.0]) * 125
    c = np.array([x, 0.0, 160.0])
    corners = [c - side - [0, 0, 110], c + side - [0, 0, 110], c + side + [0, 0, 110],
               c - side + [0, 0, 110]]  # fmt: skip
    return {"number": number, "piece": f"skirt-{number}", "centre_mm": c.tolist(),
            "normal": n.tolist(), "corners_mm": [p.tolist() for p in corners]}  # fmt: skip


def test_the_current_vents_in_the_picture(tmp_path: Path) -> None:
    dm = _module()
    # a camera in front (-y), looking at the origin
    cam = dm.Cam(np.array([math.radians(270), math.radians(10), 2.0, 0, 0, 0]),
                 np.zeros(3), 1000.0, 800, 600)  # fmt: skip
    vents = [_vent(1, -300, (0, -1)), _vent(2, 300, (0, 1))]
    (tmp_path / "vents.json").write_text(json.dumps({"vents": vents}))
    boxes = dm.vent_boxes(cam, tmp_path)
    assert [b["number"] for b in boxes] == [1, 2]
    assert boxes[0]["seen"] and not boxes[1]["seen"]  # the second faces away
    xs = [np.mean([c[0] for c in b["corners_px"]]) for b in boxes]
    assert xs[0] < 400 < xs[1]  # left of the middle, right of it
    assert dm.vent_boxes(cam, tmp_path / "none") == []
