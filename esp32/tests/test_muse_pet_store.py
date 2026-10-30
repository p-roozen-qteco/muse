# SPDX-License-Identifier: Apache-2.0
"""Exercise the production save worker with deterministic NVS/RTOS faults."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'components/muse'
HEADERS = r'''
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef int esp_err_t;
typedef int nvs_handle_t;
typedef void *QueueHandle_t;
typedef unsigned TickType_t;
#define ESP_OK 0
#define ESP_ERR_NVS_NOT_FOUND 1
#define NVS_READWRITE 1
#define pdTRUE 1
#define pdPASS 1
#define portMAX_DELAY UINT32_MAX
#define pdMS_TO_TICKS(n) (n)
#define ESP_LOGW(tag,...) ((void)(tag))
#define ESP_LOGI(tag,...) ((void)(tag))
#define MUSE_MODE_IDLE 1
int muse_state_mode(void *p);
bool muse_voice_in_call(void);
int64_t esp_timer_get_time(void);
int nvs_open(const char *,int,nvs_handle_t *);
int nvs_get_blob(nvs_handle_t,const char *,void *,size_t *);
int nvs_set_blob(nvs_handle_t,const char *,const void *,size_t);
int nvs_commit(nvs_handle_t);
void nvs_close(nvs_handle_t);
QueueHandle_t xQueueCreate(unsigned,unsigned);
void vQueueDelete(QueueHandle_t);
int xTaskCreate(void (*)(void *),const char *,unsigned,void *,unsigned,void *);
int xQueueReceive(QueueHandle_t,void *,TickType_t);
int xQueuePeek(QueueHandle_t,void *,TickType_t);
int xQueueSend(QueueHandle_t,const void *,TickType_t);
int xQueueOverwrite(QueueHandle_t,const void *);
void vTaskDelay(TickType_t);
'''
HARNESS = r'''
#include "fake.h"
#include "muse_pet_store.h"
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int scenario,closed,deleted,attempts,commits,waits,calls;
static int64_t ms,last_attempt=-15000;
static bool queued, injected, failed_seen;
static uint8_t data[24],disk[24];
static void (*worker)(void *);
static jmp_buf done;
static void snapshot(unsigned food) {muse_pet_t p;muse_pet_init(&p,0);p.food=food;muse_pet_encode(&p,data);queued=true;}
int muse_state_mode(void *p) {(void)p;return scenario==6 && ms<5000 ? 2 : MUSE_MODE_IDLE;}
bool muse_voice_in_call(void) {return scenario==6 && ms<7000;}
int64_t esp_timer_get_time(void) {return ms*1000;}
int nvs_open(const char *s,int mode,nvs_handle_t *h) {assert(!strcmp(s,"muse_pet") && mode==NVS_READWRITE);*h=7;return scenario==3 ? -1 : ESP_OK;}
int nvs_get_blob(nvs_handle_t h,const char *key,void *p,size_t *n) {
 assert(h==7 && !strcmp(key,"state") && *n==24);
 if(scenario==11)return -2;
 if(scenario!=1 && scenario!=2)return ESP_ERR_NVS_NOT_FOUND;
 muse_pet_t pet;muse_pet_init(&pet,0);pet.food=91;pet.resting=true;muse_pet_encode(&pet,disk);
 if(scenario==2)disk[4]=99;
 memcpy(p,disk,24);return ESP_OK;
}
int nvs_set_blob(nvs_handle_t h,const char *key,const void *p,size_t n) {
 assert(h==7 && !strcmp(key,"state") && n==24);
 assert(muse_state_mode(NULL)==MUSE_MODE_IDLE && !muse_voice_in_call());
 assert(ms-last_attempt>=15000);last_attempt=ms;attempts++;
 assert(ms>=2000);memcpy(disk,p,24);
 return scenario==10 && attempts==1 ? -1 : ESP_OK;
}
int nvs_commit(nvs_handle_t h) {
 assert(h==7);commits++;
 if((scenario==8 || scenario==9) && commits==1)return -1;
 if(scenario==7 && commits==1)snapshot(85);
 return ESP_OK;
}
void nvs_close(nvs_handle_t h) {assert(h==7);closed++;}
QueueHandle_t xQueueCreate(unsigned len,unsigned size) {assert(len==1 && size==24);return scenario==4 ? NULL : (void *)1;}
void vQueueDelete(QueueHandle_t q) {assert(q);deleted++;}
int xTaskCreate(void (*fn)(void *),const char *name,unsigned stack,void *arg,unsigned priority,void *handle) {
 (void)name;(void)arg;(void)handle;assert(stack>=3072 && priority==1);worker=fn;return scenario==5 ? 0 : pdPASS;
}
int xQueueReceive(QueueHandle_t q,void *p,TickType_t ticks) {
 assert(q && ++calls<1000);
 if(queued){memcpy(p,data,24);queued=false;return pdTRUE;}
 if(ticks==portMAX_DELAY)longjmp(done,1);
 if(ticks){waits++;ms+=ticks;if((scenario==6 || scenario==7) && !injected){snapshot(92);injected=true;memcpy(p,data,24);queued=false;return pdTRUE;}}
 return 0;
}
int xQueuePeek(QueueHandle_t q,void *p,TickType_t t) {(void)t;assert(q);if(queued)memcpy(p,data,24);return queued;}
int xQueueOverwrite(QueueHandle_t q,const void *p) {assert(q);memcpy(data,p,24);queued=true;return pdTRUE;}
int xQueueSend(QueueHandle_t q,const void *p,TickType_t t) {(void)t;if(queued)return 0;return xQueueOverwrite(q,p);}
void vTaskDelay(TickType_t t) {
 ms+=t;
 if(t==15000){assert(muse_pet_store_failed());failed_seen=true;if(scenario==9)snapshot(99);}
}
int main(int argc,char **argv) {
 assert(argc==2);scenario=atoi(argv[1]);muse_pet_t pet;
 bool ok=muse_pet_store_start(&pet,123);
 if((scenario>=2 && scenario<=5) || scenario==11) {
  assert(!ok && muse_pet_store_failed());muse_pet_store_save(&pet);assert(!queued && attempts==0);
  assert(closed==(scenario==3 ? 0 : 1));assert(deleted==(scenario==5));return 0;
 }
 assert(ok && !muse_pet_store_failed() && pet.last_ms==123);
 if(scenario==1){assert(pet.food==91 && pet.resting);return 0;}
 assert(pet.food==75);muse_pet_store_save(&pet);assert(queued);
 if(!setjmp(done))worker(NULL);
 assert(!muse_pet_store_failed() && waits>=1);
 if(scenario==6)assert(disk[5]==92 && last_attempt>=7000);
 else if(scenario==7)assert(disk[5]==85 && attempts==2);
 else if(scenario==8 || scenario==9 || scenario==10){assert(attempts==2 && failed_seen);assert(disk[5]==(scenario==9 ? 99 : 75));}
 else assert(attempts==1 && disk[5]==75);
 assert(closed==0 && deleted==0);
}
'''

class PetStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='muse-pet-store-')
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        (root / 'fake.h').write_text(HEADERS)
        for name in ('muse_state.h','muse_voice.h','esp_log.h','esp_timer.h','nvs.h',
                     'freertos/FreeRTOS.h','freertos/queue.h','freertos/task.h'):
            f=root/name;f.parent.mkdir(exist_ok=True);f.write_text('#include "fake.h"\n')
        (root/'store.c').write_bytes((ROOT/'muse_pet_store.c').read_bytes())
        (root/'harness.c').write_text(HARNESS)
        cls.binary=root/'store-test'
        proc=subprocess.run(shlex.split(os.environ.get('CC','cc'))+['-std=c11','-Wall','-Wextra','-Werror',
            '-fsanitize=address,undefined','-g','-I'+str(root),'-I'+str(ROOT),
            str(root/'store.c'),str(ROOT/'muse_pet.c'),str(root/'harness.c'),'-o',str(cls.binary)],capture_output=True,text=True)
        if proc.returncode:raise RuntimeError(proc.stderr)

    def run_case(self, n):
        p=subprocess.run([str(self.binary),str(n)],capture_output=True,text=True,timeout=10,
            env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1'})
        self.assertEqual(p.returncode,0,p.stderr)

for n,name in enumerate(('fresh_save','restore','corrupt_preserved','open_failure','queue_failure','task_failure',
                         'voice_deferral_coalesce','rate_limit_latest','commit_retry','retry_keeps_newer','set_retry','read_failure')):
    setattr(PetStore,'test_'+name,lambda self,n=n:self.run_case(n))
