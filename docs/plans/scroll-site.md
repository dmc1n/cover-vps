# Plan: the website as one scrolling story, in the S2DIO house style

The owner, 5 October 2026: "now we really focus on the design: a fine animation on the first
screen (the film we are rendering), a very modern website, preferably a single page where
something happens with every scroll, for example following the process of how we work".

## The story, top to bottom

| # | Section | What moves on scroll | Made from |
|---|---|---|---|
| 1 | **Hero** | the welcome film full screen; scrolling shrinks it into the S2DIO arch (the rounded corner of the logo) | our Blender film (ADR-065); a Veo clip until it is done |
| 2 | **Your furniture** | the real sofa turns slowly into view | the SUNS model itself |
| 3 | **We calculate the cover** | the cover grows around it, piece by piece in the house greens | the studio's own cover surface and pieces |
| 4 | **Seams and pieces** | the pieces step apart and the seams show | the cut (`panels.npz`) |
| 5 | **Flat, on the roll** | every piece unfolds from 3D to its flat pattern and lies on a 152 cm roll | the flattening (exact lengths) |
| 6 | **Cut, sewn, fitted** | the pieces fly back and fall over the sofa as the drape computed | Style3D (`drape.bin`) |
| 7 | **Tested in the rain** | the fabric darkens, drops fall and run off | the rain check |
| 8 | **How we work** | clips in arch frames slide in sideways: measuring, cutting, sewing, packing | Veo 3.1 (the people and the workshop) |
| 9 | **Green** | true numbers count up: made to order, no stock, our range | the catalogue |
| 10 | **Design yours** | the configurator; then the FAQ | as now |

Steps 3–7 are one pinned 3D scene in which scrolling scrubs the shapes: the same vertices
morph from the cover surface, to flat, to the draped cover. It is our own data, so no other
website can show it, and it is honest.

## Style (docs/brand.md)

- **Colours:** Off White `#F1F2F2` as the ground; Dark Green `#3C443C` for type and dark
  sections; Green and Light Green for the pieces and the lines.
- **Type:** Work Sans throughout. Large, light headings with a lot of space.
- **Shape:** the arch (a rounded top corner from the logo) frames the videos and the 3D scene.
- **Motion:** slow and smooth (Lenis for the scrolling, GSAP ScrollTrigger to scrub). Nothing
  bounces. Visitors who asked their device for less motion get the stills.

## How it is built

- **Front end.** `apps/web/src/shop/`: a new home page (`Story.tsx`). The configurator,
  orders and the rest keep working and take the new colours and type.
- **Data.**
  - `/api/shop/story/<model>.bin` and `.json`: the morph data of one catalogue model (design,
    flat and draped shape per vertex, piece per vertex). The studio computes it once and keeps
    it in `data/story/`.
  - `/api/shop/story/<model>-furniture.glb`: the furniture as one mesh.
  - The model is a setting (`story_model`, default the Kota 2-seater).
- **Texts.** A `story` section in the content, so the AI CMS edits and translates it like the
  rest.
- **Media.** Clips and the film live in the studio's `media/` and are served through the
  website at the edge.
- **Preview.** A second Worker at `preview.s2dio.living` (noindex). It serves its own fresh
  build and asks the studio for the data. The live site changes only with a release.

## Help from outside, as agreed

- **Gemini Veo 3.1 Fast** for the people and workshop clips (8 s each).
- **Modal GPU (L4)** for the heavy renders: the film, later scroll sequences rendered in Blender
  instead of live 3D where that looks better.

## Storyboard 2: everything our own render (9 October 2026, ADR-114)

The owner (9 Oct): "only when scrolling we still have the static rain; the animation is much
better — make the animations further down yourself too, so everything is based on our own
material; then we can also make animations for the scroll steps." Later the same day: one more
film, the cover at a villa on Ibiza over the sea.

The look is the start film's (ADR-108): the SUNS Kota 2-seater, its real cover in sand
Coverlast with the stitching baked from the flat pieces, the stone terrace against lime plaster,
a low hazy sun; the workshop's felt cutting table. `scripts/film/render_reel.py`, one shot a call.

**The six scroll chapters** (60 pictures each, scrubbed; the cover right of centre, the captions
on the calm left; each chapter ends at rest, its last picture is the still for less motion):

| # | Caption | What the pictures show | Our data |
|---|---|---|---|
| 1 | Your furniture | the bare sofa on the terrace, a slow arc; its length, depth and height draw themselves in as dimension lines, to the centimetre | model.glb's size |
| 2 | We calculate the cover | the designed cover surface rises around the sofa from the stone up, a thin line of light where it is being computed, a fine grid while it is still computed; then it turns into fabric with its stitching | the designed surface (cover.npz `design`) |
| 3 | Seams and pieces | the cover steps apart into its seven real pieces, the top ones lifting; the seams between them show | the cut (`piece`) |
| 4 | Flat, on the roll | the workshop: the pieces fly to the table and lie down flat, each on its own place in a nest on the 152 cm roll; the pen writes cut.dxf's labels and lines, the knife cuts the outlines, the vent hoods and membranes too | the flat patterns (`uv`), cut.dxf on the roll (`reel.json`) |
| 5 | Cut, sewn, fitted | close along the double-stitched corner seam; then the cover is lowered over the sofa and settles | seams.png, fall.npz → Style3D drape |
| 6 | Tested in the rain | the sun goes in, the stone darkens, beads form on the coating and the water runs down the paths our rain check computed and gathers at the hem; the falling rain is drawn by the page in time (RainLayer), never baked into a picture | drape_rain.json |

**The workshop cards** ("How we work", 4:5 loops of 4–5 s, AV1 + H.264 + poster, loaded when
near): cutting (the knife along a piece's edge, the pen labels beside it), sewing (along the
double-stitched corner seam from the hem up), the air vent (hood, insert, membrane), made to
measure (the cover lowered), rain (beads and runoff, falling rain), our range (other covers from
the catalogue on the terrace). The Veo clips (measuring, cutting, sewing, packing) and the Veo
rain clip go.

**The closing film**: the cover on a whitewashed villa terrace on Ibiza, terracotta tiles, a
wooden pergola's slatted shade, the sea to the horizon and a rock island in the haze, low golden
sun; a slow dolly; with the last call to action.
