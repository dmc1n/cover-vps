# Meten op de 3D-hoes en de checklist (ADR-111)

Voor het controleren van een genaaide hoes. Alle maten in cm, één decimaal, langs de stof
gemeten, naad tot naad (zonder naadtoeslag).

## Meten in de 3D-weergave

1. Open de hoes (de pagina van de hoes, tab 3D, of de kaart op Work → Desk) en klik
   **Measure** in de 3D-balk.
2. Klik twee punten op de hoes. Het punt springt naar een hoek van een ventilatiegat, het
   einde van een naad, een naad of de zoom als je er dichtbij klikt (de grijze tekst laat zien
   waarheen).
3. Je ziet drie getallen:
   - **Straight**: de rechte afstand (rode lijn);
   - **Height difference**: hoeveel hoger het tweede punt ligt;
   - **Along the fabric**: zoals een meetlint over de hoes loopt (blauwe stippellijn). Dit is
     het getal om met de genaaide hoes te vergelijken.
4. Meerdere metingen blijven staan; × haalt er één weg, **Clear all** alles. **Esc** wist een
   half gekozen punt. Slepen draait de hoes nog steeds. Op een tablet: twee keer tikken.

## Maten van de ventilatiegaten

Kies **Show ▾ → Vent sizes** in de 3D-balk. Bij elk gat staat op de hoes en in de tabel eronder:

- de opening, breedte × hoogte;
- ↕ de onderkant van de opening boven de zoom (onderrand van de hoes);
- ↔ links en rechts: van de zijkant van de opening, langs de onderkant, tot de naad ernaast
  (of tot de hoek van de hoes als die eerder komt). Links en rechts zoals je ervoor staat,
  van buiten.

Dit zijn dezelfde getallen als in het snijbestand, niet opnieuw geschat.

## Het logo op de vents

Kies **Show ▾ → Logo** in de 3D-balk (staat aan zodra **Vents** aan staat; je browser onthoudt
het). Op elke vent zie je de kap doorschijnend, met het blauwe kader en het woord LOGO waar het
logo op de genaaide kap komt: midden langs de onderkant van de vent, rechtop, leesbaar van
buiten. Het kader komt uit het snijbestand zelf (dezelfde maat en plek als op de kap P7 in de
DXF), dus de 3D kan niet iets anders laten zien dan wat de snijtafel tekent.

Op de kap in de DXF staan nu ook de stiklijnen (boven en opzij, onder open), **TOP: SEW TO
COVER** met een pijl omhoog, en **OPEN EDGE, INSERT** aan de onderrand. Het kader zit 3,5 cm
boven die onderrand (`features.vent_logo_above_edge_mm`, nog te bevestigen).

Staat er **Logo position not computed yet: run again**, dan is de hoes gemaakt voordat het
logo werd vastgelegd: bouw hem opnieuw (export). Een hoes met vents gaat daarna terug naar de
Desk, omdat de kap in het snijbestand verandert.

## De checklist (PDF)

**Check list (PDF)** in de 3D-balk, onder **More** op de Desk-kaart, bij **Pieces → Cut
pieces** en **Files** van de hoes, of op **Work → Workshop** ([workshop.md](workshop.md)). Pagina 1: de vier
zijden met genummerde gaten (V1, V2, …), de hoofdmaten, de rokhoogtes en per gat alle maten,
met een vakje voor wat je meet en een vakje OK (binnen ±0,5 cm). Daarna de panelen en naden.

## Gemeten waarden invullen (Desk)

Op de Desk-kaart, in de balk onderaan: **After sewing ▾ → Measured…**, vul in wat je gemeten
hebt (lege velden mag), druk daarna op **Fits** of **Does not fit**. Op **Work → Workshop**
zie je daarna per hoes: past / past niet, de notitie, hoeveel maten gemeten zijn en het
grootste verschil. Het verschil per maat wordt bewaard; als dezelfde afwijking op
meerdere hoezen terugkomt, ziet het leerprogramma dat (bijvoorbeeld "gaten zitten steeds 8 mm
te hoog").
