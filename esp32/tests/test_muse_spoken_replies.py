# Copyright (c) Meta Platforms, Inc. and affiliates.
# SPDX-License-Identifier: Apache-2.0
"""Run production voice-reply requests, MP3 decoding and stream handlers on host."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SpokenReplies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        out = Path(cls.tmp.name)
        src = (ROOT / 'components/muse/muse_chat_session.cpp').read_text()

        def section(start, end):
            a = src.index(start)
            return src[a:src.index(end, a)]

        code = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>
#include "host_compat.h"
#define MINIMP3_IMPLEMENTATION
#include "minimp3.h"
#include "muse_chat_priv.h"
#ifndef CONFIG_MUSE_SPOKEN_REPLIES
#define CONFIG_MUSE_SPOKEN_REPLIES 1
#endif
#define CONFIG_MUSE_AUDIO_COMMANDS 1
static const char *TAG = "test";
static void host_log(const char *, const char *, ...) {}
#define ESP_LOGI(...) host_log(__VA_ARGS__)
#define ESP_LOGW(...) host_log(__VA_ARGS__)
''' + section('#define MIC_RATE', '/* ---- Voice task') + section('enum kind_t', '/* ---- The current turn') + section('enum phase_t', '/* 10 KB') + r'''
static turn_t s_turn;
static char s_reply_shown[EV_TEXT];
static int64_t s_marks[8], clock_us = 1000;
static int captions, requests, resets;
static bool speaker_on = true, request_fails, explicit_file;
static std::string last_path, last_verb, last_accept, sent_body, last_range;
static std::atomic<uint32_t> s_gen{1};
static int16_t pcm[MINIMP3_MAX_SAMPLES_PER_FRAME], pcm16[MINIMP3_MAX_SAMPLES_PER_FRAME];
static int16_t *s_pcm = pcm, *s_pcm16 = pcm16;
static uint8_t mp3[MP3_BUF], note[NOTE_PART_BYTES];
static char texts[MAX_MSGS * TEXT_MAX];
static std::vector<int16_t> output;
static int s_out;
static size_t queue_used;
static size_t xStreamBufferSpacesAvailable(int) { return OUT_BYTES - queue_used; }
static size_t xStreamBufferSend(int, const void *p, size_t n, int) {
    assert(n <= OUT_BYTES - queue_used);
    auto samples = static_cast<const int16_t *>(p);
    output.insert(output.end(), samples, samples + n / 2);
    queue_used += n;
    return n;
}
enum mark_t { M_TTS, M_MP3, M_AUDIO };
static void mark(mark_t) {}
static int64_t now_us() { return clock_us; }
bool muse_settings_speaker_on() { return speaker_on; }
bool muse_hatch_configured() { return true; }
static bool ensure_connected() { return true; }
static void emit(muse_hatch_ev_t, const char *) {}
void muse_hatch_console(const char *, const char *, const char *, ...) {}
void muse_hatch_wav_header(uint8_t *, uint32_t) {}
static void show_reply_start(const msg_t &) { captions++; }
''' + section('static stream_t *find_stream(', 'static bool send_reset(') + r'''
static bool send_reset(int64_t id) {
    if (id) { resets++; close_stream(find_stream(id)); }
    return true;
}
static int64_t open_stream(kind_t kind, const char *verb, const char *path,
                          const char *, const char *accept, const char *, bool, const char *range = nullptr) {
    static int64_t next_id = 10;
    requests++;
    last_path = path; last_verb = verb; last_accept = accept ? accept : ""; last_range = range ? range : "";
    if (request_fails) return 0;
    for (auto &s : s_streams) if (s.kind == K_NONE) {
        s = stream_t{}; s.kind = kind; s.id = next_id++; s.msg = -1;
        return s.id;
    }
    return 0;
}
static bool send_body(int64_t, const uint8_t *p, size_t n, bool) {
    sent_body.assign(reinterpret_cast<const char *>(p), n); return true;
}
''' + section('static void resampler_init(', '/* Ends the turn once its reply is in;') + section('static bool turn_start(', 'static void turn_begin(') + section('static bool open_note(void)\n{', '/* Moves the mic') + section('/* Captions remain available', '/* Ends the turn once the reply is complete') + r'''
// Wire views and unrelated handlers are fakes; production dispatch is unchanged.
struct ConstByteSpan {
    const uint8_t *p = nullptr; size_t n = 0;
    const uint8_t *data() const { return p; }
    size_t size() const { return n; }
    bool empty() const { return !n; }
};
struct cJSON {};
static void on_event(cJSON *) {}
static void on_dictation_line(cJSON *) {}
static void feed_lines(stream_t *, const uint8_t *, size_t, void (*)(cJSON *)) {}
static void on_dictation_end(bool) {}
static void on_chat_ack(stream_t *) {}
struct ApplicationResponseView { int status = 0; ConstByteSpan body; bool end_body = false; };
enum class ServiceFrameKind { Response, BodyChunk, Reset };
struct DecodedServiceFrame {
    int64_t stream_id = 0;
    ServiceFrameKind kind = ServiceFrameKind::Response;
    ApplicationResponseView response;
    struct { ConstByteSpan data; bool end_body = false; } body_chunk;
    struct { std::string reason; } reset;
};
''' + section('static void stream_data(', '/* Handles whatever the server sent.') + r'''
static void begin(bool typed = false) {
    turn_finish();
    output.clear(); queue_used = 0; captions = requests = resets = 0;
    request_fails = false; clock_us = 1000;
    s_turn.mp3 = mp3; s_turn.note = note; s_turn.texts = texts;
    assert(turn_start(++s_gen, typed));
    s_turn.phase = P_WAIT_REPLY;
    if (explicit_file) {
        s_turn.audio_source = MUSE_AUDIO_FILE;
        strlcpy(s_turn.audio_target, "/workspace/reply ?#.mp3", sizeof(s_turn.audio_target));
    }
}
static void reply() {
    s_turn.nmsgs = 1;
    auto &m = s_turn.msgs[0];
    strlcpy(m.id, "reply /?&+\xc3\xa9", sizeof(m.id));
    strlcpy(texts, "This is the spoken answer.", sizeof(texts));
    m.len = strlen(texts); m.done = true; m.tts = TTS_QUEUED;
    start_tts();
}
static void response(int64_t id, int status, bool end = false) {
    DecodedServiceFrame f;
    f.stream_id = id; f.response.status = status; f.response.end_body = end;
    assert(on_frame(f));
}
static void chunk(int64_t id, const uint8_t *p, size_t n, bool end = false) {
    DecodedServiceFrame f;
    f.stream_id = id; f.kind = ServiceFrameKind::BodyChunk;
    f.body_chunk.data = {p, n}; f.body_chunk.end_body = end;
    assert(on_frame(f));
}
static void fallback_ok() {
    assert(s_turn.silent && !s_turn.tts_id && !s_turn.mp3_len);
    assert(s_turn.msgs[0].tts == TTS_ACTIVE && captions >= 1);
    assert(!strcmp(texts, "This is the spoken answer."));
    for (int i = 0; s_turn.tts_msg >= 0 && i < 100; i++) { queue_used = 0; decode(); }
    assert(s_turn.tts_msg == -1 && s_turn.msgs[0].tts == TTS_FINISHED);
}
static void modality() {
    for (bool enabled : {true, false}) {
        speaker_on = enabled; begin();
        assert(s_turn.spoken == enabled && open_note());
        assert(last_path == "/chat/stream" && last_verb == "POST");
        auto expected = enabled ? MUSE_HATCH_NOTE_HEAD_VOICE : MUSE_HATCH_NOTE_HEAD;
        assert(sent_body == expected && s_turn.body_sent == strlen(expected));
        reply();
        assert(s_turn.silent != enabled);
        assert(requests == (enabled ? 2 : 1));
    }
    speaker_on = true; begin(true);
    assert(!s_turn.spoken);
    begin(); speaker_on = false; reply();
    assert(s_turn.silent && requests == 0); // muted before playback
}
static void routes() {
    begin(); reply();
    assert(!s_turn.silent && captions == 1);
    assert(last_verb == "GET" && last_accept == "audio/mpeg");
    assert(last_path == "/api/voice/tts-stream?message_id=reply%20%2F%3F%26%2B%C3%A9");
    auto old = s_turn.tts_id;
    response(old, 404);
    assert(requests == 2 && resets == 1 && s_turn.tts_id != old);
    assert(last_path == "/voice/tts-stream?message_id=reply%20%2F%3F%26%2B%C3%A9");
    response(old, 500); // response for cancelled route must not affect retry
    assert(!s_turn.silent);
    response(s_turn.tts_id, 404);
    assert(requests == 2); fallback_ok();
    for (int status : {301, 400, 401, 403, 429, 500}) {
        begin(); reply(); response(s_turn.tts_id, status);
        assert(requests == 1); fallback_ok();
    }
}
static void failures() {
    begin(); request_fails = true; reply(); fallback_ok();
    begin(); reply(); clock_us += TTS_STALL_US + 1; start_tts(); fallback_ok();
    begin(); reply(); response(s_turn.tts_id, 200, true); decode(); fallback_ok();
    begin(); reply(); response(s_turn.tts_id, 200);
    const uint8_t junk[] = "not MP3";
    chunk(s_turn.tts_id, junk, sizeof(junk), true); decode(); fallback_ok();
    begin(); reply(); response(s_turn.tts_id, 200);
    s_turn.mp3_len = MP3_BUF - 2;
    chunk(s_turn.tts_id, junk, sizeof(junk)); fallback_ok();
    begin(); reply();
    DecodedServiceFrame f;
    f.stream_id = s_turn.tts_id; f.kind = ServiceFrameKind::Reset;
    assert(on_frame(f)); fallback_ok();
}
static void cancelled() {
    begin(); reply(); auto old = s_turn.tts_id;
    response(old, 200); turn_finish();
    assert(!find_stream(old) && !s_turn.tts_id && s_turn.tts_msg == -1);
    begin(); reply(); auto current = s_turn.tts_id;
    const uint8_t junk[] = {1, 2, 3};
    response(old, 200); chunk(old, junk, sizeof(junk), true);
    assert(!s_turn.mp3_len && s_turn.tts_id == current && !s_turn.silent);
    // An unrelated stale stream is also unable to cancel current speech.
    auto stale = open_stream(K_TTS, "GET", "/unused", nullptr, nullptr, nullptr, true);
    find_stream(stale)->msg = 0;
    response(stale, 403);
    assert(s_turn.tts_id == current && !s_turn.silent);
}
static void file_errors() {
    explicit_file = true; begin(); reply();
    assert(last_path == "/fs/raw/workspace/reply%20%3F%23.mp3");
    response(s_turn.tts_id, 404);
    assert(requests == 1 && s_turn.phase == P_IDLE && !s_turn.tts_id);
    begin(); reply(); response(s_turn.tts_id, 200, true); decode();
    assert(s_turn.phase == P_IDLE && !s_turn.silent);
}
static void file_ranges() {
    explicit_file = true; begin(); reply();
    assert(last_range == "bytes=0-32767");
    auto first = s_turn.tts_id;
    response(first, 206);
    static uint8_t block[AUDIO_FILE_CHUNK] = {};
    chunk(first, block, sizeof(block), true);
    assert(s_turn.tts_id != first && !s_turn.mp3_ended);
    assert(s_turn.audio_offset == AUDIO_FILE_CHUNK && s_turn.mp3_len == AUDIO_FILE_CHUNK);
    assert(last_range == "bytes=32768-65535");
    response(s_turn.tts_id, 416);
    assert(s_turn.mp3_ended && !s_turn.tts_id);
    // A server ignoring the second range must not replay the whole file.
    begin(); reply(); response(s_turn.tts_id, 206);
    chunk(s_turn.tts_id, block, sizeof(block), true);
    response(s_turn.tts_id, 200);
    assert(s_turn.phase == P_IDLE);
    // Oversized first responses are stopped within the fixed buffer.
    begin(); reply(); response(s_turn.tts_id, 200);
    chunk(s_turn.tts_id, block, sizeof(block));
    chunk(s_turn.tts_id, block, 1);
    assert(s_turn.phase == P_IDLE);
}
static void original_input() {
    speaker_on = true; begin();
    assert(!s_turn.spoken && open_note());
    assert(sent_body == MUSE_HATCH_NOTE_HEAD);
}
static void ranged_playback(const char *file) {
    std::ifstream in(file, std::ios::binary);
    std::vector<uint8_t> sample((std::istreambuf_iterator<char>(in)), {}), bytes;
    for (int i = 0; i < 3; i++) bytes.insert(bytes.end(), sample.begin(), sample.end());
    assert(bytes.size() > 2 * AUDIO_FILE_CHUNK);
    explicit_file = true; begin(); reply();
    for (size_t off = 0; off < bytes.size();) {
        auto id = s_turn.tts_id;
        assert(id && s_turn.audio_offset == off);
        response(id, 206);
        size_t end = std::min(off + AUDIO_FILE_CHUNK, bytes.size());
        while (off < end) {
            size_t n = std::min(size_t(137), end - off);
            chunk(id, bytes.data() + off, n, off + n == end);
            off += n; decode();
            if (queue_used > OUT_BYTES / 2) queue_used = 0;
        }
    }
    for (int i = 0; s_turn.tts_msg >= 0 && i < 100; i++) { queue_used = 0; decode(); }
    assert(s_turn.tts_msg == -1 && s_turn.msgs[0].tts == TTS_FINISHED);
    assert(requests == 3 && !s_turn.tts_id && !s_turn.mp3_len);
    assert(output.size() > 170000 && output.size() < 180000);
    assert(s_turn.msgs[0].pcm_frames == output.size());
}
static void playback(const char *file) {
    std::ifstream in(file, std::ios::binary);
    std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(in)), {});
    assert(bytes.size() > 10000);
    begin(); reply(); auto id = s_turn.tts_id;
    // Body without a successful response head is not decoded.
    chunk(id, bytes.data(), 100);
    assert(!s_turn.mp3_len);
    response(id, 200);
    size_t off = 0;
    for (; off < bytes.size();) {
        size_t n = std::min(size_t(137), bytes.size() - off);
        chunk(id, bytes.data() + off, n, off + n == bytes.size());
        off += n; decode();
        if (queue_used > OUT_BYTES / 2) queue_used = 0;
    }
    for (int i = 0; s_turn.tts_msg >= 0 && i < 100; i++) { queue_used = 0; decode(); }
    assert(s_turn.tts_msg == -1 && s_turn.msgs[0].tts == TTS_FINISHED);
    assert(!s_turn.silent && captions == 1 && !s_turn.mp3_len && !s_turn.tts_id);
    assert(output.size() > 58000 && output.size() < 60000);
    assert(std::any_of(output.begin(), output.end(), [](int16_t n) { return n != 0; }));
    assert(s_turn.msgs[0].pcm_frames == output.size());
    // A new generation prevents decoded samples reaching the playback queue.
    begin(); reply(); id = s_turn.tts_id; response(id, 200); ++s_gen;
    chunk(id, bytes.data(), bytes.size(), true); decode();
    assert(output.empty());
}
int main(int argc, char **argv) {
    assert(argc == 3);
    switch (atoi(argv[1])) {
    case 0: modality(); break;
    case 1: routes(); break;
    case 2: failures(); break;
    case 3: cancelled(); break;
    case 4: playback(argv[2]); break;
    case 5: explicit_file = true; playback(argv[2]); break;
    case 6: file_errors(); break;
    case 7: original_input(); break;
    case 8: file_ranges(); break;
    case 9: ranged_playback(argv[2]); break;
    default: return 2;
    }
}
'''
        (out / 'spoken.cpp').write_text(code)
        cls.binary = out / 'spoken'
        command = [*shlex.split(os.environ.get('CXX', 'c++')), '-std=c++17',
                   '-Wall', '-Wextra', '-Werror', '-O1',
                   '-I', str(ROOT / 'tests'), '-I', str(ROOT / 'components/muse'),
                   '-I', str(ROOT / 'components/minimp3/include'),
                   str(out / 'spoken.cpp'), '-o', str(cls.binary)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

        cls.file_binary = out / 'file_only'
        command[-1] = str(cls.file_binary)
        command.insert(1, '-DCONFIG_MUSE_SPOKEN_REPLIES=0')
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    def run_case(self, case, file_only=False):
        result = subprocess.run([str(self.file_binary if file_only else self.binary), str(case),
                                 str(ROOT / 'components/muse/test_reply.mp3')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_mp3_continues_across_three_file_ranges(self):
        self.run_case(9, file_only=True)

    def test_request_modality_respects_speaker_and_typed_turns(self):
        self.run_case(0)

    def test_native_route_encoding_and_404_only_legacy_fallback(self):
        self.run_case(1)

    def test_failure_timeout_empty_and_invalid_audio_keep_captions(self):
        self.run_case(2)

    def test_cancellation_and_stale_streams_cannot_affect_next_reply(self):
        self.run_case(3)

    def test_fragmented_mp3_reaches_speaker_queue_with_caption_timing(self):
        self.run_case(4)

    def test_vm_file_mp3_plays_without_changing_boot_modality(self):
        self.run_case(5, file_only=True)
        self.run_case(7, file_only=True)

    def test_file_failure_has_no_native_route_retry_or_fake_silent_success(self):
        self.run_case(6, file_only=True)

    def test_vm_audio_uses_bounded_ranges_and_rejects_ignored_ranges(self):
        self.run_case(8, file_only=True)
