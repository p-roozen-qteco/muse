# Grotere knoppen, herstartproef en duurmetingen

Kandidaat `999.0.0-s3tama-test2` bouwt voort op de door de eigenaar bevestigde
Tamagotchi. Eten, Rust/Wakker en Spelen zijn 60 px hoog in plaats van 40 px,
met grotere letters, duidelijkere indrukreactie en extra aanraakmarge. Het
karakter is iets kleiner om daarvoor ruimte te maken. Snelle tikken op
verschillende knoppen worden niet meer door een gedeelde wachttijd genegeerd.
Vegen op het gezicht blijft werken. Een kleine beweging op een knop wordt niet
naar de paginaveeg doorgegeven; buiten de knop loslaten annuleert de actie.

## Wat wordt gecontroleerd?

- **Bewaren/herstarten:** het echte 24-byte verzorgingsrecord wordt vóór en na
  een herstart uitgelezen en gecontroleerd. De nieuwe opstartlog vermeldt alle
  verzorgingswaarden, zodat ook het inladen in het actieve programma kan worden
  vergeleken. De controle wijzigt geen verzorgingswaarden of andere instellingen.
- **Bediening:** echte LVGL-aanraakgebeurtenissen testen hogere en zijdelingse
  raakpunten, vingerbewegingen, snelle knopwisselingen, annuleren, spel en
  gespreksvoorrang. Audio-, microfoon- en schermtransportcode blijven gelijk.
- **Duurtest:** de eerste meetperiode is 24 uur. Elke minuut worden alleen
  bestaande USB-status- en batterijdiagnostiek opgevraagd. We bewaren tijd sinds
  opstarten, verbindingen, vrij intern geheugen, grootste vrije geheugenblok,
  instellingen en batterijrapporten. De meetbestanden bevatten geen gesprekken,
  Wi-Fi-wachtwoorden of Muse-tokens.

Een USB-duurmeting controleert verbindingen, herstarts en geheugentrends. Ze
bewijst op zichzelf geen foutloze audio, touchscreen of batterijduur. Gebruik
het apparaat tijdens deze periode ook normaal voor korte gesprekken, aanraken
en een spelletje. Onverwachte herstarts, stilstaande audio en gemiste reacties
blijven afzonderlijke bevindingen.

## Meten op USB

Laat de Mac, Codex en de USB-verbinding beschikbaar. Slaap van de Mac, loshalen
van USB en gemiste antwoorden worden als gaten in de waarneming geregistreerd.
De monitor telt die tijd niet als succesvol waargenomen gebruik. Een mogelijke
herstart in een gat wordt apart aangegeven. Herhaalde metingen openen geen
opname, sturen geen bericht naar Muse, veranderen geen instellingen en resetten
het apparaat niet.

Vanuit `esp32`, met de Python-omgeving waarin pyserial staat:

```sh
python tools/muse/soak.py run --out /absolute/private/measurement-folder \
  --serial YOUR_BOARD_USB_SERIAL --firmware 999.0.0-s3tama-test2 \
  --hours 24 --interval 60
```

`summary --out ...` leest alleen de bestaande meetbestanden en opent geen USB.
Een tweede `run` op dezelfde map kan de oorspronkelijke periode vervolgen,
maar niet verlengen. Een bestandslot voorkomt twee gelijktijdige monitors.
Een andere firmware stopt de monitor; er wordt niet automatisch geflasht of
hersteld. `window_complete` betekent dat de geplande tijd verstreken is,
geen automatisch geslaagd resultaat. Beoordeel ook de werkelijk waargenomen
tijd, gaten, herstarts, verbindingen en geheugentrend.

## Batterijproef zonder USB

USB voedt en laadt het bord; daarmee meten we geen ontlaadduur. De bestaande
batterijlogger begint automatisch zodra USB eruit gaat en stopt wanneer USB
terugkomt. Na opnieuw aansluiten lezen we het rapport uit. Deze logger bewaart
om de 30 minuten en bij terugkeer van USB een samenvatting. Bij abrupt
spanningsverlies kan het laatste deel ontbreken; rapporteer de gemeten
ondergrens, niet een verzonnen exacte uitschakeltijd.

1. Rond de eerste USB-observatie af en laad de accu op. Noteer, indien bekend,
   de werkelijke capaciteit in mAh. Verander voor vergelijkbare metingen geen
   helderheid of volume tussendoor.
2. **Eerste stand-byproef:** druk kort PWR om het scherm te laten slapen, haal
   USB los en laat het bord vier uur ongemoeid. Sluit eerder aan als de accu
   bijna leeg raakt. De knop **Rust** verzorgt alleen het karakter en is geen
   elektrische slaapstand.
3. Sluit USB weer aan en lees `python tools/muse/power.py --json`. Het rapport
   bevat begin-/eindpercentage, spanning, tijd en het aandeel scherm-uit.
   Bewaar eerst het resultaat voordat een volgende proef begint.
4. **Gebruiksproef:** herhaal daarna met normaal gebruik, inclusief ongeveer
   één uur gesprek per dag. Houd bij hoeveel tijd het scherm aan stond en
   hoeveel er gesproken/gespeeld is. Alleen deze proef kan worden vergeleken
   met het doel van twee dagen gebruik.
