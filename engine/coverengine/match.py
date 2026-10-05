"""The customer's sizes against the covers we already make (docs/plans/hosting-scale-and-
matching.md, ADR-064): a size card per catalogue cover, a score per size, and one percentage.

Per size the difference d = catalogue furniture − customer furniture (cm):
- within [−match.tight_cm, +match.loose_cm]: 100 % (the cover's own ease takes it up);
- smaller than that: falls fast (over `match.tight_falloff_cm`): a cover too small does not go on;
- larger: falls slowly (over `match.loose_falloff_cm`): it hangs looser and folds more.
The total is the weighted geometric mean, so one size that does not fit at all gives 0 %.
A different kind of furniture, or the wrong side of an L, is never a match.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from coverengine.params import EffectiveParams

MM_PER_CM = 10.0  # param-ok: units
PCT = 100.0  # param-ok: a share as a percentage
DIMS = ("length", "width", "height")
# the catalogue's categories per product of the configurator (config/quote_products.json)
CATEGORIES = {
    "dining_set": ("Tafels", "Low dining tafels", "Bartafels"),
    "round_set": ("Tafels", "Low dining tafels", "Bartafels"),
    "sofa": ("Sofasets",),
    "corner_sofa": ("Sofasets",),
    "lounger": ("Ligbedden", "Daybeds"),
    "item": ("Stoelen", "Loungestoelen", "Hockers", "Bijzettafels", "Loungetafels", "Barstoelen",
             "Low dining stoelen", "Vuurtafels", "Sofasets"),
}  # fmt: skip
ROUND = re.compile(r"(^|-)(dia|round|rond|conico|ovaal|oval)(-|$)")
CORNER = re.compile(r"(^|-)(l-part|chaise|with-corner|2-seater-corner|moonshape|angled)(-|$)")
MODULE = re.compile(r"(^|-)(corner|middle|hocker|footstool)(-|$)")
LONG_SOFA_CM = 150.0  # param-ok: a "corner" piece shorter than this is a module, not an L


def _pretty(name: str) -> str:
    """'SUNS-2 Seater-Evora alu' → 'SUNS 2 Seater Evora alu'."""
    return re.sub(r"\s+", " ", name.replace("-", " ").replace("_", " ")).strip()


def _side(name: str) -> str | None:
    return "left" if "left" in name else "right" if "right" in name else None


def kind_of(model_id: str, category: str, size_cm: list[float]) -> str | None:
    """Which configurator product a catalogue cover answers to (None: not offered)."""
    name = model_id.removeprefix("suns-").removeprefix("lounge-")
    if category in ("Tafels", "Low dining tafels", "Bartafels"):
        return "round_set" if ROUND.search(name) else "dining_set"
    if category == "Sofasets":
        if CORNER.search(name):
            return "corner_sofa"
        if MODULE.search(name) and size_cm[0] < LONG_SOFA_CM:
            return "item"
        return "sofa"
    if category in ("Ligbedden", "Daybeds"):
        return "lounger"
    if category in CATEGORIES["item"]:
        return "item"
    return None


def card(model_dir: Path, kinds: dict[str, str] | None = None) -> dict[str, Any] | None:
    """A catalogue cover's size card: kind, the furniture's size (length ≥ width, height), the
    side of an L, whether it covers chairs, and how its drape went."""
    try:
        cover = json.loads((model_dir / "cover.json").read_text())
        size = json.loads((model_dir / "model.json").read_text())["size_mm"]
    except (OSError, ValueError, KeyError):
        return None
    category = str(cover.get("category") or "").split(" › ")[-1]
    s = sorted([size[0] / MM_PER_CM, size[1] / MM_PER_CM])[::-1] + [size[2] / MM_PER_CM]
    kind = (kinds or {}).get(model_dir.name) or kind_of(model_dir.name, category, s)
    if kind is None:
        return None
    chairs = None
    try:
        chairs = bool(json.loads((model_dir / "hull.json").read_text()).get("chairs"))
    except (OSError, ValueError):
        pass
    drape = None
    if (model_dir / "drape.json").is_file():
        try:
            d = json.loads((model_dir / "drape.json").read_text())
            drape = {"folds_pct": d.get("fold_share_pct"),
                     "sag_cm": round(float(d.get("max_sag_mm") or 0) / MM_PER_CM, 1)}  # fmt: skip
        except (OSError, ValueError):
            pass
    return {
        "model_id": model_dir.name,
        "name": _pretty((cover.get("notes") or model_dir.name).split(": ")[-1]),
        "category": category,
        "kind": kind,
        "size_cm": [round(x, 1) for x in s],
        "side": _side(model_dir.name),
        "chairs": chairs,
        "photo": (model_dir / "product.jpg").is_file(),
        "drape": drape,
    }


_CACHE: dict[str, Any] = {}


def cards(models: Path, kinds: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """All catalogue covers' size cards (the SUNS models), cached until a model folder changes."""
    dirs = sorted(models.glob("suns-*"))
    stamp = (str(models), len(dirs), max((d.stat().st_mtime for d in dirs), default=0.0),
             json.dumps(kinds or {}, sort_keys=True))  # fmt: skip
    if _CACHE.get("stamp") != stamp:
        _CACHE["stamp"] = stamp
        _CACHE["cards"] = [c for d in dirs if (c := card(d, kinds)) is not None]
    out: list[dict[str, Any]] = _CACHE["cards"]
    return out


