# Prices and costing

Since ADR-126 (12 Oct 2026) prices live in two places, nowhere else:

- **What is the same for every cover** is in **Settings → Prices & costs** (`#/settings/<tab>`):
  **Costs** (materials, labour and the exchange rate on one page), **Price rules** (per channel
  the extra costs, markup or margin, rounding, VAT; the balloon's and the frame's fixed prices;
  a configurator product's costing) and **Publish & versions** (the draft, preview, publish,
  the versions with roll back, and the Excel import).
- **What belongs to one cover** is on **that cover's page, tab Price & shop**
  (`#/model/<id>/price`): its cost line by line (EUR and IDR, CSV, PDF), its B2C and B2B price,
  margin and where each comes from (a fixed price or the rule), its fixed price (admins change
  it there, in the draft), whether the shop offers it as an existing cover, its direct-order
  price and delivery promise, the B2B companies with a price of their own for it, and its
  orders, quotes and match requests.
- **All covers' prices side by side:** Covers → All covers, *Prices: live* or *Prices: draft* in
  the filter row (`#/covers/all?prices=live`): cost, B2C, B2B, margin and source per cover; a
  price opens the cover's Price & shop tab. Sort by B2C price or by margin.

Admins change and publish; colleagues with the editor role see the same, to look only (Settings
shows them only these three tabs); viewers see no prices. The old `#/prices/...` addresses lead
to the new places. Moving between the three tabs keeps what you typed; leaving them with unsaved
numbers asks first.

## How a price is made

1. **Cost price** = fabric + components + labour (*Costs*), counted for each cover from its own
   cut pieces: metres in its cut plan, its pieces, seams, hem and vents.
2. **Landed cost** = cost price + shipping + import duties + packaging (*Price rules*).
3. **Price ex VAT** = landed cost × the channel's markup (or ÷ its margin).
4. **Shown price** = + VAT for consumers, rounded up (.95, whole euros, ...). A fixed price wins,
   without rounding.

## What the page tells you

- **Every tab starts with a short intro**: what it is for, what to fill in and in which order,
  and where the numbers go.
- **Every field has its unit and a help line** under it: what it means in the workshop, what
  it is used for and a realistic example.
- **"placeholder — please confirm"** marks every number that is still our assumption (a value
  marked "to confirm" in `config/defaults.yaml`). The counter at the top says how many are
  left ("21 of 24 values are still placeholders"). Type the real number, or tap **keep this
  value** when the assumption is right; both count once you publish.
- **Live examples** beside the settings cost one real cover with the numbers as you type them,
  before saving: the fabric line under the fabric, the components and minutes per row, the
  labour total ("takes 160 min = € 113.50"), a rupiah converter at the exchange rate, and under
  each channel the whole worked example from cost price to shown price, with the margin and
  the live price now. The example is a typical catalogue 2-seater; pick any other cover in the
  example's list (the page remembers it).
- **Terms explained** (tap to open, no hovering needed): landed cost, markup vs margin,
  "on cost + extra costs" vs "on cost only", rounding, VAT shown incl. or ex, fixed prices.

## The tabs

- **Costs:** *Materials*: fabrics (price per metre of roll in EUR or IDR, waste %, roll width,
  colours) and components (vent set, cord per metre, elastic, balloon, frame, or your own), each
  with what it is counted per. *Labour*: the hourly rate (EUR or IDR) and the minutes per
  operation: cutting setup, per piece, per metre of seam, per vent, per metre of hem, packing.
  Time one real cover and adjust the minutes until the live example matches. *Exchange rate*:
  rupiah per euro, with a date and a note; here you also switch off **indicative** once the real
  prices are in.
- **Price rules:** per channel (B2C consumers, B2B Sunsit and dealers) the extra costs
  (shipping, duties as % of cost + shipping or a fixed amount, packaging) and the rule: markup
  or margin and on what, rounding, VAT and whether prices are shown incl. VAT. Fixed prices of
  the balloon and the frame (and, folded, of products that have no calculated cover). Below: a
  configurator product's costing at the sizes you give (live, saved draft, or this page).
- **Publish & versions:** the draft bar (Save draft, Preview changes, Publish, Discard draft),
  every published version with who, when and the note, roll back, and **Import a price list
  (Excel)** (below).

## A cover's Price & shop tab

- **Prices**: per channel the live price (B2C incl. VAT, B2B ex VAT, the other one small
  under it), *fixed price* or *calculated* (with the rule), the margin, and, when there is a
  draft, its price in the draft. An admin types a fixed price and clicks **Save in draft**, or
  **Remove** (the calculated price applies again). It goes into the same draft as everything
  else, never live by itself.
- **The draft bar** on top says how many changes the draft holds (also those from elsewhere)
  and how many are this cover's. **Preview** counts the prices that would move; **Publish (N
  prices move)** asks once more and publishes the whole draft. Or publish later from Settings
  → Publish & versions.
- **Cost**: the costing line by line, with the channels' extra costs, price and margin; *live*
  or *draft*; CSV and PDF.
