# Covers → All covers: every model, families, status and many at once

**Covers → All covers** (`#/covers/all`) is every model in the studio with its cover. It used to
be two pages, Models and Catalogue; now it is one page with a **Table / Cards** switch at the top.
The map of the studio: [navigation.md](navigation.md).

## Table and Cards

- **Table** (`#/covers/all`): one row per model with how far its cover is:
  - the **cover grade**: **ready** (every piece within the stretch limit, smooth edges, seams
    matching within 5 mm), **to check** (hover to see why) or **failed**;
  - its progress (five dots: import, cover, seams, patterns, cut pieces);
  - the number of pieces, the worst stretch and the number of warnings.
- **Cards** (`#/covers/all?view=cards`): every product as a card with its photo, a 3D picture of
  its cover, the grade, size, number of pieces, worst stretch and fabric.

Click a row or a card to open the cover (`#/model/<id>/3d`). What is on a cover's page: see
[web-app.md](web-app.md).

## The filter row

One row of filters for both views; your filters stay when you switch between Table and Cards:

- **search**: name, tag, note or family;
- **category** (with its groups, as on hello-suns.com);
- **cover grade**: ready, to check, failed;
- **status**: draft, checked, production;
- **tag**;
- **sort**: name, cover ready first, stretch, size.

## Selecting and running many at once

Both views have a tick box per model (on every card too) and **select all shown**. As soon as
something is selected, the **batch bar** appears: tick the steps (cover surface, seams and
panels, flat patterns, cut pieces) and press **Run these** to calculate the selected covers
again; it shows each model's job as it runs.

On the command line the same; it also lists per model which pieces changed by more than 1 mm:

```
uv run cover batch --family table
uv run cover batch --ids model-a,model-b --steps flatten,export
```

Use it after changing a family or the company defaults, to run all models it touches.

## Families

Models of the same kind (tables, dining chairs, lounge sofas, ...) share settings through a
**family**: a file `config/presets/<family>.yaml` with only the settings that differ from the
company defaults. Put a model in a family on its page with **Edit details**, or with

```
uv run cover model models/<id> --family table
```

A change to the family file then applies to every model of that family that does not set the
value itself. The order is: company default → family → the model's own → trial.

So far there is one family, `table` (a balloon under the cover, so it forms a tent).

## Status, tags and notes

Each model has a status: **draft** (being worked on), **checked** (patterns looked over),
**production** (cut from). Tags (for example "lounge, outdoor") and notes for the machine
operator help to find and use models. Change them on the cover's page with **Edit details**
(category, family, status, tags, notes). The filter row on All covers searches and filters
them.

## Revisions

Every run that makes the cut pieces is kept as a revision (`revisions/` in the model folder):
the patterns, the cut pieces with `cut.dxf`, and the settings and seams used. On a cover's page:
**History → Revisions**; pick two to see what changed. On the command line:

```
uv run cover model models/<id>          # family, status and the last revisions
uv run cover diff models/<id>/revisions/003/pattern.json models/<id>/pattern.json
```

## Models that need no cover

Some furniture needs no cover (the Portofino daybed with its own roof). Mark it instead of
deleting it: `uv run cover model models/<id> --no-cover yes --no-cover-reason "has its own
roof"` (or `--no-cover no` to undo). The model stays in the studio with a "no cover" badge, but
the shop never offers it and the Desk leaves it out (ADR-117).
