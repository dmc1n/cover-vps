# Payments: Stripe or Mollie?

The owner: "kunnen we niet beter Stripe gebruiken?" (QUESTIONS 31, 11 Oct 2026), "willen
Stripe gebruiken" (QUESTIONS 30, 12 Oct) and "Stripe" for dealers paying online later
(QUESTIONS 52). ADR-136. Research by Codex on 14 October 2026 from the providers' public
price pages (mollie.com/nl/pricing, stripe.com/nl/pricing); standard rates, a contract can
differ.

## For us, side by side

| | Mollie | Stripe |
|---|---|---|
| iDEAL (iDEAL \| Wero) | € 0.32 | € 0.29 |
| Bancontact (Belgium) | 1.40 % + € 0.25 | € 0.35 |
| EU consumer cards | 1.80 % + € 0.25 | 1.50 % + € 0.25 |
| Klarna NL | 2.99 % + € 0.45 | 2.99 % + € 0.35 |
| in3 / Riverty (Dutch pay later) | yes (3.99 % + € 0.95 / 2.99 % + € 0.35) | not found |
| SEPA direct debit | € 0.35 | € 0.35 |
| Billie (B2B pay later, 30 days) | 3.49 % + € 0.35 | 3.50 % + € 0.30 |
| Invoices with a 14-day term | Mollie invoicing, included | Stripe Invoicing, 0.40 % per paid invoice |
| Bank transfer matched to the invoice | by hand | automatic (a virtual IBAN per customer) |
| VAT reverse charge on invoices | VAT modes on the invoice | Stripe Tax (0.50 %), handles reverse charge |
| AI agents paying (ACP, with OpenAI) | says it is compatible, not yet verified for NL | built it; Shared Payment Tokens |
| Odoo | official modules (Odoo 19) | Odoo's own connector |
| Support in Dutch | yes | Dutch checkout and help pages; Dutch-speaking staff not guaranteed |
| Payout | next business day for iDEAL | first payout 7–14 days, then about 3 business days |

Examples: a € 450 cover by iDEAL costs € 0.32 (Mollie) or € 0.29 (Stripe); a € 450 cover by
Bancontact € 6.55 or € 0.35; by a Dutch credit card € 8.35 or € 7.00.

## Advice

**Stripe, for the consumer shop and later for dealers, with the Mollie code kept behind the
same small interface.**

- Nothing is live with Mollie yet (no key on the live studio, QUESTIONS 30), so choosing Stripe
  now costs no migration: only the integration.
- Per payment Stripe is the same or cheaper for everything we expect (iDEAL, cards, and much
  cheaper for Belgium's Bancontact).
- The things the owner wants next are Stripe's strengths: invoices with automatic matching of
  bank transfers for dealers on account, reverse charge handled by Stripe Tax, and agent
  payments (ACP) when the website for AI agents takes orders.
- What we give up: in3 and Riverty (Dutch pay-later; Klarna is on both), Mollie's free
  invoicing, a next-day payout and Dutch-speaking support. If in3 turns out to matter for
  consumers, Mollie can return as a second provider behind the same interface.
- For dealers, Odoo stays the invoice system (its own invoices, 14 days, QUESTIONS 44); Stripe
  collects the money. Stripe Invoicing only if its transfer matching saves real work.

## Build (several days, starts when the owner has a Stripe account)

1. A provider interface in the shop: `create_checkout(order) -> url`, `payment(order) ->
   status`, a webhook per provider. Mollie's current code becomes one provider, unchanged
   for old orders.
2. Stripe Checkout Sessions (hosted page: iDEAL, Bancontact, cards, Klarna, Apple/Google Pay):
   the amount in cents from the server, the order id in the metadata, an idempotency key per
   order (the checkout already carries one, ADR-129).
3. The webhook `/api/shop/stripe/webhook`: the raw body checked against `Stripe-Signature`
   with the endpoint secret; `checkout.session.completed`, `…async_payment_succeeded/failed`,
   `…expired`; amount, currency, order and mode checked; an order marked paid once (then it
   waits for "Send to production", ADR-128).
4. Shop settings → payment: provider `stripe | mollie | none`, test/live from the key's
   prefix as today (`sk_test_` / `sk_live_`), never the key itself on the page.
5. B2B online payment (`b2b.online_payment`): one Checkout Session for the whole B2B order.
6. Tests with Stripe's signed test events; a real test payment in test mode before live.

## For the owner

- Open a Stripe account for the company (KvK, the directors' ID, the bank account, the website
  shop.s2dio.living), switch on iDEAL, Bancontact, cards, Klarna.
- Put the keys in deploy/.env: `STRIPE_SECRET_KEY` (first `sk_test_…`, later `sk_live_…`) and,
  after we create the webhook, `STRIPE_WEBHOOK_SECRET`. Never in a mail or the repository.
- Decide whether bank transfer stays as a fallback (QUESTIONS 31 asked; the answer was the
  Stripe question): Stripe's bank transfer costs 0.5 % (max € 5), or keep our own IBAN
  transfer by hand as now.
