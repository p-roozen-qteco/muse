# Waveshare S3 1.8 V2: spoken replies

The existing BOOT interaction is unchanged: hold to record a voice note,
release to send it. With the speaker enabled, the S3 1.8 profile now requests
a spoken answer and plays Muse's MP3 reply while showing its text captions.
There is no live call and no new external text-to-speech account.

## Configuration and protocol

`CONFIG_MUSE_SPOKEN_REPLIES` is off by default and requires `MUSE_HATCH` and
PSRAM. The `sdkconfig.muse-waveshare-s3-18` overlay enables it. Existing build
directories must also enable it in their generated `sdkconfig` or be rebuilt
with the updated defaults. `CONFIG_MUSE_REALTIME_VOICE` remains off.

- At BOOT press, the enabled speaker selects `output_modality: "voice"` for
  the existing `/chat/stream` voice-note request. Muted and typed-console turns
  retain text modality. Muting before playback avoids requesting the MP3.
- A completed assistant message belonging to that turn is fetched through
  the existing authenticated Muse daemon session with
  `GET /api/voice/tts-stream?message_id=…`, accepting `audio/mpeg`.
  Message IDs are encoded as one query value; no supplied URL is fetched.
- A 404 retries `/voice/tts-stream` once. Other HTTP errors, connection resets,
  empty/invalid MP3, buffer overflow or 30 seconds without progress fall back
  to the already received text. Authentication failures are not retried on
  another route. Audio failure does not invent or replace the reply text.
- Existing bounded MP3 buffering, TCP backpressure, streaming decoding and
  conversion to 16 kHz mono feed the onboard ES8311 speaker path. Captions use
  the decoded playback duration. A new BOOT turn cancels the old audio stream;
  late packets cannot feed the next reply. The existing three-minute turn cap
  still applies, so unusually long answers may be cut off.

The route and modality contract comes from this repository's
[`linux/src/musegadget/link_client.py`](../../linux/src/musegadget/link_client.py)
(`send_voice`, `send_chat`, `stream_tts`). Backend support must still be checked
with the user's Muse account. This feature plays replies to a device voice
note; it is not a general player for unsolicited app attachments or music.

## Validation

The production request, stream-dispatch and MP3-decoding functions are exercised
by `tests/test_muse_spoken_replies.py`. Tests cover voice/text selection, mute,
query encoding, the one-time 404 fallback, HTTP refusals, timeouts, reset,
invalid/empty audio, buffer overflow, cancellation, stale streams and a real
MP3 delivered in 137-byte fragments. Existing reply correlation/caption tests
also run with the feature disabled.

ESP-IDF 6.0.1 builds passed for the S3 1.8 with the option enabled and the
S3 2.16 with it disabled. The personal S3 1.8 test image is
`999.0.0-s3audio-test1`, 2,166,784 bytes, with 48% of its 4 MB app slot free.
Across the full host run and focused environment retries, 832 distinct tests
passed and four optional tests were skipped (host VP8/x264 encoders, PSA
development libraries and the pinned PPK2 package). The retries supplied
CMake, ESP-IDF and Python cryptography; the simulator avatar add/remove test
passed with Ninja after failing with the local Make generator. No simulator
or other unrelated source was changed for those environment adaptations.

On 29 October 2026 a full 16 MB backup of the working screen/USB firmware was
saved before installation. All four flash writes verified; NVS was identical
before and after writing. USB status confirmed the new version, Wi-Fi,
retained Muse pairing, speaker enabled and volume 35%. The owner's local MP3
test was clearly audible. An actual spoken Muse answer is the remaining
end-to-end acceptance check; a successful local MP3 test alone does not prove it.
Personal images, credentials, backup contents and raw diagnostic logs stay local.

## Test on the first board

1. Follow the backup/flash procedure in
   [`waveshare-s3-18-display.md`](waveshare-s3-18-display.md). Preserve NVS and
   use the generated split `flash_args`, not an image from Muse Open 0.3.
2. Keep the speaker enabled and initially set volume to 35%.
3. Hold BOOT, ask a short question and release. Check the text and audible
   answer. Diagnostic logs should show a TTS GET and `reply audio: … Hz`.
4. Ask a second question while the first answer is playing. Confirm the first
   answer stops and that its late audio does not enter the next answer.
5. Mute the speaker and repeat: text should remain available. Re-enable the
   speaker for the next voice note and verify audio returns.
6. Recheck a photo from the Muse app, touch controls and screen blank/wake.
   Do not update the other four boards until these checks pass.

If text arrives without sound, inspect the local log for `reply audio: HTTP …`
or `reply audio unavailable (…)`. Keep tokens and conversation contents out
of shared logs. A 403 is an authorization/backend issue, not a speaker wiring
fault; a 404 on both routes means the service did not provide that audio.
