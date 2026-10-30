# S3 1.8: spoken answers and touch companion

This branch builds on the owner-confirmed `999.0.0-s3stable-test1` firmware.
The companion candidate is `999.0.0-s3pet-test1` for the Waveshare
ESP32-S3-Touch-AMOLED-1.8 V2. The SDK token, firmware binaries, device settings,
flash backups and private test logs stay outside Git.

## Using the new features

- Hold BOOT, ask an ordinary question, and release. With the speaker enabled
  and volume above zero, the gadget asks Muse to speak its answer here and show
  the same text. You no longer need to say “play it on my gadget”.
- Tap the idle face for a wink and a short happy reaction. Touch towards either
  side of the face to attract its gaze. Hold gently for a bigger happy reaction.
  Reactions fade on their own and make no sound.
- Swipe left for Settings as before. Touching the face during listening,
  thinking, speaking, or an error does not override that expression. The first
  touch that wakes the screen is reserved for waking it.
- Disable the speaker or set volume to zero **before** starting a recording for
  the original text-only request. BOOT still interrupts audio playback.

## What automatic speech does

`CONFIG_MUSE_AUTO_AUDIO_REPLIES` adds a short, separate text delivery preference
in the voice-note request's `message` field. It identifies this exact gadget by
its existing `homelink-xxxxxx` node ID and asks Muse to create speech using its
available tools, then invoke `audio.play_file` with the same answer as captions.
The preference can be visible in the phone app. It is not added to the WAV and
is not a transcription of something the owner said.

The microphone capture, gain, 16 kHz mono PCM, streaming WAV/base64 encoding,
`output_modality: text` and existing MP3 playback path are unchanged. Native
voice modality stays disabled because the earlier trial failed on this account.
No new speech provider or local text-to-speech engine is introduced.

Automatic delivery depends on Muse interpreting the preference and having
working speech tools. It is not a server-side guarantee. If generation or
playback fails, the preference asks for the text answer and a brief explanation,
without endless retries. Existing firmware timeouts and cancellation remain.
This preference applies to **BOOT voice notes**, not every message sent from the
phone app. The phone can still explicitly send audio to the gadget.

## Implementation and stability boundaries

- `CONFIG_MUSE_COMPANION_TOUCH` enables the touch controller on the S3 1.8;
  both new options default off for other boards.
- Interaction state belongs solely to the LVGL task. No allocations, speaker
  access or network calls occur in the touch callback or face updates.
- The default procedural avatar blends touch gaze into its existing idle gaze,
  leans slightly and winks. Speaking continues to use the live audio level.
  Happiness no longer replaces a listening or speaking mouth.
- Horizontal navigation, a lost touch, sleep, image/video overlays, the menu
  and mode changes cancel pending interaction state.
- Existing custom-avatar selection is preserved. Extra pose fields default
  to zero; a custom renderer may ignore them.
- Display transport, panel/touch drivers, audio drivers, partition layout and
  the preceding startup/audio/microphone reliability fixes are retained.

## Validation

The automated tests check the actual request-building and rendering code:
byte-for-byte preservation of recorded WAV data, streaming chunk boundaries,
per-gadget routing, mute/zero-volume fallback, typed-turn isolation, bounded
interaction state, gesture cancellation, and audio-expression priority. A
100,000-transition controller stress test runs under address/undefined-behavior
sanitizers. This is not a substitute for a multiday hardware soak.

The SDL/LVGL simulator supports `--board s3-18` (368×448) as well as the original
Watcher. Tests inject real pointer events through SDL/LVGL to exercise taps,
holds, navigation, wake-touch isolation and all busy face modes. Simulator
services are stubs: they do not test the physical panel, speaker, network or
microphone. Actual screen previews are also visually inspected.

Before flash: build S3 1.8 and S3 2.16 with ESP-IDF 6.0.1, run the full host
suite and simulator tests, make a fresh 16 MB flash backup, verify its app against
the accepted firmware and compare the partition table. Preserve and compare NVS.

Hardware acceptance must cover:

1. Normal start, image and touch, Wi-Fi and Muse connection.
2. BOOT: “Hoeveel is twee keer drie?” without any request to play audio.
   Confirm both spoken answer and text on the ESP32, and the phone transcript.
3. Tap, hold, swipe to Settings and back; repeat while audio is playing.
4. Muted BOOT question: text without speaker playback; restore the original
   speaker/volume afterwards. Confirm BOOT can still interrupt an answer.
5. Longer battery, reconnect and multi-hour use separately; do not infer these
   from the short acceptance test.

See [the preceding stability work](waveshare-s3-18-stability.md) and
[the audio command protocol](waveshare-s3-18-audio.md) for retained behavior and
remaining long-term validation.

### Candidate checks, 2026-10-30

- Full host suite: **889 tests, 885 passed, 4 dependency/hardware skips**.
  Initial failures were outdated test fixtures (the new source file and a
  disabled-feature no-op); the complete suite passed after updating them.
- Both S3 1.8 and S3 2.16 ESP-IDF 6.0.1 builds passed. The S3 1.8 app is
  2,166,784 bytes, leaving 48% of the 4 MB app slot free.
- Simulator: **12 CTest checks passed**, including pointer interactions in both
  layouts, custom-avatar source selection in the host suite, and the retained
  keyboard/settings checks. Built with warnings as errors and ASan/UBSan.
- The fresh 16 MB backup matches the accepted stability app; the candidate's
  partition table is identical. Changed application sources match the build
  copy. Four actual UI screenshots were inspected at 368×448.
- Hardware automatic-speech and touch acceptance is still pending; the results
  above do not claim a successful Muse service round trip or a multiday soak.
