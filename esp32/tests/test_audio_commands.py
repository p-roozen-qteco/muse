# Copyright (c) Meta Platforms, Inc. and affiliates.
# SPDX-License-Identifier: Apache-2.0
"""Actual advertised command schema, validation and asynchronous results."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
JSON = Path(os.environ.get('CJSON_SOURCE_DIR', ROOT / 'managed_components/espressif__cjson/cJSON'))


class AudioCommands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        out = Path(cls.tmp.name)
        (out / 'freertos').mkdir()
        (out / 'esp_err.h').write_text('typedef int esp_err_t;\n')
        (out / 'freertos/FreeRTOS.h').write_text('')
        (out / 'freertos/queue.h').write_text('typedef void *QueueHandle_t;\n')
        code = r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "audio_commands.h"
#include "muse_voice.h"
static bool ready = true, accept = true;
static int requests, stops, results;
static muse_audio_message_t copy;
static muse_audio_message_done_t done;
static void *context;
static cJSON *result;
static uint64_t result_generation;
static char result_id[64];
bool muse_voice_audio_ready(void) { return ready; }
bool muse_voice_play_message(const muse_audio_message_t *r, muse_audio_message_done_t cb, void *u, const char **error) {
    requests++;
    if (!accept) { *error = "SPEAKER MUTED"; return false; }
    copy = *r; done = cb; context = u; return true;
}
void muse_voice_stop_message(void) { stops++; }
void noise_ctrl_send_command_result(uint64_t generation, const char *id, cJSON *r) {
    results++; result_generation = generation; strcpy(result_id, id); result = r;
}
static bool failed(cJSON *r) {
    bool fail = cJSON_IsFalse(cJSON_GetObjectItem(r, "ok")); cJSON_Delete(r); return fail;
}
static cJSON *invoke(const char *name, const char *json) {
    cJSON *p = cJSON_Parse(json); assert(p);
    cJSON *r = audio_commands_handle(name, p, "request-1", 42);
    cJSON_Delete(p); return r;
}
static void schema(void) {
    cJSON *c = cJSON_CreateObject(); ready = false; audio_commands_register(c);
    assert(cJSON_GetArraySize(c) == 0);
    ready = true; audio_commands_register(c); assert(cJSON_GetArraySize(c) == 3);
    for (cJSON *entry = c->child; entry; entry = entry->next) {
        assert(audio_commands_handles(entry->string));
        assert(cJSON_IsObject(cJSON_GetObjectItem(entry,"required")));
        assert(cJSON_IsObject(cJSON_GetObjectItem(entry,"optional")));
    }
    cJSON *play = cJSON_GetObjectItem(c,"audio.play_file");
    assert(cJSON_GetObjectItem(cJSON_GetObjectItem(play,"required"),"path"));
    assert(strstr(cJSON_GetStringValue(cJSON_GetObjectItem(play,"description")),"MP3"));
    cJSON_Delete(c);
}
static void params(void) {
    const char *bad[] = {"{}", "{\"path\":1}", "{\"path\":\"\"}", "{\"path\":\"a\",\"text\":false}"};
    for (unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++) assert(failed(invoke("audio.play_file",bad[i])));
    assert(requests==0);
    char long_path[513]; memset(long_path,'x',512); long_path[512]=0;
    cJSON *p=cJSON_CreateObject(); cJSON_AddStringToObject(p,"path",long_path);
    assert(failed(audio_commands_handle("audio.play_file",p,"id",1))); cJSON_Delete(p);
    assert(failed(invoke("audio.unknown","{}")));
    accept=false; assert(failed(invoke("audio.play_file","{\"path\":\"workspace/a.mp3\"}")));
    assert(results==0);
}
static void completion(void) {
    cJSON *ack=invoke("audio.play_file","{\"path\":\"workspace/a.mp3\",\"text\":\"Dit is Nederlands.\"}");
    assert(cJSON_IsTrue(cJSON_GetObjectItem(ack,"_async"))); cJSON_Delete(ack);
    assert(results==0 && copy.source==MUSE_AUDIO_FILE);
    assert(!strcmp(copy.target,"workspace/a.mp3") && !strcmp(copy.text,"Dit is Nederlands."));
    muse_audio_message_result_t played={.frames=16000};
    done(&played,context);
    assert(results==1 && result_generation==42 && !strcmp(result_id,"request-1"));
    assert(cJSON_IsTrue(cJSON_GetObjectItem(result,"ok")));
    cJSON *p=cJSON_GetObjectItem(result,"payload");
    assert(cJSON_IsTrue(cJSON_GetObjectItem(p,"played")) && cJSON_GetObjectItem(p,"duration_ms")->valueint==1000);
    cJSON_Delete(result);
    ack=invoke("audio.play_reply","{\"message_id\":\"reply /?\"}"); cJSON_Delete(ack);
    assert(copy.source==MUSE_AUDIO_REPLY && !copy.text[0]);
    played.frames=0; strcpy(played.error,"AUDIO UNAVAILABLE"); done(&played,context);
    assert(failed(result));
    ack=invoke("audio.stop","{}"); assert(cJSON_IsTrue(cJSON_GetObjectItem(ack,"ok"))); cJSON_Delete(ack);
    assert(stops==1);
}
static void paths(void) {
    char p[1600];
    assert(muse_audio_message_path(MUSE_AUDIO_FILE,"/workspace/reply ?#.mp3",false,p,sizeof(p)));
    assert(!strcmp(p,"/fs/raw/workspace/reply%20%3F%23.mp3"));
    assert(!muse_audio_message_path(MUSE_AUDIO_FILE,"///",false,p,sizeof(p)));
    assert(!muse_audio_message_path(MUSE_AUDIO_FILE,"a",true,p,sizeof(p)));
    assert(!muse_audio_message_path(MUSE_AUDIO_REPLY,"a",false,p,2));
    assert(muse_audio_message_path(MUSE_AUDIO_REPLY,"id /&",true,p,sizeof(p)));
    assert(!strcmp(p,"/voice/tts-stream?message_id=id%20%2F%26"));
}
int main(int argc,char **argv) {
    assert(argc==2);
    switch(atoi(argv[1])) { case 0:schema();break;case 1:params();break;case 2:completion();break;case 3:paths();break;default:return 2; }
}
'''
        (out / 'commands.c').write_text(code)
        cmd = [*shlex.split(os.environ.get('CC', 'cc')), '-std=c11', '-Wall', '-Wextra', '-Werror',
               '-I', str(out), '-I', str(JSON), '-I', str(ROOT / 'main'),
               '-I', str(ROOT / 'components/muse'), str(out / 'commands.c'),
               str(ROOT / 'main/audio_commands.c'), str(JSON / 'cJSON.c'), '-o', str(out / 'commands')]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            raise AssertionError(r.stdout + r.stderr)
        cls.binary = out / 'commands'

    def check(self, case):
        r = subprocess.run([str(self.binary), str(case)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_advertises_only_when_audio_is_ready(self): self.check(0)
    def test_invalid_requests_and_mute_never_report_playback(self): self.check(1)
    def test_success_is_returned_only_after_playback_to_original_session(self): self.check(2)
    def test_authenticated_paths_escape_query_and_path_bytes(self): self.check(3)

    def test_full_s3_registration_fits_and_includes_audio(self):
        # Compile the real registration builder with the S3's display/tunnel
        # options. Exceeding its 8 KiB limit would disconnect the whole gadget.
        out = Path(self.tmp.name)
        source = (ROOT / 'main/noise_control.cpp').read_text()
        builder = source[source.index('static cJSON *string_param('):
                         source.index('// ---- OTA callback')]
        code = r'''
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
extern "C" {
#include "audio_commands.h"
#include "muse_voice.h"
bool muse_voice_audio_ready(void) { return true; }
bool muse_voice_play_message(const muse_audio_message_t *, muse_audio_message_done_t, void *, const char **) { return false; }
void muse_voice_stop_message(void) {}
void noise_ctrl_send_command_result(uint64_t, const char *, cJSON *r) { cJSON_Delete(r); }
}
#define CONFIG_MUSE_AUDIO_COMMANDS 1
#define CONFIG_HOMEHUB_TUNNEL 1
#define CONFIG_HOMEHUB_DISPLAY_COMMANDS 1
#define CONFIG_HOMEHUB_LED_BACKEND_MUSE 1
static char s_wifi_ssid[33], s_node_id[65], s_display_name[65], s_register_req_id[40];
struct esp_app_desc_t { char version[32]; };
static const esp_app_desc_t *esp_app_get_description() { static esp_app_desc_t d = {"999.0.0-s3audio-test2"}; return &d; }
static void copy_wifi_ssid(char *p, size_t n) { memset(p, 'w', n-1); p[n-1]=0; }
static void make_uuid(char *p, size_t n) { snprintf(p,n,"00000000-0000-0000-0000-000000000000"); }
static bool led_status_display_info(int *w, int *h) { *w=368; *h=448; return true; }
static int led_status_display_bits() { return 16; }
static bool ota_is_enabled() { return true; }
''' + builder + r'''
int main() {
    memset(s_node_id,'n',sizeof(s_node_id)-1);
    memset(s_display_name,'d',sizeof(s_display_name)-1);
    char *json=build_register_json(); assert(json && strlen(json)<8192);
    cJSON *root=cJSON_Parse(json); assert(root);
    cJSON *commands=cJSON_GetObjectItem(cJSON_GetObjectItem(root,"params"),"commands_v2");
    for (const char *name : {"audio.play_file", "audio.play_reply", "audio.stop", "display.draw_file", "device.health"})
        assert(cJSON_IsObject(cJSON_GetObjectItem(commands,name)));
    printf("Registration: %zu bytes\n",strlen(json));
    free(json); cJSON_Delete(root);
}
'''
        # initializer_list is needed for the name loop above.
        (out / 'register.cpp').write_text('#include <initializer_list>\n' + code)
        includes = ['-I', str(out), '-I', str(JSON), '-I', str(ROOT / 'main'),
                    '-I', str(ROOT / 'components/muse')]
        objects = []
        for name, path in [('audio', ROOT / 'main/audio_commands.c'), ('json', JSON / 'cJSON.c')]:
            obj = out / (name + '.o')
            command = [*shlex.split(os.environ.get('CC', 'cc')), '-std=c11', *includes,
                       '-c', str(path), '-o', str(obj)]
            r = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            objects.append(str(obj))
        command = [*shlex.split(os.environ.get('CXX', 'c++')), '-std=c++17', *includes,
                   str(out / 'register.cpp'), *objects, '-o', str(out / 'register')]
        r = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([str(out / 'register')], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
