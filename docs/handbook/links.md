# Links: a drawing and a 3D model of the same product

Many products are in the range twice: once as a cover built from a **drawing** (drawing-*,
codes like C12, S45, D2) and once as a cover built from the manufacturer's **3D model**
(suns-*, from 3D Warehouse or a STEP file). **Covers → Links** (`#/covers/links`) links the two,
so we can learn from each pair: how the drawing's sizes, seams and vents differ from the cover
the program computes on the real furniture (ADR-132, docs/plans/drawing-model-links.md).

The program **proposes**; a person **decides**. Nothing learns from a pair until a person
confirmed it.

## Who sees what

- **Editors and admins** see the queue and decide: Confirm, Not a pair, Choose another, Reopen,
  Confirm all high.
- **Viewers** see the same rows without the buttons.
- **The workshop login** does not see the page.

## The queue

Each row shows both covers side by side:

- **left, the drawing cover**: its render, the drawing's own 3D view (from the PDF), its code
  and product name, the cover's size, plan shape (straight, L, U, round; the hand of an L) and
  kind;
- **right, the 3D-model cover**: its render, name, the cover's and the furniture's size, plan
  and kind;
- **in the middle**: the score (0–100), its strength (**high**, **likely**, **unsure**), a bar per
  signal (names, size, plan, kind, hand, picture), the reasons (✓) and the doubts (⚠). Badges:
  **mirror** (the drawing is the other hand of this model), **product list** (namecode.xlsx
  linked them), **old proposal** (the last run no longer proposes it).

Filters: **Proposed**, **Confirmed**, **Chosen** (picked by hand), **Not a pair**, **No partner**
(drawings without any link), a search box (code, model or product name) and the strength.

## Deciding

- **Confirm**: yes, the same product. Learning may now use the pair.
- **Not a pair**: no. The link is kept with your name (history), and it is no longer shown as a
  link anywhere: not on the Desk card's Products block, not on the SUNS model's Desk label, not
  in the price import.
- **Choose another**: search a 3D model and click it; tick **mirror image** when the drawing is
  the other hand. The new link is "chosen by hand"; the link you replaced becomes "not a pair".
- **Reopen**: take a decision back; it is a proposal again.
- **Confirm all high (N)**: every proposal on the page scoring at least 85 with no doubt, after
  a confirmation step. The server checks each one again and skips (and says) what does not
  qualify.

Two people on the same row: the second one gets "someone changed this link meanwhile; reload
the page" instead of overwriting the first one's decision.

## The product list's links are proposals

Before 14 October the Excel sheet's links (the "SUNS models" chips on a Desk card) were shown as
facts. They are proposals now, with their score and reasons, and a person confirms or corrects
them. The worked example is **D2**, "Evora normal D- Bed" (a cover of 230 × 204 cm): the sheet
linked it to the Evora **sunlounger** (93 cm wide) because of the word "Evora". In Links that
pair scores 34, with "the name says pair, but the size says no and the type says no". Click
**Not a pair** and the Desk card of D2 no longer shows the sunlounger. The sheet itself
(products.json) is never changed.

## No partner

A drawing of a **whole corner set** (C2–C22, U1, U2) has no single 3D model: the 3D models are
the set's modules. Its partner will be an arrangement of those modules (Covers → Arrangements).
Use **Choose a partner** when you know one.

## On a cover's page

Under the title, beside the statuses: **Linked to …** (a link a person confirmed or chose, with a
link to the partner), or **N proposed links** (opens the queue for this cover).

## For the main session (command line)

```
COVER_DATA_DIR=~/cover-data uv run python scripts/link_inventory.py          # what is there
COVER_DATA_DIR=~/cover-data uv run python scripts/link_proposals.py --dry-run [--json OUT]
COVER_DATA_DIR=~/cover-data uv run python scripts/link_proposals.py --apply  # writes app.db
COVER_DATA_DIR=~/cover-data uv run python scripts/link_compare.py            # confirmed pairs
```

`--apply` never changes a person's decision; proposals it no longer makes are marked "old",
never deleted. `--gemini-ties N` lets Gemini look at tied proposals (a reason, never a decision;
at most €5, in the AI ledger). `link_compare.py` compares each confirmed pair: the box, each skirt
side's hem and height, each top piece, the pieces, vents, hem, seams and fabric
(`--pairs d:m,...` for pairs not yet confirmed, for looking only).
