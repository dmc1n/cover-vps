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
