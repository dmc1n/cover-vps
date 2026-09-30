# Improvement plan (night of 30 Sep – 1 Oct 2026)

The owner asked: download objects, check all functions, make a plan to improve the service, and
carry it out; then: make the covers for every SUNS product on 3D Warehouse. This file records
what was checked, what was fixed, and what is next, most important first.

## 1. What was checked

- **Every command** (`version, params, import, hull, cut, flatten, drawing, export, run, diff,
  info, model, batch, improve, report, testsheet`) on the test furniture: all work.
- **The web app** in a real browser (`make e2e`): upload, every tab, settings, trial run,
  status, revisions.
- **8 CC-BY models from the FreeCAD library** (Adirondack chair, folding chair and table, IKEA
  Lack, dining table, three chairs).
- **The SUNS catalogue on 3D Warehouse:** 521 models, of which 447 need a cover; 348 single
  products, 99 sets (several products in one file). 304 of the products can be downloaded as
  GLB without a login and were all run through the whole chain.

## 2. Fixed tonight

| found on | problem | fix |
|---|---|---|
| folding chair | the frame encloses an empty area seen from above: the cover had a tube down to the floor | holes in the footprint are filled |
| IKEA-like chair, folding chair | splayed legs: the lowest edge is the floor, so no skirt | minimum automatic skirt height (15 cm, to confirm) |
| Adirondack chair | corners a few cm apart gave skirt strips of 6 cm | corners closer than 30 cm get one seam (to confirm) |
| most real models | wall seams zig-zag 4–7 mm on slightly leaning or faceted walls | the seam is smoothed in place when it zig-zags; clean seams keep their corners |
| IKEA-like chair | an invalid flat outline crashed the size drawing | outline repaired before measuring |
| dome, sofas | "an extra seam would help" without saying where | seam proposals in the seam editor; along a fold when the stretch lies in a strip |
| the whole catalogue | no overview of which covers are good | `cover report` and the web list: ready / to check / failed with the reasons |
| sofas, chairs | proposals had to be taken one by one | `cover improve`: takes proposals round by round while the stretch goes down |
| tables | the balloon makes a dome | a ridge frame (gable roof) as an option; on the test tables not better yet |

## 3. What the SUNS run shows (see the catalogue report)

- **Tables:** mostly good: stretch under 2 % on most rectangular tables; the seams between top
  and skirt differ by 1–3 cm (the balloon tent). Round tables of 150–170 cm are wider than the
  roll in one piece.
- **Seating (sofas, lounge chairs, dining chairs, loungers):** the top stretches 8–35 %. One
  top piece over seat, back and arms cannot lie flat. `cover improve` brings it down by a third
  to a half; it needs a **seam layout per family**, as the owner drew for the Blocchi (a band
  along the back).
- **Air vents** do not fit on most seating: the automatic skirt is 15–24 cm, a vent needs
  28.5 cm (question 4).
- **A few pieces fail to flatten** (thin wall strips at the ends of walls); the stretch report
  shows thousands of %.
- **The Blocchi from SUNS (GLB) fits the owner's cover far better than the STEP file:** top of
  the cover 88.1 cm above the floor (cover 88.0), depth 192.8 cm (192.4), hem 659 cm (668).

## 4. Next, in this order

1. **Seam templates per family** (owner input needed, question 18): a template is a set of
   seam rules relative to the furniture (a band along the top of the back, the arm tops, the
   front of the seat); `cover.json` names the template; the seam editor shows it. Target: every
   lounge sofa and chair of SUNS under 2 % stretch.
2. **Skirt height with vents:** when a cover has vents, the skirt is at least vent + allowance
   high (28.5 cm), if the owner agrees (question 4).
3. **Wall ends:** no wall strips thinner than a few cm (merge them with the top), which removes
   the flattening failures.
4. **Round tables wider than the roll:** split the top along its diameter or a ring (owner:
   which one; question 19).
5. **Balloon seams on tables:** the 1–3 cm difference between top and skirt (the dome edge);
   try a lower, wider balloon or a frame with a seam along the ridge.
6. **The 44 SUNS products that need a login and the 99 sets** (questions 20 and 21).
7. **Speed:** a product takes about a minute; the whole catalogue about 2 hours at 3 at a time.
   Fine for now.
