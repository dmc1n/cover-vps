"""Parameter registry: `config/defaults.yaml` plus layered overrides.

Layers, later wins: default -> preset -> model (CoverDefinition) -> trial (`--set`).
Every key is a dotted path to a scalar leaf of `defaults.yaml`. Overrides may only set keys that
exist there and must match the default's type. The YAML comments become the help text; a
comment containing "to confirm" or "TODO" marks an unconfirmed assumption, and a comment
containing `a | b | c` with the default among the options makes the key a choice (dropdown).
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from coverengine.errors import CoverError

Scalar = bool | int | float | str

SOURCES = ("default", "preset", "model", "trial")

# Integer defaults on keys with these suffixes are measurements, so a float override is fine.
_MEASURE_SUFFIXES = ("_mm", "_pct", "_deg")

_KEY_LINE = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z_][\w-]*):(?P<rest>.*)$")
_COMMENT_LINE = re.compile(r"^ *#(?P<text>.*)$")
_CHOICES = re.compile(r"[\w-]+(?:\s*\|\s*[\w-]+)+")
_UNCONFIRMED = re.compile(r"to confirm|todo", re.IGNORECASE)


class ParamError(CoverError, ValueError):
    """Invalid parameter file or override; the message is meant for the operator."""


@dataclass(frozen=True)
class ParamSpec:
    key: str
    default: Scalar
    comment: str
    to_confirm: bool
    choices: tuple[str, ...] | None

    @property
    def kind(self) -> str:
        if isinstance(self.default, bool):
            return "bool"
        if isinstance(self.default, int):
            return "number" if self.key.endswith(_MEASURE_SUFFIXES) else "int"
        if isinstance(self.default, float):
            return "number"
        return "choice" if self.choices else "str"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_config_path() -> Path:
    env = os.environ.get("COVER_DEFAULTS")
    return Path(env) if env else repo_root() / "config" / "defaults.yaml"


def _yaml() -> YAML:
    return YAML(typ="safe", pure=True)


def _flatten(tree: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in tree.items():
        path = f"{prefix}{k}"
        if isinstance(v, Mapping):
            out.update(_flatten(v, path + "."))
        else:
            out[path] = v
    return out


def _unflatten(flat: Mapping[str, Any]) -> dict[str, Any]:
    tree: dict[str, Any] = {}
    for key, value in flat.items():
        node = tree
        *parents, leaf = key.split(".")
        for p in parents:
            node = node.setdefault(p, {})
        node[leaf] = value
    return tree


def _scan_comments(text: str) -> dict[str, str]:
    """Map dotted keys to their trailing comment, including indented continuation lines."""
    comments: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    last_key: str | None = None
    for line in text.splitlines():
        m = _KEY_LINE.match(line)
        if m:
            indent = len(m["indent"])
            while stack and stack[-1][0] >= indent:
                stack.pop()
            stack.append((indent, m["key"]))
            last_key = ".".join(k for _, k in stack)
            rest = m["rest"]
            comments[last_key] = rest.split("#", 1)[1].strip() if "#" in rest else ""
            continue
        c = _COMMENT_LINE.match(line)
        if c and last_key is not None and line.startswith(" "):
            comments[last_key] = (comments[last_key] + " " + c["text"].strip()).strip()
        elif not line.strip():
            last_key = None
    return comments


def _choices(comment: str, default: Scalar) -> tuple[str, ...] | None:
    if not isinstance(default, str):
        return None
    for m in _CHOICES.finditer(comment):
        options = tuple(o.strip() for o in m.group(0).split("|"))
        if default in options:
            return options
    return None


class Registry:
    """All registered parameters with their defaults, comments and types."""

    def __init__(self, specs: Iterable[ParamSpec], path: Path | None = None) -> None:
        self.specs: dict[str, ParamSpec] = {s.key: s for s in specs}
        self.path = path

    @classmethod
    def load(cls, path: Path | str | None = None) -> Registry:
        p = Path(path) if path is not None else default_config_path()
        text = p.read_text(encoding="utf-8")
        return cls.from_text(text, p)

    @classmethod
    def from_text(cls, text: str, path: Path | None = None) -> Registry:
        tree = _yaml().load(text) or {}
        if not isinstance(tree, Mapping):
            raise ParamError(f"{path}: top level must be a mapping")
        comments = _scan_comments(text)
        specs = []
        for key, value in _flatten(tree).items():
            if not isinstance(value, bool | int | float | str):
                raise ParamError(f"{path}: {key} must be a single value, got {value!r}")
            comment = comments.get(key, "")
            specs.append(
                ParamSpec(
                    key=key,
                    default=value,
                    comment=comment,
                    to_confirm=bool(_UNCONFIRMED.search(comment)),
                    choices=_choices(comment, value),
                )
            )
        return cls(specs, path)

    def numeric_defaults(self) -> dict[float, list[str]]:
        """Numeric default value -> keys holding it (for the no-literals test)."""
        out: dict[float, list[str]] = {}
        for s in self.specs.values():
            if isinstance(s.default, int | float) and not isinstance(s.default, bool):
                out.setdefault(float(s.default), []).append(s.key)
        return out

    def coerce(self, key: str, value: Any, origin: str) -> Scalar:
        spec = self.specs.get(key)
        if spec is None:
            hint = difflib.get_close_matches(key, self.specs, n=1)
            more = f"; did you mean {hint[0]}?" if hint else ""
            raise ParamError(f"{origin}: unknown parameter {key}{more}")
        kind = spec.kind
        bad = ParamError(f"{origin}: {key} expects {kind}, got {value!r}")
        if kind == "bool":
            if not isinstance(value, bool):
                raise bad
            return value
        if isinstance(value, bool):
            raise bad
        if kind == "int":
            if not isinstance(value, int):
                raise bad
            return value
        if kind == "number":
            if not isinstance(value, int | float):
                raise bad
            return value
        if not isinstance(value, str):
            raise bad
        if spec.choices and value not in spec.choices:
            raise ParamError(
                f"{origin}: {key} must be one of {' | '.join(spec.choices)}, got {value!r}"
            )
        return value

    def resolve(
        self,
        preset: Mapping[str, Any] | None = None,
        model: Mapping[str, Any] | None = None,
        trial: Mapping[str, Any] | None = None,
    ) -> EffectiveParams:
        """Apply override layers. Each layer is a nested tree or a flat dotted-key mapping."""
        values: dict[str, Scalar] = {k: s.default for k, s in self.specs.items()}
        sources: dict[str, str] = dict.fromkeys(self.specs, "default")
        for name, layer in (("preset", preset), ("model", model), ("trial", trial)):
            if not layer:
                continue
            for key, value in _flatten(layer).items():
                values[key] = self.coerce(key, value, name)
                sources[key] = name
        return EffectiveParams(self, values, sources)


class EffectiveParams:
    """The resolved parameter set for one run."""

    # while a step runs, the keys it reads (coverengine.stepcache, ADR-080); None: not noted
    track: set[str] | None = None

    def __init__(
        self, registry: Registry, values: Mapping[str, Scalar], sources: Mapping[str, str]
    ) -> None:
        self.registry = registry
        self._values = dict(values)
        self._sources = dict(sources)

    def __getitem__(self, key: str) -> Scalar:
        value = self._values[key]
        if EffectiveParams.track is not None:
            EffectiveParams.track.add(key)
        return value

    def get(self, key: str) -> Scalar:
        return self[key]

    def peek(self, key: str) -> Scalar:
        """The value without noting it as read (for the step cache's own comparisons)."""
        return self._values[key]

    def source(self, key: str) -> str:
        return self._sources[key]

    def keys(self) -> list[str]:
        return list(self._values)

    def flat(self) -> dict[str, Scalar]:
        return dict(self._values)

    def tree(self) -> dict[str, Any]:
        return _unflatten(self._values)

    def sources(self) -> dict[str, str]:
        return dict(self._sources)

    def hash(self) -> str:
        canonical = json.dumps(self._values, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_set(items: Iterable[str]) -> dict[str, Any]:
    """Parse `key=value` strings; values are YAML scalars (15, 1.5, true, slim)."""
    out: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ParamError(f"--set expects key=value, got {item!r}")
        key, raw = item.split("=", 1)
        out[key.strip()] = _yaml().load(raw) if raw.strip() else ""
    return out


def load_yaml_layer(path: Path | str) -> dict[str, Any]:
    data = _yaml().load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, Mapping):
        raise ParamError(f"{path}: must be a mapping of parameters")
    return dict(data)


def load_cover_definition_layer(path: Path | str) -> dict[str, Any]:
    """The `parameters` subtree of a CoverDefinition JSON file, or of `<model dir>/cover.json`."""
    p = Path(path)
    if p.is_dir():
        p = p / "cover.json"
    if not p.is_file():
        raise ParamError(f"no CoverDefinition at {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    params = data.get("parameters", {})
    if not isinstance(params, Mapping):
        raise ParamError(f"{p}: 'parameters' must be an object")
    return dict(params)


def presets_dir() -> Path:
    return repo_root() / "config" / "presets"


def read_cover_definition(model_dir: Path) -> dict[str, Any]:
    """A model's `cover.json` (empty if it has none)."""
    p = model_dir / "cover.json"
    if not p.is_file():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, Mapping):
        raise ParamError(f"{p}: must be an object")
    return dict(data)


def family_preset(family: str | None) -> dict[str, Any] | None:
    """The family's preset (`config/presets/<family>.yaml`), layer 2."""
    if not family:
        return None
    p = presets_dir() / f"{family}.yaml"
    if not p.is_file():
        raise ParamError(f"no preset for family {family!r} (config/presets/{family}.yaml)")
    return load_yaml_layer(p)


def list_families() -> list[str]:
    d = presets_dir()
    return sorted(p.stem for p in d.glob("*.yaml")) if d.is_dir() else []


def resolve_model(
    model_dir: Path,
    trial: Mapping[str, Any] | None = None,
    registry: Registry | None = None,
    preset: Mapping[str, Any] | None = None,
) -> EffectiveParams:
    """The effective parameters of a model: defaults, its family's preset (unless `preset` is
    given), its own `cover.json`, then the trial overrides."""
    reg = registry or Registry.load()
    cover = read_cover_definition(model_dir)
    layer = cover.get("parameters") or None
    if layer is not None and not isinstance(layer, Mapping):
        raise ParamError(f"{model_dir / 'cover.json'}: 'parameters' must be an object")
    if preset is None:
        preset = family_preset(cover.get("family"))
    return reg.resolve(preset=preset, model=layer, trial=trial)
