# Prices and costing

Admin → **Prices & costing** (colleagues with the editor role: **Prices** in the top bar, to
look only). Every price the shop, the configurator and each costing use is set here (ADR-098).

## How a price is made

The strip at the top of the page shows it in four steps:

1. **Cost price** = fabric + components (*Materials*) + labour (*Labour*), counted for each
   cover from its own cut pieces: metres in its cut plan, its pieces, seams, hem and vents.
2. **Landed cost** = cost price + shipping + import duties + packaging (*Channels*).
3. **Price ex VAT** = landed cost × the channel's markup (or ÷ its margin).
4. **Shown price** = + VAT for consumers, rounded up (.95, whole euros, ...).

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

- **Materials:** fabrics (price per metre of roll in EUR or IDR, waste %, roll width, colours)
  and components (vent set, cord per metre, elastic, balloon, frame, or your own), each with
  what it is counted per.
- **Labour:** the hourly rate (EUR or IDR) and the minutes per operation: cutting setup, per
  piece, per metre of seam, per vent, per metre of hem, packing. Time one real cover and adjust
  the minutes until the live example matches.
- **Exchange rate:** rupiah per euro, with a date and a note. Every IDR amount is converted with
  it; nothing changes by itself. Here you also switch off **indicative** once the real prices
  are in (the shop then stops saying "indicative").
- **Channels & price lists:** per channel (B2C consumers, B2B Sunsit and dealers) the extra
  costs (shipping, duties as % of cost + shipping or a fixed amount, packaging) and the price
  list: markup or margin and on what, rounding, VAT and whether prices are shown incl. VAT,
  fixed prices per product.
- **Costing:** any cover (catalogue, drawing, arrangement, order) or a configurator product
  with its sizes, line by line, then per channel the extra costs, the price and the margin.
  Prices: **live**, the **saved draft**, or **this page** (your numbers before saving).
  **CSV** for Excel, **PDF** to print.
- **Versions:** every published version, who and when; roll back to an earlier one.

## Markup and margin

Markup is a % on top of the base: price = base × (1 + markup). Margin is the share of the
price you keep: price = base ÷ (1 − margin). The same price both ways: markup 87.5 % = margin
46.7 % (0.875 ÷ 1.875); margin 40 % = markup 66.7 % (0.40 ÷ 0.60).

## Changing a price

1. Change the numbers (the page says "unsaved changes"; the live examples follow at once).
2. **Preview changes**: a list of every price that moves, before → after.
3. Write briefly what changed and click **Publish**. Only then does the shop use it.
   **Save draft** keeps your numbers without publishing; **Discard draft** throws them away.
4. **Versions → Roll back to this** makes an older version live again; that too is stored as
   a new version, so nothing is lost.

A wrong number (a negative price, a margin of 100 %)? The page says what is wrong and does not
publish. Only admins can change prices; every publish is in the audit log.

## Prijslijst uit Excel importeren (vaste prijzen)

Heb je een prijslijst in Excel, bijvoorbeeld consumentenprijzen incl. BTW? Dan zet de studio
die in één keer als **vaste prijzen** voor onze hoezen (ADR-113). Alleen admins.

1. Ga naar **Admin → Prices & costing → Channels & price lists**. Bovenaan staat
   **Import prices (Excel)**. Kies de prijslijst (**B2C** = webshop, standaard; of **B2B**) en
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
