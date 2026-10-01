"""AI advice on a cover's layout (ADR-036).

The program describes a calculated cover in text (the product, its size, every piece with its
size, area and stretch, which pieces meet along which seams, and why the cover still needs
checking) and asks a language model how to make it simpler. The model may only choose from a
fixed list of actions the program can carry out safely (ACTIONS); it changes nothing itself: the
owner applies a suggestion with `apply_action` (the web app's buttons), and the cover is then
calculated again.

The key comes from the environment (DEEPSEEK_API_KEY), or from `deploy/.env`; it is never
written anywhere else. Settings: `ai.*` in config/defaults.yaml.
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path
from typing import Any

from coverengine.catalogue import grade
from coverengine.errors import CoverError
from coverengine.params import EffectiveParams
from coverengine.params.registry import read_cover_definition, repo_root

AI_REVIEW_JSON = "ai_review.json"
MM_PER_CM = 10.0  # param-ok: unit conversion
# "A calmer cover surface": the owner's 5 mm more room, and gaps up to 15 cm bridged.
SMOOTH_CLEARANCE_MM = 15.0  # param-ok: the action's value (owner, 1 Oct 2026)
SMOOTH_BRIDGE_MM = 150.0  # param-ok: the action's value
KEY_ENV = {"deepseek": "DEEPSEEK_API_KEY"}

# What the AI may suggest, and what each does (shown to the AI and in the web app).
ACTIONS: dict[str, str] = {
    "drop_program_seams": (
        "remove the extra seams the program added to lower the stretch (proposals.json); "
        "fewer pieces, more stretch"
    ),
    "skirt_one_piece": (
        "the skirt as one strip all round with one closing seam at the back, split only where "
        "it is longer than the longest piece; no vertical seam at every corner"
    ),
    "no_walls": (
        "no separate upright wall pieces above the skirt: the top runs down to the skirt there"
    ),
    "smoother_surface": (
        "a calmer cover surface: 15 mm from the furniture, gaps up to 15 cm bridged, maximum "
        "smoothing; fewer folds and ridges"
    ),
    "set_skirt_height": (
        "put the skirt seam at one given height above the hem (value: mm, 150 to 600)"
    ),
}


def _key(provider: str) -> str:
    name = KEY_ENV.get(provider)
    if name is None:
        raise CoverError(f"unknown ai.provider {provider!r}")
    key = os.environ.get(name)
    env = repo_root() / "deploy" / ".env"
    if not key and env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"{name}="):
                key = line.split("=", 1)[1].strip().strip("'\"")
    if not key:
        raise CoverError(f"no API key: set {name} in deploy/.env")
    return key


def describe(model_dir: Path) -> dict[str, Any]:
    """The cover in plain data, as the AI sees it."""
    cut = json.loads((model_dir / "panels.json").read_text(encoding="utf-8"))
    pattern = json.loads((model_dir / "pattern.json").read_text(encoding="utf-8"))
    cover = read_cover_definition(model_dir)
    model = json.loads((model_dir / "model.json").read_text(encoding="utf-8"))
    flat = {p["name"]: p for p in pattern["panels"]}
    g = grade(model_dir)
    proposals = model_dir / "proposals.json"
    added = json.loads(proposals.read_text())["top_seams"] if proposals.is_file() else []
    return {
        "product": (cover.get("notes") or model_dir.name).split(": ", 1)[-1],
        "family": cover.get("family"),
        "size_cm": [round(v / MM_PER_CM) for v in model.get("size_mm", [])],
        "hem_length_cm": round(cut["hem_length_mm"] / MM_PER_CM),
        "skirt_height_cm": [round(v / MM_PER_CM, 1) for v in cut.get("skirt_height_mm", [])],
        "pieces": [
            {
                "name": p["name"],
                "kind": p["region"],
                "flat_cm": [
                    round(flat[p["name"]]["flat_width_mm"] / MM_PER_CM),
                    round(flat[p["name"]]["flat_length_mm"] / MM_PER_CM),
                ],
                "area_m2": p["area_m2"],
                "stretch_pct": round(flat[p["name"]]["stretch"]["quantile_pct"], 1),
            }
            for p in cut["panels"]
        ],
        "seams": [
            {
                "between": s["panels"],
                "kind": s["kind"],
                "length_cm": round(s["length_mm"] / MM_PER_CM),
            }
            for s in cut["seams"]
        ],
        "seams_added_by_program": len(added),
        "status": g["grade"],
        "why_to_check": g.get("reasons", []),
        "settings": {
            k: cover.get("parameters", {}).get(k.split(".")[0], {}).get(k.split(".")[1])
            for k in ("seams.skirt_height_mm", "seams.corner_angle_deg", "seams.wall_min_mm")
        },
    }


SYSTEM = """You advise a workshop that sews outdoor furniture covers from acrylic canvas on a CNC
cutting table. The owner's rules: as few pieces as possible (a 2-seater sofa cover is about 5 or
6 pieces: top, back, sides, front, skirt; a table cover 5); seams are easy straight or smooth
lines for clean stitching; the skirt runs at one height all round, ideally as one strip; water
must run off the top. The fabric eases a little, so a few percent of stretch in a piece is
acceptable, but tiny scrap pieces never are. You get one calculated cover as JSON. Judge it and
choose actions ONLY from this list (use the exact action names):
__ACTIONS__
Answer with JSON only, in this form:
{"summary": "two or three plain sentences for the owner",
 "target_pieces": <the number of pieces this cover should have>,
 "problems": ["short plain sentences"],
 "suggestions": [{"action": "<name>", "value": <number or null>, "reason": "one sentence"}]}
