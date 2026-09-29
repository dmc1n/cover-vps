# Formats

Source of truth for every JSON structure and export format. Update this file in the same commit
as the code that changes a format. JSON Schemas live in `engine/schemas/`; this file explains
them.

## Conventions

- Lengths in mm, angles in degrees, coordinates right-handed Z-up, ground at z = 0, front of the
  furniture toward −Y.
- Every file carries `format_version` (integer) and `engine_version` (string).
- Ids are stable strings, never array indices.

## Parameters (M0)

`config/defaults.yaml` is the registry of every parameter with its default and a comment. The
effective value for a run is resolved in this order, later wins: defaults → family preset
(`config/presets/<family>.yaml`, M7) → the model's `CoverDefinition` → one-off `--set` or UI
trial override. Keys use dotted paths (`hull.clearance_mm`). Every `PatternSet` embeds
`parameters` (the full effective set) and `parameter_hash`, so any pattern can be reproduced and
`cover diff` can attribute a dimension change to the parameter that caused it.

## Model (M1)

`models/<id>/model.glb` (canonical mesh, may be a triangle soup) and `model.json`:

```json
{
  "format_version": 1,
  "id": "lounge-chair-a12",
  "source": { "file": "A12.step", "sha256": "...", "units_detected": "mm", "units_used": "mm" },
  "placement": { "up_axis": "z", "front": "-y", "ground_offset_mm": 0.0 },
  "parts": { "kept": 84, "dropped_small": 212, "min_part_mm": 8, "excluded": ["cushion-*"] },
  "bbox_mm": [[-400, -350, 0], [400, 350, 910]]
}
```

## CoverDefinition (M2–M5)

```json
{
  "format_version": 1,
  "model_id": "lounge-chair-a12",
  "hull": { "clearance_mm": 10, "bridge_gap_mm": 60, "hem_height_mm": 50,
            "resolution_mm": 5, "smoothing": 0.5, "sweep_down": true,
            "masks": [ { "type": "box", "min": [..], "max": [..], "mode": "exclude" } ] },
  "seams": { "template": "chair", "graph": null, "symmetry_plane": { "point": [0,0,0], "normal": [1,0,0] } },
  "fabric_profile": "acrylic-300",
  "welding": { "overlap_mm": 30, "min_weld_radius_mm": 150, "seam_tolerance_mm": 1.0 },
  "hem": { "type": "drawcord_channel", "allowance_mm": 50, "cord_exits": 2 },
  "features": [ { "type": "strap_mark", "count": 4 }, { "type": "vent", "count": 2 } ],
  "roll": { "width_mm": 1500, "usable_width_mm": 1480 }
}
```

`hull.sweep_down: true` is the drape hull (fabric hangs from the widest point); `false` gives a
fitted shell for cushion-like objects.

## Seam graph (M3)

```json
{
  "format_version": 1,
  "seams": [
    { "id": "left-corner",
      "anchors": [ { "face": 1234, "bary": [0.2, 0.3, 0.5] }, { "face": 2201, "bary": [1, 0, 0] } ],
      "closed": false, "lap_side": "auto" }
  ]
}
```

`lap_side` is `auto` (engine decides by height and front/side rule), or a patch id.

## PatternSet and Panel (M4–M5)

```json
{
  "format_version": 1,
  "model_id": "lounge-chair-a12", "revision": 3, "parameter_hash": "...",
  "parameters": { "hull": { "clearance_mm": 10, "bridge_gap_mm": 60, "...": "..." }, "welding": { "overlap_mm": 30 }, "...": "..." },
  "parameter_sources": { "hull.clearance_mm": "model", "welding.overlap_mm": "default" },
  "fabric_profile": "acrylic-300",
  "summary": { "panels": 6, "max_stretch_pct": 1.8, "fabric_length_mm_est": 3200 },
  "panels": [
    { "id": "P1", "name": "top", "quantity": 1, "mirror": false,
      "outline_mm": [[0,0],[1200,0],[1200,800],[0,800]],
      "edges": [
        { "range": [0,1], "kind": "seam", "mate": { "panel": "P2", "edge": 0 },
          "lap_side": "P1", "overlap_mm": 30, "length_3d_mm": 1200.4, "length_2d_mm": 1200.1, "ease_mm": 0.0 },
        { "range": [2,3], "kind": "hem", "allowance_mm": 50 }
      ],
      "pen": [ { "type": "label", "at": [600,400], "text": "P1 top  A12 r3" },
               { "type": "guide_line", "points": [[..],[..]], "for_mate": "P2" },
               { "type": "tick", "at": [300,0], "dir": [0,1], "pair": "P2:t1" },
               { "type": "arrow_up", "at": [600,700] } ],
      "stretch": { "max_pct": 1.2, "mean_pct": 0.4, "area_pct": 0.3 } }
  ]
}
```

`outline_mm` is the raw panel; export adds allowances from `edges`. `range` indexes outline
vertices. Ticks are paired across mates by id.

## Fabric profile (M4 placeholder, M8 measured)

```json
{
  "format_version": 1,
  "id": "acrylic-300",
  "name": "100% acrylic canvas, approx. 300 g/m2",
  "status": "placeholder",
  "stretch_pct": { "warp": 0.5, "weft": 1.0, "bias": 3.0 },
  "weld_shrinkage_pct": { "along": 0.2, "across": 0.5 },
  "thickness_mm": 0.6,
  "max_allowed_stretch_pct": 2.0,
  "roll_width_mm": 1500,
  "source": "placeholder values, replace after swatch tests (docs/CALIBRATION.md)"
}
```

`status` must be `measured` before a pattern set is marked production.

## Exports (M5)

- DXF, one file per pattern set: all panels placed on a virtual sheet with 20 mm spacing (the
  machine software nests). Closed LWPOLYLINEs on the cut layer; lines and text on the pen layer.
  Units mm (`$INSUNITS` = 4), DXF version R2010. Layer names, TEXT versus stroked text, and arc
  handling follow the result of the M0 machine test; record the findings here:
  - cut layer name: TODO (M0)
  - pen layer name: TODO (M0)
  - text: TODO (TEXT entity or strokes via `ezdxf.addons.text2path`)
  - arcs: TODO (allowed, or flatten to polylines)
- SVG preview at 1:1 mm (`width="...mm"`), groups `cut` and `pen`.
- PDF cutting list: table of panels (id, name, quantity, bounding box, area), total fabric
  estimate, model name, revision, date.
