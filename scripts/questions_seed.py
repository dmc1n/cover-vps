# ruff: noqa: E501 - the questions are data, kept as one string per line of text
"""The open questions to put on the Desk's Questions tab (ADR-109), used by
`scripts/questions.py import`.

1. DOUBTS: the rejection agents' "doubt" rows (out/rejections/*/results.json, 8 Oct 2026) carry
   their own Dutch question and options; here only a short title, the topic, and which rows
   join one question ("zelfde vraag als S38").
2. FROM_QUESTIONS_MD: the questions in docs/QUESTIONS.md still open for the owner or the
   workshop, rewritten as short Dutch questions with options.

Every question has a fixed `key`, so importing again adds nothing twice.
"""

from __future__ import annotations

from typing import Any

# question 71 (vents on the inner walls of L, U and C covers): answered YES on 9 Oct 2026
SKIP_OPTION_MARK = "vent_inner_walls"
SKIP_TEXT_MARK = "binnenwand"

# "zelfde vraag als …": the row joins the question of this model
JOIN = {
    "drawing-s39": "drawing-s38",
    "2026-07-cover-s60-rc-v1": "2026-07-cover-s53-rc-v1",
    "suns-2-seater-with-arm-avero": "suns-2-seater-open-sorrento",
}

# covers a question is about besides those whose row asked it
EXTRA_MODELS = {"drawing-r1": ["drawing-r2", "drawing-r3"]}

# pictures besides a row's own (path relative to the agent's worktree, caption)
EXTRA_PICTURES = {
    "drawing-s21": [
        (
            "out/rejections/G/alt-30deg/drawing-s21/cover.png",
            "S21 met 30 graden, zoals Rens schrijft",
        ),
    ],
}

# per leading model: (title, topic)
DOUBTS: dict[str, tuple[str, str]] = {
    "suns-lounge-vento-angled-2-seater-left": (
        "Vento hoek-2-zits: nok en schuine naad zoals Rens tekent?",
        "seams",
    ),
    "suns-lounge-fiave-l-part-right": ("Fiave L-deel: dak over de kussens volgen?", "shape"),
    "suns-lounge-nuna-lounge-chair": ("Nuna loungestoel: ronde rug ook in zijaanzicht?", "shape"),
    "drawing-d5": ("D5: hoe loopt de ronde voorkant?", "shape"),
    "drawing-s20-bora-not-ordered": ("S20 Bora: zitting volgen of overspannen?", "shape"),
    "drawing-s21": ("S21 Vento hoekbank: knik van 40 of 30 graden?", "drawings"),
    "drawing-s37": ("S37: diepte 102,1 cm of recht stuk 53,3 cm?", "sizes"),
    "drawing-s38": ("S38 en S39: wat is er mis met de vorm?", "shape"),
    "drawing-s45": ("S45: de band in één stuk van 358 cm?", "seams"),
    "drawing-s47": ("S47: hoes naar de gestippelde lijn?", "sizes"),
    "drawing-s48": ("S48: armleuningen volgen of overspannen?", "shape"),
    "suns-daybed-with-roof-portofino": (
        "Daybed met dak Portofino: geen hoes nodig, wat met het model?",
        "other",
    ),
    "drawing-r1": ("R1–R3: vents bovenin, zoals de tekening?", "vents"),
    "drawing-s25": ("S25: vents nu live, vorm later?", "vents"),
    "suns-2-seater-portofino": ("Portofino 2-zits: 1 of 2 vents op de lange zijden?", "vents"),
    "suns-daybed-portofino": ("Daybed Portofino: nieuwe vents nu al live?", "vents"),
    "suns-longue-aspen": ("Aspen ligbed: 1 of 2 vents op de lange zijde?", "vents"),
    "suns-lounge-sato-2-5-seater-bench": (
        "Sato 2,5-zits: smalle strook bij het bovenpaneel?",
        "seams",
    ),
    "2026-07-cover-s53-rc-v1": ("S53 en S60: naden op de lijnen van het model?", "seams"),
    "suns-daybed-vento": ("Daybed Vento: voorvlakken te breed voor de rol, rode lijn", "seams"),
    "suns-lounge-vento": ("Vento lounge: hoe bouwen we deze vorm?", "shape"),
    "suns-2-seater-open-sorrento": ("SUNS-banken als doos: rechte bovenrand per wand?", "seams"),
    "suns-3-seater-with-corner-sorrento": (
        "Sorrento 3-zits met hoek: extra deling langs de rode lijn?",
        "seams",
    ),
}

