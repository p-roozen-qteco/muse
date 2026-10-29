# Waveshare S3 1.8 V2: photo and touch regression test

This profile is for the **ESP32-S3-Touch-AMOLED-1.8 V2**, with CO5300
display and CST820 touch. It does not support the original SH8601 revision.

The starting point is `q-teco/muse` branch `add-waveshare-s3-18`, commit
`1a996a12eb4bcfebd11b4c82aef7a330b8659844`. The owner reports that this
firmware runs but the screen freezes when a photo arrives from the Muse app,
and that touch/navigation is sluggish. The installed binary has not been
read back or matched to that commit. A serial trace of the freeze is still
needed to confirm the exact failure on the device.

## What changed

The Waveshare BSP 2.0.3 creates a QSPI CO5300 panel, but its high-level
`bsp_display_start_with_config()` registers it with
`lvgl_port_add_disp_rgb()`. On the S3, that RGB route installs RGB-panel
callbacks on the supplied panel object, and its partial-refresh path reports
the buffer ready immediately after starting a transfer. That is the wrong
interface and completion contract for this SPI panel. Small draw buffers
do not fix that mismatch.

The board now uses the BSP's lower-level panel and touch initialization with
Muse's existing `muse_lcd_bands` transport and `esp_lvgl_adapter` 0.6.4:

- Two 112-row RGB565 draw buffers use PSRAM (164,864 bytes total). Four
  bands cover the display instead of about 45 ten-row updates.
- Two fixed 5,888-byte internal DMA buffers carry the pixels. They are
  allocated before radio startup; a flush does not allocate a new bounce buffer.
- The existing transport returns the draw buffer only after its final
  transfer finishes. SPI work runs on the same core as the SPI interrupt.
- Brightness, including screen blank/wake, runs between completed transfers
  on the same sender task.
- The BSP's touch probe, panel x offset, orientation and even-pixel update
  windows remain in use. Touch setup finishes before rendering starts.

The BSP is pinned to 2.0.3. The chip pins, audio path, PMU rails, pairing,
partition layout and photo-download protocol are unchanged. There is no new
deep-sleep, video or external-speaker support in this change.

## Source evidence

