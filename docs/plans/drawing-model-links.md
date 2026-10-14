# Drawing ↔ 3D model links: one product, two covers, one lesson (ADR-132)

The owner, 14 Oct 2026: "we hebben tekening + 3d modellen in het pakket staan voor hetzelfde
product, er moet een optie komen waarbij deze gelinked worden zodat we hier van kunnen leren,
zou jij een voorstel kunnen maken waar jij denkt wat bij elkaar hoort, dat we dit kunnen
bevestigen en als het niet goed is handmatig kunnen aanpassen, gebruik hiervoor alles wat je
hebt."

And the same day, with an example: D2 shows as "sunlounger evora" in the studio, which is wrong.
The link came from the Excel upload (namecode.xlsx: `Evora normal D- Bed · Cover 2 · D2`); the
studio turned the word "Evora" into the SUNS Evora sunlounger and showed it as a fact. So a
name in the sheet is **one signal, not the truth**.

## 1. Inventory (live, read only, 14 Oct 2026)

`COVER_DATA_DIR=~/cover-data uv run python scripts/link_inventory.py`

| | drawing-* | suns-* | bbq-* | arr-* | other |
|---|---:|---:|---:|---:|---:|
| folders | 115 | 302 | 23 | 3 | 13 |
| hull.json / cover.png | 115 / 115 | 302 / 302 | 23 / 23 | 3 / 3 | 12 / 11 |
| reference.png (the drawing's 3D view) | 100 | – | – | – | – |
| reference.pdf | 111 | – | – | – | – |
| products.json (namecode.xlsx) | 115 | – | – | – | – |
| drawings.json (the sheet's links back) | – | 89 | – | – | – |
| product.jpg | – | 302 | – | – | – |
| marked "no cover" | 0 | 1 | 0 | 0 | 0 |
| Desk: approved / ai-checked / rejected | 75 / 27 / 12 | 126 / 164 / 12 | 0 / 23 / 0 | 0 / 3 / 0 | |

The product list's links today: 53 drawings link at least one SUNS model (94 pairs), 14 only
"suggest" (112 pairs), 48 none; 8 codes carry more than one product.

What the 115 drawings are: 43 corner sofas (L, mostly whole sets C1–C22 and L1–L8), 29 sofas,
16 single items, 10 round and 7 dining sets, 7 loungers. The 302 SUNS models are single
pieces: 132 items (chairs, modules, side tables), 61 dining tables, 58 sofas, 26 corner pieces,
13 loungers. **A drawing of a whole corner set has no single 3D model**; its partner is an
arrangement (arr-*) of the modules, and three exist so far.

## 2. The signals and how they are scored

Every drawing cover is scored against every SUNS model and arrangement
(`apps/api/coverapi/link_score.py`, 34 700 pairs in about 20 s). Each signal is 0..1, or left out
when we do not have it; `links.weights` in config/defaults.yaml sets their shares.

| signal | where it comes from | weight |
|---|---|---:|
| names | the drawing's product names (namecode.xlsx → products.json), its price list rows (code, section, item, "suits", ADR-113/114) and its code, against the SUNS model's own name: a family in common (Evora, Kota, Vento…) 0.6, the type (2-seater, corner, chair, **D-bed vs sunlounger**, table…) 0.4 | 0.25 |
| size | the two covers' boxes, length ≥ width and height in cm (hull.json): within `links.size_tol_cm` (6.5) the same, falling to 0 over 45 cm (30 cm for the height) | 0.30 |
| plan shape | each cover surface (hull.glb) seen from above on a 48-cell grid: straight, L, U/C, round; the hand of an L (its long and short arm turn left or right) | 0.15 |
| kind | the configurator kind of both: the ADR-114 match card for the drawing, `match.kind_of` for the model (sofa, corner sofa, lounger, item, dining, round) | 0.10 |
| side | left/right from the names, else the hand of the L; two different hands are a **mirror pair** (0.5, flagged, never refused) | 0.10 |
| picture | the two cover.png renders' silhouettes (IoU, the mirror image too) | 0.10 |
| product list | a pair namecode.xlsx linked adds `links.sheet_bonus` (0.08), a suggestion 0.04 | bonus |
| contradiction | the name says "pair" but the size, the plan shape or the type says no: the score × `links.contradiction_factor` (0.57) and the row says why | factor |
| Gemini (tie-break only) | for drawings whose two best proposals are within 0.02: the drawing's 3D view and the candidates' renders, "which is the same product, or none"; a reason and +0.03, never a decision; ledger, ≤ €5 | – |

Doubts (each one makes a proposal "unsure", whatever its score): another family in the names,
a type that disagrees, sizes that differ (size score < 0.3), a different plan shape or kind, the
product list and the price list naming different hands (C6: "Right" in namecode.xlsx, "corner set
left" in the price list).

Strength: **high** = score ≥ `links.bulk_min` (0.85) and no doubt (bulk-confirmable), **likely**
= ≥ `links.propose_min` (0.5) and no doubt, **unsure** = the rest. Per drawing the best three
pairs from 0.5 on are proposed (a pair whose sizes do not agree at all is not), plus **every pair
the product list links, whatever its score**, so a person sees each of them. The sheet's mere
suggestions (a family, no type: the "suggested ?" chips) are proposed only when they score 0.5
on their own; on the Desk card they stay "suggested" until a person rejects them.

## 3. The proposal (dry run on live, 14 Oct 2026)

`COVER_DATA_DIR=~/cover-data uv run python scripts/link_proposals.py --dry-run --json out/links/proposals.json`

- **287 proposals** for 96 drawings: 53 high, 55 likely, 179 unsure; 93 of them are the product
  list's own links. 8 are mirror pairs. **19 drawings have no partner**: C2–C4, C6–C11,
  C14–C17, C19–C22 (whole corner sets) and U1, U2.
- The product list's 93 links: **41 high** (the sheet and the geometry agree), 1 likely and
  **51 unsure**: 47 with sizes that differ, 35 with another kind, 25 with another plan shape.
  Most are a set's drawing linked to one module of the set (S18/S19 "Ibiza Big corner",
  380 × 110 cm, to the 99 × 97 cm Evora corner chair; D6 Blocchi daybed 180 × 215 to the
  258 × 258 Blocchi daybed model).
- Best per drawing: 28 high, 22 likely, 46 unsure.

### Worked example: D2

| D2 "Evora normal D- Bed", cover 230 × 204 × 82 | score | why |
|---|---:|---|
| suns-daybed-vento (197 × 191 × 87) | 0.71 unsure | both a D-bed, straight, same kind, renders 77 % alike; **another family** (Evora vs Vento) |
| suns-daybed-portofino (267 × 214 × 81) | 0.71 unsure | as above, renders 88 % alike; another family; Gemini's tie-break picked it |
| suns-daybed-marolo (201 × 201 × 84) | 0.57 unsure | another family; plan round, D2 straight |
| **suns-sunlounger-evora** (222 × 93 × 78), the sheet's link | **0.34 unsure** | family Evora in both; but **the size says no** (93 cm wide against 204) **and the type says no** (a D-bed is not a sunlounger) |

So D2 has no partner among today's 3D models (there is no Evora D-bed model); its sheet link is
shown as a doubtful proposal, and "Not a pair" takes it off the Desk card (screenshot
out/links/03, 04). The reason the sheet linked it: products_sheet.kinds calls a D-bed and a
sunlounger both "daybed"; link_score tells them apart (`lounger_type`).

### Top proposals (examples)

- D1 "Portofino/Aspen/Kota normal D-Bed" ↔ suns-daybed-portofino: 1.00 high (sheet; 266 × 220 ×
  82 against 267 × 214 × 81; renders 92 %).
- D5 ↔ suns-daybed-vento 1.00 high; S22 ↔ suns-lounge-vento-4-seater 1.00; S26 ↔
  suns-lounge-blocchi-2-seater 1.00; S11 ↔ suns-lounge-tosca-lounge-chair 1.00.
- S38 (left) ↔ suns-lounge-vento-2-seater-left 0.99 and ↔ …-right 0.93 as a **mirror pair**;
  S39 (right) the other way round: one drawing, both hands, the mirror flagged.
- L1 ↔ arr-portofino-chaise-2seater 0.94 (an arrangement, mirror).
- Without a name in common, by size and shape: T1 ↔ the 340 dining tables (Basta, Savona,
  Savona HPL) 0.83 each; R3 ↔ Sorolo Ø120 0.83; T2 ↔ Pemba 290 0.83. One drawing, several models:
  many-to-one is allowed.

### Unsure examples

- S3 ↔ suns-3-seater-with-corner-sorrento 0.86, sheet: kind sofa vs corner sofa.
- S45 ↔ suns-lounge-blocchi-organic-hocker 0.50, sheet: plan shape says no.
- L1 ↔ suns-chaise-lounge-portofino 0.31, sheet: the size and the plan shape say no (a set's
  drawing against one module of it).

## 4. What the pairs let us learn

Only pairs a person confirmed or chose (`links.learning_pairs`) are ever read; a proposal never
teaches anything. A mirror pair is compared mirrored.

1. **Size: the drawing's cover against the cover computed on the real furniture.**
   `scripts/link_compare.py` (first report, below) gives the box, every skirt side's hem and
   height, every top piece by size, the pieces, vents, hem and seam length and the fabric area.
   D1 ↔ Portofino daybed (not yet confirmed, `--pairs`): box +1.4 / −6.4 / −1.4 cm, hem 9.72 m
   against 9.62 m, the skirt band 180 mm on the drawing against 121 mm on the computed cover,
   4 vents against 8, 12.4 m² against 11.0 m². From many confirmed pairs per family: the
   workshop's real clearance (drawing minus furniture), its hem height and its slopes.
2. **Seams and vents.** The drawing's piece layout (proven in production) against the
   engine's: where the workshop puts the skirt seam, how many top pieces, vent count and place
   (D1: the drawing 4, the engine 8).
3. **A pair as a reference.** A new 3D model of a confirmed family (a new Portofino module) gets
   the drawing's proven pattern decisions: skirt height, piece split, vent count; and a new
   drawing of a family with a confirmed 3D model can be checked against the computed cover
   before it is cut.
4. **Per-family corrections.** When several confirmed pairs of one family differ the same way
   (the drawing 6 cm wider, a 18 cm skirt), that becomes a family rule (ADR-082's learned rules,
   `learning/rules/<family>.yaml`), proposed to a person as today, so both routes improve.

## 5. What was built (this branch)

- **Store**: app.db `model_links` (drawing, model, status proposed / confirmed / rejected /
  manual, score, strength, signals, reasons, doubts, both covers' facts, mirror, source sheet /
  proposer / person, note, stale, who and when, version) and `model_link_log` (every change).
  Many-to-one both ways; one row per pair.
- **API** (`apps/api/coverapi/links.py`): `GET /api/links?status=&q=&strength=` (viewers and up;
  `status=nopartner` lists drawings without a live link), `GET /api/links/of/<cover>`,
  `GET /api/links/<id>` (with history), `POST /api/links/<id>/decide` (confirmed, rejected, back
  to proposed; with the version seen: 409 on a stale page), `POST /api/links/choose` (a partner by
  hand; the link it replaces becomes rejected), `POST /api/links/bulk-confirm` (only proposals
  ≥ `links.bulk_min` without a doubt; the rest skipped with the reason), `GET /api/links-search`.
  Editors and admins decide; viewers look; the workshop login is refused at the front door
  (not on its allow-list) and by the routes.
- **Page**: Covers → Links (own icon, a drawing and a block joined by a seam): the queue with
  both covers side by side (renders, the drawing's 3D view, sizes, plan, kind), the score and its
  signal bars, reasons and doubts; Confirm, Not a pair, Choose another (search picker, mirror
  tick), Reopen; filters Proposed / Confirmed / Chosen / Not a pair / No partner, search,
  strength; "Confirm all high (N)" with a confirmation step. On a cover's page a "Linked to …"
  chip (or "N proposed links").
- **The Excel links are proposals now**: the Desk card's Products block shows the sheet's links
  as "proposed by the product list" until confirmed; a rejected or replaced link disappears from
  it, from the SUNS model's Desk label and from the price import (ADR-113, `Matcher.linked_suns`).
  products.json and drawings.json are never changed (history kept). The shop's "Bestel direct"
  (ADR-118) does not read these links: it matches by kind and size, with the price list's
  families as a tie-break only.
- **Scripts**: `link_inventory.py` (Codex), `link_proposals.py --dry-run|--apply`
  (never touches a person's decision; stale proposals are marked, never deleted),
  `link_compare.py` (confirmed pairs; `--pairs` for looking).

## 6. Next steps

1. **The main session runs** `scripts/link_proposals.py --apply` on live after review, then
   people confirm the 53 high ones (bulk) and go through the 51 doubtful sheet links, D2 first.
2. **Arrangements for the corner sets** (C1–C22, L1–L8): the 19 drawings without a partner are
   whole sets; build each set as an arrangement of its SUNS modules (ADR-089), so the pair
   becomes drawing ↔ arrangement.
3. **Fix the root cause in the sheet import**: products_sheet.kinds should tell a D-bed from a
   sunlounger (as `link_score.lounger_type` does) and check the size before it calls a pair
   "linked"; and a new upload should feed the Links queue instead of writing facts.
4. **The compare report per family** once ~10 pairs are confirmed: clearance, skirt height,
   vents, top piece split; then propose family rules (ADR-082) from it.
5. Learn the weights from the confirmed and rejected pairs (a logistic fit on the signals) once
   there are 50 or more decisions.
