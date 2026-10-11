# Covers for premium barbecues (11 October 2026)

## Samenvatting (Nederlands)

De eigenaar vroeg (11 okt): "in de nieuwe versie ook een optie voor hoezen voor BBQ's; onderzoek
de best verkochte luxe BBQ's (Big Green Egg enz.), wij zijn een premium hoes; laad die modellen en
maak een voorstel voor een hoes."

- **Markt (NL/BE/DE).** Meer dan de helft van alle zoekopdrachten naar barbecuesoorten gaat over de
  kamado (Barbecue Marktmonitor 2026). Big Green Egg is de best verkochte kamado. Daarna komen
  Kamado Joe, The Bastard en Grill Guru. Bij BGE is de **Large in een nest** het populairste model.
  Bij gas zijn Weber Genesis, Napoleon Prestige en Broil King Regal de premium bestsellers. Bij
  pellet zijn dat Traeger en de Weber Searwood. Bij vuurtafels is OFYR Classic 85 het populairst.
  De bronnen staan in `bbq-covers-research.md`.
- **Hoezen van de fabrikanten zelf.** Ze kosten **€45–240** en zijn allemaal generiek: een buis
  of een ronde hoes, nooit gevormd naar ei + nest + zijtafels. OFYR heeft geen hoes voor het hele
  toestel. Een premium hoes op maat heeft dus ruimte.
- **25 modellen geladen (27 opstellingen)** als catalogusmodellen `bbq-<merk>-<model>` in staging
  (`out/bbq/`):
  - BGE Large: het ei is een 3D Warehouse-model, geschaald naar de gepubliceerde maten.
  - Weber Genesis II EP-335: 3D Warehouse-model.
  - De rest is getekend uit de gepubliceerde maten.
  - Elke hoes is gemaakt met de normale pijplijn en twee keer gecontroleerd (`cover audit` en
    `fewer_check`). **23 van de 27 slagen allebei.** Bij 4 is iets na te kijken (zie hieronder).
  - Niets is live gezet.
- **Vormen van de hoezen.**
  - Kamado los in een nest, of een ronde vuurtafel: rond, een cilinder met een kegeldak (de
    ronde logica van ADR-107). 4 stukken, 2 ventilatieopeningen.
  - Alle andere (gas, pellet, kamado met zijtafels of in een tafel): een rechte doos met een
    schuin dak. 7 tot 9 stukken, 4 tot 5 ventilatieopeningen.
  - Water loopt altijd af. Onderaan zit een trekkoord.
  - **Een hoes gaat alleen over een afgekoelde barbecue.** Acryl is niet hittebestendig. De
    winkel zegt dat in alle talen. De extra ruimte (20 mm, `config/presets/bbq.yaml`) is voor
    handvat, thermometer, scharnier en het ventiel bovenop, niet voor warmte.
- **Configurator (winkel en B2B).** Er is een nieuwe keuze "Tuinmeubels | Barbecue" met 5
  producten:
  - kamado in een nest, eventueel met zijtafels;
  - kamado in een tafel;
  - gasbarbecue met zijtafels;
  - pelletbarbecue;
  - vuurtafel of plancha, rond of vierkant.

  De maten zijn schuiven. De 3D-weergave toont de barbecue onder de hoes. De prijs komt uit de
  bestaande calculatie. Een goedgekeurde BBQ-hoes uit de catalogus wordt aangeboden als "Big
  Green Egg Large in nest past je voor 100 %". In de browser getest in NL en DE, op desktop en
  telefoon.
- **Vragen aan de eigenaar:** zie het einde van dit document. Het belangrijkste is de prijs. De
  voorlopige calculatie geeft €475 voor een kamado-hoes en €880 voor een gasbarbecue-hoes. De
  fabrikanten vragen €45–240.

## Ranked list (top 25) with sizes and sources

W × D × H in mm, lid closed. W runs side to side, including the shelves when they are up. D
runs from the front of the handle to the back of the hinge. "est." means estimated.
Popularity evidence is in `bbq-covers-research.md` §0, and every number has its URL there.

