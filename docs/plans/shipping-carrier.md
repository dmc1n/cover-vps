# Delivery cost by carrier (DHL), with fixed amounts as the fallback

The owner, 11 October 2026 (QUESTIONS 28 and 29): "we make a link with the carrier, such as DHL,
so that the shipping cost is known at once from the weight and the box." ADR-136.

## What is built (this branch)

- `apps/api/coverapi/shipping.py`: a carrier interface (`Carrier.configured()`,
  `Carrier.rate(parcel, country, postcode)`) and `quote()`, which takes the carrier's rate when
  it is set up and answers, else the country's fixed amount from Shop settings → shipping (as
  today). A carrier that fails or times out never stops an order.
- The parcel comes from the cover: cut fabric m² (in every quote) × `shipping.fabric_g_per_m2`
  plus `shipping.pack_g`; the box is the first of `shipping.boxes_cm` whose volume holds the
  folded cover (`shipping.folded_l_per_m2`). All four are "to confirm" in config/defaults.yaml.
- `shipping.carrier: fixed` (default) or `dhl`. `DhlCarrier` is a placeholder until the
  account exists: without `DHL_API_USER_ID` and `DHL_API_KEY` in deploy/.env it gives no rate,
  so every order uses the fixed amounts.
- The order endpoint asks `shipping.quote()`; the order keeps `shipping_eur` and where it came
  from (`shipping_source`).

## For the owner

1. **A DHL business account** (DHL Parcel NL, "My DHL Parcel"; or DHL eCommerce for DE/BE) with
   API access: a user id and an API key. Put them in deploy/.env as `DHL_API_USER_ID` and
   `DHL_API_KEY` (never in the repository). Ask DHL for the contract's rates per weight class
   and the countries.
2. **The fixed amounts per country** in Shop settings → shipping (incl. VAT): they are the
   fallback and today the only price. Empty means € 0, so fill NL, BE, DE now.
3. **The workshop's boxes** (`shipping.boxes_cm`), the fabric's weight per m² and what a folded
   m² takes in a box: weigh and measure two or three packed covers.
4. **Shipping inside the price:** the price set still has a cost line `quote.b2c_shipping_eur`
   (€ 18.50 a cover). Once delivery is charged on its own, set that line to 0 in Settings →
   Prices & costs and publish, or the customer pays twice. Until then both stay (the line is
   the owner's choice of what the price contains).

## Next (once the account exists, about a day)

- Fill in `DhlCarrier.rate()`: authenticate (`POST /authenticate/api-key` with user id and key,
  a short-lived token), ask the capabilities/rates for the parcel (weight, box L×W×H,
  sender postcode, receiver country and postcode), take the cheapest parcel product with
  home delivery, add VAT if the answer is ex VAT. Cache a rate per (country, weight class,
  box) for a day so the configurator's price shows quickly.
- Show the delivery cost in the configurator as soon as the country is chosen (it is now shown
  at the checkout).
- Labels: the same account can create the shipping label when an order is sent to production
  (a button on the order; the track-and-trace link in the customer's mail). Separate step.
- A cover too large for the largest box: today the largest box is used; the workshop should
  say whether it then packs two parcels (double the rate) or uses a roll.
- B2B: dealers keep `b2b.shipping_eur` per order (0 now) until the owner wants carrier rates
  there too (pallets are a different product).
