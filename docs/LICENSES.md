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
| fastapi | 0.141.1 | MIT | API (M6) |  |
| uvicorn | 0.54.0 | BSD-3-Clause | API server (M6) |  |
| pytest | 9.1.1 | MIT | tests (dev) |  |
| ruff | 0.16.9 | MIT | lint and format (dev) |  |
| mypy | 2.3.1 | MIT | type checks (dev) |  |
| pre-commit | 4.6.2 | MIT | commit hooks (dev) |  |
| python-multipart | 0.0.32 | Apache-2.0 | file uploads in the API (M6) |  |
| httpx | 0.28.1 | BSD-3-Clause | API test client (M6) |  |
<!-- END GENERATED -->

## Not Python

| Component | Licence | Used for |
|-----------|---------|----------|
| React, Vite, Three.js | MIT | web app (M6) |
| cloudflared | Apache-2.0 | Cloudflare Tunnel (M6) |
| Single-stroke pen font (`coverengine/export/strokefont.py`) | ours | pen text |
