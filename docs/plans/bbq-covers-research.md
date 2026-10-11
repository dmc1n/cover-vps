# BBQ covers: market and dimension research (raw)

Date: 2026-10-11. Scope: premium/luxury barbecues sold in NL/BE/DE, to design made-to-measure acrylic covers.
Method: web only (manufacturer sites, NL/DE retailers, manufacturer built-in spec PDFs, forum measurement threads).
WebFetch was rate-limited (HTTP 429) on several manufacturer sites, so many pages were read via curl; a few figures
come only from search-engine snippets and are marked **(snippet)**. Anything not verified is marked **estimated**.

Conventions: W = side to side (incl. side shelves when up), D = front to back (incl. front handle and rear hinge),
H = floor (or table surface for table-top units) to top of lid, lid closed. All mm unless stated.

---

## 0. Market / popularity signals (NL/BE/DE)

| Signal | Detail | Source |
|---|---|---|
| Kamado is the dominant BBQ type in NL searches | "Ruim de helft van het zoekvolume naar barbecue-soorten heeft betrekking op dit keramische toestel"; table BBQ 15 %, skottelbraai 13 %. Fuel share: charcoal 37.2 %, gas 36.7 % (gas growing fastest). May+June ≈ 35 % of annual search volume. Based on 24 M searches 2022–2025 (Barbecue Marktmonitor 2026, Marktdata.nl) | https://www.wonen360.nl/article/9827087/barbecue-marktmonitor-2026-consument-kiest-voor-merken-boven-verkoopkanaal/ ; https://persportaal.anp.nl/artikel/ce873ee5-b73b-4241-aa16-9e6cf8e620dd/kamado-blijft-populairste-barbecue-van-nederland-in-aanloop-naar-piekseizoen |
| Most-searched brands NL | Weber and Boretti are #1/#2 most-searched brands; 7 manufacturers in top-10 search terms | same as above |
| Most-sold kamados NL | 1 Big Green Egg, 2 Kamado Joe, 3 The Bastard, 4 Grill Guru, 5 Jamestown; KJ Classic and Bastard Large most chosen sizes | https://www.kamadomeester.nl/blog/top-5-meest-verkochte-kamado-bbqs-nederland |
| BGE Large = most popular BGE | "the most popular model of the Big Green Egg family" | https://www.biggreenegg.eu/en/products/models/large |
| BGE Medium | "one of our most popular models" | https://www.biggreenegg.eu/en/products/models/medium |
| Genesis = Weber's premium bestseller | Genesis called the bestseller in NL roundups; Genesis E-315 in bol.com top-10 best-selling Weber gas BBQs | https://www.bol.com/be/nl/t/top-10-best-verkochte-weber-gasbarbecues/21790+4286525005/ ; https://bestebbq.nl/bbq/beste-gas-bbq/ (snippet) |
| DE gas | Broil King Regal 590 "Vergleichssieger 2026", Napoleon Prestige 665 and Weber Genesis E-335 close behind; gas ≈ 46 % share DE (snippet, review site, low reliability) | https://topgrillreviews.de/vergleich/beste-gasgrill-2026/ |
| Pellet | Traeger ≈ 23.8 % of global pellet-grill revenue 2025 (analyst estimate); DE comparison sites rank Weber Searwood 600 often #1 | https://matrixbcg.com/blogs/competitors/traeger (snippet) ; https://www.testsieger.de/pelletgrills/ ; https://www.vergleich.org/pelletgrill/ |
| OFYR | 85 cm "het populairste formaat voor thuis" | https://buiten.studio/ofyr-bbq/ |
| Coolblue top-10 (mass-market, no BGE) | Boretti Barilo 2.0 (77 reviews), Boretti Carbone 2.0 (158 reviews), Weber Kettle 47, Napoleon kettles — shows Boretti strong in mid-market | https://www.coolblue.nl/barbecues/top-10 |

---

## 1. Big Green Egg (kamado, egg/round plan)

### 1a. Egg bodies (official grid Ø and height; outer dims from dealers/forum)

