# Dependency licences

Internal tool: any OSI licence is acceptable (ADR-013). Keep this list complete anyway so a
later decision to distribute the software can be evaluated.

The table below is generated from installed package metadata by `scripts/licenses.py`; the test
suite fails when it is out of date or a direct dependency is missing. Versions are the ones
locked in `uv.lock`. Transitive dependencies are in `uv.lock`; the notable ones are named in the
Note column.

<!-- BEGIN GENERATED -->
| Package | Version | Licence | Used for | Note |
|---|---|---|---|---|
| numpy | 2.5.3 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | arrays |  |
| scipy | 1.18.1 | BSD License | sparse solvers, spatial queries |  |
| scikit-image | 0.26.0 | BSD License | marching cubes on the SDF grid |  |
| trimesh | 5.1.0 | MIT License | mesh I/O |  |
| libigl | 2.6.3 | Mozilla Public License 2.0 (MPL 2.0) | SLIM/ARAP parameterisation, winding numbers, cut_mesh |  |
| potpourri3d | 1.4.0 | MIT License | geodesic paths (geometry-central) |  |
| cadquery-ocp | 8.0.1.0.0 | Apache-2.0 | STEP/IGES import (OpenCascade) | bindings Apache-2.0; bundles OpenCascade (LGPL-2.1 with exception) and VTK (BSD) |
| manifold3d | 3.5.4 | Apache Software License | mesh booleans and repair |  |
| pymeshlab | 2025.7.post1 | GPL3 | remeshing, repair filters | GPL-3.0: fine for internal use (ADR-013); review before distributing |
| shapely | 2.1.2 | BSD 3-Clause | 2D offsets |  |
| ezdxf | 1.4.4 | MIT License | DXF read and write |  |
| ruamel.yaml | 0.19.1 | MIT | parameter file (config/defaults.yaml) |  |
| matplotlib | 3.11.2 | Python Software Foundation License | DXF preview renders, plots |  |
| pymupdf | 1.28.2 | see package | reading the owner's PDF drawings (learning) | AGPL-3.0: fine for internal use (ADR-037); review before distributing |
| newton | 1.6.0 | Apache-2.0 |  |  |
| warp-lang | 1.17.0 | Apache-2.0 |  |  |
| modal | 1.6.1 | Apache-2.0 |  |  |
| fastapi | 0.141.1 | MIT | API (M6) |  |
| uvicorn | 0.54.0 | BSD-3-Clause | API server (M6) |  |
| pytest | 9.1.1 | MIT | tests (dev) |  |
| pytest-xdist | 3.8.0 | MIT | parallel tests in make test (dev, ADR-129) |  |
| ruff | 0.16.9 | MIT | lint and format (dev) |  |
| mypy | 2.3.1 | MIT | type checks (dev) |  |
| pre-commit | 4.6.2 | MIT | commit hooks (dev) |  |
| python-multipart | 0.0.32 | Apache-2.0 | file uploads in the API (M6) |  |
| httpx | 0.28.1 | BSD-3-Clause | API test client (M6) |  |
| openpyxl | 3.1.5 | MIT |  |  |
| pillow | 12.3.0 | MIT-CMU | pictures attached at the Desk, checked and re-encoded (ADR-096) |  |
<!-- END GENERATED -->

## Not Python

| Component | Licence | Used for |
|-----------|---------|----------|
| React, Vite, Three.js | MIT | web app (M6) |
| Work Sans (`@fontsource-variable/work-sans`) | OFL-1.1 | the website's typeface and, in the studio, only the customers' configurator, self-hosted (ADR-105, ADR-130) |
| Lucide (`lucide-react` 1.56.0) | ISC; MIT for the Feather-derived icons | generic utility glyphs in the studio (chevrons, close, the (i), copy, external link, more, undo, delete, theme); keep the copyright and permission notices of the package's LICENSE (Copyright (c) 2026 Lucide Icons and Contributors; Copyright (c) 2013-present Cole Bemis) (Studio 2.0, ADR-130) |
| Inter (`@fontsource-variable/inter`) | OFL-1.1 | the studio's typeface where the device has no SF (system font first), self-hosted (ADR-130) |
| Cover Studio's own icons (`apps/web/src/icons/glyphs.tsx`) | ours | every section, page, tab, toolbar action, status and Settings tile icon of the studio, drawn for it (owner, 13 Oct 2026; ADR-130); no third-party licence |
| cloudflared | Apache-2.0 | Cloudflare Tunnel (M6) |
| Single-stroke pen font (`coverengine/export/strokefont.py`) | ours | pen text |
| Blender 4.2 LTS | GPL-3.0-or-later | renders the website's films offline (ADR-065, ADR-071, ADR-108); not shipped |
| FFmpeg (static build, libaom, libx264) | GPL-3.0 | encodes the films offline (ADR-108); not shipped |
| Poly Haven assets: HDRIs *hotel_rooftop_balcony*, *kloofendal_overcast*; textures *stretch_poplin*, *large_grey_tiles*, *white_plaster_02*, *concrete_floor_02*; model *potted_plant_04* | CC0-1.0 | the hero film's light, weave, stone, plaster and plant (`scripts/film/hero_assets.py`, ADR-108) |
| Poly Haven assets for the story and the clips: textures *terracotta_floor_tiles*, *white_stucco*, *rough_wood*; models *potted_plant_01*, *island_tree_02* | CC0-1.0 | the villa on Ibiza and the clips (`scripts/film/hero_assets.py`, ADR-121) |
| Work Sans (Google Fonts, `WorkSans[wght].ttf`) | OFL-1.1 | the dimension lines in the rendered story (fetched to the film assets, not in the repo; ADR-121) |
| Kling start frames (`scripts/film/kling_frames.py`): the Poly Haven assets above (CC0-1.0) and Blender's procedural Nishita sky; the woven canvas, the stitch relief and the cutter's gantry are procedural, ours | CC0-1.0 / ours | no new third-party asset (ADR-125) |
| Kling AI image-to-video (Kuaishou), paid API | service, Kling's terms of service | the website's clips from our own stills (`scripts/film/kling.py`, ADR-125); before a clip goes live, confirm the paid plan's commercial-use clause for generated output |