| # | Model / set-up | W × D × H (mm) | Shape | The cover must clear | Maker's cover (EUR) | Source |
|---|---|---|---|---|---|---|
| 1 | Big Green Egg Large in Nest / IntEGGrated Nest+Handler | 560 (egg) × 720 × 1140 | egg on a stand | top vent, thermometer, front handle, rear hinge, nest handler | 119.50–138.75 | greeneggtotaal.nl; biggreenegg.eu |
| 2 | BGE Large in Modular Nest (EGG Frame) | 760 × 760 × ≈1230 (est.) | egg on a square frame | as #1 | 136.50 | biggreenegg.com |
| 3 | Kamado Joe Classic III on cart | 1094 (official; shops say 1180–1194) × 762 × 1258 | egg with 2 shelves | Kontrol Tower, hinge, handle | 65–84 | kamadojoe.com |
| 4 | Weber Genesis E-335 (and Genesis II EP-335 in many gardens) | 1560 × 685 × 1220 | rectangle | handle bar, side burner | 139.99 | weber.com/NL |
| 5 | BGE Medium in Nest | 475 × 595 × ≈990 (est.) | egg | as #1 | 118 | basbq.nl (snippet) |
| 6 | BGE XLarge in Nest | 670 × 840 × ≈1100 (est.) | egg | as #1 | 136.50–138.75 | grillsportverein.de |
| 7 | BGE Large with 2 EGG Mates | ≈1322 (est.) × 720 × 1140 | egg with 2 wings | as #1, plus shelves | none that fits | biggreenegg.com |
| 8 | BGE MiniMax in carrier | 540 × 530 × 530 | small egg | carrier handles | 118 | grillsportverein.de |
| 9 | Weber Genesis E-435 / SP-435 | 1730–1830 × 685 × 1220 | rectangle | as #4 | 149.99 | weber.com/NL |
| 10 | The Bastard Large Complete | 1490 × 800 × 1270 | egg with 2 shelves | hinge, handle, vent | ≈71 | bakkerbrandstoffen.nl |
| 11 | Napoleon Prestige 500 | 1670 × 670 × 1300 | rectangle, roll-top lid | rotisserie bracket, side burner | ≈90–95 | bbqexperiencecenter.nl |
| 12 | OFYR Classic 85 / 100 | Ø850 / Ø1000 × 1000 | round plate on a cone | flat plate | 45–50 soft cover (steel lid 219) | ofyr.com |
| 13 | Kamado Joe Big Joe III on cart | 1310 (official; shops say 1483) × 909 × 1400 | egg with 2 shelves | as #3 | 79.90–99.90 | kamadojoe.com |
| 14 | BGE Large in acacia table | 1524 × 635 × ≈1250 (dome est.) | table with a dome | dome above the table | 175 | bbq-authority.com |
| 15 | Weber Master-Touch 57 (kettle) | 650 × 760 × 1000 | round kettle | handle, ash catcher | Weber's own | weber.com/NL (not built: no kettle builder yet) |
| 16 | Broil King Regal S590 Pro | 1590 × 630 × 1250 | rectangle | rotisserie, side burner | 139.90 | grillgoods.de |
| 17 | Weber Searwood XL 600 | 1280 × 585 × 1160 | rectangle | hopper (inside W) | 89.99 | weber.com/DE |
| 18 | Weber Summit FS38 | 1800 × 685 × 1330 | rectangle | rotisserie bracket, side burner | 239 | weber.com/AT |
| 19 | Traeger Ironwood / Ironwood XL | 1500 / 1778 × 635–640 × 1220 | barrel on a cart | hopper box, rail | 169.90 / 179.90 | traeger.com/nl; grillstar.de |
| 20 | Monolith Classic (TWO.55) with side tables | 1200 × 710 × 1200 | egg with 2 shelves | hinge, chip feeder | 89.90 | grillfuerst.de |
| 21 | Traeger Timberline | 1500 × 640 × 1300 | rectangular cabinet | rail | 189.90–219.90 | grillfuerst.de |
| 22 | Napoleon Prestige PRO 665 | 1950 × 650 × 1300 | rectangle | rotisserie, side burner | 109–119 | bbqkopen.nl |
| 23 | OFYR Island 100 | 1350 × 500–650 × 1000 | round plate over a cabinet | worktop | none for the whole unit | firepit-online.com (not built: the sources disagree) |
| 24 | BGE 2XL in Nest | ≈1000 × ≈1000 × ≈1200 (est.); egg Ø ≈825 | egg | as #1 | 144.25 | thestoveyard.com |
| 25 | Broil King Imperial S690 XL | 1930 × 630 × 1250 | long rectangle, 2 lids | rotisserie, side burner | 149.90 | grillfuerst.de |

