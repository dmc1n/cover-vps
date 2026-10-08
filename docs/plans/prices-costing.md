# Plan: prices and costing, later linked to Odoo

The owner, 7–8 October 2026: "an admin page where I easily fill in prices and make costings;
later it must link to our Odoo in Indonesia." His answers:

1. **Currency:** a fixed exchange rate, entered by hand. Production costs are in rupiah (IDR),
   sales in euros (EUR). Every IDR cost is converted with the stored rate, and both are shown.
2. **Two channels, two shops:** consumers (B2C webshop) and business (B2B: Sunsit, dealers).
   Each has its own price list: markup or margin, rounding, VAT shown or not, an optional fixed
   price per product. The pricing for both is built now; the B2B storefront is not.
3. **Extra costs** (shipping, import duties, packaging) are separate lines next to the cost
   price, never folded into it; per channel, and shown in the costing.
4. **All admins** may edit prices.

Later (8 Oct): their Odoo is their own installation, and he can give full access (an API user).

## Step 1 — the page (built, ADR-098)

Admin → **Prices & costing** (and `#/prices` for editors, read only):

| Part | What |
|---|---|
| Materials | fabrics (code, name/quality, colours, price per metre in EUR or IDR, roll width, waste %); components (vent set, cord per m, elastic per m, balloon, frame, and any added one) with purchase price, currency and what it is counted per |
| Labour | hourly rate in EUR or IDR; operations with minutes, each counted per cover, piece, metre of seam, metre of hem, vent, ... (cutting setup, per piece, stitching, vent, hem, packing) |
| Exchange rate | rupiah per euro, a date and a note; the "indicative" switch |
| Channels | per channel (B2C, B2B): shipping, duties (% of cost + shipping, or fixed), packaging; markup or margin, on cost + extra costs ("landed") or on cost only; rounding (.95, .99, whole euros, 5, 10, none); VAT % and whether prices are shown with VAT; fixed prices per product (a model id, balloon, frame) |
| Costing | any calculated cover (catalogue, drawing, arrangement, order) or a configurator product with its sizes: fabric metres from the cut plan (`finished.json`, the nesting estimate) plus waste, components, labour minutes per operation = cost price; then per channel the extra costs, the landed cost, the price ex and incl. VAT, the margin, and balloons/frame sold with it. Every line in EUR and IDR. CSV and PDF |
| Versions | every published version with who, when and a note; roll back to any (a rollback is a new version, so the history only grows) |

**Draft → preview → publish.** Changing numbers makes a draft; *Preview changes* lists every
price that moves (covers, the configurator's products at default sizes, balloon, frame), before
→ after; *Publish* stores a new version and writes the audit log. Admins edit; editors see the
prices and costings; viewers nothing.

**Storage:** app.db, table `price_sets` (version, created, username, note, data JSON,
from_version) and the setting `prices_draft`. `config/defaults.yaml` (`quote.*`) keeps the
documented defaults: until the first publish the price set is those defaults with the old Shop
settings prices on top, so the shop does not change until the owner publishes. The shop, the
configurator, the public API and the rain check's upsell read the published set; "indicative"
goes only when the owner publishes a set with it switched off.

Code: `engine/coverengine/costing.py` (the maths, the facts of a cover), `apps/api/coverapi/
prices.py` (API, versions), `apps/api/coverapi/odoo.py` (the Odoo seam), `apps/web/src/
Prices.tsx`; tests `engine/tests/test_costing.py`, `apps/api/tests/test_prices.py`, browser
check `apps/web/e2e/prices.py`.

## The data model, shaped like Odoo

| Cover Studio | Odoo (17) | Notes |
|---|---|---|
| `exchange.idr_per_eur`, `date` | `res.currency.rate` (currency IDR, name = date, rate) | if the company currency is IDR, Odoo stores EUR at 1 / rate |
| a fabric | `product.template` (type storable, uom m) + `product.supplierinfo` (price, currency) | roll width, waste, colours as custom fields (x_) or product attributes for colours |
| a component | `product.template` + `product.supplierinfo` | balloon and frame are also sale_ok (sold next to the cover) |
| a cover (model id) | `product.template` (default_code = model id, route Manufacture) | `standard_price` = our cost price |
| a cover's lines: fabric m, components | `mrp.bom` + `mrp.bom.line` (product, qty, uom) | quantities from the cut pieces (`finished.json`) |
| labour rate | `mrp.workcenter.costs_hour` | one workcenter "Cover workshop" now; cutting and sewing can split later |
| operations with minutes | `mrp.routing.workcenter` on the BoM (`time_cycle_manual`) | per cover, from the per-piece / per-metre minutes |
| a channel's price list | `product.pricelist` + `product.pricelist.item` | global formula on standard_price: `price_markup` (Odoo 17) or `price_discount = -pct`; rounding as `price_round` + `price_surcharge` (.95 = round 1, surcharge -0.05); fixed prices as product items |
| extra costs (shipping, duties, packaging) | `stock.landed.cost` on receipts (if they use Inventory valuation) or kept in our price list | the owner keeps them separate; Odoo folds landed costs into the stock value |
| VAT shown or not | `account.tax` with `price_include` on the B2C list | per country later |
| the margin method | no Odoo rule | price = cost / (1 − margin): we push the computed fixed prices, or use markup = margin / (1 − margin) |

`odoo.records(price_set, covers)` already returns these records with external ids
(`cover_studio.<code>`), so step 2 can create or update the same record each time. Admins can
see them at `GET /api/prices/odoo?model=<id>`.

## Step 2 — the link to Odoo (not built)

Odoo's external API (XML-RPC or JSON-RPC) against their own server: log in with
`/xmlrpc/2/common` `authenticate`, then `/xmlrpc/2/object` `execute_kw` for `search_read`,
`create` and `write`. Everything in `coverapi/odoo.py` (`push()` is the stub); credentials in
`deploy/.env` only.

1. Read first: products, BoMs, price lists and the IDR rate as they are in Odoo; show the
   differences on the Prices page (nothing written).
2. Then choose per field who is the source: purchase prices and rate probably from Odoo
   (Indonesia buys), the BoM per cover and the price lists from Cover Studio.
3. Push on publish (and a "sync now" button), with a log of every call; never delete in Odoo.

**What we need from them:**

- the URL of their Odoo, and the database name;
- an API user with an API key (Settings → Users → API keys), with rights on Sales, Purchase,
  Inventory, Manufacturing and Accounting (read first, write later);
- the Odoo version number (16, 17, 18, ...) and whether it is Community or Enterprise;
- which apps are installed: Sales, Purchase, MRP (Manufacturing), Inventory, Accounting,
  multi-currency on; and the company currency (IDR?);
- how they name products now (internal references), so covers and fabrics match existing
  records instead of making doubles;
- whether a test database (a copy) exists to try against first.

## Better later

- Prices per colour or fabric quality chosen in the configurator (the costing already picks the
  fabric that offers a colour).
- Separate workcenters (cutting, sewing) with their own rates.
- Shipping per country and per size of box; duties per HS code and country of destination.
- The B2B storefront itself, reading the B2B price list.
