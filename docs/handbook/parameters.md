# Changing a setting

Every number the engine uses is in one file: `config/defaults.yaml`. Each line has a comment
that says what it does. Lines marked "to confirm" are assumptions we still need to check.

## See what is in effect

```
uv run cover params
```

prints every setting, its value, where the value comes from and a note:

| source  | meaning |
|---------|---------|
| default | from `config/defaults.yaml` |
| preset  | from a furniture-family preset (M7) |
| model   | saved for this one model (its `cover.json`) |
| trial   | given on the command line with `--set`, this run only |

`* to confirm` marks an assumption. `choices: a | b` lists the allowed values of a setting.
In the web app (M6) these become dropdowns.

## Change a company default

1. Open `config/defaults.yaml`, change the value, and keep the comment up to date.
2. Run `uv run cover params` and check the new value shows.
3. Commit the change with a message that says why, e.g. "clearance 10 → 12 after M4 fit test".

## Try a value once, without saving

```
uv run cover params --set hull.clearance_mm=15
uv run cover params --set construction.method=welded
```

A misspelt name is refused with a suggestion ("did you mean hull.clearance_mm?"). So is a value
of the wrong kind: text where a number belongs, or a choice that is not on the list.

## Joining method per model

`construction.method` is `double_stitch` (today's practice) or `welded`. The company default is
`double_stitch`; a model that should be welded stores `"construction": {"method": "welded"}` in
its `cover.json` (in the web app: the dropdown on the model page, M6).

## If `make test` fails after you changed a number

One test checks that no setting's value is also written directly into the engine code. If your
new value happens to match a number in the code, that test names the file and line. Tell Claude
Code; the fix is in the code, not in your setting.
