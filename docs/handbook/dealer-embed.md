# Dealer embed: our configurator on a dealer's website (ADR-150)

A dealer (a B2B customer) can show our configurator on its own website, in its own look and at
its own prices. **Preview only** until the owner's go: it works on `preview.s2dio.living` and for
colleagues logged in to the studio; the live shop answers 404.

## Setting up a dealer site

1. The dealer must be an active B2B customer (Shop → B2B customers).
2. Shop → **Dealer embeds** → choose the dealer, give the site a name → **New dealer site**.
3. Fill in, then **Save**:
   - **Domains**: the dealer's website addresses, one per line, `https://www.dealer.nl`. The
     configurator works only there.
   - **Look**: colours, corners, fonts (`inherit` = the font of the dealer's page), logo
     (an https address), layout (full or compact), 3D on or off. The preview on the right
     changes as you type.
   - **Languages and texts**: the default language and which of nl/en/de/fr; the dealer's own
     title, intro, button and thank-you text per language (empty = ours).
   - **Range**: which kinds of furniture and which fabric colours (none ticked = all).
   - **Prices**: our B2B price for this dealer plus its margin (one margin, or one per kind),
     or a price list from Settings → Prices (never the dealer's own purchase list); rounding;
     incl. or ex VAT. The example line shows what the dealer buys at and what its customer sees.
     Only we see the purchase price.
   - **Ordering**: our checkout in the dealer's look (we invoice the customer, Mollie), or the
     order goes to the dealer (the dealer confirms it with one click in its mail; then it is a B2B
     order on account), or the dealer's own cart (a browser event; for dealers with a developer).
4. Copy the **Snippet** to the dealer: the script tag (recommended) or the frame (Wix,
   Squarespace and other builders that refuse scripts).
5. For a dealer with its own shop software: **Make a secret key**. It is shown once. Its server
   uses it to check a price: `GET /api/embed/v1/verify/<quote id>` with
   `Authorization: Bearer dsk_…`.

## What the dealer can do itself

On its own page, without us:

```html
<s2dio-configurator dealer="dpk_…" lang="de" layout="compact" view3d="off"
                    kinds="sofa,lounger"></s2dio-configurator>
<style>
  s2dio-configurator { --s2dio-primary: #8a2be2; --s2dio-radius: 4px; }
  s2dio-configurator::part(button) { text-transform: uppercase; }
</style>
<script>
  document.addEventListener("s2dio:priced", (e) => console.log(e.detail));
</script>
```

Events: `s2dio:ready`, `s2dio:priced`, `s2dio:added-to-cart`, `s2dio:checkout-started`,
`s2dio:order-sent`, `s2dio:error`. In the frame the same arrive as `postMessage`
(`{source: "s2dio-configurator", type, detail}`).

## Orders

- **Our checkout**: the order is under Shop → Orders like any shop order; its data names the
  dealer site, the purchase price and the dealer's margin. Send to production as always.
- **Sent to the dealer**: listed on the dealer site's card; once the dealer confirms, a B2B order
  on account (PO `WEB-D<n>`) appears under Shop → Orders, waiting for Send to production.

## The demo

`https://preview.s2dio.living/embed-demo`: two made-up dealers (Tuinhuis Voorbeeld, Dutch,
compact, sent to the dealer; Maison Exemple, French, dark, 3D, our checkout) and the frame. The
demo dealers never make an order.

## Switching it on for live (after the owner's go)

The shop setting `dealer_embed_enabled` in the studio, and `DEALER_EMBED = "1"` in
`apps/site/wrangler.toml` with a Worker deploy. Both are needed.