- [Waveshare BSP source](https://github.com/waveshareteam/Waveshare-ESP32-components/blob/23a6012d5e87d27399cf90fb851cab3689e29159/bsp/esp32_s3_touch_amoled_1_8/esp32_s3_touch_amoled_1_8.c):
  `bsp_display_new`, `bsp_touch_new`, `bsp_display_lcd_init`.
- The registry's `waveshare/esp32_s3_touch_amoled_1_8` 2.0.3 package was
  inspected too; it has the same RGB registration.
- `espressif/esp_lvgl_port` 2.9.0 resolved during validation:
  `src/lvgl9/esp_lvgl_port_disp.c`, `lvgl_port_add_disp_rgb` and the flush
  callback. The older 2.6.2 source has the same mismatch.
- [ESP-IDF 6.0.1 RGB callback registration](https://github.com/espressif/esp-idf/blob/v6.0.1/components/esp_lcd/rgb/esp_lcd_panel_rgb.c)
  treats its handle as an RGB-panel object; it does not accept a CO5300 handle.
- Existing Muse implementation: `boards/muse_lcd_bands.[ch]` and
  `boards/board_waveshare_s3_216.c`.

## Build and host checks

Use ESP-IDF **6.0.1** and the `s3-18` profile, as described in
[`../AGENTS.md`](../AGENTS.md). From `esp32/`:

```sh
tools/muse/board.sh build s3-18
python3 -m unittest discover -s tests -p test_waveshare_s3_18_display.py -v
python3 -m unittest discover -s tests -p test_link_image_fetch.py -v
```

The display test executes the actual setup functions against fakes: it checks
the QSPI transport, bounded buffers, touch-before-render ordering, every
single-pixel update at this resolution, brightness serialization and failure
paths. It does not emulate the physical panel or its timing. The existing
image tests cover streaming and memory failure handling. The new host tests are discovered by the existing GitHub Actions host-test
job. The S3 1.8 firmware build was checked locally; adding its profile to the
remote build matrix requires a GitHub connection with workflow-write access.

A firmware image for pairing needs your Muse SDK token in its local generated
`sdkconfig`. Never put the token in Git, a public build log, or an issue. A
token-free compilation check is not a configured firmware release.

Validation on 29 October 2026:

- ESP-IDF 6.0.1 builds passed for `s3-18`, the default C5 and `s3-216`.
  The S3 1.8 application is 2,166,784 bytes; 48% of its 4 MB slot is free.
  All explicit settings in the S3 1.8 overlay reached its generated config.
- Across the full host run and the retry of environment-blocked modules,
  827 distinct tests passed. Four optional tests were skipped because host
  libvpx, x264, PSA Crypto or `ppk2-api==0.9.2` was unavailable.
  The retry used the configured cJSON path, local loopback permission, and
  Apple-clang equivalents for GNU linker flags; upstream cJSON deprecation
  warnings were allowed. No firmware/test source was changed for those adaptations.
- These were token-free compilation checks, as in the repository's CI.
  They were not flashed and are not published as configured releases.

Hardware installation check on 29 October 2026:

- A full 16 MB backup was saved privately before writing. Its transfer digest
  passed and its partition table matched this profile. The original app reported
  `999.0.0` and the Waveshare S3 1.8 board name.
- The owner confirmed that Muse appeared and touch responded with the first
  screen-fix build. The default UART-primary/USB-secondary console did not
  return application logs or status over USB. This overlay now selects native
  USB Serial/JTAG as the primary console, with no secondary console.
- The personal build `999.0.0-s3fix.c57b3a5-usb` was installed with all four
  flash writes verified. NVS was read back before starting the app and was
  byte-for-byte identical to its pre-write contents.
- A full restart with esptool 5.6.0's `watchdog-reset` exited the download mode
  that the simple RTS reset had retained. The boot log confirmed the version,
  `QSPI bands: 112 rows, 2 x 5888-byte DMA buffers`, and `UI up: 368x448`.
  USB status replies worked; Wi-Fi was connected and pairing was retained.
- No fatal boot markers appeared in the captured startup. Nonfatal messages
  included an already-installed GPIO ISR service, the panel initialization's
  3Ah override and disabled advanced LVGL gesture recognition.
- The owner subsequently confirmed that photo delivery worked and the screen
  was substantially more stable. The repeated stress sequence below remains
  to be completed. A local MP3 speaker test at 35% volume was clearly audible;
  this establishes output functionality, not a full audio quality measurement.
- Personal binaries, backups and raw logs contain private data and remain local.

For the experimental Muse audio-message playback commands, see
[`waveshare-s3-18-audio.md`](waveshare-s3-18-audio.md).

## Test on one board before updating the other four

1. Record the currently working firmware version and keep its original
   installer/binary. Before flashing, identify the serial port and back up
   the full 16 MB flash locally. That backup includes private pairing data:
   keep it out of GitHub. See the flashing instructions in `../AGENTS.md`.
2. Use this project's own `flash_args` with its build, not the old Muse Open
   0.3 merged-image instructions. This SDK uses a different partition layout.
   Preserve NVS and do not use `erase-flash`.
   This board has **PWR and BOOT**, not a separate RESET button. If automatic
   download fails, hold PWR for at least six seconds to switch off, hold BOOT,
   then briefly press PWR to power on; release BOOT after startup. After flashing,
   a simple USB reset may retain download mode. Power-cycle with PWR without
   holding BOOT, or use esptool 5.6.0's supported `watchdog-reset` on this S3.
   See the [Waveshare board instructions](https://www.waveshare.com/wiki/ESP32-S3-Touch-AMOLED-1.8).
3. Capture the boot log. Expect the board name, PSRAM, `UI up: 368x448`, and
   `QSPI bands: 112 rows, 2 x 5888-byte DMA buffers`. Note any allocation,
   SPI, panic or watchdog messages. Redact tokens and personal data before sharing.
4. Verify red/green/blue and white/black images, screen edges and all four
   touch corners. Swipe to settings, change brightness, return and talk.
5. Send the exact photo that previously froze the screen from the Muse app.
   Wait for completion, tap to dismiss, open settings and send a voice note.
   Repeat at least 20 times, including a landscape and a portrait photo.
6. Repeat photo delivery after screen blank/wake, and change brightness
   during a download. Check that audio still works and that a Wi-Fi reconnect
   does not leave the screen stuck.
7. If it freezes, save the serial log from before the transfer through the
   failure. Record whether BOOT still starts speech and whether the phone
   still sees the device online. These distinguish a blocked UI from a full
   device failure.

Physical photo delivery, touch responsiveness and long-running stability
remain to be verified on the owner's board. Do not describe this patch as a
confirmed hardware fix until those checks pass.
