# Plan: customers design their own cover in the webshop (configurator and API)

The owner, 4 October 2026: "prepare for customers who want to make their own cover through a
webshop, by an API or a 3D interface in an iframe. People give the rough sizes of their set
(the table and the chairs), and with the data we have we make a proposal: all options, the
volumes, the cost price. A first version, where customers fill in their data and we make a
cover proposal from it."

## What the customer does

1. Opens the configurator: on our site, or in an iframe in the webshop (hello-suns.com or
   another).
2. Chooses what to cover:
   - **dining set:** table and chairs;
   - **round dining set;**
   - **sofa;**
   - **corner sofa (L);**
   - **sun lounger;**
   - **loose item** (a box: a chair, a side table, a hocker).
3. Gives the rough sizes in cm: for example the table's length, width and height and the
   number of chairs; or the sofa's length, depth and back and seat height.
4. Chooses options:
   - colour;
   - air vents (on by default, by the company rule);
   - drawcord;
   - balloons for a table;
   - room for the chairs.
5. Sees at once:
   - the cover in 3D (turnable);
   - the pieces with their sizes;
   - how much fabric (m² and metres of roll);
   - the price.

   It may also say "looks like SUNS Kota 2-seater: tested cover available".
6. Can send it as a request (name, e-mail, a note). We get it by mail and on the admin page,
   with all the data, to make the definitive pattern with the full program.

## How (first version)

- **The proposal in under a second**, from the shapes we already build from the owner's
  drawings (`coverengine/drawn.py`: box, sloped box, L shape, round) and the company rules:
  - chair space;
  - balloons for tables;
  - vents per metre of side;
  - drawcord;
  - pieces split by the 1.48 m roll.

  Every piece of these shapes is flat, so its size and area are exact without the slow steps.
  The definitive pattern is made after the order, through the normal route (hull, cut,
  flatten, export, drape).
- **The price** comes from a cost model in `config/defaults.yaml` (`quote.*`, all to confirm by
  the owner):
  - fabric per metre of roll, and cutting waste;
  - sewing per metre of seam;
  - vents, cord and balloons per piece;
  - handling per cover;
  - margin, and VAT.

  The cost price and the selling price are both shown on our side; to the customer, only the
  selling price.
- **Learning from what we have.** The proposal is compared with the SUNS catalogue: the
  nearest model by category and size, and its tested cover and drape result, if one is near
  enough. The default proportions (back strip, front height) come from the owner's 115
  drawings.
- **The public API** (`/api/public/v1/…`), separate from the internal app:
  - `GET options`: the products, their fields with units and ranges, and the options;
  - `POST quote`: the sizes and options in, the proposal out (pieces, fabric, price, a
    preview id, near SUNS models);
  - `GET preview/<id>.glb`: the 3D model for the webshop's own viewer;
  - `POST request`: the customer's request, with contact data.

  A webshop calls it with an API key (`X-Api-Key`, made on the admin page). The configurator on
  our own site calls it without a key, limited per address. Nothing internal (models,
  patterns, users) can be reached through it.
- **The configurator page** `#/configure`: no login, no header, made for an iframe; the
  colours of the house style. Embedding is allowed only from the origins set on the admin page
  (`frame-ancestors`); the rest of the app stays closed to framing.
- **Requests** go to `app.db` (table `requests`), the admin page (a tab **Requests**) and a mail
  to the owner.

## For the owner (QUESTIONS 52–56)

- **The prices** (cost model): the fabric's purchase price per metre, sewing time and rate,
  vents, cord, balloons, margin. Until then they are clearly marked placeholders.
- **The webshop:** which one (Shopify, WooCommerce, …) and its address, for the iframe and the
  API key.
- **Colours** to offer (the Coverlast colours).
- **Who gets the requests** (rick@ or a sales address).
- **Should the customer see the pieces**, or only the 3D view and the price?
