"""Golden `cover info` output for every test model after `cover import` (M1 acceptance).

When an intended change alters the output, regenerate with `make golden` and review the diff.
"""

import os
from pathlib import Path

import pytest
from coverengine.io.info import format_model_info
from coverengine.io.model_io import import_model
from coverengine.params import Registry
from coverengine.params.registry import repo_root
from coverengine.testshapes import BUILDERS, write_all
from test_import import PARAMS

GOLDEN = repo_root() / "testdata" / "golden" / "info"
UPDATE = os.environ.get("COVER_UPDATE_GOLDEN") == "1"
SOURCES = [f"{n}.stl" for n in BUILDERS] + [
    "chair_assembly.step",
    "chair_assembly-inch.step",
    "chair_assembly.iges",
    "chair_faceted.step",
]


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("generated")
    write_all(out)
    return out


@pytest.mark.parametrize("source", SOURCES)
def test_golden_info(generated: Path, tmp_path: Path, source: str) -> None:
    name = source.replace(".", "-")
    out = tmp_path / name
    import_model(generated / source, out, Registry.load().resolve(trial=PARAMS))
    text = format_model_info(out) + "\n"
    golden = GOLDEN / f"{name}.txt"
    if UPDATE:
        GOLDEN.mkdir(parents=True, exist_ok=True)
        golden.write_text(text, encoding="utf-8")
    assert golden.is_file(), f"no golden file {golden}; run make golden"
    assert text == golden.read_text(encoding="utf-8")
