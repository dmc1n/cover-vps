# The cover surface

After a model is imported (`importing.md`), `cover hull` works out the shape of the cover.
Seams and flat patterns are cut from this surface in the next steps.

```
uv run cover hull models/blocchi-2seater-moon-right
```

```
cover surface -> models/blocchi-2seater-moon-right/hull.glb (view it with .../preview.glb)
settings clearance 10 mm, bridge gap 60 mm, hem 50 mm above the floor
size     2381 x 1432 x 869 mm, fabric area 6.04 m2, hem length 6.30 m
distance closest 10.0 mm from the furniture (clearance 10 mm)
ridges   77 sharp ridges (seam candidates for the next step)
water    would stay on the top (see warning)
```

It takes from a few seconds (a chair) to under a minute (a large sofa).

## What the cover looks like

- **Pulled tight on top.** The top runs in straight lines between the highest parts of the
  furniture, from the front edge of a seat straight up to the top of the back. It never sags
  into a seat or a recess, so water can run off. That is the rule for every cover.
- **Straight down at the sides.** Below the widest point the cover hangs vertically to the hem,
  so legs and undercuts are hidden.
- **Open at the bottom**, with a straight hem at the hem height.

## Look at it

`preview.glb` shows the furniture in grey with the cover in see-through blue. Copy it to your
laptop and drag it onto gltf-viewer.donmccurdy.com (run this on the laptop, not on the server):

```
scp dev@168.119.50.82:~/cover-pattern-engine/models/blocchi-2seater-moon-right/preview.glb ~/Downloads/
```

## Does water run off?

Every run checks the top for two things:
- **hollows:** spots lower than everything around them;
- **flat patches:** areas flatter than 5° (`hull.min_slope_deg`) and at least 10 cm across
  (`hull.flat_patch_mm`). The crest of a backrest and the rim of the cover do not count; water
  runs off them.

If water would stay, the output says so and the warning gives the place (x, y in mm; x runs
across, y from front to back, the front at negative y).

## Tables and other flat tops: the balloon

A flat top holds water. Put a balloon under the cover so the fabric forms a tent:

```
uv run cover hull models/<table> --set hull.support=balloon
```

```
water    runs off
support  balloon 69 mm high (automatic), radius 150 mm, centred at x 0, y 0
```

The program places the balloon under the middle of the flat area and finds the lowest height
at which the whole top sheds water. That height is the one to use in the workshop. To use a
fixed height instead: `--set hull.support_height_mm=100`. To keep the balloon for that model,
put it in the model's `cover.json`:

```json
{ "format_version": 1, "parameters": { "hull": { "support": "balloon" } } }
```

## The settings

| setting | flag | default | what it does |
|---|---|---|---|
| clearance | `--clearance 10` | 10 mm | gap between furniture and fabric everywhere. Raise it for a looser cover. |
| hem height | `--hem-height 50` | 50 mm | how high above the floor the cover ends. |
| bridge gap | `--bridge-gap 60` | 60 mm | slots in the outline seen from above (between slats, between two seat units) narrower than this are closed. |
| balloon | `--set hull.support=balloon` | none | tent support for flat tops (above). |

A flag changes the value for that run only ("trial"). To keep a value for one model, put it in
the model's `cover.json`:

```json
{ "format_version": 1, "parameters": { "hull": { "clearance_mm": 15 } } }
```

To change it for every model, edit `config/defaults.yaml` (see `parameters.md`).

The old behaviour, where the cover follows the seat instead of spanning it, is still available
with `--set hull.top=draped`. It holds water on most furniture, so use it only for special cases.

## Leaving something out, or filling a gap

Some things should not shape the cover, for example a parasol pole or a cable. Others should
be covered as if they were solid. Add boxes to `cover.json` (coordinates in mm, as in
`model.glb`: x across, y front to back with the front at -y, z up from the floor):

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

- **closest:** never below the clearance. If it is, a warning says so; tell Claude Code.
- **fabric area:** the cover surface without seam allowances. Real fabric use is higher.
- **ridges:** sharp edges of the cover, where seams will most likely go (next step).
- **water:** runs off, or where it would stay.

Everything is also written to `hull.json` next to the model.

## Box covers

For furniture that is roughly a box (most sofas, chairs, tables, poufs), set
`hull.top: box` (in the model's settings, or for a family in its preset). The cover is then the
tightest box with flat faces round the furniture: every face is one piece that lies flat
exactly, every seam is a straight edge. The program tries 5 to 10 pieces and the AI chooses how
many (fewer pieces means more room between cover and furniture); `hull.box_pieces` fixes the
number yourself. A flat top gets a slight slope (or a low gable on a table) so water runs off.

