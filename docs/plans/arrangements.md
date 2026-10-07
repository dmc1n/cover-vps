# Plan: arrangements, one cover over furniture placed together

The owner, 7 October 2026: "we want to put products together, e.g. the SUNS 2-seater Portofino
with the chaise lounge Portofino. We first place the products in the arrangement we want, then
we produce a cover; so we can also make larger covers for fixed arrangements."

## What the owner gets

- **An "Arrangements" page in the studio.**
  - Pick models from the catalogue.
  - See them from above and move them by dragging.
  - Turn a model 90° or mirror it.
  - Use "snap to the side of …", so nothing has to be typed in mm.
  - The overall size is shown all the time.
- **"Build cover".** The furniture as placed becomes one new model, `arr-<name>`, and is
  calculated like every model: the cover surface, seams, pieces that fit the roll, vents by the
  rule, the DXF.
  - It shows up in the catalogue (tag "arrangement") and at the Desk, to be approved like any
    cover.
  - The model page has everything: 3D with Show dimensions and air vents, Unfold, sizes.pdf.
- **Rebuild.** The arrangement keeps its members, their places and each member's version
  (`arrangement.json`). When a member changes, or a member is moved, "Build cover" makes the
  cover again.

## Steps

1. **Engine** (`coverengine/arrange.py`).
   - Load each member's own furniture mesh (its `model.glb`, not its cover).
   - Mirror, turn and place each one.
   - Join them into one mesh and import it as a new model.
   - Snap helpers: put a member against another's left, right, front or back side, aligned at
     the back, the front or the middle.
2. **The standard pipeline makes one cover over the whole.**
   - The drape hull bridges gaps up to `hull.bridge_gap_mm`.
   - The skirt is at one height.
   - Pieces are split to fit the roll.
3. **API.**
   - `GET /api/arrangements` lists them.
   - `POST`/`PUT` create or update one and build it (a background job).
   - Outlines of the members for the page.
   - Snapping, computed on the real meshes.
4. **Web page:** the top view (SVG) with dragging, turning, mirroring and snapping, a small 3D
   view, and "Build cover".
5. **Tests**, an ADR and the handbook.

## Open questions for the owner

1. **One cover or several that join?** Over a fixed arrangement this version makes one cover.
   Should a large arrangement instead be several covers that zip or velcro together (easier to
   put on, and parts can be used apart)?
2. **The gap between members.** Members touch (gap 0), or stand a little apart? Where they
   stand apart, the cover spans the gap as one surface.
3. **Mixed heights.** A sofa (back 85 cm) next to a lower chaise lounge: one skirt height all
   round, with the top following each member (the current hull), or one flat top over all?
4. **Names.** Should an arrangement get a product number or name in the catalogue, like the
   SUNS sets ("Portofino corner set left")?