| Size | Grid Ø (US / EU site) | H closed (egg only) | Outer ceramic Ø | W×D incl. hinge + handle | Weight | Sources |
|---|---|---|---|---|---|---|
| Mini | 250 | 430 | ≈305 **estimated** (12" "width") | n/a | 17–18 kg | https://biggreenegg.com/pages/what-size-is-my-egg ; https://designingidea.com/big-green-egg-dimensions/ |
| MiniMax | 330 | 500 (BGE); 530 measured incl. carrier | 390 (measured) | W 540 (with carrier handles) × D 530 | 35 kg | https://biggreenegg.com/pages/what-size-is-my-egg ; https://www.grillsportverein.de/forum/threads/big-green-egg-minimax-zahlen-daten-fakten-gesammelte-infos.327210/ |
| Small | 330 | 610 | ≈405 **estimated** (16") | n/a | 36 kg | https://biggreenegg.com/pages/what-size-is-my-egg ; https://designingidea.com/big-green-egg-dimensions/ |
| Medium | 380 (US) / 400 (EU) | 720 | ≈457 **estimated** (18") | W 475 × D 595 (H 720) **(snippet, basbq.nl)** | 51 kg | https://biggreenegg.com/pages/what-size-is-my-egg ; https://www.biggreenegg.eu/en/products/models/medium ; https://basbq.nl/shop/big-green-egg-medium-met-onderstel/ (snippet) |
| **Large** | 460 | 840 | **560** at thickest point (band) | **Ø 720 incl. hinge + handle** (i.e. W ≈560, D ≈720) | 73 kg | https://www.biggreenegg.eu/en/products/models/large ; https://www.greeneggtotaal.nl/big-green-egg-large/ ; https://fonteyn.nl/products/big-green-egg-large-standaard (Ø56 × 84) |
| **XLarge** | 610 | 780 | **670** (measured) | D **840** (measured, incl. handle+hinge) | 99 kg | https://www.grillsportverein.de/forum/threads/big-green-egg-xlarge-zahlen-daten-fakten-gesammelte-infos.327211/ ; https://biggreenegg.com/pages/what-size-is-my-egg |
| 2XL | 740 (US) / 730 (EU) | 900 (BGE) / 890 (dealer) | ≈825 "approx" (dealer) | D ≈1000 **estimated** | 170 kg (EU) / 193 kg (built-in PDF) | https://www.thestoveyard.com/products/2xl-big-green-egg ; https://waves-console-big-green-egg.s3.amazonaws.com/products/41048/2XL-EGG-BUILT-IN-SPECS-011218-1.pdf |

Cross-check from BGE's own built-in spec PDFs (hole cut-out "ensures small air gap between ceramics and surrounding surface", so ceramic Ø is a bit below these):

| Size | Hole cut-out Ø | Min. distance centre→rear wall for fully opened dome | Shelf height above nest base | Source |
|---|---|---|---|---|
| Large | 540 | 508 | 381 | https://cdn.spasoftwaresolutions.net/product_documents/big_green_egg/2024/BUILT-IN-SPECS-FINAL-LARGE-EGG-122117-1300472.pdf |
| XLarge | 673 | 597 | 300 | https://cdn.spasoftwaresolutions.net/product_documents/big_green_egg/2024/XLARGE-EGG-BUILT-IN-SPECS-051121-v1-833838.pdf |
| 2XL | 830 | 724 | 330 | https://waves-console-big-green-egg.s3.amazonaws.com/products/41048/2XL-EGG-BUILT-IN-SPECS-011218-1.pdf |

Note: the band/hinge ring is wider than the ceramic, hence Large 560 (band) vs 540 cut-out (ceramic). Rear-wall distance tells how far the open dome swings back: Large ≈ 508 mm behind centre, so lid-open depth ≈ 280 (front half + handle) + 508 ≈ 790 **estimated**; lid-open height not published (Large ≈ 1.25–1.3× closed **estimated**).

Protrusions (all sizes): top rEGGulator cap (cast iron, ≈ 50–70 mm above dome **estimated**), dome thermometer (Ø 75 mm dial on 2XL, front of dome), front wooden handle (acacia, ~80 mm), rear spring hinge (Large/XL "easy-lift" hinge sticks out at the back), lower draft door (flush). For a cover: tall egg dome with a "chimney" nub and a front handle.

### 1b. Set-ups (stands, tables)

| Set-up | W×D×H (lid closed) | Notes | Sources |
|---|---|---|---|
| Large in Nest (or IntEGGrated Nest+Handler) | ≈ 720 (handle+hinge) × ≈ 720 × **1140** | "Op het Nest onderstel … totale hoogte ongeveer 114 cm; hoogte tot grilloppervlak 79 cm". IntEGGrated Nest+Handler adds a handle bar on one side (≈ +150–200 mm **estimated**). Retailer box spec for Large IntEGGrated nest: 35" H × 21" W × 25.7" L (likely nest only/packaging, **unreliable**) | https://www.greeneggtotaal.nl/big-green-egg-large/ ; https://www.acehardware.com/departments/outdoor-living/grills-and-smokers/grill-stands-tables-and-shelves/8025199 |
| Large in Nest + 2 Acacia EGG Mates | ≈ 560 + 2 × shelf; Mates 21"×15" (533×381) or 17.5"×11" (445×279) | Total W ≈ 1300 **estimated** (21" mates). Mates fold down. | https://biggreenegg.com/products/solid-acacia-egg-mates-21-x-15-for-large/ ; https://www.gertens.com/big-green-egg-acacia-wood-egg-mates-21 |
| XL in Nest | ≈ 840 × 840 × ≈ 1100 **estimated** | XL nest 25.5" high per retailer (snippet) | https://biggreenegg.com/products/nest-for-xl-egg (snippet) |
| Modular Nest – EGG Frame (L, XL, 2XL) | Frame **760 W × 760 D × 770 H**; egg dome above that: Large total ≈ 1230, XL ≈ 1250 **estimated** | Base unit, stainless grid insert, 4 adjustable legs (caster option +100 mm) | https://biggreenegg.com/products/large-egg-frame-with-stainless-grid-insert-for-modular-nest-system |
| EGG Frame + Expansion Frame/Cabinet | 760 + 760 = **1520 W × 760 D**, cabinet 762 × 762 × 775 H | Rectangular plinth + egg dome on one end | https://biggreenegg.com/products/expansion-cabinet-for-modular-nest-system |
| Acacia table – Large | Table **1524 × 635 × 787** (60"×25"×31") + egg dome above ≈ 460 → total H ≈ 1250 **estimated** | Egg sits in table nest offset to one side | https://bbq-authority.com/big-green-egg-solid-acacia-hardwood-table-for-large-eggs/ |
| Acacia table – XL | Table **1549 × 813 × 787** (61"×32"×31") | BGE "Cover C" fits XL in acacia table: 60 × 32 × 31.5 in | https://bbq-authority.com/big-green-egg-solid-acacia-hardwood-table-for-xlarge-eggs/ ; https://biggreenegg.com/collections/covers |
| MiniMax in carrier | 540 × 530 × 530 | Carrier with 2 handles | grillsportverein (above) |

### 1c. BGE own covers ("Universal-Fit", ventilated polyester)

| Cover | Fits | EUR (NL) | USD (US) | Source |
|---|---|---|---|---|
| MiniMax–Small–Medium | MX/S/M in nest/carrier | €118.00 | $69.99 (Cover H) / $44.99 (Cover G) | https://bbqgreeneggstore.nl/product-categorie/big-green-egg-accessoires/afdekhoezen/ |
| IntEGGrated Nest L–XL / Modular Frame M (Cover B, 126467) | L & XL in (IntEGGrated) nest | €138.75 (bbqgreeneggstore), €119.50 (bol.com); bol lists 65 × 78 cm | $79.99 | same ; https://www.bol.com/nl/nl/p/bge-large-cover-integgrated-nest-big-green-egg/9300000000689236/ |
| Modular EGG Frame L–XL–XXL (Cover A, 126450) | eggs in EGG Frame | €136.50 | $89.99 | same |
| Dome cover L–XL (Cover F) | dome only (built-in) | €86.00 | $49.99 | same |
| Table cover 150 × 60 | acacia table | €175.00 | $89.99 | same |
| Frame + Expansion Frame/Cabinet (Cover C) | | €186.00 | $89.99 | same |
| XXL / 2XL (Cover I) | 2XL in nest | €144.25 | $74.99 | same |

Gap for us: BGE covers are generic tube covers; none hug the egg + nest + EGG Mates shape.

Prices of eggs (NL, indicative): Large €1,924–1,995 (egg only), MiniMax €1,245, Medium €1,442 (adviesprijs) — https://vdmerwe.nl/overzicht-big-green-egg-modellen/ ; https://www.greenegg-store.nl/big-green-egg-large-solo.html

---

## 2. Other kamados (Kamado Joe, Monolith, The Bastard, Grill Guru)

| Model / set-up | W (mm) | D (mm) | H closed | Body Ø | Grid Ø | Sources |
|---|---|---|---|---|---|---|
| KJ Classic III, cart + shelves UP | 1094 official; retailers 1180–1194 | 762 (atbbq) / 765 | 1258 official; retailers 1265–1290 | ≈570 (snippet, Birstall) | 460 | https://www.kamadojoe.com/products/classic-joe-iii ; https://www.atbbq.com/products/kamado-joe-classic-iii-ceramic-grill-with-cart ; https://www.santosgrills.de/kamado-joe-classic-iii-rollwagen-seitentische |
| KJ Classic III, shelves DOWN | ≈760 **estimated** (Konnected Joe same cart: 30" folded / 47" out) | 762 | 1258 | | | https://www.thebbqdepot.com/kamado-konnected-joe/ |
| KJ Classic III Standalone | 560 official | 762 | 900 | ≈570 | 460 | https://www.kamadojoe.com/products/classic-joe-iii-standalone |
| KJ Classic II, cart + shelves | 1174 official | ≈760 **estimated** | 1210 | 570 (snippet) | 460 | https://www.kamadojoe.com/products/classic-joe-ii |
| KJ Konnected Joe | 1190 official (762 folded / 1194 extended) | ≈740 | 1220 | ≈570 | 460 | https://www.kamadojoe.com/products/konnected-joe |
| KJ Big Joe III, cart + shelves UP | 1310 official; retailers 1481–1483 | 909–914 | 1400 official; retailers 1364–1369 | 720 (snippet) | 610 | https://www.kamadojoe.com/products/big-joe-iii ; https://www.bbqtime.nl/kamado-joe-big-joe-3.html |
| KJ Big Joe III, shelves DOWN | ≈910–960 **estimated** | 909 | 1364–1400 | 720 | 610 | |
| KJ Big Joe III Standalone | 715 | 909 | 1135 | 720 | 610 | https://www.kamadojoe.com/products/big-joe-iii-standalone |
| KJ Joe Jr on cast-iron stand | ≈505 | ≈527 | ≈690 | ≈450 **estimated** | 343 | https://www.kamadojoe.com/products/joe-jr-and-cart-bundle |
| Monolith Classic Pro 2.0 / TWO.55, frame + bamboo side tables | 1200 | 710 | 1200 | ≈550 **estimated** | 440 | https://www.grillfuerst.de/Monolith/Two/Two-55-Keramikgrill-mit-Gestell-Seitentische.php |
| Monolith LeChef Pro 2.0 / TWO.66, frame + side tables | 1350 | 800 | 1290 | ≈660 **estimated** | 520 | grillheaven.at / bbq24.de (snippet) |
| Monolith Junior Pro 2.0 with frame | 470 | 520 | 950 | n/a | 330 | https://www.grillfuerst.de/Monolith/Junior/Pro-Serie-2-0-schwarz-mit-Gestell.php (snippet) |
| The Bastard Large Complete | 1490 | 800 | 1270 | ≈570–580 | 490 | https://www.bakkerbrandstoffen.nl/product/the-bastard-large-complete/ ; https://www.coolblue.nl/product/835710 |
| Grill Guru Large Complete | n/a | n/a | 1240 | 560 | 460 | https://www.grillguru.com/nl/product/grill-guru-large-complete/ (snippet) |

Protrusions: KJ Kontrol Tower top vent, dome thermometer, front handle + latch, Air Lift hinge band rear, slide-out ash drawer; Konnected Joe control panel/fan front-low. Monolith: rear spring hinge, side smoke-chip feeder port, bamboo side tables. Lid-open heights not published; Classic on cart ≈ 1600–1700 **estimated**.

Own covers: KJ Classic cover KJ-GC23BWFS 850 × 850 × 1230 mm (33.5"×33.5"×48.5"), €65–84 (https://www.bol.com/nl/nl/p/kamado-joe-flexible-grill-cover-classic-joe-kj-gc23bwfs/9200000107067896/ ; https://cookersandgrills.nl/product/kamado-joe-beschermhoes-classic-konnected-joe/); KJ Big Joe cover BJ-GC24BWFS 960 × 960 × 1400, €79.90–99.90 (https://kamadoexpress.nl/product/beschermhoes-big-joe/); Monolith .55 cover €89.90 (https://www.monolith-grill.de/products/classic-abdeckhaube); Monolith LeChef cover €69.90–129 (https://geizhals.de/monolith-lechef-abdeckhaube-201037-a2855952.html); Monolith Buggy cover €169.90; The Bastard Raincover Large 570 × 570 × 1350, ≈€71 (https://www.bosrand.nl/the-bastard-beschermhoes-large).

Prices: KJ Classic III €1,879–1,889 street (list €2,399); Big Joe III €2,999; Bastard Large Complete €1,499; Bastard PRO Large Complete €2,399.

**Warning:** KJ Classic III / Big Joe III widths conflict between kamadojoe.com and retailers (1094 vs ≈1190; 1310 vs ≈1480). Measure a physical unit before patterning.

---

## 3. Premium gas

| Model | W×D×H closed | Lid-open H (D) | Shelves folded W | Shape | Protrusions | Own cover + EUR | Popularity | Sources |
|---|---|---|---|---|---|---|---|---|
| Weber Genesis E-335W (2026 "W" gen) | 1560 × 685 × 1220 | 1600 (D 775) | fixed | rectangular cart, curved hood, side burner right | front handle bar, display, Weber Works rails | Genesis 300 Premium cover €139.99 (7757/7194B) | Genesis = Weber premium bestseller | https://www.weber.com/NL/nl/gasbarbecues/genesis-series/-/1501249.html |
| Weber Genesis EX-335 Smart (2022) | 1575 × 686 × 1232 | 1600 (D 787) | fixed | same | same + smart display | €139.99 | high search interest DE (snippet) | https://www.weber.com/NL/nl/gasbarbecues/genesis-series/genesis-ex-335-smart-gas-barbecue/35610064.html |
| Weber Genesis E-435W | 1730 × 685 × 1220 | 1600 (D 775) | fixed | rectangular, 4 burners | handle, display | Genesis 400 Premium cover €149.99 (7195), cover size 1100 H × 1800 W × 650 D | | https://www.weber.com/NL/nl/gasbarbecues/genesis-series/-/1501267.html ; https://www.weber.com/NL/nl/gas-covers/genesis-covers/7195.html |
| Weber Genesis SP-435W (top stainless; no "SPX-435" in NL) | 1830 × 685 × 1220 | 1600 (D 775) | fixed | rectangular | handle, display | 400 cover €149.99 (assumed fit) | | https://www.weber.com/NL/nl/gasbarbecues/genesis-series/-/1501187.html |
| Weber Summit FS38 E/S/X | 1800 × 685 × 1330 | 1530 (D 750) | fixed | large rectangular cart, side burner in right shelf | rotisserie motor bracket at side, IR sear, handle | Summit Premium cover €239 (3400173B, AT); US cover 1270 H × 1956 W × 762 D | flagship €4,499 | https://www.weber.com/AT/de/gasgrills/summit/summit-fs38-e-gasgrill/1500057.html ; https://www.weber.com/US/en/accessories/grill-covers/3400173.html |
| Weber Summit S-670 (legacy) | 1883 × 674 × 1283 (snippet) | ≈1450 (snippet) | fixed | rectangular | rotisserie, side burner, smoker | 3400173 | legacy stock | weber.com/NL (404 now) |
| Napoleon Prestige 500 RSIB | 1660–1670 × 660–670 × 1295–1300 | 1450–1470 | **1370** (one shelf folds) | rectangular, roll-top domed lid | rear IR burner + rotisserie motor bracket side, IR side burner | 61500, ≈€90–95 (snippet) | NL premium pick, €1,999–2,299 | https://www.bbqexperiencecenter.nl/napoleon-prestige-500-rsib/ ; https://www.forestoutdoor.nl/napoleon-prestige-500-connected/ |
| Napoleon Prestige 665 RSIB | 1900 × 675 × 1270 (snippet) | 1450 | n/a | rectangular | as above | 61665 €109 | DE "top performer" (snippet) | https://www.tuincentrumschmitz.nl/napoleon-bbq-hoes-voor-prestige-en-prestige-pro-665 |
| Napoleon Prestige PRO 500 RSIB | 1690 × 640 × 1320 | 1450 | fixed | rectangular, high dome | rotisserie kit incl., side burner | 61500 ≈€90–95 | €2,849 | https://hout-art.nl/product/bbq-napoleon-prestige-pro-500-rvs-inclusief-draaispit/ |
| Napoleon Prestige PRO 665 RSIB | 1950 × 650 × 1300 | 1420 (snippet) | fixed | rectangular | rotisserie, IR side burner, smoker box | 61665 €109–119 | €4,499 | https://www.bbqkopen.nl/product/napoleon-prestige-pro-665-rsib-zilver |
| Napoleon Prestige PRO 825 RSBI | ≈2390 × 640 × 1300 (snippet, US) | ≈1450 **estimated** | fixed | long rectangle, 2 lids | | 61825, no EUR price | niche | https://www.dimensions.com/element/napoleon-prestige-pro-825 |
| Broil King Regal S590 Pro IR | 1590 × 630 × 1250 | 1450–1460 | fixed SS | rectangular, roll-top with cast end caps | rotisserie bracket, IR side burner | 500-series cover RRP €139.90 | DE "Vergleichssieger 2026" (snippet); Grillfürst 5★/43 reviews (Regal 590 Black) | https://www.grillgoods.de/products/broil-king-regal-s-590-pro-ir-inkl-drehspiess ; https://www.grillfuerst.de/broil-king/gasgrill/broil-king-regal-590-black.php |
| Broil King Imperial S690 XL Pro IR | 1930 × 630 × 1250 | 1480 (snippet) | fixed | long rectangle, 2 lids | rotisserie, side burner, 2 handles | 68490 RRP €149.90 | premium flagship | https://www.grillfuerst.de/broil-king/gasgrill/broil-king-imperial-690-xl-pro.php |
| Lynx Professional 27" freestanding | ≈1340 × 641 × 1470 **estimated** (H may be lid-open) | n/a | fold down | rectangular, square SS hood | rotisserie | USD 329 only | very rare NL/DE | bbqguys.com (snippet) |
| Lynx Professional 36" freestanding | ≈1568 × 670 × 1490 **estimated** | n/a | fold down | rectangular | rotisserie | USD 359 | rare | authenteak.com (snippet) |
| Everdure Furnace (3 burner, cart) | 1310 × 750 × 1068 | 1549 | fixed | low flat-lid rectangle | handle | yes, no EUR price | design niche | https://everdure.com/products/furnace |
| Everdure Force (2 burner, cart) | 1175 × 743 × 1067 | 1447 | fixed | same | handle | same | niche | outdoorsdomain.com.au (snippet) |

Notes: Genesis 300/400/SP share depth 685 and height 1220 → one pattern per width class. Weber covers are deliberately shorter than the grill (400 cover 1100 H on a 1220 grill). Napoleon/Broil King rotisserie motor brackets protrude from the hood side.

### Premium charcoal kettle (added: very high volume, premium price band)

| Model | W×D×H closed | Lid open H | Source |
|---|---|---|---|
| Weber Master-Touch GBS Premium E-5775 (57 cm) | 650 × 760 × 1000 | 1410 | https://www.weber.com/NL/nl/barbecues/houtskoolbarbecues/master-touch/master-touch-gbs-premium-e-5775-charcoal-barbecue-57-cm/17401004.html (via snippet) |

---

## 4. Pellet

| Model | W×D×H closed | Lid open | Shape / protrusions | Own cover EUR | Grill EUR | Sources |
|---|---|---|---|---|---|---|
| Traeger Timberline XL (2023) | 1810 × 640 × 1300 | not published (≈1600–1650 **estimated**) | rectangular cabinet; hopper + induction side shelf inside width; P.A.L. rail front | €189.90–219.90 | €4,399.90 | https://www.grillfuerst.de/Traeger/Pelletgrill/Timberline-XL-Pelletsmoker.php ; https://www.traeger.com/nl/nl/pellet-grills/timberline-xl |
| Traeger Timberline (2023) | 1500 × 640 × 1300 | **estimated** | same | ≈€190–220 **estimated** | €3,499.90 | https://www.grillfuerst.de/Traeger/Pelletgrill/Timberline-Pelletsmoker.php |
| Traeger Ironwood XL (2023) | 1778 × 635 × 1219 | n/a | barrel lid, side hopper box, side shelf, P.A.L. rail | €179.90 (snippet) | €2,599.90 | https://www.traeger.com/nl/nl/pellet-grills/ironwood-xl ; alternate.de (snippet) |
| Traeger Ironwood (2023, replaces 650) | ≈1500 × 640 × 1220 (snippet) | n/a | same | €169.90 (BAC690) | €2,299.90 | https://grillstar.de/products/traeger-abdeckhaube-ironwood |
| Traeger Ironwood 650 (gen 1) | ≈1170 × 690 × 1190 (snippet) | n/a | barrel, hopper left | €100.90–129.90 | from €1,699.90 | grangecoop.com (snippet) |
| Traeger Ironwood 885 (gen 1/D2) | 1350 × 690 × 1190 | n/a | barrel, hopper left | €149.90 (snippet) | | santosgrills.de (snippet) |
| Weber Searwood 600 | 980 × 585 × 1160 | 1510 (D 725) | rectangular hood on cart; hopper one side, table other (inside W) | Premium cover €69.99 | €1,099–1,199 | bol.com (snippet) |
| Weber Searwood XL 600 | 1280 × 585 × 1160 | 1510 (D 725) | same | 3400170 €89.99, cover 1190 H × 1280 W × 650 D | €1,499 | https://www.weber.com/DE/de/zubehoer/grill-schuetzen/abdeckhauben-fuer-pelletgrills/3400170.html |
| Weber SmokeFire EPX6 (phasing out) | 1410 × 838 × 1194 | 1651 | hopper left | yes | | weber.com/CH (snippet) |

Hopper offset/side not verified for Traeger; in all quoted figures the hopper is inside the overall W.

---

## 5. Fire tables / plancha / ovens

| Model | Top | Base | Overall W×D×H | Shape | Own cover EUR | Unit EUR | Sources |
|---|---|---|---|---|---|---|---|
| OFYR Classic+ 85 | Ø 850 plate | cone, base Ø 500 | 850 × 850 × 1000 | round disc on cone | Soft cover 85 ≈€49.95; steel lid sold | €1,795–1,945 | https://ofyr.com/nl/products/ofyr-classic-black-85 ; https://www.vuurkorfwinkel.nl/ofyr-classic-85-100.html |
| OFYR Classic+ 100 | Ø 1000 | cone, base Ø 500 | 1000 × 1000 × 1000 (1010) | round | Soft cover €45; hard Cover Black 100 €219 | €1,995–2,145 | https://ofyr.com/nl/products/ofyr-classic-black-100 ; https://ofyr.com/nl/products/ofyr-cover-black-100 |
| OFYR Classic+ Storage 85/100 (+PRO) | Ø 850/1000 | square storage column ≈650 × 650 × 670 (**unverified**) | 1000 × 1000 × 1000 | round top on square base | as Classic | €1,995–2,545 | https://ofyr.com/nl/products/ofyr-classic-storage-black-100 |
| OFYR Island 100 (+PRO) | Ø 1000 | cabinet 1350 × 500 (PRO 650) × ≈730–750 with side worktop | 1350 × 500 × 1000 (one source 1700 × 1000 × 980 incl. overhang) | round plate overhanging rectangle ("keyhole") | plate soft cover only | €3,795–3,995 | https://www.firepit-online.com/ofyr-island-100-100.html ; https://ofyr.com/nl/products/ofyr-island-corten-100-pro-ceramic-dark-grey |
| OFYR 120 / XL 150 | Ø 1200 / 1500 | XL base 770 × 770 × 620 | XL 1490 × 1490 × 1080 | round | | €2,995 / €4,245 | https://buiten.studio/ofyr-bbq/ |
| Arteflame Classic 40" | Ø 1016 | tall round base Ø 533 | ≈1016 × 1016 × 965 | round | vinyl 40" $139; One/Euro 40 cover €199 (snippet) | | https://arteflame.com/products/arteflame-40-vinyl-cover |
| Höfats Cone | grate Ø 450 | SS cone | 600 × 600 × 1050 | round cone | €69.95 | €799.95 | https://hofats.com/en/CONE-Cover/010401 |
| Feuerring D100 / D120 | Ø 1000 / 1200 | ring | Ø1000 × 230 / Ø1200 × 280 | round | | ≈€6,500 (Luna) | mit-haerzbluet.ch (snippet) |
| Morsø Forno | – | on table/stand | 750 × 683 × 607 | dome oven + chimney | ≈€79 (snippet) | ≈€1,399 | https://www.morsoe.com/de/produkte/outdoor/aussenoefen-und-kamine/forno |
| Ooni Karu 16 | – | tabletop | 825 × 502 × 825 (with chimney) | box + chimney + door | €50 | €799 | https://ooni.com/products/ooni-karu-16 ; https://eu.ooni.com/products/ooni-karu-16-cover |
| Ooni Koda 16 | – | tabletop | 630 × 580 × 370 | wedge/dome | €45 | ≈€599–649 | https://ooni.com/products/ooni-koda-16 |

Not researched: Le Feu. OFYR has no full-unit or Island cover → clear opportunity (round top over cone/square base; Island keyhole).

---

## 6. Outdoor kitchen modules (brief)

- Napoleon OASIS Compact / OASIS 100 (built-in 500 series): ≈2210–2245 × 830 × 1291, lid open 1537 (snippet). Modules: BIPRO500 base cabinet 1395 × 610 × 900; 2-drawer / gas-bottle cabinets 610 × 610 × 900. https://www.napoleon.com/en/us/grills/products/outdoor-kitchens/oasis-compact-series/oasis-100-outdoor-kitchen-built-500-series-32-odk100-bi32nss
- Weber Outdoor Kitchen (EU): modules 640 W × 611 D, fridge 642 × 642, worktop 930–995 H; with Summit FS38 E a run of 3670 × 610/1280 × 930–995. https://www.weber.com/GB/en/bbq-kitchen-configurator.html (dims via thebarbecuestore.es snippet)
- BGE Modular Nest System: 760 × 760 modules (see 1b).
- Cover form: stepped profile (hood ≈1290, worktop ≈900–995) or worktop cover + separate hood cover.

---

## 7. Open items / what to measure physically

1. BGE lid-open heights and IntEGGrated Nest+Handler handle overhang; Medium/2XL outer Ø (only snippet/approx).
2. Kamado Joe Classic III and Big Joe III cart widths (official vs retailer conflict).
3. Traeger hopper side and offset; lid-open heights.
4. Napoleon numbers came via retailers (napoleon.com returned 403).
5. Lynx heights.

---

## 8. Ranked priority list (cover design order)

Rank is a judgement call combining popularity in NL/BE/DE (sources in §0), premium price band and fit for a made-to-measure acrylic cover. "est." = estimated.

| # | Brand / model | Set-up | W×D×H closed (mm) | Shape | Key protrusions | Own cover EUR |
|---|---|---|---|---|---|---|
| 1 | Big Green Egg Large | Nest / IntEGGrated Nest+Handler | ≈720 × 720 × 1140 | egg on stand | rEGGulator cap, thermometer, front handle, rear hinge, nest handle bar | €119.50–138.75 |
| 2 | Big Green Egg Large | Modular Nest EGG Frame | 760 × 760 × ≈1230 (est.) | egg on square frame | as above | €136.50 |
| 3 | Kamado Joe Classic III | cart + shelves | 1094–1194 × 762 × 1258–1290 | egg on cart + 2 shelves | Kontrol Tower, hinge, handle, ash drawer | €65–84 |
| 4 | Weber Genesis E-335W / EX-335 | cart | 1560–1575 × 685 × 1220–1232 | rectangle | handle bar, side burner, display | €139.99 |
| 5 | Big Green Egg Medium | Nest | 475 × 595 (egg) × ≈990 (est.) | egg on stand | as BGE | €118 |
| 6 | Big Green Egg XLarge | Nest / EGG Frame | 840 × 840 × ≈1100 (est.) / 760 × 760 frame | egg on stand | as BGE | €136.50–138.75 |
| 7 | Big Green Egg Large + EGG Mates | Nest + 2 shelves | ≈1300 (est.) × 720 × 1140 | egg + 2 wings | as BGE + shelves | none fitted |
| 8 | Big Green Egg MiniMax | carrier | 540 × 530 × 530 | small egg | carrier handles | €118 |
| 9 | Weber Genesis E-435W / SP-435W | cart | 1730–1830 × 685 × 1220 | rectangle | as #4 | €149.99 |
| 10 | The Bastard Large Complete | frame + side tables | 1490 × 800 × 1270 | egg + 2 shelves | hinge, handle, vent | ≈€71 |
| 11 | Napoleon Prestige 500 | cart | 1660–1670 × 660–670 × 1295–1300 (1370 W folded) | rectangle, roll-top | rotisserie bracket, side burner | ≈€90–95 |
| 12 | OFYR Classic+ 85 / 100 | cone base | 850/1000 Ø × 1000 | round disc on cone | none (flat plate) | €45–50 soft, €219 lid |
| 13 | Kamado Joe Big Joe III | cart + shelves | 1310–1483 × 909 × 1364–1400 | egg on cart | as #3 | €79.90–99.90 |
| 14 | Big Green Egg Large / XL | Acacia table | 1524 × 635 / 1549 × 813, table 787 H, dome ≈1250 (est.) | rectangle + dome | egg dome sticks up from table | €175 |
| 15 | Weber Master-Touch Premium 57 | kettle | 650 × 760 × 1000 | round kettle | handle, ash catcher | Weber cover |
| 16 | Broil King Regal S590 Pro IR | cart | 1590 × 630 × 1250 | rectangle, roll-top | rotisserie, side burner | €139.90 |
| 17 | Weber Searwood 600 / XL 600 | cart | 980 / 1280 × 585 × 1160 | rectangle | hopper (inside W) | €69.99 / €89.99 |
| 18 | Weber Summit FS38 | cart | 1800 × 685 × 1330 | rectangle | rotisserie bracket, side burner | €239 |
| 19 | Traeger Ironwood (2023) / Ironwood XL | cart | ≈1500 / 1778 × 635–640 × 1219–1220 | barrel on cart | hopper box, P.A.L. rail | €169.90 / €179.90 |
| 20 | Monolith Classic / TWO.55 | frame + tables | 1200 × 710 × 1200 | egg + 2 shelves | hinge, chip feeder | €89.90 |
| 21 | Traeger Timberline / XL | cabinet | 1500 / 1810 × 640 × 1300 | rectangle | P.A.L. rail | €189.90–219.90 |
| 22 | Napoleon Prestige PRO 500 / 665 | cart | 1690 × 640 × 1320 / 1950 × 650 × 1300 | rectangle | rotisserie, side burner | €90–119 |
| 23 | OFYR Island 100 (PRO) | cabinet | 1350 × 500–650 × 1000 | round over rectangle (keyhole) | worktop | none for full unit |
| 24 | Big Green Egg 2XL | Nest | ≈1000 (est.) × ≈1000 × ≈1200 (est.); egg Ø ≈825, H 890–900 | egg | as BGE | €144.25 |
| 25 | Broil King Imperial S690 XL | cart | 1930 × 630 × 1250 | long rectangle, 2 lids | rotisserie, side burner | €149.90 |
