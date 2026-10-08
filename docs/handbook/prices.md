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

Later we link this to Odoo (docs/plans/prices-costing.md); until then this is the place.
