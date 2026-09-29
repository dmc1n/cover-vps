"""Parameter registry: layering, types, choices, comments, CLI.

Tests use their own small YAML files so a change of company defaults never breaks them.
"""

import json
from pathlib import Path

import pytest
from coverengine.cli import main
from coverengine.params import ParamError, Registry, parse_set

YAML_TEXT = """\
# header comment, ignored
units: mm                  # do not change

hull:                      # the cover surface
  clearance_mm: 10         # distance to the furniture
  bridge_gap_mm: 60        # gaps narrower than this are bridged;
                           # wider recesses are followed
  hem_height_mm: 50        # to confirm; hem above ground
  smoothing: 0.5
  sweep_down: true

construction:
  method: double_stitch    # double_stitch | welded

flatten:
  iterations: 50
  solver: slim             # slim | arap, TODO check
"""


@pytest.fixture
def defaults(tmp_path: Path) -> Path:
    p = tmp_path / "defaults.yaml"
    p.write_text(YAML_TEXT)
    return p


@pytest.fixture
def registry(defaults: Path) -> Registry:
    return Registry.load(defaults)


def test_defaults_and_sources(registry: Registry) -> None:
    eff = registry.resolve()
    assert eff["hull.clearance_mm"] == 10
    assert eff.source("hull.clearance_mm") == "default"
    assert eff.tree()["hull"]["sweep_down"] is True


def test_layers_later_wins(registry: Registry) -> None:
    eff = registry.resolve(
        preset={"hull": {"clearance_mm": 12, "bridge_gap_mm": 70}},
        model={"hull.clearance_mm": 14},
        trial={"hull.clearance_mm": 15.5},
    )
    assert eff["hull.clearance_mm"] == 15.5
    assert eff.source("hull.clearance_mm") == "trial"
    assert eff["hull.bridge_gap_mm"] == 70
    assert eff.source("hull.bridge_gap_mm") == "preset"
    assert eff.source("hull.smoothing") == "default"


def test_comments_confirm_and_choices(registry: Registry) -> None:
    s = registry.specs
    assert s["hull.bridge_gap_mm"].comment == (
        "gaps narrower than this are bridged; wider recesses are followed"
    )
    assert s["hull.hem_height_mm"].to_confirm
    assert not s["hull.clearance_mm"].to_confirm
    assert s["flatten.solver"].to_confirm  # TODO counts as unconfirmed
    assert s["construction.method"].choices == ("double_stitch", "welded")
    assert s["flatten.solver"].choices == ("slim", "arap")
    assert s["units"].choices is None


def test_unknown_key_suggests(registry: Registry) -> None:
    with pytest.raises(ParamError, match="did you mean hull.clearance_mm"):
        registry.resolve(trial={"hull.clearence_mm": 3})


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("hull.sweep_down", 1),
        ("hull.clearance_mm", "ten"),
        ("hull.clearance_mm", True),
        ("flatten.iterations", 2.5),
        ("construction.method", "glue"),
        ("flatten.solver", 3),
    ],
)
def test_type_errors(registry: Registry, key: str, value: object) -> None:
    with pytest.raises(ParamError):
        registry.resolve(trial={key: value})


def test_measurement_int_accepts_float(registry: Registry) -> None:
    assert registry.resolve(trial={"hull.clearance_mm": 12.5})["hull.clearance_mm"] == 12.5


def test_hash_changes_with_values(registry: Registry) -> None:
    a = registry.resolve()
    assert a.hash() == registry.resolve().hash()
    assert a.hash() != registry.resolve(trial={"hull.clearance_mm": 11}).hash()


def test_parse_set() -> None:
    assert parse_set(["a.b=15", "c=1.5", "d=true", "e=slim"]) == {
        "a.b": 15,
        "c": 1.5,
        "d": True,
        "e": "slim",
    }
    with pytest.raises(ParamError):
        parse_set(["novalue"])


def _params_json(capsys: pytest.CaptureFixture[str], *argv: str) -> dict:
    assert main(["params", "--json", *argv]) == 0
    return json.loads(capsys.readouterr().out)


def test_cli_edit_file_changes_output(defaults: Path, capsys: pytest.CaptureFixture[str]) -> None:
    before = _params_json(capsys, "--defaults", str(defaults))
    assert before["parameters"]["hull"]["clearance_mm"] == 10
    defaults.write_text(YAML_TEXT.replace("clearance_mm: 10", "clearance_mm: 13"))
    after = _params_json(capsys, "--defaults", str(defaults))
    assert after["parameters"]["hull"]["clearance_mm"] == 13
    assert after["parameter_sources"]["hull.clearance_mm"] == "default"
    assert after["parameter_hash"] != before["parameter_hash"]


def test_cli_set_and_model(
    defaults: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    model = tmp_path / "chair-01"
    model.mkdir()
    (model / "cover.json").write_text(
        json.dumps({"format_version": 1, "parameters": {"construction": {"method": "welded"}}})
    )
    doc = _params_json(
        capsys, str(model), "--defaults", str(defaults), "--set", "hull.clearance_mm=15"
    )
    assert doc["parameters"]["hull"]["clearance_mm"] == 15
    assert doc["parameter_sources"]["hull.clearance_mm"] == "trial"
    assert doc["parameters"]["construction"]["method"] == "welded"
    assert doc["parameter_sources"]["construction.method"] == "model"


def test_cli_table_marks(defaults: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["params", "--defaults", str(defaults)]) == 0
    out = capsys.readouterr().out
    line = next(ln for ln in out.splitlines() if ln.startswith("hull.hem_height_mm"))
    assert "* to confirm" in line


def test_cli_error_exit(defaults: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["params", "--defaults", str(defaults), "--set", "nope=1"]) == 1
    assert "unknown parameter" in capsys.readouterr().err


def test_company_defaults_load() -> None:
    """The real config/defaults.yaml parses and every value is a valid scalar."""
    reg = Registry.load()
    eff = reg.resolve()
    assert "hull.clearance_mm" in eff.keys()
    assert reg.specs["construction.method"].choices