Suggest at most four actions, most important first; none if the cover is already good."""


def ask(params: EffectiveParams, system: str, user: str) -> dict[str, Any]:
    provider = str(params["ai.provider"])
    if provider == "none":
        raise CoverError("AI advice is off (ai.provider = none)")
    body = {
        "model": str(params["ai.model"]),
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        str(params["ai.base_url"]).rstrip("/") + "/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {_key(provider)}", "Content-Type": "application/json"},
    )
    timeout = float(params["ai.timeout_s"])  # type: ignore[arg-type]
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 - configured host
            reply = json.loads(r.read())
    except Exception as exc:  # noqa: BLE001 - network or service: tell the operator
        raise CoverError(f"the AI did not answer: {exc}") from None
    text = reply["choices"][0]["message"]["content"]
    try:
        doc: dict[str, Any] = json.loads(text)
    except json.JSONDecodeError:
        raise CoverError("the AI's answer was not readable (no JSON)") from None
    doc["_usage"] = reply.get("usage", {})
    return doc


def review(model_dir: Path, params: EffectiveParams) -> dict[str, Any]:
    """Ask the AI about this cover; the advice is saved to ai_review.json."""
    for name in ("panels.json", "pattern.json", "model.json"):
        if not (model_dir / name).is_file():
            raise CoverError(f"no {name} in {model_dir} (calculate the cover first)")
    facts = describe(model_dir)
    actions = "\n".join(f"- {k}: {v}" for k, v in ACTIONS.items())
    answer = ask(params, SYSTEM.replace("__ACTIONS__", actions), json.dumps(facts))
    suggestions = [
        s
        for s in answer.get("suggestions", [])
        if isinstance(s, dict) and s.get("action") in ACTIONS
    ]
    doc = {
        "time": round(time.time()),
        "model": str(params["ai.model"]),
        "summary": str(answer.get("summary", "")),
        "target_pieces": answer.get("target_pieces"),
        "pieces_now": len(facts["pieces"]),
        "problems": [str(p) for p in answer.get("problems", [])],
        "suggestions": suggestions,
        "applied": [],
        "usage": answer.get("_usage", {}),
    }
    (model_dir / AI_REVIEW_JSON).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return doc


def _set_parameters(model_dir: Path, values: dict[str, Any]) -> None:
    path = model_dir / "cover.json"
    doc = read_cover_definition(model_dir) or {"format_version": 1, "model_id": model_dir.name}
    tree = doc.setdefault("parameters", {})
    for key, value in values.items():
        group, leaf = key.split(".", 1)
        tree.setdefault(group, {})[leaf] = value
    path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")


def apply_action(model_dir: Path, action: str, value: float | None = None) -> list[str]:
    """Carry out one suggested action; returns the steps to run again."""
    if action == "drop_program_seams":
        (model_dir / "proposals.json").unlink(missing_ok=True)
        steps = ["cut", "flatten", "export"]
    elif action == "skirt_one_piece":
        _set_parameters(model_dir, {"seams.corner_angle_deg": NO_CORNERS_DEG})
        steps = ["cut", "flatten", "export"]
    elif action == "no_walls":
        _set_parameters(model_dir, {"seams.wall_min_mm": NO_WALLS_MM})
        steps = ["cut", "flatten", "export"]
    elif action == "smoother_surface":
        _set_parameters(
            model_dir,
            {
                "hull.clearance_mm": SMOOTH_CLEARANCE_MM,
                "hull.bridge_gap_mm": SMOOTH_BRIDGE_MM,
                "hull.smoothing": 1.0,
            },
        )
        steps = ["hull", "cut", "flatten", "export"]
    elif action == "set_skirt_height":
        if value is None or not SKIRT_RANGE[0] <= float(value) <= SKIRT_RANGE[1]:
            raise CoverError(f"skirt height must be {SKIRT_RANGE[0]}-{SKIRT_RANGE[1]} mm")
        _set_parameters(model_dir, {"seams.skirt_height_mm": float(value)})
        steps = ["cut", "flatten", "export"]
    else:
        raise CoverError(f"unknown action {action!r}")
    path = model_dir / AI_REVIEW_JSON
    if path.is_file():
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc.setdefault("applied", []).append({"action": action, "value": value})
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    return steps


NO_CORNERS_DEG = 179  # param-ok: a corner would have to turn more than this: none do
NO_WALLS_MM = 100000  # param-ok: a wall would have to be this tall: none are
SKIRT_RANGE = (150.0, 600.0)  # param-ok: sensible skirt heights (mm)