## The cover types we need

1. **Round, a cone on a cylinder:**
   - Used for a kamado alone in a nest or on a carrier (BGE Mini to 2XL, Joe Jr), and for round
     fire tables (OFYR Classic, Arteflame, Höfats Cone).
   - Built as 2 cone sectors and 2 band strips, the strips under the sectors' seams (ADR-107). The
     drawcord runs in the hem.
2. **A box with a hipped or faceted roof:**
   - Used for gas and pellet grills, and for a kamado with side tables, on a cart or in a table.
   - Takes 7 to 9 pieces. The hood or dome carries the roof, so water runs off and no balloon is
     needed.
3. **Later:**
   - a kettle (Weber Master-Touch): a round cover like type 1, but low;
   - the OFYR Island (keyhole: a round plate over a cabinet);
   - outdoor kitchens (a stepped profile, or a worktop cover plus a hood cover);
   - variants with the shelves folded down (Napoleon Prestige: 1370 wide).

## Models loaded (staging, `out/bbq/`; built by `scripts/bbq_models.py`)

**How each model was made:**
- **BGE Large** (3 set-ups): the egg is the 3D Warehouse model "Big Green Egg Large" (Ryan Marko,
  public, General Model Licence). It is scaled to the published 560 × 720 × 840. As modelled it
  measured 596 × 700 × 840, so within 6 %. The nest, the EGG Mates and the handler are drawn.
- **Weber Genesis II EP-335:** the 3D Warehouse model by Fran L., as modelled (1657 × 743 × 1312).
- **All others:** drawn from the published sizes (`coverengine/bbq.py`). The estimated parts are
  listed in each model's notes, mostly shelf heights and hood widths.
- **Models found but not used:**
  - The Kamado Joe Big Joe (III) and Traeger Ironwood 885 models from 3D Warehouse. The Traeger's
    extents do not match the published sizes (it looks modelled with the lid open).
  - The two OFYR models: 3D Warehouse offers no GLB for them.

**The checks:** every cover went through hull, cut, flatten and export. It was then checked
twice: by `cover audit`, and by `fewer_check`, which re-measures the cut.dxf, both sides of every
seam, the 3D lengths and the areas. The covers are 2–8 cm wider than the barbecue on each side:
20 mm clearance plus what the shape adds.

**Where to look:**
- pictures: `out/bbq/pictures/<id>.png` (the barbecue under the cover, two views) and
  `out/bbq/contact-sheet.png`;
- the engine's own: `models/<id>/cover.png`;
- `out/bbq/summary.json`, `out/bbq/results.json`.

