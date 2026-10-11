"""Learning that changes the cover itself (ADR-082).

Until 6 October 2026 a "lesson" was only text in the AI's prompts; the geometry never read it
(the team: "when we apply a learning, it does not show in a new version"). Now a correction
made at the Desk is something the program uses, deterministically:

- **per cover**: a parameter override in the model's `cover.json` (vent count, vent height,
  skirt seam height, ...), or a piece edit in `part_edits.json` (join two pieces where a seam
  should not be; split a piece where one should be), read by the cut (seams/build.py);
- **per family**: when the same parameter correction is made on `desk.learn_after` covers of
  one group, the Desk proposes it as the group's rule; a person accepts it and it is written to
  <data>/learning/rules/<group>.yaml, a layer on top of the family preset that every cover of
  the group then uses (params/registry.resolve_model);
- **as a test**: every correction is kept as a case in <data>/learning/cases/ with what must
  hold afterwards (`evaluate`); `scripts/learned_check.py` replays them all, the measuring rod.

A group is the cover's family (`cover.json` "family") or, for a drawing cover, its series: the
letter of its drawing code (S45 -> drawing-s, "L1 & L5 mirror" -> drawing-l).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import numpy as np

PART_EDITS = "part_edits.json"
NEAR_MM = 40.0  # param-ok: a seam or piece is found within this of the point given
SERIES = re.compile(r"([A-Za-z])\d")
TINY = 1e-6  # param-ok: two numbers this close are the same


# ---- where the learning lives ---------------------------------------------------------------


def data_dir() -> Path | None:
    """The data folder, only when the app says which (COVER_DATA_DIR): a hand-run CLI or a test
    never picks up the server's learned rules by accident (deterministic output, rule 10)."""
    env = os.environ.get("COVER_DATA_DIR")
    return Path(env) if env else None


def rules_dir(base: Path | None = None) -> Path | None:
    base = base or data_dir()
    return base / "learning" / "rules" if base else None


def cases_dir(base: Path | None = None) -> Path | None:
    base = base or data_dir()
    return base / "learning" / "cases" if base else None


def group_of(model_dir: Path, cover: dict[str, Any] | None = None) -> str | None:
    """The group a cover learns with: its family, or the series of its drawing code."""
    if cover is None:
        p = model_dir / "cover.json"
        cover = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    if cover.get("family"):
        return str(cover["family"])
    if not model_dir.name.startswith("drawing-"):
        return None
    code = ""
    desk = model_dir / "desk.json"
    if desk.is_file():
        try:
            code = str(json.loads(desk.read_text(encoding="utf-8")).get("code") or "")
        except (OSError, json.JSONDecodeError):
            code = ""
    m = SERIES.search(code) or SERIES.search(model_dir.name.removeprefix("drawing-"))
    return f"drawing-{m.group(1).lower()}" if m else None


# ---- the rules: a layer on the family preset ------------------------------------------------


def _yaml() -> Any:
    from ruamel.yaml import YAML

    y = YAML()
    y.default_flow_style = False
    return y


def rules(group: str | None, base: Path | None = None) -> dict[str, Any]:
    """The group's learned rules as a parameter tree ({} when none)."""
    d = rules_dir(base)
    if not group or d is None:
        return {}
    p = d / f"{group}.yaml"
    if not p.is_file():
        return {}
    data = _yaml().load(p.read_text(encoding="utf-8")) or {}
    return _plain(data) if isinstance(data, dict) else {}


def _plain(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_plain(v) for v in x]
    return x


def merge(base: dict[str, Any] | None, over: dict[str, Any]) -> dict[str, Any] | None:
    """A deep merge: `over` wins (learned rules on the family preset)."""
    if not over:
        return base
    out: dict[str, Any] = json.loads(json.dumps(base or {}))
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = merge(out[k], v)
        else:
            out[k] = v
    return out


def set_dotted(tree: dict[str, Any], key: str, value: Any) -> None:
    *path, last = key.split(".")
    node = tree
    for part in path:
        node = node.setdefault(part, {})
    node[last] = value


