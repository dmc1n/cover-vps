"""ADR-067: the scroll story's pieces laid out on the roll, without overlap, within its width."""

import numpy as np
from coverengine import story


def test_the_pieces_lie_on_the_roll_side_by_side() -> None:
    rng = np.random.default_rng(3)
    pieces = {k: rng.random((40, 2)) * (900 + 300 * k, 500 + 100 * k) for k in range(4)}
    placed, (length, width) = story._layout(pieces, 1480.0)
    boxes = [(p.min(axis=0), p.max(axis=0)) for p in placed.values()]
    assert all(lo[1] >= -1e-6 and hi[1] <= width + 1e-6 for lo, hi in boxes)  # on the roll
    assert all(hi[0] <= length + 1e-6 for _, hi in boxes)
    for i, (a0, a1) in enumerate(boxes):  # no two pieces on top of each other
        for b0, b1 in boxes[i + 1 :]:
            assert (
                a1[0] <= b0[0] + 1e-6
                or b1[0] <= a0[0] + 1e-6
                or a1[1] <= b0[1] + 1e-6
                or (b1[1] <= a0[1] + 1e-6)
            )
    # each piece keeps its shape (a turn and a move only)
    for k, p in pieces.items():
        q = placed[k]
        d0 = np.linalg.norm(p[0] - p[1])
        d1 = np.linalg.norm(q[0] - q[1])
        assert abs(d0 - d1) < 1e-6
