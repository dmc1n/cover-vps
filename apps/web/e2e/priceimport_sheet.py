"""The sample price list for apps/web/e2e/priceimport.py (ADR-113): codes, SUNS names, an
unknown row, a shared family without a type, the balloon, a row without a price, and prices
written the Dutch way ("€ 1.234,95", "€ 459,-") next to plain number cells.

    uv run python apps/web/e2e/priceimport_sheet.py OUT.xlsx
"""

import sys

from openpyxl import Workbook

ROWS = [
    ("S40", "Bellano/Sato - Lounge chair", "Cover 105", "€ 1.234,95"),
    ("C5", "Aspen/ Kota/ Evora lounge normal SMALL w/o side table", "Cover 7", 899),
    ("", "SUNS 2 Seater Kota", "", "€ 649,00"),
    ("", "Kota 3-seater", "", 749.5),
    ("D1", "Portofino/ Aspen/ Kota normal D-Bed", "Cover 1", "€ 459,-"),
    ("", "Bellano lounge chair", "", "€ 1.199,00"),
    ("", "Unknown Fantasy Sofa XL", "", "€ 499,95"),
    ("", "Aspen lounge set", "", 1299),
    ("", "Ballon", "", "€ 24,95"),
    ("T1", "Table 340x100", "Cover 13", "n.v.t."),
    ("S99", "Nieuw model 2027", "Cover 999", "€ 2.345,50"),
]


def main(out: str) -> None:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Prijslijst 2027"
    ws.append(["SUNS consumentenprijzen 2027"])
    ws.append([])
    ws.append(["Code", "Omschrijving", "Cover", "Verkoopprijs incl. BTW"])
    for r in ROWS:
        ws.append(list(r))
    for cell in ws["D"][3:]:
        if isinstance(cell.value, int | float):
            cell.number_format = "€ #,##0.00"
    wb.save(out)


if __name__ == "__main__":
    main(sys.argv[1])
