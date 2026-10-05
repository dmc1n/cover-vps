"""Cover pattern engine: 3D furniture model to 2D cover cutting patterns."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("coverengine")
except PackageNotFoundError:  # shipped as plain files (the GPU container, ADR-069)
    __version__ = "0.0.0+files"
