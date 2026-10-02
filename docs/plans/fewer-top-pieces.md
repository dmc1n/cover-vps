# Plan: no slivers, the top in as few pieces as the roll allows (learning from the Lucia)

The owner, 2 October 2026, on suns-lounge-lucia-2-seater-right: "the top can be cut in one
piece". And on the follow-up: "we must learn from these mistakes and make sure this does not
happen again".

## What went wrong

The Lucia 2-seater right got 7 cover pieces. Its top alone was 4 pieces: a diagonal split, a
393 mm strip and a **37 mm sliver**, although the whole top lies flat about 1.17 m wide and
fits the 1.48 m roll.

There are four causes.

1. **The AI's choice of the number of pieces.** The box route offers 5 to 10 pieces, with how
   much room each leaves around the furniture. The AI weighed the room (8.6 % extra volume at
   7 pieces, 28.5 % at 5) above few pieces, and nothing looked at what the chosen option did
   to the top.
2. **Every crease becomes a seam.** The box cover makes one piece per flat face, so where two
   faces of the top meet at a crease, that is always a seam. A seam on top is a weak point for
   water, and two flat faces that share an edge can always be cut as one piece with a fold.
3. **The checks do not see it.** The audit's "pieces" check counts pieces, but it does not
   look for slivers or for a top that could be fewer pieces. The DeepSeek second opinion was
   not asked about it.
4. **The lesson was not stored.** The owner's remark lived only in the chat.

## How big it is (scan of all 414 models, 2 October 2026)

- **21 SUNS models have a piece narrower than 8 cm:**
  - lucia-3-seater-sofa 41 mm, pemba-lounge-chair 29 mm, sunlounger-basta-aluminium 32 mm,
    corner-tovara 37 mm;
  - fiave, fiora, rios, prato, termoli, tagia, aspen, kota chaise, vento angled hocker;
  - …
  - (the full list is in the sweep report).
- **168 SUNS models have a top in 2 or more pieces that together are narrower than the roll.**
  These are candidates for one piece with a fold. Not all of them should change: the owner
  approved the Kota's separate back strip.
- The owner's drawings (drawing-*) have narrow strips on purpose; they follow the drawing and
  are left alone.

## What changes

1. **A rule: no slivers** (`seams.min_piece_width_mm`, 100 mm, to confirm).
   - No piece of a box cover may be narrower than this.
   - An option that makes one is rejected, or its narrow face goes into its neighbour.
   - It is a parameter like every other limit.
2. **A fold instead of a seam** (`seams.fold_merge`).
   - Neighbouring top faces that lie flat together within the roll width and the longest
     piece become one piece, with a fold line on the pen layer (`FOLD`).
   - Flat faces sharing an edge unfold exactly (0 % stretch), so the fit does not change.
   - Default *off* until the owner answers question 47. Until then it is *on* per model where
     the owner asks, starting with the Lucia.
3. **The AI chooses with the result in view.**
   - Every option gets the number of top pieces and its narrowest piece.
   - The prompt, and a stored lesson in `config/ai_lessons.json`, say: the fewest top pieces
     that fit the roll; never a sliver; extra room around the furniture is acceptable to save
     a top seam.
4. **Two new checks in the audit**, so the class of error is caught on every model, also
   later ones:
   - *slivers*: a piece narrower than the minimum fails;
   - *top pieces*: a top that could be fewer pieces (it fits the roll together) is reported.
   - The DeepSeek second opinion is asked about both.
5. **Tests that keep it fixed:**
   - a box test (a top that fits the roll is one or two pieces, no piece under the minimum);
   - the Lucia as a reference case (its top at most 2 pieces, no sliver).
6. **The sweep.**
   - Run the 21 models with slivers and the 168 candidates again.
   - Compare before and after (`cover diff`).
   - Write a report with a picture per model that changed. The owner looks at a sample.
   - Then a new version (v1.2.0) goes live.
7. **How we learn from now on.** Every remark of the owner on a model becomes four things, in
   the same commit:
   - a stored lesson (for the AI);
   - a check (for every model);
   - a test (so it stays fixed);
   - a line in DECISIONS.md.

   The fix of the one model is never the end; the sweep over all models is. This goes in
   CLAUDE.md as a working rule (ADR-055).

## Order

1. Rule 1 and the checks (4), with tests (5): the error class becomes visible on every model.
2. The AI's choice with the result in view (3) and the stored lesson.
3. Fold instead of seam (2), with the fold line on the pen layer, the cut file and the size
   drawing; on for the Lucia.
4. The sweep (6), the report for the owner, and the release v1.2.0 after the owner's look.

## Waiting for the owner

- **Question 47:** should the fold be the default for every cover (one piece where the roll
  allows it), or only where you ask for it? It would also merge the Kota's back strip into its
  slope.
- The minimum piece width: is 10 cm right?
- A look at the sweep report before v1.2.0 goes live.
