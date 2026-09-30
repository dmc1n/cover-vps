# Plan: an overview of all products and their covers

Owner, 1 Oct 2026 (night): "make a nice overview of all products we uploaded, including showing
the cover, so we have an online database".

## Options considered

1. **A catalogue page in the web app** — the live database: always current, every model the
   program has, search and filters, a click leads to the model with its drawings and downloads.
   Online for the team once the Cloudflare tunnel and login are set up (question 14); until
   then through the SSH tunnel.
2. **A published snapshot page** (a private page on claude.ai the owner can share) — useful
   right now without the tunnel, for the team discussion; not live.
3. A PDF catalogue — already there as `cover report` (a table); a picture version would be
   large (300 products) and goes out of date.

Chosen: 1 as the database, 2 as a snapshot of this night's run.

## What each product shows

- A photo of the product (3D Warehouse's own thumbnail, for SUNS models) and a 3D picture of the
  calculated cover with its panels in colour (`cover.png`, made by `cover export`).
- Name, family, grade (ready / to check / failed, with the reasons), size, number of pieces,
  fabric needed, worst stretch, status.
- Links: the model page, the size drawing, the cut pieces (DXF), the cutting list.

## Technical

- `export/preview.py`: the 3D view of the panels as a PNG (the size drawing's shaded view,
  panels in their colours), written by `cover export` and by `cover preview`.
- `scripts/warehouse.py`: fetch a creator's product list and each product's GLB and photo from
  3D Warehouse (what was done by hand for SUNS tonight, as a tool).
- API: `product.jpg` and `cover.png` as model files; the model list already carries grade,
  sizes and pieces.
- Web: a **Catalogue** page (#/catalogue): a grid of cards with the two pictures and the key
  numbers, search, filters by family, grade and tag, sorting.
