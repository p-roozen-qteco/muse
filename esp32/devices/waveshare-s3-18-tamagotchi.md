# Zachte Muse Tamagotchi — Waveshare AMOLED 1.8 V2

Testversie `999.0.0-s3tama-test1`, boven op de goedgekeurde automatische
spraakantwoorden en aanraakreacties van `999.0.0-s3pet-test1`.

## Bediening

- **Praten:** houd BOOT vast, spreek en laat los. De bestaande Muse-route geeft
  automatisch geluid en tekst; microfooninstellingen en audioformaat zijn gelijk.
- **Aaien:** tik op het gezicht voor een blijde reactie. Vasthouden laat het
  gezicht reageren; vegen naar links opent de bestaande instellingen.
- **Eten:** vult het buikje. Is het al vol, dan krijg je geen extra punten.
- **Rust / Wakker:** laat het karakter uitrusten of weer wakker worden. Rust is
  een verzorgingsstand, geen uitschakeling van de elektronica. BOOT blijft werken.
- **Spelen:** tik in 20 seconden zoveel mogelijk sterren aan. De ster verplaatst
  na elke treffer. Na afloop verschijnen de score en **Nog eens**. **Terug** stopt
  zonder beloning. Begin je een gesprek, dan sluit het spel onmiddellijk.

De zwarte achtergrond, zachte crèmekleur, roze wangen, glanzende ogen, rustige
ademhaling en kleine hartjes passen bij het AMOLED-scherm. Het gezicht kijkt mee,
knippert en beweegt zijn mond bij bestaande spraakactiviteit. Dit verandert geen
speakerhardware, stemkwaliteit of audiocodec.

## Wat wordt onthouden?

Buik, energie, plezier, ruststand, tijdelijke speelse stemming, verzorgingspunten,
bandniveau en spelrecord blijven na opnieuw opstarten behouden zodra ze zijn
opgeslagen. Het spel zelf wordt niet hervat. Er is geen straf of verval voor tijd
waarin het apparaat helemaal uit staat.

De beginwaarden zijn buik 75, energie 80 en plezier 70 (0–100). Tijdens ingeschakeld
gebruik daalt buik met 1 per 20 minuten, plezier met 1 per 30 minuten en energie
met 1 per 15 minuten. Tijdens rust stijgt energie met 1 per 2 minuten. Het gezicht
kiest uit tevreden, speels, slaperig, trek en rust; luisteren en antwoorden hebben
altijd voorrang. Aaien telt maximaal eens per 15 seconden. Een spelbeloning komt
eenmaal na afloop. Niveaus zijn speels en cosmetisch: zorg en gesprekken blijven
altijd beschikbaar, ook bij lage waarden.

Verzorgingsacties worden samengevoegd en buiten de schermbediening opgeslagen:
twee rustige seconden, minimaal 15 seconden tussen schrijfpogingen, en pas als
Muse niet bezig is met audio. Gewoon tijdsverloop wordt eens per vijf minuten
vastgelegd. Bij abrupt uitschakelen kunnen de laatste nog niet opgeslagen acties
of minuten verloren gaan. Tijdens een gesprek wacht het opslaan langer.

Voortgang staat in een eigen `muse_pet`-naamruimte met versie en checksum; Wi-Fi,
Muse-koppeling en bestaande instellingen blijven in hun eigen opslag. Een
onleesbaar of nieuwer record wordt bewaard en niet overschreven. Op het scherm
verschijnt dan **Voortgang bewaren lukt niet**. Ook schrijffouten worden zichtbaar
en later opnieuw geprobeerd met de nieuwste voortgang. Er is geen automatische
wisactie of fabrieksreset.

## Bouw en ontwerp

De S3 1.8-overlay schakelt `CONFIG_MUSE_SOFT_AVATAR=y` en `CONFIG_MUSE_PET=y` in.
Andere overlays houden hun bestaande standaard. Een eigen avatar in
`components/muse/avatar/muse_pixel.c` houdt voorrang. De verzorgingsindeling
wordt alleen op een rechthoekig scherm van minimaal 320×400 gebruikt.

Gebruik ESP-IDF **6.0.1** en de bestaande S3 1.8-bouwprocedure. De nieuwe renderer
gebruikt eenmaal 64 KiB PSRAM voor 128×128 RGB888; de bestaande stripdecoder zet
dat met interpolatie en dithering om naar RGB565. Er is geen allocatie per frame.
Bij allocatiefalen blijft een klein intern raster beschikbaar. Spel en verzorging
werken lokaal zonder extra cloudverkeer. De bestaande schermtransportcode,
BOOT-opname, MP3-afspeler, netwerkroutes en automatische antwoordvoorkeur zijn
niet aangepast. Antwoordtekst krijgt wel een eigen ruimte en zachter lettertype.

De desktoppreview bouwt met `-DMUSE_SIM_PET=ON`. Zie de
[simulatorhandleiding](../simulator/README.md). De simulator test de echte UI en
het echte karakter; hij emuleert geen ESP32-timing, fysieke audio of batterij.

## Controle vóór en na installatie

1. De petkern, renderer en opslagwerker testen met geheugen- en foutcontroles:
   bewaren/herstellen, corrupt record, mislukte allocatie, schrijffout, nieuwste
   wachtrij-item, audio-uitstel, scoregrenzen en één beloning per spel.
2. De echte LVGL-interface testen met aanraakgebeurtenissen: verzorgen,
   herstartbestand, sterren, annuleren, slaap, instellingen en gespreksvoorrang.
3. De volledige hosttestreeks en zowel S3 1.8 als S3 2.16 bouwen.
4. Volledige 16 MB-back-up maken; huidige app en partitietabel vergelijken.
   Alleen de nieuwe firmwaresegmenten schrijven. Geen NVS wissen.
5. Op het apparaat: opstartregel `starting`, verbindingen, instellingen,
   beeld/touch, gewone BOOT-vraag met automatisch geluid én tekst, en starten
   met praten terwijl het spel openstaat controleren.
6. Verzorg iets, wacht zonder audio minstens 20 seconden, herstart gecontroleerd
   en controleer dat de waarden zijn teruggekomen.

Korte tests bewijzen geen meerdaagse stabiliteit of batterijduur. Die blijven
aparte duurproeven na deze functieronde.
