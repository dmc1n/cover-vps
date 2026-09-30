# Families, status and many models at once

## Families

Models of the same kind (tables, dining chairs, lounge sofas, ...) share settings through a
**family**: a file `config/presets/<family>.yaml` with only the settings that differ from the
company defaults. Put a model in a family in the web app (the box above the tabs) or with

```
uv run cover model models/<id> --family table
```

A change to the family file then applies to every model of that family that does not set the
value itself. The order is: company default → family → the model's own → trial.

So far there is one family, `table` (a balloon under the cover, so it forms a tent).

## Status, tags and notes

Each model has a status: **draft** (being worked on), **checked** (patterns looked over),
**production** (cut from). Tags (for example "lounge, outdoor") and notes for the machine
operator help to find and use models. In the web app: the box above the tabs; the models list
can be searched and filtered by family and status.

## Revisions

Every run that makes the cut pieces is kept as a revision (`revisions/` in the model folder):
the patterns, the cut pieces with `cut.dxf`, and the settings and seams used. In the web app:
tab **Revisions**; pick two to see what changed. On the command line:

```
uv run cover model models/<id>          # family, status and the last revisions
uv run cover diff models/<id>/revisions/003/pattern.json models/<id>/pattern.json
```

## Many models at once

After changing a family or the company defaults, run all models it touches:

```
uv run cover batch --family table
uv run cover batch --ids model-a,model-b --steps flatten,export
```

It lists per model which pieces changed by more than 1 mm. In the web app: tick the models in
the list and press **Run these**.
