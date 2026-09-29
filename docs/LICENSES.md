# Dependency licences

Internal tool: any OSI licence is acceptable (ADR-013). Keep this list complete anyway so a
later decision to distribute the software can be evaluated. Filled in and maintained from M0.

| Package | Licence | Used for |
|---------|---------|----------|
| libigl (python) | MPL-2.0 | parameterisation, winding numbers, cut_mesh |
| potpourri3d | MIT | geodesic paths (geometry-central) |
| trimesh | MIT | mesh I/O |
| cadquery-ocp | LGPL-2.1 (OpenCascade) | STEP/IGES import |
| manifold3d | Apache-2.0 | mesh booleans and repair |
| pymeshlab | GPL-3.0 | remeshing, repair filters |
| shapely | BSD-3 | 2D offsets |
| ezdxf | MIT | DXF export |
| FastAPI, uvicorn | MIT, BSD-3 | API |
| React, Vite, Three.js | MIT | web app |

Verify each entry against the package metadata when pinning versions in M0.