5. Een eerste proef van vier uur bevestigt geen vijf dagen stand-by. Verleng
   pas op basis van de gemeten ontlading; de echte 120-uursdoelstelling blijft
   een afzonderlijke duurproef.

Percentages komen van de accumeter in stappen van 1%. Korte metingen en een
rechte extrapolatie daarvan leveren geen betrouwbare gegarandeerde looptijd.
De logger meet geen elektrische stroom. Zonder bekende accucapaciteit is er
ook geen onderbouwde omrekening naar gemiddeld mA.

## Aanwezige oudere meting

Vóór de wijziging was een opgeslagen, niet gedateerde batterijmeting aanwezig:
3.601 seconden, 100% naar 33%, 4.075 naar 3.530 mV, scherm-uit 0%. De precieze
firmware, accucapaciteit en gebruiksbelasting van die oudere meting zijn niet
vastgesteld. Daarom dient zij alleen als aanleiding om continu schermgebruik
en schermslaap afzonderlijk te meten, niet als resultaat van deze nieuwe test.

De huidige schermslaap is bovendien nog geen bevestigde zuinige stand-by:
voor deze boardport zijn displaypauze en CPU-slaap niet met deze wijziging
uitgebreid. We rapporteren wat de bestaande firmware werkelijk doet.

## Vastgelegde resultaten, 30 oktober 2026

- Op test1 bleef het volledige verzorgingsrecord bytegetrouw behouden na een
  normale herstart. De opgeslagen waarden bij die eerste proef waren buik 99,
  energie 79, plezier 87, vijf verzorgingsacties en zes bandpunten.
- Vóór installatie van test2 is de recentste voortgang opnieuw gelezen: buik
  99, energie 78, plezier 86, rust uit, speels-vlag aan, bonus 0, record 0,
  bandpunten 6, verzorgingsacties 5 en 34 minuten. Het kleine verschil met de
  eerdere proef komt door het normale tijdsverloop op het ingeschakelde bord.
- Na installatie én een daaropvolgende normale herstart laadt test2 alle tien
  waarden exact terug. Alle geschreven NVS-records zijn ongewijzigd. Beide
  opstartcontroles bereiken `starting` zonder crashmeldingen; Muse/Link komen
  online en bestaande geluids- en scherminstellingen blijven gelijk.
- **928 hosttests: 924 geslaagd, 4 bestaande skips.** Daarnaast slagen alle
  **13 simulator-CTestcontroles**, inclusief de uitgebreidere aanrakingstests.
  Beide S3-builds slagen met ESP-IDF 6.0.1. De 368×448-indeling is visueel bekeken.
- De eigenaar bevestigt dat de grotere knoppen op het echte scherm **duidelijk
  makkelijker werken**, ook bij een kleine vingerbeweging. De eerdere bevestiging
  van audio betreft test1; de audio- en microfooncode is in test2 ongewijzigd.

De USB-duurmeting is gestart op **30 oktober 2026 om 15:19:50 Nederlandse tijd**
en eindigt na 24 uur op **31 oktober om 15:19:50**. Een onafhankelijke
opvolgcontrole beoordeelt de rapporten elk uur. Alleen nieuwe bevindingen of
voltooiing worden gemeld. Automatische sluimering van de Mac wordt tijdelijk
voorkomen tot het einde van de meetperiode; de Mac en Codex moeten beschikbaar
blijven. Dit is de start van de duurtest, geen afgerond stabiliteitsresultaat.
De vieruursproef op accu wacht op het afronden van de USB-fase en het fysiek
loshalen van de kabel. De eigenaar geeft voor de aangesloten accu **200 mAh** op. Dat is een
opgegeven nominale capaciteit, geen gemeten bruikbare capaciteit. Gebruik die
waarde alleen voor een duidelijk als schatting aangeduide omrekening; de
daadwerkelijke looptijd moet uit de batterijproef blijken.

## Beoordeling van de ruststatus

`Saved` betekent dat de Muse-koppeling is opgeslagen, maar er op dat moment
geen bevestigde actieve gesprekssessie is. De firmware sluit een ongebruikte
sessie na tien minuten en zet de status dan bewust op `Saved`; een volgende
vraag maakt opnieuw verbinding. Dezelfde status kan ook kort tijdens herstel
voorkomen. Daarom telt de analyse deze waarde apart als `muse_saved_samples`,
zonder haar op zichzelf als uitval of als bewezen werkend gesprek te behandelen.
Wi-Fi-/Link-uitval en expliciete Muse-verbindingsfouten blijven meetellen.

De aanvankelijke beoordelaar telde `Saved` te streng als uitval. Rapporten met
`summary_schema: 2` gebruiken de gecorrigeerde beoordeling. De lopende sampler
blijft ongewijzigd doorlopen; zijn ruwe metingen blijven behouden. Gebruik
`soak.py summary` voor de actuele herberekening, ook wanneer het tijdens de
meetperiode geschreven `summary.json` nog de oudere beoordelaar gebruikt.
Er is hiervoor geen firmware gewijzigd, apparaat herstart of meting onderbroken.