| # | Model | Barbecue W × D × H (mm) | Cover | Pieces | Fabric m² (net) | Vents | Max stretch % | Checks |
|---|---|---|---|---|---|---|---|---|
| 1 | BGE Large in IntEGGrated Nest + Handler | 684 × 720 × 1140 | round | 4 | 2.75 | 2 | 0.50 | pass |
| 1 | BGE Large in nest | 560 × 720 × 1140 | round | 4 | 2.72 | 2 | 0.50 | pass |
| 2 | BGE Large in Modular Nest (EGG Frame) | 760 × 800 × 1230 | box | 9 | 3.74 | 4 | 0.0 | pass |
| 3 | Kamado Joe Classic III on cart | 1094 × 762 × 1258 | box | 9 | 4.32 | 5 | 0.0 | check: 1 vent does not fit (a 12 cm chamfer strip) |
| 4 | Weber Genesis E-335 | 1560 × 685 × 1220 | box | 7 | 5.89 | 4 | 0.0 | pass |
| 4 | Weber Genesis II EP-335 (3D Warehouse) | 1657 × 743 × 1312 | box | 9 | 6.77 | 4 | 0.0 | pass |
| 5 | BGE Medium in nest | 475 × 595 × 990 | round | 4 | 1.98 | 2 | 0.50 | pass |
| 6 | BGE XLarge in nest | 670 × 840 × 1100 | round | 4 | 3.10 | 2 | 0.33 | pass |
| 7 | BGE Large in nest with two EGG Mates | 1322 × 720 × 1140 | box | 9 | 4.42 | 4 | 0.0 | check: a scrap piece (top-3) at a 3° fold |
| 8 | BGE MiniMax in carrier | 540 × 530 × 500 | round | 4 | 0.89 | 2 | 0.43 | pass |
| 9 | Weber Genesis E-435 | 1730 × 685 × 1220 | box | 7 | 6.41 | 4 | 0.0 | pass |
| 10 | The Bastard Large Complete | 1490 × 800 × 1270 | box | 9 | 5.46 | 5 | 0.0 | check: 1 vent does not fit |
| 11 | Napoleon Prestige 500 | 1670 × 670 × 1300 | box | 7 | 6.41 | 4 | 0.0 | pass |
| 12 | OFYR Classic 100 | 1000 × 1000 × 1000 | round | 4 | 4.16 | 2 | 0.01 | pass |
| 12 | OFYR Classic 85 | 850 × 850 × 1000 | round | 4 | 3.46 | 2 | 0.01 | pass |
| 13 | Kamado Joe Big Joe III on cart | 1310 × 909 × 1400 | box | 9 | 5.81 | 4 | 0.0 | pass |
| 14 | BGE Large in acacia table | 1524 × 767 × 1250 | box | 7 | 5.59 | 4 | 0.0 | pass |
| 16 | Broil King Regal S590 Pro | 1590 × 630 × 1250 | box | 7 | 5.89 | 4 | 0.0 | pass |
| 17 | Weber Searwood XL 600 | 1280 × 585 × 1160 | box | 9 | 4.67 | 4 | 0.0 | pass |
| 18 | Weber Summit FS38 | 1800 × 685 × 1330 | box | 7 | 6.97 | 4 | 0.0 | pass |
| 19 | Traeger Ironwood | 1500 × 640 × 1220 | box | 8 | 5.70 | 4 | 0.0 | pass |
| 19 | Traeger Ironwood XL | 1778 × 635 × 1219 | box | 8 | 6.48 | 4 | 0.0 | pass |
| 20 | Monolith Classic (TWO.55) with side tables | 1200 × 710 × 1200 | box | 9 | 4.29 | 5 | 0.0 | check: 1 vent does not fit |
| 21 | Traeger Timberline | 1500 × 640 × 1300 | box | 9 | 5.96 | 4 | 0.0 | pass |
| 22 | Napoleon Prestige PRO 665 | 1950 × 650 × 1300 | box | 7 | 7.21 | 5 | 0.0 | pass |
| 24 | BGE 2XL in nest | 825 × 1000 × 1200 | round | 4 | 4.03 | 2 | 0.32 | pass |
| 25 | Broil King Imperial S690 XL | 1930 × 630 × 1250 | box | 7 | 6.90 | 4 | 0.0 | pass |

**The four to check.** On the three kamados with side tables, the egg's handle stands in front
of the shelves. The box's plan then gets a narrow chamfer strip (116 mm) next to the front, and
one vent does not fit on it. Options:
- move that vent to the neighbouring piece;
- accept one vent less;
- or make the plan a plain rectangle. That fits 5 pieces with a single sloped top, but adds
  60–75 % more air.

The BGE with EGG Mates keeps a small scrap piece at a 3° fold.

**Importing them live (main session):**
1. Copy `out/bbq/models/bbq-*` into the models.
2. Each cover.json already carries `"family": "bbq"`, the hull settings and
   `"match": {"kind", "name", "families"}`.
