# Prijzen en kostprijs

Admin → **Prices & costing** (collega's met de rol editor: **Prices** in de bovenbalk, alleen
kijken). Hier staan alle prijzen waarmee de shop, de configurator en elke kostprijsberekening
rekenen.

## Wat staat waar

- **Materials:** stoffen (prijs per meter, in EUR of IDR, rolbreedte, snijverlies) en
  onderdelen (ventilatieset, koord per meter, elastiek, ballon, frame, of zelf toegevoegd),
  met wat ze tellen: per ventilatie, per meter koord, per hoes ...
- **Labour:** het uurloon (EUR of IDR) en de minuten per handeling: snijtafel klaarzetten,
  per stuk, per meter naad, per ventilatie, per meter zoom, inpakken.
- **Exchange rate:** de vaste koers, rupiah per euro, met datum. Elke IDR-prijs wordt hiermee
  omgerekend; overal staan beide bedragen. Hier zet je ook **indicative** uit zodra de echte
  prijzen erin staan (dan verdwijnt "indicatief" in de shop).
- **Channels & price lists:** per kanaal (B2C consumenten, B2B Sunsit en dealers) de extra
  kosten (verzending, invoerrechten als % of vast bedrag, verpakking), en de prijslijst: opslag
  of marge, afronding (.95, hele euro's ...), btw en of prijzen incl. btw getoond worden, en
  vaste prijzen per product.
- **Costing:** kies een hoes (catalogus, tekening, combinatie) of een configurator-product met
  maten, en je ziet regel voor regel: stof (meters uit het snijplan + verlies), onderdelen,
  arbeid per handeling = kostprijs; dan per kanaal de extra kosten, de prijs en de marge.
  **CSV** voor Excel, **PDF** om te printen.
- **Versions:** elke gepubliceerde versie, wie en wanneer; terug naar een eerdere met één klik.

## Een prijs veranderen

1. Pas de getallen aan (de pagina meldt "unsaved changes").
2. **Preview changes**: een lijst van elke prijs die verschuift, oud → nieuw.
3. Schrijf kort wat er veranderde en klik **Publish**. Pas dan rekent de shop ermee.
   **Save draft** bewaart zonder te publiceren; **Discard draft** gooit het concept weg.

Fout getal (een negatieve prijs, een marge van 100 %)? Dan zegt de pagina wat er mis is en
publiceert niet. Alleen admins kunnen wijzigen; elke publicatie staat in het audit log.

Later koppelen we dit aan Odoo (docs/plans/prices-costing.md); tot die tijd is dit de plek.
