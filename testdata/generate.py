"""Write the procedural test shapes to testdata/generated/ (STL plus JSON sidecar).

Usage: uv run python testdata/generate.py [--out DIR]   (or: make shapes)
Dimensions come from testdata/shapes.yaml; output is deterministic.
"""

import argparse
from pathlib import Path

from coverengine.testshapes import write_all

HERE = Path(__file__).resolve().parent

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE / "generated")
    out = ap.parse_args().out
    for path in write_all(out):
        print(path)
