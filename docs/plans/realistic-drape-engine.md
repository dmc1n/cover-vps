# Research: a more realistic drape engine (for v1.6)

The owner, 3 October 2026: "research a better engine, so the simulation looks more realistic
than now, to use in v1.6".

## What our own solver lacks

The own solver (ADR-056) is projective dynamics in numpy/scipy, on the CPU. It gets the places
of folds and sag right, but it:

- has **no stretch per direction**. Woven fabric is stiff along the warp and weft and soft on
  the bias; Coverlast's weft is about half as strong as its warp.
- has **no self-contact**. Folds pass through each other instead of lying on each other.
- has a **linear stretch limit** (1 ± limit) instead of the real stress-strain curve.
- uses a **coarse mesh**: the cut's 15–30 mm. Real fold detail needs 5–8 mm.
- is **slow** on 8 CPU cores: 5–20 minutes per cover.

## Candidates (tested here where possible)

| Engine | Licence | Fits our data | Per direction | Self-contact | Speed here (CPU, 10k points, 1 s) | With a GPU |
|---|---|---|---|---|---|---|
| Own (projective dynamics) | ours | yes | no | no | ~50 s | n/a |
| **Newton: Style3D solver** | Apache 2.0 | **yes: flat panels + 3D + sewing** | **yes** (stretch and bending) | partly | **51 s** | ~50–100× faster |
| Newton: VBD solver | Apache 2.0 | via meshes | yes | **yes** | 564 s | real-time-ish |
| Newton: XPBD solver | Apache 2.0 | via meshes | limited | basic | 88 s | fast |
| libuipc (GPU IPC) | Apache 2.0 | via meshes | yes | **yes, no penetration ever** | no CPU version | the most exact; needs CUDA 12.8 |
| Blender cloth | GPL | via sewing springs | weak | yes | slow | no |
| CLO3D / Marvelous Designer | commercial | yes | yes | yes | n/a (desktop, licence) | n/a |

**Newton** is developed by NVIDIA, Disney Research and Google DeepMind, and is now a Linux
Foundation project, built on NVIDIA Warp.

- Version 1.6 installs here with `pip install newton` and runs on the CPU. Tested in a scratch
  environment; the project was not touched.
- Its **Style3D** solver comes from the garment industry. Its `add_cloth_mesh` takes every
  panel's **flat pattern** (`panel_verts`) together with its **3D placement** and sews the
  panels. That is exactly what `cover cut` and `cover flatten` produce.
- Its fabric model has stretch per direction (warp, weft, shear: `tri_aniso_ke`) and bending
  per direction (`edge_aniso_ke`).

## Recommendation

1. **v1.6: Newton Style3D as the drape engine**, behind the outputs we already have:
   - `drape.glb`, `.bin` and `.json`, and the rain and the heatmap on it;
   - `drape.engine: own | style3d` in `config/defaults.yaml`;
   - both run on the Kota, the Lucia and the Basta, and compared;
   - the switch to Style3D as the default after the owner has looked.

   Gains: the warp and weft of Coverlast, a proven garment model, and sewing as in a workshop.
   It is the same speed on the CPU as now.
2. **A GPU, for the real realism.** Self-contact (VBD) and a 5 mm mesh are too slow on this
   server's CPU (10× slower than now). With an NVIDIA GPU they take minutes or less. The
   options, a decision for the owner:
   - **a GPU server at Hetzner** (GEX44, RTX 4000 SFF Ada 20 GB): about €190 a month plus a
     one-off fee. Always available, and the same place as now;
   - **a GPU by the hour** for the night runs (RunPod, Lambda and others): a few euros per
     night, but more to set up and the models leave our server;
   - **no GPU:** Style3D on the CPU (point 1). Realistic directions and sewing, but no
     self-contact and a coarser mesh.
3. **Fit the fabric to reality, whatever the engine.** The fabric values decide the size of
   the folds.
   - **Cantilever test:** a strip of Coverlast 2.5 × 20 cm pushed over a table edge; the length
     at which it bends down 41.5° gives the bending stiffness, lengthways and across.
   - **Strip test:** 1 kg on a 5 cm strip, lengthways, across and on the bias, gives the
     stretch per direction.
   - **Cusick drape test** (optional): a 30 cm round sample over an 18 cm disc, photographed
     from above. The simulation of the same test must give the same outline: the literature's
     "simulation in the loop".
   - Then **one real cover** (the Kota) photographed from fixed angles against the simulation.

## For v1.6 concretely

1. The adapter: from `panels.npz` and `pattern.json` to Style3D's `add_cloth_mesh`. Each panel
   is meshed evenly at `drape.edge_mm`, with the flat shape as `panel_verts`, the 3D placement,
   and the seam pairs as sewing. The furniture, balloons and chair space are colliders.
2. The fabric from `testdata/fabrics/coverlast.json`: warp, weft and bias stretch, and bending
   both ways.
3. Runs as a job like now; the same playback, heatmap and audit check.
4. Tests: the tablecloth over a box (like now), a strip over two supports (sag), and the same
   input giving the same result.
5. **On a GPU** (if chosen): VBD with self-contact at 5 mm, as a "fine" level.

## What the owner decides

- **The GPU.** No GPU (Style3D on the CPU), a Hetzner GPU server, or a GPU by the hour.
- **The fabric tests on Monday:** the cantilever and strip tests (15 minutes), for both
  directions.
