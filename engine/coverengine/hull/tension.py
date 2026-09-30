"""Tensioned cover top: the upper convex envelope of the furniture (ADR-025).

A cover pulled tight runs in straight lines between the furniture's high points: from the
front edge of a seat straight up to the top of the back. Over the planform, the top is
therefore the lowest concave height function on or above the obstacle (the height map after
bridging and clearance): the upper convex hull of the obstacle's surface points. A concave top
has no hollow anywhere, so water runs off (CLAUDE.md rule 12). Only flat areas can still hold
water; the drainage check finds them and a support (balloon) under the cover lifts them.
"""

from __future__ import annotations

import numpy as np
from matplotlib.tri import LinearTriInterpolator, Triangulation
from numpy.typing import NDArray
from scipy.spatial import ConvexHull

Array = NDArray[np.float64]
Mask = NDArray[np.bool_]

# A facet belongs to the upper hull when its outward normal points up by more than this.
UP = 1e-9


def concave_envelope(obstacle: Array, inside: Mask, xs: Array, ys: Array) -> Array:
    """Upper convex envelope of the obstacle, evaluated on the cells `inside` (-inf elsewhere)."""
    ii, jj = np.nonzero(inside)
    pts = np.column_stack([xs[ii], ys[jj], obstacle[ii, jj]])
    # the same points one unit below the lowest: a flat obstacle (a table top) is otherwise
    # coplanar, which Qhull cannot hull. They only form the hull's bottom and vertical sides.
    below = pts.copy()
    below[:, 2] = pts[:, 2].min() - 1.0
    hull = ConvexHull(np.vstack([pts, below]))
    upper = hull.simplices[hull.equations[:, 2] > UP]
    if np.any(upper >= len(pts)):  # cannot happen: the copies lie under the originals
        upper = upper[np.all(upper < len(pts), axis=1)]
    tri = Triangulation(pts[:, 0], pts[:, 1], upper)
    z = LinearTriInterpolator(tri, pts[:, 2])(xs[ii], ys[jj])
    out = np.full(obstacle.shape, -np.inf)
    # cells on the hull's own edge can fall a hair outside every facet; they keep the obstacle
    values = np.where(np.ma.getmaskarray(z), pts[:, 2], np.ma.getdata(z))
    out[ii, jj] = np.maximum(values, pts[:, 2])
    return out
