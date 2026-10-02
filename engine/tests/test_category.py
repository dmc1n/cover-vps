"""Categories with the SUNS names (ADR-050)."""

import pytest
from coverengine.category import NAMES, by_name, full


@pytest.mark.parametrize(
    ("name", "height", "want"),
    [
        ("suns-dining-table-palermo-240", 762, "Tafels"),
        ("suns-low-dining-table-grado-170", 684, "Low dining tafels"),
        ("suns-bar-table-80x80-teak", 1099, "Bartafels"),
        ("suns-bar-chair-virenze", 692, "Barstoelen"),
        ("suns-dining-chair-nappa", 886, "Stoelen"),
        ("suns-2-seater-kota", 842, "Sofasets"),
        ("suns-lounge-vivaro-lounge-chair", 935, "Loungestoelen"),
        ("suns-table-kota", 99, "Loungetafels"),  # a low table is a lounge table
        ("suns-lounge-conico-small", 250, "Loungetafels"),
        ("suns-side-table-aspen", 101, "Bijzettafels"),
        ("suns-lounge-pienza-curved-hocker", 349, "Hockers"),
        ("suns-daybed-vento", 881, "Daybeds"),
        ("suns-lounge-lucia-sunlounger", 785, "Ligbedden"),
        ("suns-fire-pit-monte-vari-80-teak", 1257, "Vuurtafels"),
    ],
)
def test_the_name_decides(name: str, height: float, want: str) -> None:
    assert by_name(name, height) == want
    assert full(want) in NAMES
