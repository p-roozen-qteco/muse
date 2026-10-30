# Copyright (c) Meta Platforms, Inc. and affiliates.
# SPDX-License-Identifier: Apache-2.0
"""Production speaker loop: completion, failure, mute, BOOT and handoff."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class VoiceAudioMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        out = Path(cls.tmp.name)
        src = (ROOT / 'components/muse/muse_voice.c').read_text()
        start = src.index('static bool hatch_reply(')
        player = src[start:src.index('\n}\n', start) + 3]
        limit = next(line for line in src.splitlines() if line.startswith('#define REPLY_WAIT_MAX_US'))
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include "host_compat.h"
#include "muse_chat.h"
#define CONFIG_MUSE_AUDIO_COMMANDS 1
#define MUSE_AUDIO_CHUNK 320
#define MUSE_AUDIO_RATE 16000
#define MUSE_CAPTION_MAX 400
#define MUSE_MODE_THINKING 2
#define MUSE_MODE_SPEAKING 3
#define MUSE_PTT_DOWN 1
#define ESP_OK 0
#define pdMS_TO_TICKS(x) (x)
typedef int esp_err_t;
static const char *TAG = "test";
static void host_log(const char *tag,const char *fmt,...) { (void)tag; (void)fmt; }
#define ESP_LOGI(...) host_log(__VA_ARGS__)
#define ESP_LOGW(...) host_log(__VA_ARGS__)
static atomic_bool s_audio_stop, s_shutdown;
static bool enabled=true, pending, interrupt, write_fails, input_error;
static bool no_events, lose_done, caption_storm;
static int volume=35, event_step, writes, reads, cancels, polls;
static int64_t clock_us;
static int64_t clock_step=20000;
static bool audio_pending(void) { return pending; }
static bool muse_settings_speaker_on(void) { return enabled; }
static int muse_settings_volume(void) { return volume; }
static int64_t esp_timer_get_time(void) { clock_us+=clock_step; return clock_us; }
static void muse_state_set_mode(int n) { (void)n; }
static void muse_state_set_caption(const char *fmt,...) { (void)fmt; }
static void muse_state_set_level(float n) { (void)n; }
static float muse_audio_level(const int16_t *p,size_t n) { (void)p;(void)n;return 0; }
static esp_err_t muse_audio_write(const int16_t *p,size_t n) { (void)p;(void)n; writes++; return write_fails ? -1 : ESP_OK; }
static void go_idle(const char *text) { (void)text; }
static void vTaskDelay(int n) { (void)n; }
static bool got_event(int n) { (void)n; assert(++polls<100); return interrupt; }
void muse_hatch_turn_cancel(void) { cancels++; }
muse_hatch_ev_t muse_hatch_turn_event(char *text,size_t cap) {
    if (no_events) return MUSE_HATCH_EV_NONE;
    if (caption_storm) { strlcpy(text,"progress",cap); return MUSE_HATCH_EV_REPLY; }
    if (input_error) { input_error=false; strlcpy(text,"DOWNLOAD FAILED",cap); return MUSE_HATCH_EV_ERROR; }
    if (event_step==0) { event_step++; return MUSE_HATCH_EV_SENT; }
    if (event_step==1) { event_step++; strlcpy(text,"Dit is een antwoord.",cap); return MUSE_HATCH_EV_REPLY; }
    if (!lose_done && reads && event_step==2) { event_step++; return MUSE_HATCH_EV_DONE; }
    return MUSE_HATCH_EV_NONE;
}
size_t muse_hatch_turn_read(int16_t *pcm,size_t frames,int wait_ms) {
    (void)wait_ms;
    if (no_events) return 0;
    if (reads++) return 0;
    for (size_t i=0;i<frames;i++) pcm[i]=100;
    return frames;
}
bool muse_hatch_turn_caption(size_t played,char *out,size_t cap) { (void)played; strlcpy(out,"Dit is een antwoord.",cap); return true; }
''' + limit + '\n' + player + r'''
int main(int argc,char **argv) {
    assert(argc==2); bool delivered=false;
    muse_audio_message_result_t r={0};
    switch(atoi(argv[1])) {
    case 0:
        assert(!hatch_reply(&delivered,&r));
        assert(delivered && r.frames==320 && !r.error[0] && writes==1 && cancels==0); break;
    case 1:
        input_error=true; assert(!hatch_reply(&delivered,&r));
        assert(!r.frames && strstr(r.error,"DOWNLOAD") && writes==0); break;
    case 2:
        enabled=false; assert(!hatch_reply(&delivered,&r));
        assert(!r.frames && r.error[0] && writes==0 && cancels==1); break;
    case 3:
        interrupt=true; assert(hatch_reply(&delivered,&r));
        assert(!r.frames && strstr(r.error,"BOOT") && writes==0 && cancels==1); break;
    case 4:
        pending=true; assert(!hatch_reply(&delivered,NULL));
        assert(delivered && writes==0 && cancels==1); break;
    case 5:
        write_fails=true; assert(!hatch_reply(&delivered,&r));
        assert(!r.frames && strstr(r.error,"SPEAKER") && cancels==1); break;
    case 6:
        atomic_store(&s_audio_stop,true); assert(!hatch_reply(&delivered,&r));
        assert(!r.frames && r.error[0] && writes==0 && cancels==1); break;
    case 7:
        no_events=true; clock_step=60000000;
        assert(!hatch_reply(&delivered,&r));
        assert(!delivered && strstr(r.error,"TIMED OUT") && cancels==1); break;
    case 8:
        lose_done=true; clock_step=60000000;
        assert(!hatch_reply(&delivered,&r));
        assert(delivered && strstr(r.error,"TIMED OUT") && writes>0 && cancels==1); break;
    case 9:
        lose_done=true; clock_step=60000000;
        assert(!hatch_reply(&delivered,NULL));
        assert(delivered && cancels==1); break;
    case 10:
        caption_storm=true; clock_step=60000000;
        assert(!hatch_reply(&delivered,&r));
        assert(strstr(r.error,"TIMED OUT") && cancels==1); break;
    default: return 2;
    }
}
'''
        (out / 'player.c').write_text(code)
        command = [*shlex.split(os.environ.get('CC', 'cc')), '-std=c11', '-Wall', '-Wextra', '-Werror',
                   '-I', str(ROOT / 'tests'), '-I', str(ROOT / 'components/muse'),
                   str(out / 'player.c'), '-o', str(out / 'player')]
        r = subprocess.run(command, capture_output=True, text=True)
        if r.returncode:
            raise AssertionError(r.stdout + r.stderr)
        cls.binary = out / 'player'

    def check(self, case):
        r = subprocess.run([str(self.binary), str(case)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_reports_frames_after_speaker_write(self): self.check(0)
    def test_download_failure_is_not_success(self): self.check(1)
    def test_mute_stops_playback(self): self.check(2)
    def test_boot_interrupts_without_speaker_tail(self): self.check(3)
    def test_acknowledged_boot_note_hands_off_to_agent_audio_command(self): self.check(4)
    def test_speaker_failure_cancels_stream(self): self.check(5)
    def test_stop_command_cancels_stream(self): self.check(6)
    def test_no_worker_response_has_bounded_wait(self): self.check(7)
    def test_missing_completion_after_audio_has_bounded_wait(self): self.check(8)
    def test_normal_boot_reply_also_has_timeout_backstop(self): self.check(9)
    def test_caption_storm_cannot_starve_deadline(self): self.check(10)
