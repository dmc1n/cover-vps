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
5. **Choose the cover plan** (the card **Cover plan** under the picture). It shows the set
   seen from above three ways, with the cover's outline in red and its size in cm (ADR-095):
   - **Follow the products (sharp corners)** — the default. The cover runs round each piece:
     an L stays an L with a right-angled inner corner, every wall hangs straight down. Each
     piece gets its own top, sloping down to its own front; where one piece is higher (the
     chaise longue's long slope next to the sofa), its side wall continues up as a step.
   - **One rectangle around everything** — a simple box over the whole set; it also covers the
     open corner.
   - **Smoothed outline** — the first version: the tightest box, with a slanted wall cutting
     the open corner diagonally.
   The card also says how much floor each plan covers where no piece stands.
6. **Build cover**. It takes from half a minute to a few minutes. When it is done, **Open the
   model ↗** shows the cover in 3D, its sizes, the air vents and Unfold, like any product.

The arrangement is a normal model called `arr-<name>`, with the tag **arrangement**: it is in
the catalogue and at the Desk, and it has cut files, a size drawing and revisions.

## Change one

Open it from the list under the name field, move the pieces and press **Build cover again**.
Clicking another plan in **Cover plan** builds the cover again at once with that plan. If one
of its products was changed after the arrangement was made (a new 3D file), the page says so:
build the cover again. Arrangements made before 7 October 2026 were built with the smoothed
outline; opened, they offer the default plan, and the page says the cover was built smoothed.

## What to know (to be decided with the owner)

- The cover is a box made of flat pieces (`arrange.hull_top: box`). With **Follow the
  products** every face is one piece; a top wider than the roll is cut into strips with seams
  running downhill. Settings: `arrange.footprint` (the default plan), `align_mm` (sides of
  neighbours this close are lined up), `close_mm` (gaps this narrow are closed), `top_faces`,
  `top_gain_pct`, `top_slopes` (front: tops slope only to each piece's front, so no diagonal
  seams on top).
- Each piece is covered as its plan rectangle: a rounded arm is covered square.
- Air vents go only on the outer walls; the walls of the inner corner get none (ADR-093).
- The skirt runs at one height all round; where a piece is lower (the chaise longue's back),
  the skirt there is short, and the program may place no air vent on that side.
- **Snap** puts pieces touching (`arrange.gap_mm: 0`, a company setting). For a gap, drag the
  piece a little after snapping.
