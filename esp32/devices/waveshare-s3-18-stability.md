# Waveshare S3 1.8 V2: startup and voice recovery

`999.0.0-s3stable-test1` follows the owner-accepted `999.0.0-s3audio-test2`.
It fixes three failure paths identified in the 30 October 2026 code review.
These are reproduced software faults; they are not a diagnosis of the earlier
black-screen incident or the occasional Dutch transcription errors.

## Changes

- Session startup validates every required buffer, including each stream's
  line buffer. Partial initialization is released with the matching FreeRTOS
  allocation API. Readiness is published only after task creation succeeds.
  Three bounded attempts cover transient allocation/task failures; an explicit
  reconnect can retry after persistent failure. Buffer APIs reject access
  before startup completes. Optional realtime-call initialization runs once
  on the successfully created worker, avoiding repeated call allocations when
  session startup fails. Live calls remain disabled on the S3 1.8 profile.
- Delivery and terminal events are stored separately from the lossy caption
  queue. Their generation is checked when published and consumed, so stale
  replies cannot complete a newer request. Completion has priority over
  captions. End-of-upload and cancellation also survive a full command queue;
  a rejected start reports an error. The voice player has an independent
  210-second backstop (the session already has a 180-second cap). Caption
  processing is bounded per iteration so input and deadlines remain serviced.
- A microphone read failure cancels a partial upload and returns a capture
  error. The voice loop discards its buffer and pre-roll before returning to
  idle. Incomplete recordings never enter the retry queue. This also applies
  to failure while discarding playback tail or before the minimum hold time.

The display/touch transport, codec driver, microphone gain, sample rate,
normal pre-roll, voice-note payload and text-plus-audio commands are unchanged.
No language instruction is appended. Deliberately ending a valid recording at
the existing duration limit remains supported.

## Validation

ESP-IDF 6.0.1 builds pass for S3 1.8 with audio commands enabled and S3 2.16
with them disabled. The S3 1.8 app is 2,166,784 bytes, with 48% of its 4 MiB
application slot free. Security/flash settings and partition geometry are
unchanged; the private candidate uses the existing SDK token.

The full host suite runs **874 tests: 870 passed, four skipped** for unavailable
optional dependencies. This includes the existing display setup, touch,
brightness serialization, image, MP3, caption, BOOT, mute, stop, command
registration and normal voice-note tests.

Added regression coverage runs actual production functions or the complete
voice translation unit against deterministic fakes:

- Every startup allocation can fail once and recover; persistent queue,
  stream, MP3, line-buffer and task failures remain unavailable, release all
  tracked allocations and permit a later successful retry.
- Full caption queues cannot lose delivery/completion/error; late events
  cannot replace newer results; full command queues cannot lose end/cancel.
- 10,000 simulated turns complete with bounded queues, including old captions
  left queued between generations. This is not a hardware soak test.
- Missing events, missing completion after playback and continuous captions
  cannot make the player wait forever. Existing completion, interruption,
  mute, stop and handoff behavior still passes.
- Microphone failures at the first read, after a usable-length capture,
  after pre-roll, during playback-tail discard and while offline all fail
  cleanly. A following valid recording succeeds. The complete voice loop
  releases the failed recording without finalizing or retaining it, with
  realtime support both enabled and disabled.

The failure-injection memory tests use AddressSanitizer/UndefinedBehaviorSanitizer
and explicit allocation accounting. Host fakes do not prove hardware timing,
audibility, Wi-Fi reliability or multi-day stability.

## Hardware checks

Before installation, the connected board identified itself as the expected
Waveshare S3 1.8 running audio2. A fresh complete 16 MiB backup matches the
audio2 application and the candidate partition table. It is stored privately
alongside its SHA-256, with the NVS region extracted for comparison.

Physical checks and owner acceptance are recorded separately from the host
tests. A 48-hour run, battery cold starts, repeated Wi-Fi loss/recovery and
controlled Dutch speech comparisons remain necessary before calling this a
long-term stable release. The earlier black-screen cause is still unconfirmed.

Private firmware binaries, SDK configuration, flash backups and raw serial logs
must not be committed or attached to a public pull request.
