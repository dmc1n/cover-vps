"""Test markers for the whole suite (ADR-129).

- `timing`: a test that asserts how long something takes. `make test` runs these on their own,
  after the parallel run, so other tests never slow them down.
- `slow`: the tests that take 15 s or more (the golden hulls, the drape, the big drawings). They
  run in `make test` and every release; `make test-fast` leaves them out while developing.

Names are listed here, measured with `pytest --durations=0` (13 Oct 2026), so the test files
stay as they are; a name that no longer exists fails the run, so this list cannot rot.
"""

from typing import Any

import pytest

TIMING = {
    "engine/tests/test_hull.py::test_500k_triangle_soup_under_a_minute",
    "engine/tests/test_import.py::test_2000_part_assembly_under_two_minutes",
    "engine/tests/test_flatten.py::test_200k_triangle_panel_under_3_seconds",
}
SLOW = {
    "engine/tests/test_drape.py::test_style3d_drapes_the_tablecloth_with_canvas_like_stretch",
    "engine/tests/test_hull.py::test_500k_triangle_soup_under_a_minute",
    "engine/tests/test_hull.py::test_balloon_makes_a_table_drain",
    "engine/tests/test_hull.py::test_golden_hull",
    "engine/tests/test_hull.py::test_preview_shows_where_water_stays",
    "engine/tests/test_hull.py::test_draped_table_follows_slats_with_small_bridge",
    "engine/tests/test_drawing_isofit.py",
    "engine/tests/test_kind.py::test_an_l_shaped_cover_from_a_drawing_becomes_the_drawn_pieces",
    "engine/tests/test_flatten.py::test_cli_run_and_diff",
    "engine/tests/test_flatten.py::test_the_vents_on_the_inner_walls_of_an_l_face_the_open_corner",
    "engine/tests/test_answers_box.py::test_a_box_top_wider_than_the_roll_is_cut_in_strips",
    "engine/tests/test_answers_box.py::test_a_corner_sofa_in_one_file_is_built_as_an_l",
    "engine/tests/test_outline.py::test_an_organic_outline_is_followed_bays_and_all",
    "engine/tests/test_arrange.py::test_an_l_arrangement_gets_an_l_cover_with_a_sharp_inner_corner",
    "apps/api/tests/test_arrangements.py::test_place_snap_and_build_one_cover",
}


def pytest_configure(config: Any) -> None:
    config.addinivalue_line("markers", "timing: asserts a duration; run apart from the rest")
    config.addinivalue_line("markers", "slow: 15 s or more; left out by make test-fast")


def _base(nodeid: str) -> str:
    return nodeid.split("[", 1)[0]


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    seen = set()
    for item in items:
        base = _base(item.nodeid)
        path = base.split("::", 1)[0]
        for name in (base, path):
            if name in TIMING:
                item.add_marker(pytest.mark.timing)
                seen.add(name)
            if name in SLOW:
                item.add_marker(pytest.mark.slow)
                seen.add(name)
    # every listed name in a collected file must exist (a renamed test would lose its mark)
    if config.getoption("-k") or config.getoption("-m"):
        return
    files = {_base(i.nodeid).split("::", 1)[0] for i in items}
    names = {_base(i.nodeid) for i in items} | files
    gone = {n for n in TIMING | SLOW if n.split("::", 1)[0] in files and n not in names}
    if gone:
        raise pytest.UsageError(f"conftest.py lists tests that are gone: {sorted(gone)}")
