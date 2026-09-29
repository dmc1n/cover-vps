import importlib

import pytest
from coverengine.cli import main

HEAVY = [
    "OCP",
    "igl",
    "potpourri3d",
    "pymeshlab",
    "manifold3d",
    "trimesh",
    "shapely",
    "ezdxf",
    "skimage",
    "scipy",
]


@pytest.mark.parametrize("name", HEAVY)
def test_heavy_dependency_imports(name: str) -> None:
    importlib.import_module(name)


def test_cover_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.startswith("coverengine ")
