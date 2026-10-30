# Copyright (c) Meta Platforms, Inc. and affiliates.
# SPDX-License-Identifier: Apache-2.0
"""Actual startup/event/API functions with allocation and queue fault injection."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ChatReliability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        out = Path(cls.tmp.name)
        src = (ROOT / 'components/muse/muse_chat_session.cpp').read_text()

        def fn(signature):
            start = src.index(signature)
            return src[start:src.index('\n}\n', start) + 3]

        constants = src[src.index('#define MIC_RATE'):src.index('/* ---- Voice task')]
        globals_ = src[src.index('enum cmd_type_t'):src.index('/* ---- Connection')]
        streams = src[src.index('enum kind_t'):src.index('/* ---- The current turn')]
        turn = src[src.index('enum phase_t'):src.index('/* 10 KB')]
        code = r'''
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <vector>
#include <unordered_map>
#include "host_compat.h"
#include "minimp3.h"
#include "muse_chat_priv.h"
#define CONFIG_MUSE_REALTIME_VOICE 0
#define CONFIG_MUSE_AUDIO_COMMANDS 1
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define MALLOC_CAP_INTERNAL 4
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
using portMUX_TYPE = int;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(x) ((void)(x))
#define portEXIT_CRITICAL(x) ((void)(x))
struct queue_t { int capacity, item_size; std::deque<std::vector<char>> items; };
using QueueHandle_t = queue_t *;
using StreamBufferHandle_t = void *;
static std::unordered_map<void *,size_t> blocks;
static int alloc_calls, fail_once, fail_kind, tasks, task_attempts, reports;
static bool wifi=true, configured=true;
static void *allocate(size_t n,bool fail=false) {
    ++alloc_calls;
    if(fail || alloc_calls==fail_once) return nullptr;
    void *p=calloc(1,n); assert(p); blocks[p]=n; return p;
}
static void release(void *p) {
    if(p) { assert(blocks.erase(p)==1); std::free(p); }
}
#define free release
static QueueHandle_t xQueueCreateWithCaps(int count,int size,int) {
    void *p=allocate(sizeof(queue_t),fail_kind==1);
    return p ? new(p) queue_t{count,size,{}} : nullptr;
}
static void vQueueDeleteWithCaps(QueueHandle_t q) { q->~queue_t(); release(q); }
static int xQueueSend(QueueHandle_t q,const void *item,int) {
    assert(q); if(q->items.size()==(size_t)q->capacity) return 0;
    q->items.emplace_back((const char *)item,(const char *)item+q->item_size); return pdTRUE;
}
static int xQueueReceive(QueueHandle_t q,void *item,int) {
    assert(q); if(q->items.empty()) return 0;
    memcpy(item,q->items.front().data(),q->item_size);q->items.pop_front();return pdTRUE;
}
static StreamBufferHandle_t xStreamBufferCreateWithCaps(int bytes,int,int) { return allocate(bytes,fail_kind==2); }
static void vStreamBufferDeleteWithCaps(void *p) { release(p); }
static size_t xStreamBufferReceive(void *p,void *,size_t,int) { assert(p);return 0; }
static size_t xStreamBufferSend(void *p,const void *,size_t n,int) { assert(p);return n; }
static void xStreamBufferReset(void *p) { assert(p); }
static void vTaskDelay(int) {}
static void *json_alloc(size_t n) { return allocate(n); }
static void heap_caps_free(void *p) { release(p); }
struct cJSON_Hooks { void *(*alloc)(size_t); void (*release)(void *); };
static void cJSON_InitHooks(cJSON_Hooks *) {}
static void hatch_task(void *) {}
static int xTaskCreatePinnedToCoreWithCaps(void (*)(void *),const char *,int,void *,int,void *,int,int) {
    ++task_attempts; if(fail_kind==5 || (fail_kind==6 && task_attempts==1)) return 0;
    ++tasks; return pdPASS;
}
bool muse_hatch_configured(void) { return configured; }
static bool muse_wifi_connected(void) { return wifi; }
void muse_hatch_report(muse_hatch_state_t,const char *) { ++reports; }
void muse_hatch_tail_words(const char *s,char *d,size_t n) { strlcpy(d,s,n); }
''' + constants + globals_ + streams + turn + r'''
static turn_t s_turn;
static int16_t *s_pcm,*s_pcm16;
static int finishes;
static void turn_finish(void) { ++finishes; s_turn.phase=P_IDLE; }
static void *psram_alloc(size_t n) {
    return allocate(n,(fail_kind==3 && n==MP3_BUF) || (fail_kind==4 && n==NDJSON_LINE_MAX));
}
''' + ''.join(fn(sig) for sig in (
            'static void publish_critical(', 'static bool take_critical(', 'static void emit(',
            'static void apply_voice_requests(', 'static bool post(', 'static void drain_out(',
            'static void start_cleanup(', 'static bool start_attempt(',
            'extern "C" void muse_hatch_start(', 'extern "C" bool muse_hatch_ready(',
            'extern "C" void muse_hatch_turn_begin(', 'extern "C" void muse_hatch_turn_end(',
            'extern "C" void muse_hatch_turn_cancel(', 'extern "C" void muse_hatch_turn_audio(',
            'extern "C" size_t muse_hatch_turn_audio_wait(',
            'extern "C" muse_hatch_ev_t muse_hatch_turn_event(', 'extern "C" size_t muse_hatch_turn_read(',
        )) + r'''
static muse_hatch_ev_t next(char *text) { return muse_hatch_turn_event(text,72); }
static void fill_commands() {
    cmd_t c{CMD_WAKE,0,nullptr};
    while(xQueueSend(s_cmds,&c,0)) {}
}
int main(int argc,char **argv) {
    assert(argc==2); int test=atoi(argv[1]); char text[72];
    if(test==0) {
        // Every allocation point fails once, then retries may succeed.
        muse_hatch_start(); assert(muse_hatch_ready() && tasks==1);
        int count=alloc_calls; size_t live=blocks.size();
        start_cleanup(); s_started=false; tasks=0;
        assert(blocks.empty());
        for(int i=1;i<=count;i++) {
            alloc_calls=0; fail_once=i; muse_hatch_start();
            assert(muse_hatch_ready() && tasks==1);
            assert(blocks.size()==live || blocks.size()==live-1); // optional caption texts
            muse_hatch_start(); assert(tasks==1); // idempotent
            start_cleanup(); s_started=false; tasks=0; assert(blocks.empty());
        }
    } else if(test>=1 && test<=5) {
        fail_kind=test; muse_hatch_start();
        assert(!muse_hatch_ready() && tasks==0 && blocks.empty() && reports==1);
        assert(!s_cmds && !s_events && !s_in && !s_out);
        int16_t pcm[4];
        muse_hatch_turn_begin(); muse_hatch_turn_cancel(); muse_hatch_turn_audio(pcm,4);
        assert(!muse_hatch_turn_audio_wait(pcm,4,0) && !muse_hatch_turn_read(pcm,4,0));
        assert(next(text)==MUSE_HATCH_EV_NONE);
        fail_kind=0; muse_hatch_start(); assert(muse_hatch_ready() && tasks==1);
        start_cleanup(); assert(blocks.empty());
    } else if(test==6) {
        fail_kind=6; muse_hatch_start();
        assert(tasks==1 && task_attempts==2 && muse_hatch_ready());
        start_cleanup(); assert(blocks.empty());
    } else {
        muse_hatch_start(); assert(muse_hatch_ready()); s_gen=1;s_turn.gen=1;
        if(test==7 || test==8) {
            for(int i=0;i<40;i++) emit(MUSE_HATCH_EV_REPLY,"caption");
            emit(MUSE_HATCH_EV_SENT,nullptr);
            emit(test==7?MUSE_HATCH_EV_DONE:MUSE_HATCH_EV_ERROR,"terminal");
            assert(next(text)==MUSE_HATCH_EV_SENT);
            assert(next(text)==(test==7?MUSE_HATCH_EV_DONE:MUSE_HATCH_EV_ERROR));
            assert(!strcmp(text,"terminal"));
            for(int i=0;i<16;i++) assert(next(text)==MUSE_HATCH_EV_REPLY);
            assert(next(text)==MUSE_HATCH_EV_NONE);
        } else if(test==9) {
            emit(MUSE_HATCH_EV_SENT,nullptr); emit(MUSE_HATCH_EV_ERROR,"old");
            s_gen=2;s_turn.gen=2;emit(MUSE_HATCH_EV_SENT,nullptr);emit(MUSE_HATCH_EV_DONE,"new");
            s_turn.gen=1;emit(MUSE_HATCH_EV_ERROR,"late old");
            assert(next(text)==MUSE_HATCH_EV_SENT && next(text)==MUSE_HATCH_EV_DONE);
            assert(!strcmp(text,"new") && next(text)==MUSE_HATCH_EV_NONE);
        } else if(test==10) {
            fill_commands(); muse_hatch_turn_begin();
            assert(next(text)==MUSE_HATCH_EV_ERROR && strstr(text,"BUSY"));
        } else if(test==11) {
            s_turn.phase=P_LISTEN; fill_commands();
            muse_hatch_turn_end(); apply_voice_requests(); assert(s_turn.end_requested);
            muse_hatch_turn_cancel(); apply_voice_requests(); assert(finishes==1 && s_turn.phase==P_IDLE);
            s_turn.end_requested=false;s_turn.gen=s_gen.load();s_turn.phase=P_LISTEN;
            apply_voice_requests();assert(!s_turn.end_requested && s_turn.phase==P_LISTEN);
            s_turn.text=true;++s_gen;apply_voice_requests();assert(s_turn.phase==P_LISTEN);
        } else if(test==12) {
            size_t live=blocks.size();
            for(int turn=0;turn<10000;turn++) {
                s_turn.gen=++s_gen;
                for(int i=0;i<40;i++) emit(MUSE_HATCH_EV_REPLY,"caption");
                emit(MUSE_HATCH_EV_SENT,nullptr); emit(MUSE_HATCH_EV_DONE,nullptr);
                assert(next(text)==MUSE_HATCH_EV_SENT && next(text)==MUSE_HATCH_EV_DONE);
                // Leave old captions queued across the next generation.
                assert(s_events->items.size()<=16 && blocks.size()==live);
            }
        } else return 2;
        start_cleanup(); assert(blocks.empty());
    }
}
'''
        (out / 'reliability.cpp').write_text(code)
        command = [*shlex.split(os.environ.get('CXX', 'c++')), '-std=c++17',
                   '-fsanitize=address,undefined', '-g', '-I', str(ROOT / 'tests'),
                   '-I', str(ROOT / 'components/minimp3/include'),
                   '-I', str(ROOT / 'components/muse'), str(out / 'reliability.cpp'), '-o', str(out / 'reliability')]
        r = subprocess.run(command, capture_output=True, text=True)
        if r.returncode:
            raise AssertionError(r.stdout + r.stderr)
        cls.binary = out / 'reliability'

    def check(self, case):
        r = subprocess.run([str(self.binary), str(case)], capture_output=True, text=True, timeout=10)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_each_allocation_failure_recovers_without_leaking(self): self.check(0)
    def test_missing_queues_reject_work_then_retry(self): self.check(1)
    def test_missing_stream_buffers_reject_work_then_retry(self): self.check(2)
    def test_missing_mp3_buffer_rejects_work_then_retries(self): self.check(3)
    def test_missing_line_buffers_never_start_worker(self): self.check(4)
    def test_task_creation_failure_is_not_ready_and_can_retry(self): self.check(5)
    def test_transient_task_creation_failure_retries_automatically(self): self.check(6)
    def test_full_caption_queue_cannot_lose_sent_or_done(self): self.check(7)
    def test_full_caption_queue_cannot_lose_error(self): self.check(8)
    def test_late_old_events_cannot_replace_new_completion(self): self.check(9)
    def test_rejected_begin_reports_failure(self): self.check(10)
    def test_end_cancel_survive_full_command_queue_without_touching_new_or_typed_turn(self): self.check(11)
    def test_ten_thousand_turns_keep_completion_and_bounded_queues(self): self.check(12)
