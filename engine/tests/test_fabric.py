import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from coverengine.flatten.pattern import compensation
from coverengine.params import Registry
from coverengine.params.registry import repo_root


def load_script() -> Any:
    path = repo_root() / "scripts" / "fabric_profile.py"
    spec = importlib.util.spec_from_file_location("fabric_profile", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_measurements_become_a_profile(tmp_path: Path) -> None:
    fp = load_script()
    m = json.loads((repo_root() / "testdata/fabrics/measurements.template.json").read_text())
    m["fabric"] = "test-fabric"
    m["stretch_mm"] = {"warp": [201, 201, 201], "weft": [202, 202, 202], "bias": [206, 206, 206]}
    m["relaxed_mm"] = {"warp": [200.2, 200.2, 200.2]}
    m["weld"] = {
        "along": {"before_mm": 300, "after_mm": [299.4, 299.4, 299.4]},
        "across": {"before_mm": 300, "after_mm": [298.5, 298.5, 298.5]},
    }
    m["thickness_mm"] = [0.6, 0.62, 0.61]
    src = tmp_path / "test-fabric.measurements.json"
    src.write_text(json.dumps(m))
    assert fp.main([str(src)]) == 0
    doc = json.loads((tmp_path / "test-fabric.json").read_text())
    assert doc["status"] == "measured"
    assert doc["stretch_pct"] == {"warp": 0.5, "weft": 1.0, "bias": 3.0}
    assert doc["weld_shrinkage_pct"] == {"along": 0.2, "across": 0.5}
    assert doc["thickness_mm"] == pytest.approx(0.61)


def test_compensation_off_by_default_and_the_warp_weft_mean_when_on() -> None:
    reg = Registry.load()
    assert compensation(reg.resolve()) == 1.0
    on = reg.resolve(trial={"flatten.fabric_compensation": True})
    # the placeholder acrylic profile: warp 0.5 %, weft 1.0 % -> 1 / 1.0075
    assert compensation(on) == pytest.approx(1 / 1.0075)
