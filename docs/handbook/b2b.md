# The B2B shop: business customers with a login

Business customers (Sunsit, dealers, garden centres) order at **/b2b** on the website
(shop.s2dio.living/b2b; on the studio: covers.suns.nu/shop/b2b/). They see the same
configurator and the covers of our range as consumers, but at **their own prices, ex VAT**,
with **quantities**, their **order reference (PO number)**, their **delivery addresses**, their
**previous orders** ("order again"), and they order **on account**: an invoice, no online
payment. Decision: ADR-104.

## A new business customer

1. Admin → **B2B customers** → *Invite a company*: company, VAT number, contact, the e-mail
   address that logs in, the invoice address, the price list (Business by default) and the
   language of the mails. *Invite*.
2. The contact gets a mail with a link (valid 7 days) to choose a password (at least 12
   characters). Without a mail server the link is shown on the page: send it yourself.
3. Once the password is set, the company is **active**.

A company can also **ask** for an account (*Request an account* on the login page). The request
appears at the top of *B2B customers* and the alert address gets a mail: *Approve and invite*
(the asker gets the invitation) or *Reject*.

## Per company

Click a company in the list:

- **Price list:** the channel of *Prices & costing* it buys at (Business by default).
- **Fixed prices:** one per line, ex VAT: `suns-2-seater-kota = 289`, `balloon = 12`,
  `frame = 55`. They win over the price list. (A fixed price in the price list itself, on the
  Prices page, holds for every company on that list.)
- **VAT reverse-charged:** no VAT on its orders (an EU company outside NL with a valid VAT
  number; check with the accountant).
- **Block (logs everyone out):** nobody of that company can log in or reset a password;
  *Unblock* opens it again.
- **People who log in:** add someone (they get an invitation), send a new password link,
  switch a person off.
- **Delivery addresses:** the company manages them itself in the shop; you see them here.
- **Orders:** its B2B orders, with every line's status.

## Orders

Every line of a B2B order appears under Admin → **Orders** with a green **B2B n · PO …** mark,
its quantity and its price ex VAT, status *on_account*. It goes into production at once, the
same way as a paid consumer order (a made-to-measure cover becomes `order-<n>`, a catalogue
cover is cut from its own pattern). The buyer, the company's e-mail and the alert address get a
confirmation. The customer sees each line's status under *Previous orders*.

## B2B settings (bottom of the tab)

- **Minimum order** ex VAT (0: none).
- **Shipping per order on top** ex VAT (0: shipping is in the price list's extra costs).
- **Payment term** in days (in the confirmation).
- **Into production at once** (on).
- **Online payment:** later; every order is on account now.

## Safety

B2B logins are not studio users: a business customer can never open Cover Studio, and a
colleague's studio login does not open the B2B shop. Passwords are stored as hashes; 5 wrong
passwords lock that person for 15 minutes (10 from one address lock that address). A forgotten
password: *Forgot your password?* on the login page mails a link valid for 2 hours. Every
login, failure, order and change is in Admin → **Audit log** as `b2b:<e-mail>`.

## Languages

The B2B words are part of the site's content (`ui.b2b`), in Dutch, English, German and French;
the Website (AI) tab edits and translates them like the rest.

## Checking it in a browser

`apps/web/e2e/b2b.py` (usage in its docstring) runs the whole story against a scratch studio
and saves the screens in out/b2btest/.
