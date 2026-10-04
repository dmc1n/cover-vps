# Webshop: the configurator and the API (ADR-061)

Customers design their own cover from rough sizes and get a proposal at once: the cover in 3D,
the pieces, the fabric and a price. A webshop offers this in one of two ways.

## 1. The configurator in an iframe (the simplest)

```html
<iframe src="https://covers.suns.nu/#/configure"
        style="width:100%;height:950px;border:0" title="Design your cover"></iframe>
```

First add the webshop's address on the admin page (Admin → Webshop → *Configurator in the
webshop*), for example `https://hello-suns.com`. Without that the browser refuses to show it.
Customers' requests appear on the same page and are mailed to the address set there.

## 2. The API (for the webshop's own design)

Base `https://covers.suns.nu/api/public/v1`. Every call sends the header
`X-Api-Key: <key>`; an admin makes keys on the admin page (shown once). The limit is 30 calls
a minute per address.

| Call | What |
|---|---|
| `GET /options` | the products, their fields (cm, default, min, max) and the colours |
| `POST /quote` | a proposal; returns `id`, `pieces`, `fabric_m2`, `roll_m`, `vents`, `balloons`, `price.sale_eur` (incl. VAT), `price.indicative`, `near` (SUNS models alike), `preview` |
| `GET /preview/<id>.glb` | the proposal in 3D (glTF, metres, Y up) for any 3D viewer |
| `POST /request` | the customer asks for it: `{"quote_id", "name", "email", "phone"?, "note"?}` |

The products:

- `dining_set`: table length, width and height, and chairs;
- `round_set`: table diameter and height, and chairs;
- `sofa`: length, depth, back height and front height;
- `corner_sofa`: long side, short side, depth, back height and front height;
- `lounger`: length, width and height;
- `item`: length, width and height.

Their ranges are in `config/quote_products.json`.

An example request for `POST /quote`:

```json
{"product": "dining_set",
 "sizes": {"table_length_cm": 220, "table_width_cm": 100, "chairs": true},
 "colour": "Charcoal", "vents": true}
```

The customer never sees the cost price. Nothing internal (models, patterns, users) can be
reached through this API.

## Prices

The price comes from `quote.*` in `config/defaults.yaml`:

- the fabric per metre and the cutting waste;
- the sewing time per cover, per piece, per metre of seam and per vent, and the hourly rate;
- the parts;
- the markup and VAT.

Until the owner has set them, `quote.prices_are_placeholders` is true, and the price is shown
as indicative.
