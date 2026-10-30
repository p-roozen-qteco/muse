# Rood balletje — Waveshare S3 AMOLED 1.8 V2

Kandidaat `999.0.0-s3tama-test3` voegt een lokaal balansspel toe aan test2.

## Spelen

1. Tik op **Spelen**. Kies **Rood balletje** of het bestaande **Sterren vangen**.
2. Houd het apparaat met het scherm naar boven, ongeveer vlak en één seconde
   stil. Het spel ijkt de houding waarin je het vasthoudt.
3. Kantel voorzichtig links/rechts en voor/achter. Houd het rode balletje
   **30 seconden binnen het kader**. Een lichte wisselende drift maakt het een
   balansuitdaging. De timer telt de daadwerkelijk verwerkte speeltijd.
4. Bij de rand stopt de ronde. **Nog eens** begint opnieuw, inclusief ijking.
   **Terug** sluit het spel. Houd bij een mislukte ijking het bord vlakker en stil.
5. **BOOT** blijft de praatknop. Luisteren, antwoorden, schermslaap, instellingen
   en ontvangen media sluiten het spel. Je hoeft het niet eerst zelf te sluiten.

Een voltooide ronde geeft een kleine blije reactie en, als Muse wakker is en
plezier nog niet vol is, één verzorgingsbeloning. Voortijdig afsluiten en een
sensorfout geven geen beloning. **Beste** is de beste balanstijd sinds opstarten;
het bestaande sterrenrecord en alle opgeslagen verzorgingswaarden blijven
ongewijzigd van formaat. Een herstart begint geen lopende ronde opnieuw.

De 200 mAh-accu is de door de eigenaar opgegeven nominale capaciteit. Dit spel
gebruikt het scherm en de bewegingssensor en is geen zuinige stand-bymodus.

## Sensor en behoud van bestaande functies

De QMI8658 bevat een versnellingsmeter en gyroscoop. Voor blijvende kantelhoek
gebruiken we de zwaartekrachtmeting van de versnellingsmeter, zonder het verloop
van geïntegreerde gyroscoopmetingen. Schermassen volgen de Waveshare-demo:
`x = -sensor-y`, `y = sensor-x`. De gyroscoop blijft uit.