def size_score(diff: float, p: EffectiveParams) -> float:
    """One size's fit (0..1) for a difference catalogue − customer in cm."""
    tight, loose = float(p["match.tight_cm"]), float(p["match.loose_cm"])
    if diff < -tight:
        return max(0.0, 1.0 - (-tight - diff) / float(p["match.tight_falloff_cm"]))
    if diff > loose:
        return max(0.0, 1.0 - (diff - loose) / float(p["match.loose_falloff_cm"]))
    return 1.0


def score(target: list[float], c: dict[str, Any], p: EffectiveParams) -> dict[str, Any]:
    """The percentage for one cover, with the difference per size and its word."""
    weights = [float(w) for w in str(p["match.weights"]).split(",")]
    diffs, logsum, wsum = [], 0.0, 0.0
    for name, want, have, w in zip(DIMS, target, c["size_cm"], weights, strict=True):
        d = have - want
        s = size_score(d, p)
        verdict = ("exact" if s >= 1 and abs(d) <= float(p["match.tight_cm"]) else
                   "roomier" if d > 0 else "tighter")  # fmt: skip
        diffs.append({"size": name, "customer_cm": round(want, 1), "cover_cm": have,
                      "difference_cm": round(d, 1), "fit_pct": round(PCT * s),
                      "verdict": verdict})  # fmt: skip
        logsum += w * math.log(max(s, 1e-9))  # param-ok: no log of zero
        wsum += w
    fits = all(d["fit_pct"] > 0 for d in diffs)  # one size that does not fit at all: 0 %
    pct = PCT * math.exp(logsum / wsum) if fits else 0.0
    return {"score_pct": round(pct, 1), "sizes": diffs}


def match(
    product: str,
    given: dict[str, Any],
    models: Path,
    p: EffectiveParams,
    top: int = 3,
    kinds: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The best existing covers for the customer's furniture, and what to offer: the existing
    cover (≥ match.threshold_pct), a choice (≥ match.choice_pct), or a custom cover."""
    from coverengine.quote import PRODUCTS, _bbox_cm

    if product not in PRODUCTS:
        raise ValueError(f"unknown product {product!r}")
    target = _bbox_cm(product, given)
    side = given.get("side") if given.get("side") in ("left", "right") else None
    chairs = given.get("chairs")
    out = []
    for c in cards(models, kinds):
        if c["kind"] != product:
            continue
        if side and c["side"] and c["side"] != side:
            continue  # the other hand of an L does not fit
        if isinstance(chairs, bool) and c["chairs"] is not None and c["chairs"] != chairs:
            continue
        out.append({**{k: c[k] for k in ("model_id", "name", "size_cm", "side", "photo", "drape")},
                    **score(target, c, p)})  # fmt: skip
    out.sort(key=lambda r: (-float(r["score_pct"]), r["model_id"]))
    best = float(out[0]["score_pct"]) if out else 0.0
    decision = ("existing" if best >= float(p["match.threshold_pct"]) else
                "choice" if best >= float(p["match.choice_pct"]) else "custom")  # fmt: skip
    return {
        "product": product,
        "customer_cm": [round(x, 1) for x in target],
        "matches": out[:top],
        "decision": decision,
        "threshold_pct": float(p["match.threshold_pct"]),
        "choice_pct": float(p["match.choice_pct"]),
    }


def fields_for(product: str, size_cm: list[float]) -> dict[str, int]:
    """A catalogue cover's sizes as the configurator's fields (to price that cover)."""
    length, width, height = (round(x) for x in size_cm)
    return {
        "dining_set": {"table_length_cm": length, "table_width_cm": width,
                       "table_height_cm": height},
        "round_set": {"table_diameter_cm": length, "table_height_cm": height},
        "sofa": {"length_cm": length, "depth_cm": width, "back_height_cm": height},
        "corner_sofa": {"long_side_cm": length, "short_side_cm": width, "back_height_cm": height},
    }.get(product, {"length_cm": length, "width_cm": width, "height_cm": height})  # fmt: skip


def entry(models: Path, model_id: str, product: str, given: dict[str, Any],
          p: EffectiveParams) -> dict[str, Any] | None:  # fmt: skip
    """One named cover scored against the customer's sizes (a colleague's own choice)."""
    from coverengine.quote import _bbox_cm

    c = card(models / model_id)
    if c is None:
        return None
    keep = ("model_id", "name", "size_cm", "side", "photo", "drape")
    return {**{k: c[k] for k in keep}, **score(_bbox_cm(product, given), c, p)}