def get_dotted(tree: dict[str, Any], key: str) -> Any:
    node: Any = tree
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def write_rule(group: str, key: str, value: Any, by: str, why: str, base: Path) -> dict[str, Any]:
    """A rule for the whole group, accepted by a person; logged in learning/rules.jsonl."""
    d = rules_dir(base)
    assert d is not None
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{group}.yaml"
    tree = rules(group, base)
    set_dotted(tree, key, value)
    tmp = p.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        fh.write(f"# Learned rules for {group} (ADR-082): accepted at the Desk, a layer on the\n")
        fh.write(
            "# family preset. Every cover of the group uses them; its own settings still win.\n"
        )
        _yaml().dump(tree, fh)
    tmp.replace(p)
    row = {"time": time.time(), "group": group, "key": key, "value": value, "by": by, "why": why}
    with (base / "learning" / "rules.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return row


# ---- the cut's seams and pieces, with a point on each ---------------------------------------


def _json(path: Path) -> dict[str, Any]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, json.JSONDecodeError):
        doc = {}
    return doc if isinstance(doc, dict) else {}


def _nearest(pts: np.ndarray) -> list[float]:
    """The point of `pts` nearest their middle: a point that lies on the seam or piece."""
    c = pts.mean(axis=0)
    return [round(float(x), 1) for x in pts[int(np.argmin(np.linalg.norm(pts - c, axis=1)))]]


def seam_points(model_dir: Path) -> list[dict[str, Any]]:
    """The cover's seams (panels.json) with a point on each in mm (panels.npz)."""
    doc = _json(model_dir / "panels.json")
    seams = doc.get("seams") or []
    names = [str(p.get("name")) for p in doc.get("panels") or []]
    npz = model_dir / "panels.npz"
    mids: dict[int, list[float]] = {}
    if npz.is_file() and seams:
        # a seam is where its two panels meet: the cover's points both panels use (the cut
        # opened the mesh along seams, so the points are found through `original_vertex`)
        z = np.load(npz)
        v, f, lab, orig = z["vertices"], z["faces"], z["labels"], z["original_vertex"]
        own = [set(orig[np.unique(f[lab == k])].tolist()) for k in range(len(names))]
        for i, sm in enumerate(seams):
            pair = sm.get("panels") or []
            if len(pair) != 2 or pair[0] not in names or pair[1] not in names:  # noqa: PLR2004
                continue
            common = own[names.index(pair[0])] & own[names.index(pair[1])]
            pts = v[np.isin(orig, list(common))] if common else np.zeros((0, 3))
            if len(pts):
                mids[i] = _nearest(pts)
    return [{"id": sm.get("id"), "kind": sm.get("kind"), "panels": sm.get("panels"),
             "length_mm": sm.get("length_mm"), "at": mids.get(i)}
            for i, sm in enumerate(seams)]  # fmt: skip


def piece_points(model_dir: Path) -> list[dict[str, Any]]:
    """The cut's pieces with a point on each and their reach in mm, to split one."""
    npz = model_dir / "panels.npz"
    if not npz.is_file():
        return []
    z = np.load(npz)
    v, f, lab = z["vertices"], z["faces"], z["labels"]
    out = []
    for k, p in enumerate(_json(model_dir / "panels.json").get("panels") or []):
        fs = f[lab == k]
        if not len(fs):
            continue
        pts = v[np.unique(fs)]
        out.append({"name": p.get("name"), "region": p.get("region"), "at": _nearest(pts),
                    "min": [round(float(x), 1) for x in pts.min(axis=0)],
                    "max": [round(float(x), 1) for x in pts.max(axis=0)]})  # fmt: skip
    return out


def editable(model_dir: Path) -> bool:
    """Seams that are piece edges (a cover drawn in parts, or a box cover): join and split
    apply; a tensioned cover's seams follow the furniture (the seam editor places those)."""
    return (model_dir / "hull_parts.npy").is_file() or bool(
        _json(model_dir / "panels.json").get("box")
    )


# ---- piece edits: join and split, read by the cut -------------------------------------------


def read_edits(model_dir: Path) -> list[dict[str, Any]]:
    p = model_dir / PART_EDITS
    if not p.is_file():
        return []
    doc = json.loads(p.read_text(encoding="utf-8"))
    return list(doc.get("edits") or [])


def add_edit(model_dir: Path, edit: dict[str, Any]) -> None:
    edits = [*read_edits(model_dir), edit]
    p = model_dir / PART_EDITS
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"format_version": 1, "edits": edits}, indent=1) + "\n", "utf-8")
    tmp.replace(p)