Bron: [Waveshare S3 1.8, vastgezet op 78e13f8](https://github.com/waveshareteam/ESP32-S3-Touch-AMOLED-1.8/tree/78e13f852929c2ab4f9d5e0ad1c50ea378dbf2b4),
`examples/esp-idf/92_qmi8658_imu`, de V2 SensorLib-registerdefinities en
`firmware/brookesia/components/Gravitysphere/Gravitysphere.cpp`.
De eigen kleine driver gebruikt deze registerfeiten; er is geen vendorcode gekopieerd.

- De bestaande I2C-bus blijft op SDA15/SCL14. Alleen identiteit 0x05 wordt
  geaccepteerd op 0x6a/0x6b. Een ontbrekende sensor onderbreekt het opstarten niet.
- Accelerometer: ±4g, 62,5 Hz met laagdoorlaatfilter, uitlezen maximaal 25 Hz.
  Buiten het spel worden accelerometer en gyroscoop uitgeschakeld.
- Geen nieuwe taak of dynamische allocaties voor de sensor of spelberekening.
  De bestaande invoertaak leest de sensor; LVGL leest uitsluitend een kort
  vergrendelde kopie. Busbewerkingen hebben een eindige timeout van 10 ms per
  transactie en een foutpauze van één seconde. IDF serialiseert de gedeelde bus.
- Ontbrekende, niet-eindige, onwaarschijnlijke of verouderde metingen bewegen
  het balletje niet en verhogen de score niet. Een langere onderbreking stopt
  de ronde met een melding. IJking vereist meerdere verse, rustige metingen.
- Beweging heeft filtering, dode zone, snelheidsgrenzen en kleine rekenstappen.
  Na een onderbreking wordt geen lange tijdsprong ingehaald.
- Schermtransport, codec, microfoon, audioweergave, gespreksvoorkeur, netwerk en
  het bestaande 24-byte verzorgingsrecord zijn niet veranderd.

## Controle

De hosttests gebruiken de echte spelkern met adres-/geheugencontroles:
kantelrichtingen, randen, winnen, onrustige ijking, verticale houding, ontbrekende
of vastgelopen metingen, niet-eindige waarden, klokonderbreking en 2.000 rondes.
De echte sensordriver wordt met een nagebootste bus getest op foutieve identiteit,
ontbrekende sensor, instelfouten, asomzetting, oude samples, slaapstand,
gespreksvoorrang en begrensde herstelpogingen.

De LVGL-simulator bedient echte knoppen en gesimuleerde kantelingen, inclusief
opnieuw proberen, stoppen, instellingen, slaap en alle gespreksstanden. De
bestaande verzorging, sterren en opslagtests blijven onderdeel van de reeks.
De simulator bewijst geen fysieke sensororiëntatie, geluid of ESP32-timing.

Installatie vereist een verse volledige back-up, behoud van de partitietabel,
herstelvergelijking van alle tien verzorgingsvelden, dezelfde gebruikersinstellingen
en een opstartlog zonder crashlus. Daarna bevestigt de eigenaar fysieke
kantelrichtingen, touch en een BOOT-vraag met automatisch geluid én tekst.

## Duurtest per firmware

De test2-USB-ronde is voor deze gevraagde functie-update bewust afgesloten:
40 meetpogingen, 39 geslaagd, ongeveer 40 minuten verstreken en 37 minuten
waargenomen dekking. Geen gedetecteerde herstarts of expliciete verbindingsfouten.
Eén ontbrekende statusmeting herstelde de volgende minuut. `Saved` betekent een
bewaarde Muse-sessie zonder actuele bereikbaarheidsbevestiging. Dit is een
onvoltooide USB-observatie, geen geslaagde 24-uurstest en geen batterijmeting.

Een volgende duurtest gebruikt een nieuwe meetmap, firmwareversie en starttijd.
De oude meetgegevens en back-up worden privé bewaard. Tijdens de installatie
is de geplande opvolging gepauzeerd om geen twee USB-lezers tegelijk te starten.

## Geautomatiseerde resultaten, 30 oktober 2026

- **945 hosttests:** 941 geslaagd en 4 bestaande skips voor externe
  afhankelijkheden/hardware. Inclusief de 14 nieuwe sensor-/spelkerntests.
- **13 simulatorcontroles geslaagd** met ASan/UBSan, echte LVGL-aanrakingen,
  gesimuleerde kanteling en behoud van de eerdere spel-/verzorgingsproeven.
- Beide S3-varianten bouwen met ESP-IDF 6.0.1. De S3 1.8-app is 2.166.784
  bytes; 48% van de app-partitie blijft vrij. Nieuwe sensor-/spelobjecten zijn
  gelinkt en de partitietabel is bytegelijk aan test2.
- De verse volledige 16 MB-back-up bevat exact de eerder geaccepteerde
  test2-app. Het nieuwe firmwarepakket is privé en heeft bestandscontrolesommen.

Fysieke kantelrichting en geluid worden na installatie apart gecontroleerd.
Een nieuwe 24-uurstest is nog geen afgeronde stabiliteits- of batterijproef.

## Installatie op het bord

Test3 is geïnstalleerd; alle vier firmwaresegmenten zijn geverifieerd.
Het bord bereikt `starting`, herkent de QMI8658 en verbindt met Wi-Fi, Muse en
Link zonder crashmeldingen in de opstartregistratie. Alle tien direct vóór het
flashen opgeslagen verzorgingsvelden zijn exact teruggekomen. Volume 100,
speaker aan, microfoonversterking 30 dB, helderheid 50 en slaapinstelling 0 zijn
behouden. Dit bevestigt de softwarestart en sensoridentiteit, nog niet de
fysieke kantelrichting of het hoorbare antwoord tijdens dit spel.

De nieuwe USB-observatie is gestart op **30 oktober 2026 om 16:15 CET** en loopt
maximaal tot **31 oktober om 16:15 CET**. De eerste status-/powermeting is geslaagd.
De geplande opvolging is hervat voor deze nieuwe meetronde. De fysieke
spel-/audiovragen zijn nog niet beantwoord; dit wordt niet als goedgekeurd
geboekt. Accu-ontlading is nog niet getest.
