# Plan: the drape simulation, the sewn cover falling over the furniture

The owner, 2 October 2026: "a simulation button where the cover really falls over the product.
The surface is now built on the cover surface, but when that disappears the cover itself will
fall over the product. This must be a lifelike simulation where you also see, for example,
folds where there is too much fabric."

## What it shows, and why it matters

Today the 3D view shows the *designed* cover surface: the shape we want. The simulation shows
the *real* cover: the cut pieces, sewn along their seams, hanging under their own weight on
the furniture (and on the balloons for tables).

Its value is that the pieces keep their **flat lengths**. Where a pattern is too big, the
fabric folds; where it is too small, it pulls tight. Where the top sags between supports,
water may stand. So it checks the patterns themselves, before anything is cut: the step
between "the drawing is right" and "the sewn cover is right".

## How

1. **The pieces as cloth.**
   - Every piece of `pattern.json` (the outline without seam allowances, as sewn) is
     triangulated at an even size, about 15 mm (`drape.edge_mm`).
   - The two sides of every seam get the same points (from the seam lengths and the matching
     marks), and are sewn: the points of both sides become one.
   - The rest length of every triangle comes from the flat piece, not from the 3D shape.
2. **The start.**
   - Every piece starts where it lies in the designed cover (each flat piece knows its 3D
     place), a few millimetres outward. That is the cover sewn and slipped on.
   - Then the support (the designed surface) is gone and gravity acts.
   - The hem drawcord can pull the bottom edge in (`drape.cord_tension_n`).
3. **The physics:** extended position-based dynamics (XPBD), our own solver, compiled with
   numba (BSD licence) for speed, and deterministic.
   - **Stretch:** the fabric's stretch per direction (warp, weft, bias) from the fabric profile.
     Acrylic canvas hardly stretches.
   - **Bending:** stiffness from the fabric profile. A stiff canvas makes big, soft folds; a thin
     cloth makes many small ones.
   - **Weight:** gravity on the fabric's weight (g/m²), plus damping and friction against the
     furniture.
   - **Contact** with the furniture through its distance field (we compute that already for the
     cover surface), with the balloons, and with the ground.
   - **Self-contact**, so folds lie on each other instead of through each other. Done with a
     spatial grid; it costs time, so it is the last step to switch on.
   - The simulation stops when the cover lies still, with movement below `drape.rest_mm_s`.
4. **What comes out** (`drape.glb`, `drape.json`):
   - the cover as it falls, as an animation (about 60 frames), and as it lies at the end;
   - **folds:** where the fabric is compressed or bends sharply (too much fabric), as a colour;
   - **tension:** where it pulls tight (too little fabric);
   - **sag** between supports, and **water** on the draped shape. The rain simulation runs on
     the real shape, not on the designed one;
   - the **gap** between cover and furniture, and where the cover touches it.
5. **In the 3D view:** a **Drape** button.
   - It runs the simulation as a background job, minutes for a sofa.
   - It plays the fall, then shows the cover as it lies.
   - Layers: folds, tension, sag and water, and the designed surface to compare.
   - A short verdict comes from DeepSeek on the picture and the numbers ("folds along the
     front edge: about 2 cm too much fabric there").
6. **In the audit:** a new check, *drape*: no large folds, no ponding on the draped shape, and
   no tension above the fabric's limit. With `cover drape --all` it runs over the catalogue at
   night.

## Tests (that it is real, not just pretty)

- **A square cloth on a sphere and on a box:** it folds at the corners, like a tablecloth. This
  is the standard cloth test; compare the fold count and shape with the reference pictures.
- **A strip hanging between two supports:** the sag matches the catenary within 2 %.
- **A pattern that is exactly right** (a box cover flattened at 0 % stretch) **drapes without
  folds**. The same with 3 % too much fabric shows folds where the extra is.
- Deterministic: the same input gives the same result.
- The real test is a physical gate: the first sewn cover on the furniture, photographed from
  fixed angles, against the simulation from the same angles. The fabric values are then
  adjusted to the photos (`config/defaults.yaml`, `testdata/fabrics/`).

## Order (tonight and onward)

1. The solver with stretch, bending, gravity, furniture contact and ground; the analytic tests.
2. Sewing the pieces from `pattern.json`; the start position; the Kota 2-seater as the first
   case, then the Lucia and a table with balloons.
3. The fold, tension and sag measures; `drape.glb` and `drape.json`; `cover drape`.
4. The Drape button, the playback and the layers in the 3D view; the job in the background.
5. Self-contact, the cord tension, the AI verdict, the audit check, the night run over the
   catalogue.

Steps 1 to 4 are for tonight. Step 5 follows when the first results look right.

## Limits, said honestly

- The server has no graphics card (8 CPU cores, 15 GB), so a sofa cover at 15 mm takes minutes,
  not seconds. The button starts a job; the result is kept and shown again at once.
- Without measured fabric values the folds have the right *places* (too much or too little
  fabric is geometry), but their *size and number* are an estimate until the fabric is
  measured.