def apply_edits(
    centres: np.ndarray, faces_adj: np.ndarray, label: np.ndarray, edits: list[dict[str, Any]]
) -> tuple[np.ndarray, list[str]]:
    """The pieces after the people's edits. `centres`: each face's centre (mm); `faces_adj`:
    pairs of neighbouring faces; `label`: each face's piece.

    - join {"at": point}: the two pieces whose shared seam passes nearest the point become one;
    - split {"at": point, "axis": "x"|"y"|"z", "value_mm": v}: the piece at the point is cut in
      two where that coordinate is v (faces by their centre).

    Edits that find nothing are reported, never guessed."""
    label = label.copy()
    notes: list[str] = []
    for e in edits:
        p = np.asarray(e.get("at") or [0, 0, 0], dtype=np.float64)
        if e.get("op") == "join":
            a, b = label[faces_adj[:, 0]], label[faces_adj[:, 1]]
            seam = faces_adj[a != b]
            if not len(seam):
                notes.append("join: no seam left on this cover")
                continue
            mid = (centres[seam[:, 0]] + centres[seam[:, 1]]) / 2
            dist = np.linalg.norm(mid - p, axis=1)
            k = int(np.argmin(dist))
            if dist[k] > NEAR_MM * 3:
                notes.append(f"join: no seam within {NEAR_MM * 3:.0f} mm of {p.round(0).tolist()}")
                continue
            la, lb = int(label[seam[k, 0]]), int(label[seam[k, 1]])
            label[label == lb] = la
            notes.append(f"joined two pieces at {p.round(0).tolist()}")
        elif e.get("op") == "split":
            k = int(np.argmin(np.linalg.norm(centres - p, axis=1)))
            piece = label == label[k]
            axis = "xyz".index(str(e.get("axis", "z")))
            v = float(e.get("value_mm", p[axis]))
            side = piece & (centres[:, axis] > v)
            if not side.any() or side.sum() == piece.sum():
                notes.append(f"split: the piece does not reach {e.get('axis', 'z')} = {v:.0f} mm")
                continue
            label[side] = int(label.max()) + 1
            notes.append(f"split a piece at {e.get('axis', 'z')} = {v:.0f} mm")
        else:
            notes.append(f"unknown piece edit {e.get('op')!r}")
    _, label = np.unique(label, return_inverse=True)
    return label.ravel().astype(np.int64), notes


# ---- cases: what must hold after a correction -----------------------------------------------


def write_case(model_dir: Path, case: dict[str, Any], base: Path) -> Path:
    d = cases_dir(base)
    assert d is not None
    d.mkdir(parents=True, exist_ok=True)
    n = len(list(d.glob(f"{model_dir.name}-*.json"))) + 1
    p = d / f"{model_dir.name}-{n}.json"
    p.write_text(json.dumps({"model": model_dir.name, "time": time.time(), **case}, indent=1)
                 + "\n", "utf-8")  # fmt: skip
    return p


def evaluate(model_dir: Path, expect: dict[str, Any]) -> list[str]:
    """What fails of a case's expectations on the cover as it is now ([] = it holds)."""
    from coverengine.params import resolve_model

    bad: list[str] = []
    fin_p = model_dir / "finished.json"
    fin = json.loads(fin_p.read_text(encoding="utf-8")) if fin_p.is_file() else {"pieces": []}
    pieces = [p for p in fin["pieces"] if not str(p["name"]).startswith("vent-")]
    hoods = sum(int(p.get("quantity") or 0) for p in fin["pieces"] if p["name"] == "vent-hood")
    if "pieces_at_most" in expect and len(pieces) > int(expect["pieces_at_most"]):
        bad.append(f"{len(pieces)} pieces, expected at most {expect['pieces_at_most']}")
    if "pieces_at_least" in expect and len(pieces) < int(expect["pieces_at_least"]):
        bad.append(f"{len(pieces)} pieces, expected at least {expect['pieces_at_least']}")
    if "vents" in expect and hoods != int(expect["vents"]):
        bad.append(f"{hoods} vents, expected {expect['vents']}")
    for key, value in (expect.get("params") or {}).items():
        got = resolve_model(model_dir)[key]
        same = got == value or (_num(got) and _num(value) and abs(float(got) - float(value)) < TINY)  # type: ignore[arg-type]
        if not same:
            bad.append(f"{key} is {got}, expected {value}")
    if "no_seam_near" in expect:
        v = seam_vertices(model_dir)
        p = np.asarray(expect["no_seam_near"], dtype=np.float64)
        if len(v) and float(np.linalg.norm(v - p, axis=1).min()) < NEAR_MM:
            bad.append(f"a seam still runs within {NEAR_MM:.0f} mm of {p.round(0).tolist()}")
    return bad