- **Shop**: offered as an existing cover or why not (Desk status, kind unknown, no cover), its
  kind and sizes, its rows in the price list (code, section, item, what it suits), how its
  direct-order price is made (its fixed B2C price, or the configurator's minus the stock
  discount) and the delivery promise.
- **B2B** (admins): companies with their own price for it (set on the company, Shop → B2B
  customers).
- **Orders, quotes and requests** (admins): its orders (consumer and B2B), recent quotes, and
  the match requests that proposed or chose it, with links.

## Markup and margin

Markup is a % on top of the base: price = base × (1 + markup). Margin is the share of the
price you keep: price = base ÷ (1 − margin). The same price both ways: markup 87.5 % = margin
46.7 % (0.875 ÷ 1.875); margin 40 % = markup 66.7 % (0.40 ÷ 0.60).

## Changing a price

1. Change the numbers on Costs or Price rules (the page says "unsaved changes"; the live
   examples follow at once), or a cover's fixed price on its Price & shop tab.
2. **Preview changes**: a list of every price that moves, before → after.
3. Write briefly what changed and click **Publish**. Only then does the shop use it.
   **Save draft** keeps your numbers without publishing; **Discard draft** throws them away.
4. **Publish & versions → Roll back to this** makes an older version live again; that too is stored as
   a new version, so nothing is lost.

A wrong number (a negative price, a margin of 100 %)? The page says what is wrong and does not
publish. Only admins can change prices; every publish is in the audit log (Settings → System
& logs). Someone changed the draft after your page loaded it (a price on a cover, an import)?
Then *Save draft* and *Publish* refuse and the page offers to load the newer draft, so nobody
overwrites or publishes what he has not seen.

## Prijslijst uit Excel importeren (vaste prijzen)

Heb je een prijslijst in Excel, bijvoorbeeld consumentenprijzen incl. BTW? Dan zet de studio
die in één keer als **vaste prijzen** voor onze hoezen (ADR-113). Alleen admins.

1. Ga naar **Settings → Publish & versions** (sinds ADR-126; was Prices → Import). Onderaan
   staat **Import prices (Excel)**. Kies de prijslijst (**B2C** = webshop, standaard; of **B2B**) en
   klik **Upload price list (Excel)**. Een .xlsx, een .csv of een .zip met zulke bestanden.
2. **Kijk wat er gevonden is.** De studio zoekt zelf de prijskolom (bedragen als
   "€ 1.234,95", "459,-" of gewone getallen; een kop met prijs / verkoop / incl helpt) en de
   kolommen die zeggen welke hoes het is: de code (S40, C23), het nummer van de tekening
   ("Cover 66") of de naam (SUNS-modellen, de productnamen uit de productlijst). Klopt de
   keuze niet, kies dan zelf een andere prijskolom of vink kolommen aan of uit. Staan je
   prijzen **ex BTW**, zet dan "The sheet's prices are" op *ex VAT* (standaard: incl. BTW;
   een kop met "excl" zet het vanzelf op ex).
   - **exact** (groen): gevonden op code, tekeningnummer of eigen naam.
   - **probable** (oranje): een SUNS-model waarvan familie en soort kloppen ("Kota
     3-seater"), of een SUNS-model dat de productlijst aan die tekening koppelt. Even
     nakijken; een vinkje uit = niet meenemen. Links en rechts worden nooit verwisseld.
   - **One cover, two prices**: twee regels geven één hoes een verschillende prijs. Kies welke
     regel telt, of laat de hoes weg.
   - **Not matched or not sure**: regels zonder hoes ("which cover?" of "not found"). Kies de
     hoes zelf (typ een code, naam of id) of laat de regel weg.
   - Per regel zie je de prijs uit Excel, wat we opslaan, de prijs incl. BTW die de klant
     ziet, en de prijs van nu.
3. Klik **Put N prices in the draft**. De prijzen gaan in het **concept**, niet live. Daarna
   zoals altijd: **Preview changes** (welke prijzen veranderen) en **Publish**. De notitie
   "Imported from <bestand> (N prices, B2C)" staat al klaar voor de geschiedenis.

Goed om te weten:

- **Geen afronding**: een vaste prijs is precies de prijs uit de lijst. B2B toont prijzen ex
  BTW; een prijs incl. BTW wordt daar ex BTW opgeslagen (÷ 1,21, met zes decimalen), zodat de
  prijs incl. BTW tot op de cent gelijk blijft aan die in je Excel.
- De webshop verkoopt een bestaande hoes (een SUNS-model) voor zijn vaste B2C-prijs; de
  korting voor bestaande hoezen geldt dan niet, de vaste prijs is de prijs.
- Producten uit de configurator (bank, eethoek op maat) krijgen geen vaste prijs: hun prijs
  hangt van de maten af.
- Elke geüploade lijst blijft bewaard in de datamap (`prices/imports/`).
- Voor Claude: `uv run python scripts/prices_import.py LIJST.xlsx [--channel b2c]
  [--incl-vat | --ex-vat] [--json uit.json]` toont hetzelfde overzicht; pas met `--apply`
  komen de prijzen in het concept.

Later we link this to Odoo (docs/plans/prices-costing.md); until then this is the place.
