"""Run a module under resource limits (ADR-123): `python -m coverapi.limited AS_MB CPU_S MODULE
ARGS...` sets the address-space and CPU-time limits on itself and then runs MODULE as `python -m`
would. The job runner starts every `cover` step this way, so a hostile or broken file (a
decompression bomb, an endless loop) ends that one job, not the server. 0 means no limit.

(Setting the limits here rather than in a `preexec_fn` keeps them out of the job runner's
threads, where `preexec_fn` is not safe.)
"""

from __future__ import annotations

import resource
import runpy
import sys

MIB = 1024 * 1024


def apply(as_mb: int, cpu_s: int) -> None:
    if as_mb > 0:
        b = as_mb * MIB
        resource.setrlimit(resource.RLIMIT_AS, (b, b))
    if cpu_s > 0:
        # the soft limit sends SIGXCPU (the process ends); the hard one a moment later SIGKILL
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 1))


def main() -> None:
    as_mb, cpu_s, module, *rest = sys.argv[1:]
    apply(int(as_mb), int(cpu_s))
    sys.argv = [module, *rest]
    runpy.run_module(module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