def seam_vertices(model_dir: Path) -> np.ndarray:
    """Every point of the cover where two panels meet (mm)."""
    npz = model_dir / "panels.npz"
    if not npz.is_file():
        return np.zeros((0, 3))
    z = np.load(npz)
    v, f, lab, orig = z["vertices"], z["faces"], z["labels"], z["original_vertex"]
    owners: dict[int, set[int]] = {}
    for k in np.unique(lab):
        for o in np.unique(orig[np.unique(f[lab == k])]).tolist():
            owners.setdefault(int(o), set()).add(int(k))
    shared = [o for o, ks in owners.items() if len(ks) > 1]
    return np.asarray(v[np.isin(orig, shared)], dtype=np.float64)


def _num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


# ---- proposals: the same correction on several covers of a group ----------------------------


def proposals(models: Path, base: Path, learn_after: int) -> list[dict[str, Any]]:
    """Parameter corrections made on at least `learn_after` covers of one group, that are not
    yet the group's rule: candidates for a person to make the rule."""
    seen: dict[tuple[str, str, str], set[str]] = {}
    values: dict[tuple[str, str, str], Any] = {}
    for d in sorted(p for p in models.iterdir() if (p / "feedback.json").is_file()):
        group = group_of(d)
        if not group:
            continue
        for f in json.loads((d / "feedback.json").read_text(encoding="utf-8")):
            for key, value in (f.get("params") or {}).items():
                k = (group, key, json.dumps(value))
                seen.setdefault(k, set()).add(d.name)
                values[k] = value
    out = []
    for (group, key, vj), names in sorted(seen.items()):
        if len(names) < learn_after:
            continue
        if get_dotted(rules(group, base), key) == values[(group, key, vj)]:
            continue
        out.append({"group": group, "key": key, "value": values[(group, key, vj)],
                    "covers": sorted(names), "count": len(names)})  # fmt: skip
    return out


# ---- measured on sewn covers (ADR-111) ------------------------------------------------------


def measure_kind(key: str) -> str:
    """A check-list key without its cover's own names: vent.3.above_hem -> vent.above_hem,
    skirt.skirt-left -> skirt, piece.top-1.hem -> piece.hem, seam.a/b -> seam."""
    parts = key.split(".")
    if parts[0] == "vent" and len(parts) == 3:  # param-ok: vent.<n>.<what>
        return f"vent.{parts[2]}"
    if parts[0] == "piece" and len(parts) >= 3:  # param-ok: piece.<name>.<what>
        return f"piece.{parts[-1]}"
    if parts[0] in ("skirt", "seam"):
        return parts[0]
    return key


def measured_deviations(
    models: Path, tolerance_mm: float, learn_after: int
) -> list[dict[str, Any]]:
    """What sewn covers measured against their check lists (the Desk's fit, ADR-111), per group
    and kind of size: how many values on how many covers, the mean and the largest difference
    (measured - calculated, mm). `systematic` when the mean is off by more than `tolerance_mm`
    on at least `learn_after` covers: then the program is off, not one cover."""
    found: dict[tuple[str, str], list[tuple[str, float]]] = {}
    for d in sorted(p for p in models.iterdir() if (p / "desk.json").is_file()):
        try:
            fit = json.loads((d / "desk.json").read_text(encoding="utf-8")).get("fit") or {}
        except (OSError, json.JSONDecodeError):
            continue
        group = group_of(d) or "other"
        for row in fit.get("measured") or []:
            if _num(row.get("diff_mm")):
                found.setdefault((group, measure_kind(str(row["key"]))), []).append(
                    (d.name, float(row["diff_mm"]))
                )
    out = []
    for (group, kind), values in sorted(found.items()):
        diffs = [v for _, v in values]
        covers = sorted({c for c, _ in values})
        mean = sum(diffs) / len(diffs)
        worst = float(sorted(diffs, key=lambda x: -abs(x))[0])
        out.append(
            {
                "group": group,
                "kind": kind,
                "values": len(diffs),
                "covers": covers,
                "mean_mm": round(mean, 1),
                "max_mm": round(worst, 1),
                "systematic": abs(mean) > tolerance_mm and len(covers) >= learn_after,
            }
        )
    return out