3. Once Rens or Wout approve a cover at the Desk, the configurator offers it.

## The configurator option (ADR-119)

There is a **Garden furniture | Barbecue** choice above the product cards, in the shop and in
B2B. The ranges are in `config/quote_products.json` (the defaults are the best sellers):

| Product | Fields (cm, default and range) | Cover |
|---|---|---|
| Kamado (egg) in a nest | egg Ø 56 (30–90), height lid closed 114 (40–170), depth handle to hinge 72 (35–120), side tables yes/no and their width 132 (60–230) | round with a cone; with side tables a hipped box |
| Kamado in a table | table 152 × 64 × 79, egg Ø 56, height 125 | hipped box |
| Gas grill with side shelves | width 156, depth 69, height 122, shelf height 92, hood width 88 | hipped box |
| Pellet grill | width 150, depth 64, height 122, lid length 90 | hipped box |
| Fire table or plancha | Ø or width 85, height 100, square yes/no and its depth | round with a cone, or a hipped box |

The proposals at the defaults, with the provisional prices. These are placeholders, marked
"indicative":

| Product | Shape | Pieces | Cut fabric m² | Vents | Roof slope | Consumer € | B2B € ex VAT |
|---|---|---|---|---|---|---|---|
| Kamado in a nest | cone round | 4 | 3.65 | 2 | 29.5° | 474.95 | 289 |
| Kamado with side tables | hip box | 8 | 6.79 | 4 | 29.5° | 800.95 | 497 |
| Kamado in a table | hip box | 8 | 8.21 | 4 | 29.5° | 911.95 | 568 |
| Gas grill | hip box | 8 | 8.05 | 4 | 27.5° | 879.95 | 548 |
| Pellet grill | hip box | 8 | 7.66 | 4 | 12.5° | 872.95 | 543 |
| Fire table, round | cone round | 4 | 4.11 | 2 | 12.5° | 500.95 | 305 |
| Fire table, square | hip box | 8 | 6.33 | 4 | 13.5° | 777.95 | 483 |

**Browser check** (Playwright in Docker against a local build with scratch data;
`apps/web/e2e/bbq.py`; screenshots in `out/bbq/browser/`):
- Covered NL and DE, desktop and 390 px phone.
- All 5 cards show, and the cold-barbecue note is there.
- Every product gets a price and a 3D scene.
- With the staged BGE Large in nest approved, the shop says "Big Green Egg Large in nest past je
  voor 100 %".
- No sideways scrolling and no page errors.

## Questions for the owner

1. **Price positioning.** The makers' own covers cost €45–240: BGE €118–175, Weber Genesis
   €140–150, Summit €239, Traeger €170–220. Our provisional costing gives a kamado cover at about
   €475 and a gas-grill cover at about €880. Do we set fixed BBQ prices, for example per
   catalogue cover in the price list, or a BBQ markup? Which price band: 1.5×, 2× or 3× the
   maker's cover?
2. **Which models first?** Our proposal: BGE Large in nest (rank 1), BGE Large with EGG Mates
   (no maker's cover fits it), Weber Genesis E-335, Kamado Joe Classic III, OFYR Classic 85. Then
   one sample each to sew and fit.
3. **Kamado shape.** Is the round cylinder with a cone (4 pieces) right? Or should it follow the
   egg more closely, as a dome in more sectors?
4. **Room.** Is 20 mm more clearance than furniture enough? Should the cover reach the ground
   (5 cm hem) or stop above the wheels and the nest feet?
5. **Shelves.** On the three kamados with side tables, should we move the vent, accept one vent
   less, or use a plain rectangular plan with more air?
6. **To measure on a real unit:** Kamado Joe Classic III and Big Joe III widths (the maker says
   1094 and 1310, shops say about 1190 and 1480), BGE Medium and 2XL outer sizes, shelf heights
   and hood widths of the gas grills, and the Traeger hopper side.
7. **Heat.** Is the note "only on a cold barbecue" enough? Or should we add a heat-resistant
   patch or a cap over the top vent (for example on the BGE's rEGGulator)?
