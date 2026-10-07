# Plan: the program reads the drawings itself, the AIs check (optimising ADR-072)

The owner, 5 October 2026, after S45: "this looks much better, this is the way to go. Is there a
way to optimise this way of working? If so, make a proposal."

## Where we stand (measured today)

Gemini and DeepSeek checked all 24 free-form drawing covers built so far, and checked each
other (`scripts/drawing_crosscheck.py`, out/drawings/crosscheck/):

| Outcome | Covers |
|---|---|
| Agreed: the same | S25, S45 (new way), S46 |
| A person to check (they disagree) | S26 (Gemini 100, DeepSeek 70; most likely right) |
| Agreed: different, only small things (score ≥ 85) | C26, L4, S43 |
| Agreed: different, the shape is wrong | C27, D1, D5, D6, S24, S27, S32, S37, S38, S39, S44, S47, U2, L1/L5, L4/L8, S13/S14 Nardo, C31 |

- 16 of the 24 have **the wrong number of air vents**. The drawing writes it ("4 Air Pocket"),
  the program used its own rule (one per metre of each side).
- The shape errors are of a few kinds:
  - **a footprint that is not a rectangle** (tapered, trapezoid: S38, S39, D6, S24);
  - **a curved front or rounded end** (S37, S32, S44, D5, S47);
  - **U and L shapes** read wrongly (C27, L1/L5);
  - **two covers on one drawing** (S13/S14).

## The way of working, in five steps (what changes)

1. **Read the lines, not the picture.** The PDF is CAD output: every view is exact lines.
   - The program sorts them into views: top, front, side, and the 3D view.
   - It links every written size to the two points its arrows touch, so a size belongs to a
     line, not to a guess.
   - It reads counts and features from the text: "4 Air Pocket", "Open From Bottom",
     drawstring, zip.
2. **One shape family for everything: footprint plus heights.**
   - The footprint is the outline seen from above: rectangle, trapezoid, kidney, U, L, curved
     front.
   - Over it go the heights: front and back height, slope, rounded edges, from the front and
     side views.
   - This one generator replaces box, sloped box, L shape, round and most of the swept shape.
     It already works for S45.
3. **No plan view? Fit the 3D view.**
   - Many drawings show the shape only in the 3D view (S44, S47, S32, C26).
   - The program then adjusts the footprint until its projection lies on the 3D view's lines.
   - This is the check that settled S45's 152.4 against 358.4 today, used as the builder.
4. **Every written thing must come back.**
   - Each size, each count (vents) and each feature is checked against the built cover.
   - What does not come back is listed by name.
   - Two written sizes that contradict each other become a question to you, never a silent
     choice.
5. **Two AIs check, and check each other.**
   - Gemini looks, DeepSeek reads; when they disagree, a person looks.
   - The AIs never decide the shape.
   - What you approve or correct becomes a test drawing: the next change to the program must
     still build it right.

## Phases

| Phase | What | Result you can see |
|---|---|---|
| 1. Quick win | Air vent count and features read from the drawing text, per cover (a new setting `features.vents_total`, spread over the sides) | 16 covers right on vents; one re-run |
| 2. Views and size arrows | Sort each drawing's lines into views; link sizes to their arrows | per drawing: "the program read: …", shown beside the drawing |
| 3. Footprint plus heights | The one generator; trapezoid, curved front, rounded end, U, L | S38, S39, D6, S24, S37 rebuilt |
| 4. Fitting the 3D view | Heights over the top view's footprint fitted to the 3D view (done for corner sofas, ADR-091); footprint from the 3D view alone still open | C3, C4, C8, C9, C10, C29, C30, C31, S33 built in staging (out/drawings/phase4) |
| 5. Drawing desk in the studio | One page with every drawing: the drawing beside our cover, the check's outcome, buttons "right" / "wrong, because …" | you approve in minutes; each "wrong" becomes a lesson and a test |
| 6. Faster and cheaper | Only changed drawings are re-run; the AI check only after a change; builds in parallel (Modal CPU when there are many) | a full run of 130 drawings in about 15 minutes instead of hours |

Phases 1 and 2 are a day's work. Phase 3 is the core and takes about two days. Phases 4 to 6
take one to two days each.

## What I need from you

- **Question 64 (S45):** 152.4 cm long, or 358.4 cm round as written in inches?
- **Vents:** when a drawing gives a number, does the drawing win over the rule of one per
  metre? (I assume yes.)
- **The drawing desk:** who approves the covers? Every editor, or you only?

## Phase 4, as built (7 October 2026, ADR-091)

- **What it does.** A corner sofa (L, C, V) drawn as a top view plus a shaded 3D picture, with
  no front or side view. Until now route A could only stand the top view straight up, a flat
  block. The block's outline still covers the picture about 97 %, so the IoU check let it through.
- **How.** The top view gives the footprint. Over it go the heights: the back height, a flat
  strip, a slope to the front height, and the arm ends falling to a lower end wall. Each height
  is one of the sizes written on the drawing, a different one each. They are chosen so that the
  cover, drawn as the CAD program draws its 3D view, lies on the picture: its outline (IoU ≥ 85 %)
  and its creases, where faces meet (≥ 65 %). The footprint's own lengths must be written too.
- **Result.** C4, C8, C9 and C10 come back with every written height: back, strip, front,
  end wall, hip length. So do C31 and S33, and C3, C29 and C30 (also rejected on shape). The
  3D view's creases match about 85 % against 35-50 % for the live covers.
- **Not yet.** The fit needs a shaded 3D picture with its transparency mask. That leaves out:
  - wireframe drawings (S4/S5, S6/S7, L1, L1/L5, S6, S8, S20, U2, D1, D2): this needs the vector
    lines read as a 3D view, the next step;
  - curved footprints without a top view (S32, C28, S44, S43, S25);
  - shapes outside the family: S19 (an arm block beside the seat), S27 (a Blocchi chair).
