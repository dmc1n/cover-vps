"""The Style3D drape on a GPU on demand (Modal; ADR-069). The same solver as drape_style3d.run,
in a container with CUDA: this server prepares the cloth (the flat pieces, a CPU job of seconds)
and the furniture, Modal runs the fall on an NVIDIA GPU and sends the frames back; measuring, the
rain and the AI's verdict stay here. Billed per second, nothing when idle; MODAL_TOKEN_ID and
MODAL_TOKEN_SECRET in deploy/.env. Many models run side by side (`run_many`), one GPU each.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import trimesh

from coverengine.params import EffectiveParams

APP = "cover-drape"
PKG = __import__("pathlib").Path(__file__).resolve().parent  # this package, shipped as files
GPU = "L4"  # param-ok: NVIDIA L4 (24 GB), the price/speed sweet spot for a sofa cover
TIMEOUT_S = 3600  # param-ok: an hour at most per model


def configured() -> bool:
    """Modal's keys: from the environment, or deploy/.env (as the AI's key; the service and the
    releases see that file too). Put into the environment, where Modal looks for them."""
    import os

    from coverengine.ai import repo_root

    names = ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET")
    env = repo_root() / "deploy" / ".env"
    if not all(os.environ.get(n) for n in names) and env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            k, _, v = line.partition("=")
            if k.strip() in names and v.strip():
                os.environ.setdefault(k.strip(), v.strip().strip("'\""))
    return all(os.environ.get(n) for n in names)


def _app() -> Any:
    import modal

    image = (
        modal.Image.debian_slim(python_version="3.12")
        .pip_install(
            "numpy==2.5.3",
            "scipy==1.18.1",
            "trimesh==5.1.0",
            "libigl==2.6.3",
            "newton==1.6.0",
            "warp-lang==1.17.0",
            "pyyaml==6.0.3",
            "shapely==2.1.2",
            "ruamel.yaml==0.19.1",
        )  # fmt: skip
        .add_local_dir(str(PKG), remote_path="/root/pkg/coverengine")
    )
    app = modal.App(APP, image=image)

    @app.function(gpu=GPU, timeout=TIMEOUT_S, serialized=True)
    def fall(
        cloth: dict[str, Any], meshes: list[tuple[Any, Any]], params: dict[str, Any]
    ) -> dict[str, Any]:
        import sys
        import time as t

        sys.path.insert(0, "/root/pkg")
        import scipy.sparse as sp
        import trimesh as tm

        from coverengine import drape_style3d
        from coverengine.drape import Cloth

        n = len(cloth["x"])
        c = Cloth(cloth["x"], cloth["faces"], cloth["piece"], cloth["rest_inv"],
                  cloth["rest_area"], cloth["names"], sp.csr_matrix((n, n)),
                  cloth["flat"])  # fmt: skip

        lines: list[str] = []
        t0 = t.time()
        values: Any = params  # the values only: the registry stays on the server
        frames, extra = drape_style3d.run(
            c, [tm.Trimesh(v, f, process=False) for v, f in meshes], values, lines.append
        )
        extra["gpu_s"] = round(t.time() - t0, 1)
        return {"frames": frames, "extra": extra, "log": lines[-12:]}

    return app, fall


def _arrays(c: Any) -> dict[str, Any]:
    """The cloth as plain arrays (the bending matrix is not needed by Style3D)."""
    return {"x": np.asarray(c.x), "faces": np.asarray(c.faces), "piece": np.asarray(c.piece),
            "rest_inv": np.asarray(c.rest_inv), "rest_area": np.asarray(c.rest_area),
            "names": list(c.names), "flat": np.asarray(c.flat)}  # fmt: skip


def _plain(params: EffectiveParams) -> dict[str, Any]:
    return dict(params.flat()) if hasattr(params, "flat") else dict(params)


def run(
    c: Any, colliders: list[trimesh.Trimesh], params: EffectiveParams, log: Any = print
) -> tuple[list[Any], dict[str, Any]]:
    """drape_style3d.run, on a GPU: the frames (mm) and how long it took."""
    return run_many([(c, colliders)], params, log)[0]


def run_many(
    jobs: list[tuple[Any, list[trimesh.Trimesh]]], params: EffectiveParams, log: Any = print
) -> list[tuple[list[Any], dict[str, Any]]]:
    app, fall = _app()
    plain = _plain(params)
    args = [(_arrays(c), [(np.asarray(m.vertices), np.asarray(m.faces)) for m in ms], plain)
            for c, ms in jobs]  # fmt: skip
    t0 = time.time()
    out = []
    with app.run():
        for res in fall.starmap(args):
            for line in res["log"]:
                log(f"  gpu: {line}")
            res["extra"]["engine"] = "style3d-gpu"
            res["extra"]["gpu"] = GPU
            out.append((res["frames"], res["extra"]))
    log(f"{len(jobs)} drape(s) on {GPU} in {time.time() - t0:.0f} s")
    return out
