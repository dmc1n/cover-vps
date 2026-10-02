# Rain on the cover: research and plan (2 October 2026)

The owner asked for an AI-driven rain simulation in the 3D view, as real as possible, to see
where water could collect on a cover. This note sets out what decides where water goes on a
fabric cover, which methods exist, and what the program does with each.

## What happens to rain on a fabric cover

1. **Water runs down the steepest way.** On each point of the cover the water goes where the
   surface drops fastest; streams join where the surface forms a valley (a crease between two
   slopes, the low middle of a gable end). That is ordinary surface hydrology.
2. **Water stays in hollows and on flat parts.** A hollow (a point lower than everything round
   it) fills until it runs over its lowest edge; a nearly flat part (less than about 5° on
   fabric) drains so slowly that water stands on it and dirt and algae collect.
3. **The fabric gives under the water.** A pond is heavy (1 cm of water is 10 kg/m²); tensioned
   fabric sags under it, the hollow gets deeper, more water collects: ponding, the classic
   failure of tents and fabric roofs. Whether it stops or grows depends on the span between
   supports (furniture, balloons) and the tension in the fabric.
4. **Seams leak when water runs along them.** A stitched seam is a row of holes; water that
   crosses a seam runs over it, water that runs along a seam for a long way soaks in. The
   upper piece lapping over the lower one (rule 6) helps on crossings, not along.
5. **Smaller effects:** the fabric's water repellency (WeatherMax beads water), wind-driven rain
   from the side, dripping from the hem. Second order for "where does water stand".

## Methods, from simple to heavy

| method | what it gives | cost | used |
|---|---|---|---|
| depression filling (priority flood) on the cover's height map | every hollow, its depth, area and volume, exactly, for a rigid cover | a second | yes |
| slope map | the parts flatter than the minimum slope | instant | yes |
| flow accumulation (how much area drains through each point) | the streams and valleys, where water concentrates | a second | yes |
| drop tracing (drops follow the steepest descent) | animated rain in the 3D view, where each drop leaves the cover | a second for a few hundred drops | yes |
| membrane sag under pond weight (tension T, span L: sag = water load × L² / 8T), iterated | whether a pond stays small or grows (ponding) | a second | yes, as an estimate; T to measure (M8) |
| seam crossing check (does the flow run along or across seams) | seams at risk of leaking | a second | yes |
| shallow-water equations on the surface | water moving in time, splashing | minutes to hours | no: the static answer is what matters for a cover |
| fabric finite elements with water load | the real sag shape | hours, needs measured fabric data | later, when the fabric is measured |

## What the AI does

The physics is computed, not guessed: an AI model cannot simulate water reliably. The AI
(DeepSeek) gets the results (ponds with depth and area, flat parts, streams, seams the water
runs along, the sag estimate) and a top view of the cover with the streams and ponds drawn
on, and answers in plain words: is this cover safe in the rain, where is the risk, why, and
what would help (another balloon, a steeper slope, a seam moved, a gable instead of a flat
top). Its answer is shown next to the simulation and kept in rain.json.

## In the program

- `cover rain models/<id>/` writes `rain.json` (the numbers, the drop paths, the AI's advice)
  and `rain.glb` (the ponds and flat parts as blue surfaces just above the cover).
- In the web app, 3D tab: a **Rain** button runs it (or shows the last result): drops run down
  the cover along their paths, ponds and flat parts light up, and the AI's verdict is shown.
- Settings (config/defaults.yaml, `rain.*`): drops, the cell size, the depth that counts as a
  pond, the fabric tension for the sag estimate (to measure in the swatch tests).
