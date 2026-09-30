# Seams and panels

After the cover surface (`cover-surface.md`), `cover cut` divides it into panels.

```
uv run cover cut models/blocchi-2seater-moon-right
```

```
panels -> models/blocchi-2seater-moon-right/panels.glb (each panel in its own colour)
  skirt-front       0.861 m2   flat    405 x   2611 mm   fits the roll
  top-1             1.992 m2   flat    966 x   2758 mm   fits the roll
  top-2             2.069 m2   flat   1002 x   2860 mm   fits the roll
  skirt-back        0.774 m2   flat    334 x   2594 mm   fits the roll
  skirt-right       0.342 m2   flat    313 x   1148 mm   fits the roll
seams  9, hem 6.30 m
  skirt-front/top-1                    258.8 cm   top-1 laps over
  ...
```

## Look at it

`panels.glb` shows every panel in its own colour on the furniture. Copy it to your laptop and
drag it onto gltf-viewer.donmccurdy.com:

```
scp dev@168.119.50.82:~/cover-pattern-engine/models/blocchi-2seater-moon-right/panels.glb ~/Downloads/
```

## Where the seams go by themselves

- **Skirt seam:** all round at one height (company rule: easy, straight lines for clean
  stitching), just below the lowest point where the top starts to round over. The skirt panels
  are straight strips. The top laps over the skirt. To set the height yourself (for example
  40.6 cm, as on a cover that fits), put `seams.skirt_height_mm` in the model's `cover.json`.
- **Walls:** where the furniture's top edge stands clearly higher than the skirt seam (more than
  2 cm, `seams.wall_min_mm`, over at least 30 cm), the upright part between them becomes a wall
  panel: the back and sides of a chair, the middle of the Blocchi front. The top then never has
  to wrap down over its edge (which would stop it lying flat). A wall ends in a short upright
  line where the edge comes down again; it laps under the top and over the skirt.
- **Corners:** a vertical seam wherever the skirt turns a sharp corner (tables, boxes, the
  straight end of the Blocchi), placed in the middle of the bend. A skirt stretch longer than
  3 m (`seams.max_skirt_panel_mm`, to confirm) is split into equal parts. A round skirt with no
  corners gets one seam at the back.
- **Too wide for the roll:** a top panel wider than the usable roll width (1480 mm) is split.
  First the program tries a seam at constant height (the upper panel laps over the lower, like
  roof tiles, so water runs over it). If that would leave a panel that cannot lie flat, it
  splits straight along the panel's length.

Every panel is checked: it must lie flat in one piece, and it must fit the roll. The flat sizes
shown here are a quick estimate; the exact patterns come in the next step (M4).

## Placing seams yourself

Copy the seams the program used, then edit them:

```
cp models/<id>/seams.auto.json models/<id>/seams.json
```

`seams.json` holds floor-plan coordinates in mm (x across, y from front to back, front at
negative y), as seen from above:

```json
{
  "format_version": 1,
  "skirt_seams": [[731.8, -699.4], [1182.8, 325.7], [-600.0, 650.0]],
  "top_seams": [[[-1100.0, 150.0], [0.0, 250.0], [1100.0, 180.0]]]
}
```

- `skirt_seams`: one point per vertical skirt seam. The seam goes where the outline is nearest
  to the point.
- `top_seams`: lines across the top, as a list of points. Two points make a straight seam; more
  points make a curve.

`cover cut` uses `seams.json` automatically when it is there; `--seams other.json` picks
another file. Leave out `skirt_seams` or `top_seams` to keep the automatic ones for that part.

Tip: open `panels.glb` in the viewer, look from above, and read positions off the cover's size
(`cover info` gives it), or ask Claude Code to place a seam "along the back cushions".

## Reading the list

- **flat … x … mm:** the panel laid flat, width first (in its narrowest direction).
- **fits the roll / TOO WIDE:** compared with the usable roll width.
- **laps over:** the panel whose edge lies on top at that seam. For water: higher over lower, the
  top over the skirt, and the front panel over a side panel.
- Seams that curve tightly are listed in `panels.json` (`tight_seams`). For welded covers they are
  also printed as a warning.