DONE_ELSEWHERE = "Ik regel het zelf in de studio (Shop settings / Prices & costing)"


def _q(key: str, topic: str, title: str, text: str, options: list[str] | None = None,
       context: str = "", source: str = "docs/QUESTIONS.md") -> dict[str, Any]:  # fmt: skip
    return {"key": f"qmd:{key}", "topic": topic, "title": title, "text": text,
            "options": options or [], "context": context, "source": source}  # fmt: skip


FROM_QUESTIONS_MD: list[dict[str, Any]] = [
    # ---- the consumer shop goes public (question 73)
    _q(
        "73-company",
        "webshop",
        "Bedrijfsgegevens voor de webshop",
        "Welke bedrijfsgegevens komen in de shop (voorwaarden, voettekst, Google)? Handelsnaam, "
        "statutaire naam, adres, KvK, btw-nummer, e-mail en telefoon.",
        ["Staan in mijn opmerking hieronder", DONE_ELSEWHERE],
        "Vraag 73. Shop settings → company vult de juridische pagina's, de voettekst en de "
        "gegevens voor Google.",
    ),
    _q(
        "73-legal",
        "webshop",
        "Juridische teksten van de shop",
        "De voorwaarden, privacy, retour, cookies, contact en garantie zijn concepten "
        '("CONCEPT — TER GOEDKEURING"). Wat doen we ermee?',
        [
            "Ik laat ze nakijken (jurist, Thuiswinkel of Juridisch Loket) en stuur de tekst",
            "De concepten zijn goed: publiceren",
            "Eerst samen bespreken",
        ],
        "Vraag 73. De teksten staan in config/shop_legal.json; een eigen tekst per pagina gaat via "
        "Website (AI).",
    ),
    _q(
        "73-legal-choices",
        "webshop",
        "Keuzes in de voorwaarden",
        "In de concepten staan: annuleren als de levering 30 dagen te laat is, een eigen garantie op "
        "naden en stof, bestelgegevens 7 jaar bewaren, maataanvragen 12 maanden bewaren. Akkoord?",
        ["Alles akkoord", "Akkoord met wijzigingen (zie opmerking)", "Eerst bespreken"],
        "Vraag 73.",
    ),
    _q(
        "73-withdrawal",
        "webshop",
        "Bedenktijd bij hoezen uit het assortiment",
        "Een hoes uit ons vaste assortiment (de match) heeft wettelijk 14 dagen bedenktijd; alleen "
        "maatwerk is uitgezonderd. Wat willen we?",
        [
            "Akkoord: 14 dagen bedenktijd voor hoezen uit het assortiment",
            "Alleen maatwerk verkopen (elke hoes op de maten van de klant)",
        ],
        "Vraag 73. De checkout zegt het nu al.",
    ),
    _q(
        "73-delivery",
        "webshop",
        "Bezorgkosten per land",
        "Naar welke landen leveren we, en wat kost de bezorging per land (incl. btw)? Nu staat er "
        "niets, dus de checkout rekent € 0.",
        [
            "Alleen Nederland (bedrag in opmerking)",
            "NL, BE en DE (bedragen in opmerking)",
            "Gratis bezorging: het zit in de prijs",
        ],
        "Vraag 73. Shop settings → shipping.",
    ),
    _q(
        "73-delivery-double",
        "webshop",
        "Verzendkosten: in de prijs, apart of beide?",
        "De prijsset rekent € 18,50 verzending als kostenregel in de prijs van de hoes; de bezorgkosten "
        "per land komen er bovenop. Houden we beide, of één?",
        [
            "Beide houden",
            "Alleen in de prijs (geen bezorgkosten apart)",
            "Alleen apart per land (uit de prijs halen)",
        ],
        "Vraag 73.",
    ),
    _q(
        "73-mollie",
        "webshop",
        "Mollie live zetten",
        "Er is nog geen Mollie-sleutel op de live studio, dus bestellingen wachten op betaling met de "
        "hand. Hoe ver is het Mollie-account (KvK, bankrekening, website shop.s2dio.living)?",
        [
            "Account is klaar: ik zet eerst de test-sleutel en daarna de live-sleutel",
            "Nog bezig met het account",
            "Geen Mollie: alleen bankoverschrijving",
        ],
        "Vraag 73. Eerst een testbestelling met de test-sleutel (test_…), dan de live-sleutel "
        "(live_…) in Shop settings → payment.",
    ),
    _q(
        "73-bank",
        "webshop",
        "Bankoverschrijving als terugval houden?",
        "Als Mollie werkt: blijft betalen per bankoverschrijving mogelijk?",
        ["Ja, houden", "Nee, alleen Mollie"],
        "Vraag 73.",
    ),
    _q(
        "73-turnstile",
        "webshop",
        "Botbescherming: Cloudflare Turnstile?",
        "Nu beschermen een honeypot en limieten de formulieren. Willen we ook Cloudflare Turnstile "
        "(gratis)?",
        [
            "Ja: ik maak de site key en secret aan in Cloudflare",
            "Nee, honeypot en limieten zijn genoeg",
        ],
        "Vraag 73. De sleutels gaan in deploy/.env als TURNSTILE_SITE_KEY en TURNSTILE_SECRET_KEY.",
    ),
    _q(
        "73-golive",
        "webshop",
        "Wanneer gaat de shop live?",
        "Wanneer kondigen we de shop aan, en gaat het scrollverhaal op de homepage (home_story) "
        "mee aan?",
        [
            "Zo snel mogelijk, met het scrollverhaal",
            "Zo snel mogelijk, scrollverhaal later",
            "Op een datum (zie opmerking)",
        ],
        "Vraag 73.",
    ),
    _q(
        "73-og",
        "webshop",
        "Deelafbeelding van de shop",
        "De afbeelding die je ziet als iemand de shop deelt (/brand/og-shop.png) is een eenvoudige "
        "placeholder. Een foto van een echte hoes (1200×630) is beter.",
        ["Ik lever een foto aan", "Maak er een uit onze film of 3D", "De placeholder is goed"],
        "Vraag 73. Shop settings → og_image.",
    ),
    _q(
        "73-indicative",
        "prices",
        'Prijzen nog "indicatief"?',
        'Elke prijs in de shop zegt nu "indicatief". Zijn de prijzen definitief, zodat dat eraf '
        "mag?",
        [
            "Ja, definitief: indicatief mag eraf",
            "Nee, eerst de prijzen invullen (zie de prijsvragen)",
        ],
        "Vraag 73. Uitzetten gaat door een prijsset zonder 'indicatief' te publiceren (Prices & "
        "costing).",
    ),
    # ---- prices and costing (question 70)
    _q(
        "70-rate",
        "prices",
        "Wisselkoers rupiah per euro",
        "De kostprijs rekent met 18.500 rupiah per euro. Klopt dat, en vanaf welke datum?",
        ["18.500 klopt", "Andere koers (zie opmerking)", DONE_ELSEWHERE],
        "Vraag 70.",
    ),
    _q(
        "70-fabric",
        "prices",
        "Stof: inkoopprijs en snijafval",
        "Coverlast kost nu € 24,50 per meter (rol 150 cm), snijafval 12,5 %. Klopt dat? En welke "
        "andere stoffen of kwaliteiten, met hun kleuren?",
        ["Klopt", "Andere waarden (zie opmerking)", DONE_ELSEWHERE],
        "Vraag 70.",
    ),
    _q(
        "70-components",
        "prices",
        "Onderdelen: prijzen",
        "Ventset € 3,75, trekkoord € 0,65/m, elastiek € 0,85/m, ballon € 14,50, frame € 64,50. "
        "Kloppen die, en komt er per hoes nog iets bij (labels, garen, zakken)?",
        [
            "Klopt, er komt niets bij",
            "Andere waarden of extra onderdelen (zie opmerking)",
            DONE_ELSEWHERE,
        ],
        "Vraag 70.",
    ),
    _q(
        "70-labour",
        "prices",
        "Arbeid: uurtarief en minuten",
        "Nu: € 42,50 per uur; minuten: snij-opzet 12,5, per stuk 6,5, per meter naad 2,5, per vent "
        "9,5, per meter zoom 1,75, inpakken 6,5. Klopt dat?",
        ["Klopt", "Andere waarden (zie opmerking)", DONE_ELSEWHERE],
        "Vraag 70.",
    ),
    _q(
        "70-b2c",
        "prices",
        "Consumentenprijs: opslag en extra kosten",
        "Nu: opslag 87,5 %, afronden op ,95 incl. btw, btw 21 %, verzending € 18,50, invoer 12,5 % "
        "(kost + verzending), verpakking € 2,75. Klopt dat?",
        ["Klopt", "Andere waarden (zie opmerking)", DONE_ELSEWHERE],
        "Vraag 70.",
    ),
    _q(
        "70-markup-base",
        "prices",
        "Opslag op welke kosten?",
        "Rekenen we de opslag over de kostprijs plus de extra kosten (nu), of alleen over de "
        "kostprijs?",
        ["Kostprijs + extra kosten (zoals nu)", "Alleen de kostprijs"],
        "Vraag 70.",
    ),
    _q(
        "70-balloons",
        "prices",
        "Ballonnen en frame: apart verkopen?",
        "Worden ballonnen en het frame altijd apart verkocht (nu), of horen ze bij sommige hoezen?",
        ["Altijd apart (zoals nu)", "Bij tafelhoezen inbegrepen", "Anders (zie opmerking)"],
        "Vraag 70.",
    ),
    _q(
        "70-odoo",
        "prices",
        "Odoo-koppeling",
        "Voor stap 2 (prijzen en kostprijzen naar Odoo) zijn nodig: de URL en database, een "
        "API-gebruiker en sleutel, de versie (Community of Enterprise), de apps (Sales, Purchase, "
        "MRP, Inventory, Accounting, meerdere valuta) en de bedrijfsvaluta.",
        ["Ik stuur de gegevens naar Rick", "Nog geen Odoo-koppeling", "Eerst bespreken"],
        "Vraag 70.",
    ),
    # ---- the B2B shop (question 72)
    _q(
        "72-terms",
        "b2b",
        "B2B: betaaltermijn",
        "Hoeveel dagen krijgt een dealer om de factuur te betalen (nu 30)? Voor iedereen gelijk of "
        "per bedrijf? En wie stuurt de facturen (Odoo)?",
        ["30 dagen voor iedereen", "Per bedrijf verschillend", "Anders (zie opmerking)"],
        "Vraag 72.",
    ),
    _q(
        "72-roles",
        "b2b",
        "B2B: wie mag bestellen?",
        "Mag iedereen met een login bij een dealer bestellen, of mogen sommigen alleen prijzen "
        "bekijken (een rol 'inkoper' en een rol 'kijker')?",
        ["Iedereen met een login mag bestellen", "Twee rollen: inkoper en kijker"],
        "Vraag 72.",
    ),
    _q(
        "72-minimum",
        "b2b",
        "B2B: minimale bestelling",
        "Is er een minimale bestelling (nu geen), per bestelling of per jaar?",
        [
            "Geen minimum",
            "Minimum per bestelling (zie opmerking)",
            "Minimum per jaar (zie opmerking)",
        ],
        "Vraag 72.",
    ),
    _q(
        "72-delivery",
        "b2b",
        "B2B: verzendkosten",
        "Zitten de verzendkosten in de prijs (nu € 9,50 per hoes in het B2B-kanaal) of komt er een "
        "regel per bestelling bovenop? Gratis vanaf een bedrag?",
        [
            "In de prijs (zoals nu)",
            "Per bestelling erbovenop",
            "Gratis vanaf een bedrag (zie opmerking)",
        ],
        "Vraag 72.",
    ),
    _q(
        "72-custom",
        "b2b",
        "B2B: maatwerk voor dealers",
        "Mogen dealers hoezen op maat bestellen, of alleen de vaste hoezen uit de catalogus? En moet "
        "een maathoes eerst door ons goedgekeurd worden?",
        [
            "Alleen de catalogus",
            "Ook maatwerk, eerst door ons goedgekeurd",
            "Ook maatwerk, direct in productie",
        ],
        "Vraag 72.",
    ),
    _q(
        "72-production",
        "b2b",
        "B2B: wanneer in productie?",
        "Een bestelling op rekening gaat nu direct in productie (zoals een betaalde "
        "consumentenbestelling). Of pas nadat een collega hem bevestigt?",
        ["Direct (zoals nu)", "Pas na bevestiging door een collega"],
        "Vraag 72.",
    ),
    _q(
        "72-vat",
        "b2b",
        "B2B: btw verlegd en VIES",
        "Welke bedrijven krijgen btw verlegd (buitenlandse bedrijven in de EU)? Moeten we de "
        "btw-nummers automatisch controleren in VIES?",
        [
            "EU-bedrijven buiten NL: verlegd, automatisch controleren in VIES",
            "Verlegd, maar ik controleer zelf",
            "Anders (zie opmerking)",
        ],
        "Vraag 72.",
    ),
    _q(
        "72-address",
        "b2b",
        "B2B: welk adres?",
        "Blijft de B2B-shop op /b2b van het shopdomein (nu), of krijgt hij een eigen domein (zoals "
        "trade.s2dio.living)?",
        ["/b2b op het shopdomein (zoals nu)", "Een eigen domein (zie opmerking)"],
        "Vraag 72.",
    ),
    _q(
        "72-online",
        "b2b",
        "B2B: online betalen?",
        "Willen dealers later ook online betalen (Mollie), of altijd op rekening?",
        ["Altijd op rekening", "Later ook online (Mollie)"],
        "Vraag 72.",
    ),
    _q(
        "72-prices",
        "b2b",
        "B2B: prijzen voor dealers",
        "De B2B-opslag is 45 %. Eén prijslijst voor alle dealers, of vaste prijzen per dealer (beide "
        "kan nu)? Vaste prijzen voor Sunsit?",
        [
            "Eén lijst voor alle dealers",
            "Vaste prijzen per dealer (zie opmerking)",
            "Andere opslag (zie opmerking)",
        ],
        "Vraag 72 en 70.",
    ),
    # ---- the home page's film (ADR-108)
    _q(
        "film-setting",
        "film",
        "Film op de homepage: welke omgeving?",
        "De film toont de Kota 2-zits onder zijn hoes op een stenen terras tegen een kalkwand, met "
        "laag zonlicht en regen. Past die omgeving bij ons?",
        [
            "Ja, het terras is goed",
            "Liever een tuin met gras",
            "Liever bij een zwembad of het strand",
        ],
        "ADR-108. De film is gemaakt uit onze eigen hoesdata; geen gegenereerde video.",
        source="docs/DECISIONS.md ADR-108",
    ),
    _q(
        "film-real",
        "film",
        "Film: echte opnames uit de werkplaats?",
        "De film is nog niet zo goed als een foto: het weefsel is op afstand niet te zien. Een paar "
        "seconden echte opnames en close-ups van Coverlast zouden het meest helpen. Kunnen we die "
        "maken?",
        [
            "Ja, ik regel opnames in de werkplaats",
            "Alleen close-up foto's van de stof",
            "Nee, zo laten",
        ],
        "ADR-108.",
        source="docs/DECISIONS.md ADR-108",
    ),
    # ---- drawings
    _q(
        "38-step",
        "drawings",
        "3D-bestanden van de tekeningen",
        "De tekeningen zijn in een CAD-programma gemaakt. Zijn de 3D-bestanden (STEP) er nog? Dan "
        "kan elke hoes precies worden overgenomen, ook de gebogen (S24, S44, C26, …).",
        ["Ja, ik stuur ze", "Een deel ervan", "Nee, die zijn er niet meer"],
        "Vraag 38.",
    ),
    _q(
        "64-s45",
        "sizes",
        "S45: welke maat klopt?",
        'De tekening schrijft "[152.4] Length 141.1in circumference". 141,1 inch is 358,4 cm '
        "rondom; met de getekende niervorm is de hoes dan 125,8 cm lang, niet 152,4. De hoes volgt nu "
        "358,4 cm rondom.",
        ["358,4 cm rondom (125,8 cm lang), zoals nu", "152,4 cm lang (dan 434 cm rondom)"],
        "Vraag 64.",
    ),
    _q(
        "45-low-tables",
        "vents",
        "Vents op heel lage tafels",
        "Op heel lage tafels (de Conico small, 25 cm) past geen vent in de zijkant van de hoes. Wat "
        "doen we?",
        ["Geen vent", "Vent in de bovenkant", "Een kleinere vent"],
        "Vraag 45.",
    ),
    # ---- arrangements (ADR-095)
    _q(
        "69-side-slopes",
        "shape",
        "Arrangementen: dak ook naar de zijkant laten aflopen?",
        "Bij een arrangement loopt het dak van elk stuk nu alleen naar voren af. Moet een stuk met "
        "hoge armleuningen ook naar de zijkanten aflopen?",
        ["Nee, alleen naar voren (zoals nu)", "Ja, ook naar de zijkanten"],
        "Vraag 69 (arrange.top_slopes).",
    ),
    # ---- the workshop (still to confirm since M5)
    _q(
        "5-seams",
        "workshop",
        "Naden: naadtoeslag en soort naad",
        "We rekenen 15 mm naadtoeslag op beide stukken van een naad. Klopt dat? En welke naad "
        "gebruiken jullie (dubbel gestikt, overlock en doorgestikt, …)?",
        ["15 mm op beide stukken klopt", "Andere toeslag of naad (zie opmerking)"],
        "Vraag 5 (stitching.*).",
    ),
    _q(
        "6-hem",
        "workshop",
        "De zoom onderaan",
        "We rekenen met een tunnel voor een trekkoord, 50 mm toeslag, de zoom 5 cm boven de grond en "
        "2 uitgangen voor het koord. Klopt dat?",
        ["Klopt", "Elastiek in plaats van koord", "Anders (zie opmerking)"],
        "Vraag 6 (hem.*).",
    ),
    _q(
        "7-vent-hood",
        "workshop",
        "De kap van een vent",
        "De kap over het plastic inzetstuk: we rekenen 80 mm diep, en het gaas binnenin zo groot als "
        "de opening plus de toeslag. Klopt dat?",
        ["Klopt", "Andere maten (zie opmerking)"],
        "Vraag 7 (features.vent_*).",
    ),
    _q(
        "36-logo",
        "workshop",
        "Logo op de vents",
        "Hoe groot is het logo, en waar op de kap? Nu tekent de pen een kader van 12 × 4 cm met "
        "LOGO midden op de voorkant van de kap.",
        ["12 × 4 cm midden op de kap klopt", "Andere maat of plek (zie opmerking)", "Geen logo"],
        "Vraag 36.",
    ),
    _q(
        "49-roll",
        "workshop",
        "Bruikbare rolbreedte",
        "Coverlast is 152 cm breed. Het programma gebruikt 148 cm bruikbaar. Klopt 148, of is het 150 "
        "van de 152?",
        ["148 cm klopt", "150 cm", "Anders (zie opmerking)"],
        "Vraag 49 (roll.usable_width_mm).",
    ),
    _q(
        "50-hem-cord",
        "workshop",
        "Trekkoord: strak of los?",
        "Wordt het koord onderaan strak getrokken als de hoes erop zit (de onderrand onder het meubel "
        "getrokken), of hangt de hoes los?",
        ["Strak getrokken", "Los"],
        "Vraag 50; de drape-simulatie laat het nu los.",
    ),
    _q(
        "57-size-band",
        "sizes",
        "Hoeveel groter mag een bestaande hoes zijn?",
        "Als een klant een hoes uit ons assortiment kiest: hoeveel groter dan het meubel mag die zijn "
        "en toch goed passen (bijvoorbeeld +4 cm lengte en diepte, +3 cm hoogte)? Mag hij ooit "
        "kleiner zijn?",
        ["+4 cm lengte en diepte, +3 cm hoogte, nooit kleiner", "Andere marges (zie opmerking)"],
        "Vraag 57.",
    ),
]
