# The cover surface

After a model is imported (`importing.md`), `cover hull` works out the shape of the cover: the
surface a tight fabric cover takes over the furniture. Seams and flat patterns are cut from this
surface in the next steps.

```
uv run cover hull models/blocchi-2seater-moon-right
```

```
cover surface -> models/blocchi-2seater-moon-right/hull.glb (view it with .../preview.glb)
settings clearance 10 mm, bridge gap 60 mm, hem 50 mm above the floor
size     2380 x 1432 x 869 mm, fabric area 6.49 m2, hem length 6.42 m
distance closest 10.0 mm from the furniture (clearance 10 mm)
ridges   43 sharp ridges (seam candidates for the next step)
```

It takes from a few seconds (a chair) to under a minute (a large sofa).

## Look at it

`preview.glb` shows the furniture in grey with the cover in see-through blue. Copy it to your
laptop and drag it onto gltf-viewer.donmccurdy.com (run this on the laptop, not on the server):

```
scp dev@168.119.50.82:~/cover-pattern-engine/models/blocchi-2seater-moon-right/preview.glb ~/Downloads/
```

Check three things:
1. The cover hangs straight down from the widest point, with legs and undercuts hidden.
2. Gaps you want spanned (slats, the gap between cushions) are spanned, and recesses you want
   followed (seat to backrest) are followed.
3. The bottom edge is at the right height.

## The three settings

| setting | flag | default | what it does |
|---|---|---|---|
| clearance | `--clearance 10` | 10 mm | gap between furniture and fabric everywhere. Raise it for a looser cover. |
| bridge gap | `--bridge-gap 60` | 60 mm | gaps narrower than this are spanned. Wider recesses are followed. |
| hem height | `--hem-height 50` | 50 mm | how high above the floor the cover ends. |

A flag changes the value for that run only ("trial"). To keep a value for one model, put it
in the model's `cover.json`:

```json
{ "format_version": 1, "parameters": { "hull": { "clearance_mm": 15, "bridge_gap_mm": 80 } } }
```

To change it for every model, edit `config/defaults.yaml` (see `parameters.md`).

About the bridge gap: the fabric is modelled as a ball of half the bridge gap rolling over
the furniture. A gap much narrower than the setting is spanned flat. A gap close to the
setting still sags a little (a 20 mm slat gap sags about 1 mm at the default 60 mm). A gap wider
than the setting is followed.

## Leaving something out, or filling a gap

Some things should not shape the cover, for example a parasol pole or a cable. Others should
be covered as if they were solid, for example a gap you want closed. Add boxes to `cover.json`
(coordinates in mm, as in `model.glb`: x across, y front to back with the front at -y,
z up from the floor):

```json
{
  "format_version": 1,
  "parameters": {},
  "hull_masks": [
    { "type": "box", "min": [-30, -30, 800], "max": [30, 30, 2500], "mode": "exclude" },
    { "type": "box", "min": [-400, 200, 300], "max": [400, 300, 450], "mode": "solid" }
  ]
}
```

`exclude`: the furniture inside the box is ignored. `solid`: the box is covered as if it were
part of the furniture.

## Reading the check

- **closest:** never below the clearance. If it is, a warning says so. Tell Claude Code.
- **fabric area:** the cover surface without seam allowances. Real fabric use is higher.
- **ridges:** sharp edges of the cover, where seams will most likely go (next step).

Everything is also written to `hull.json` next to the model.
