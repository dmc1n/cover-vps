# Importing a furniture model

`cover import` turns the file a manufacturer sends into one clean model: in millimetres,
standing on the floor, front facing forward, with screws and washers left out. Every later
step (the cover shape, seams, patterns) starts from this model.

Files it reads: STEP (`.step`, `.stp`), IGES (`.iges`, `.igs`), STL, OBJ, PLY and glTF
(`.glb`, `.gltf`).

## Import a file

```
uv run cover import testdata/models/lounge-a12.step --out models/lounge-a12
```

`--out` is the model's folder; its name is the model's id. The command prints a short summary:

```
imported lounge-a12.step -> models/lounge-a12
units    mm (file declares mm)
size     1800.0 x 850.0 x 760.0 mm, 412000 triangles
parts    84 kept, 212 dropped as smaller than 8 mm, 0 excluded by name
```

Check the size first. If it is not the real size of the furniture, the units are wrong (see
below).

The folder now holds:

| file | what it is |
|---|---|
| `model.glb` | the model. Open it in any 3D viewer to look at it, e.g. drag it onto gltf-viewer.donmccurdy.com or into Windows 3D Viewer. It should stand upright at true size. |
| `model.json` | summary: source file, units, placement, part counts, warnings |
| `parts.json` | every part with its size, and whether it was kept, dropped or excluded |

`uv run cover info models/lounge-a12` shows the summary again at any time.

## Small parts (screws, washers)

Parts whose largest dimension is below 8 mm are left out. That size is the setting
`import.min_part_mm`. For one import you can change it:

```
uv run cover import lounge.step --out models/lounge --min-part-mm 15
```

Longer screws and bolts are bigger than 8 mm, so they stay in. That is usually harmless: the
cover surface (M2) bridges small bumps. Leave them out by name if they are in the way.

## Leaving parts out by name

Cushions, a parasol or packaging can be left out by name:

```
uv run cover import lounge.step --out models/lounge --exclude "cushion*" --exclude "*bolt*"
```

- `*` means "anything". Upper and lower case do not matter.
- A pattern matches a part name anywhere in the assembly: `cushion*` also drops
  `lounge/seat unit/Cushion left`.
- Look up part names in `parts.json` (field `path`).
- Exclusions are remembered: the next import into the same folder uses them again.
  `--forget-exclusions` starts over.
- IGES files carry no part names, so exclusion by name does not work for them; STEP does.

## Units

STEP and IGES files state their unit, and the import uses it. STL, OBJ and PLY files store no
unit; the import assumes mm (`import.default_units`). If the result is too small or too large
for furniture, you get a warning that names the units that would fit:

```
warning: model is 20 x 25 x 37 mm with units mm, which looks too small for furniture;
in cm it would be 197 x 247 x 371 mm (--units cm); in inch it would be 500 x 628 x 943 mm (--units inch)
```

Pick the one that matches the real furniture and import again with `--units inch`. The import
never switches units by itself.

Some files state a wrong unit. The first real sofa we imported calls its unit "METRE" but
defines it as 1 mm, while its numbers are metres. The import then warns that the name and the
definition disagree, and the size warning suggests `--units m`. Trust the size: a two-seater
sofa is about 2 m wide, not 2 mm.

## Lying down or facing the wrong way

The model should stand upright with its front toward you in the viewer. If a file was drawn
differently:

- `--up y` (or `x`, `-y`, …): the axis that points up in the file. Most CAD files use `z`
  (the default); glTF files use `y` and are handled automatically.
- `--front x` (or `-y`, `y`, `-x`): which side is the front once the model stands upright. The
  import turns that side to face forward.

Open `model.glb` after the import to check.

## Meshes saved as STEP

Some manufacturers send a mesh saved as STEP instead of real CAD data (in Drive the file looks
like any other `.stp`). The import recognises these and reads them quickly: the 208 MB Blocchi
sofa takes about 20 seconds. Such files have no part names: the parts are called `Root/1`,
`Root/2`, … Look at `parts.json` for their sizes to tell the cushions from the frame.

## If the import fails

- "all N parts were dropped": everything was smaller than `--min-part-mm` or excluded. Often
  the units are wrong; the message then suggests the right `--units`.
- "not a readable STEP file": the file is damaged or not really STEP. Ask the manufacturer
  for a fresh export.

Put real manufacturer files in `testdata/models/`. That folder and the `models/` output folder
never go to GitHub: the repository is public and the files are the manufacturers'.
