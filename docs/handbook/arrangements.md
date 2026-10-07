# Arrangements: one cover over furniture placed together

A customer who always keeps the SUNS Portofino 2-seater and its chaise longue together as a
corner wants one cover over the set, not two. An arrangement does this: you place catalogue
products where they stand, and the program builds one cover over the whole (ADR-089).

## Make one

1. Top bar → **Arrangements**.
2. Give it a name (for example "Portofino corner").
3. Type in **Add a model** and pick a product. Add the second one the same way. Only products
   with an imported 3D model can be added; an arrangement cannot be part of another one.
4. Place them. The picture is the set **seen from above, the front at the bottom**.
   - **Drag** a piece to move it. It moves in steps of 1 cm (`arrange.grid_mm`).
   - Click a piece to select it, then **Turn** (90° left or right, `arrange.rotation_step_deg`)
     or **Mirror** (a left-hand chaise longue becomes a right-hand one).
   - **Snap to**: choose the other piece, the side (left, right, front, back) and how to line
     up (back, front or middle; for front and back: left, right or middle), then **Snap**. The
     selected piece is put tight against the other one.
   - The overall size (cm) is shown above the picture.
5. **Build cover**. It takes from half a minute to a few minutes. When it is done, **Open the
   model ↗** shows the cover in 3D, its sizes, the air vents and Unfold, like any product.

The arrangement is a normal model called `arr-<name>`, with the tag **arrangement**: it is in
the catalogue and at the Desk, and it has cut files, a size drawing and revisions.

## Change one

Open it from the list under the name field, move the pieces and press **Build cover again**.
If one of its products was changed after the arrangement was made (a new 3D file), the page
says so: build the cover again.

## What to know (to be decided with the owner)

- The cover is built as a box (`arrange.hull_top: box`, `arrange.box_pieces: 8`): one sloping
  top over the whole set. On a corner (an L shape) the top is one big panel and can be wider
  than the roll; the size drawing then warns. A top that follows each piece is a later step.
- The skirt runs at one height all round; where a piece is lower (the chaise longue's back),
  the skirt there is short, and the program may place no air vent on that side.
- **Snap** puts pieces touching (`arrange.gap_mm: 0`, a company setting). For a gap, drag the
  piece a little after snapping.
