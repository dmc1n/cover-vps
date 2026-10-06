# Plan: back to two routes, simple and fast

The team (6 October 2026): "We may need to reduce the complexity. With so many functions, every
improvement has to recalculate so much (time and tokens). The focus must be on two things: a
model from our 2D drawing, and a cover from our 3D cover surface. Both with the air vents by our
rule and the pieces split to fit the roll. And does the learning really learn?"

## What runs today (measured)

- **The four core steps** (hull, cut, flatten, export) make no paid calls, but they always do
  extra work:
  - flatten always writes the size drawing (sizes.pdf);
  - export always renders cover.png;
  - export always flattens every skirt piece a second time for the vents in 3D;
  - export always copies a revision.
- **After every save in the web app** a drape job is queued automatically. It runs the Style3D
  fall (on a Modal GPU), a rain simulation and two AI verdicts. This is the expensive part.
- **No caching.** "Run again" recalculates hull → export in full, and nothing compares the
  stored parameter hash before a step runs. The browser decides which steps follow a change.
- **The 2D route exists only as scripts.** Six different readers (AI-based and AI-free), then
  the 3D route's "given" path. There is no upload for it in the web app.
- **The learning:** an accepted lesson is only text in the AI's prompts. The geometry (seams,
  drawing reading, pieces) never reads it, so a lesson does not change the next cover.

## The two routes

**A. Drawing (PDF) → cover**
1. Upload the PDF on the Models page, as a new model or onto an existing one.
2. The program reads the drawing itself (ADR-075):
   - the views and the scale from the size arrows;
   - the shape: the plan, cut by the side view, or the plan straight up;
   - the vent count from the text or the arrows.

   One reader, no AI.
3. **When the reader cannot build the shape**, the cover is marked "needs a person"; nothing is
   guessed. The AI reading (ADR-068) is only a button for that case.
4. The pieces are joined where there is no crease (ADR-076). From there it is route B.

**B. 3D cover surface → cover**
1. Upload a STEP/STL/GLB of the cover.
2. Seams:
   - one panel per part when the file has parts (as drawn by you);
   - otherwise found from the folds;
   - the skirt at one height.
3. Air vents by your rule: the drawing's number wins.
4. Pieces split to fit the roll (1480 mm).
5. The DXF for the cutting table.

**Common to both:** after the cover is built, one AI check (Gemini Flash + DeepSeek, about
€0.05). It is optional, and on by default only for new covers.

## What goes out of the standard route (still available as a button)

| Feature | Now | After |
|---|---|---|
| Drape on GPU + rain + 2 AI verdicts | after every save | button "Drape check" |
| AI choosing box pieces / balloons | automatic for tables | a fixed rule; the AI only as a button |
| Size drawing (sizes.pdf) | every flatten | when opened or downloaded |
| cover.png render | every export | once, after the last step |
| Second flattening for vents in 3D | every export | reuses the flatten result |
| Revision copy | every export | when the DXF changes, or on "save version" |
| Seam proposals / improve loop | button | unchanged |

The shop, the website and the configurator are a separate line. They stay as they are and are
not part of a cover's calculation.

## Faster improvements: only what changed

- Every step stores the hash of its inputs: the parameters it reads, plus the files of the step
  before.
- A step whose inputs did not change is skipped.
- A changed vent setting reruns export only; a changed clearance reruns hull and everything
  after it. The server decides this, not the browser.
- A batch over 115 covers after a vent rule change then takes minutes, not hours.

## Learning that really learns

1. **Structured feedback at the Desk** instead of free text:
   - "this seam: remove / move here / add";
   - "this size was read wrong: it is …";
   - "this shape is missing: round front / back profile / …".
2. **Each piece of feedback becomes a parameter or rule per cover family**, for example:
   - "corner sofa: back strip 30 cm, seam on the ridge";
   - "skirt seam 2 cm below the edge".

   The next calculation uses it. Every accepted correction also becomes a test case.
3. **The team's reference set** (10–20 good covers with their seams; question 67) becomes a
   score that every change is measured against. The program may only change when the score
   stays the same or improves.

## Order of work

1. **Off by default:**
   - the automatic drape;
   - the hull AI choosers;
   - the always-on extras.

   Result: saves money and time at once.
2. **Step cache and server-side dependencies.**
3. **Route A as one command and one upload in the web app.** It uses the AI-free reader, with
   "needs a person" as the fallback.
4. **Structured Desk feedback → parameters and tests.**
5. **The reference set as a score.** This waits for the team's covers (question 67).

Steps 1 and 2 are about a day. Step 3 is about a day. Step 4 is one to two days.
