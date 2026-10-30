# SPDX-License-Identifier: Apache-2.0
"""Real motion driver against an I2C fake: fault bounds, signed axes and standby."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
I2C=r'''
#pragma once
#include <stdint.h>
#include <stddef.h>
typedef int esp_err_t;
typedef void *i2c_master_bus_handle_t;
typedef void *i2c_master_dev_handle_t;
typedef struct {int dev_addr_length,device_address,scl_speed_hz;} i2c_device_config_t;
#define ESP_OK 0
#define I2C_ADDR_BIT_LEN_7 7
esp_err_t i2c_master_bus_add_device(void *,const i2c_device_config_t *,void **);
esp_err_t i2c_master_bus_rm_device(void *);
esp_err_t i2c_master_transmit_receive(void *,const uint8_t *,size_t,uint8_t *,size_t,int);
esp_err_t i2c_master_transmit(void *,const uint8_t *,size_t,int);
'''
CORE=r'''
#include "muse_qmi8658.h"
#include <assert.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
static uint8_t regs[256];static unsigned calls,writes,removed,critical,delayed,address;
static int fail_reg=-1,wrong_id,missing;
void enter(void) {assert(!critical);critical++;}
void leave(void) {assert(critical==1);critical--;}
void vTaskDelay(unsigned n) {assert(n<=20);delayed+=n;}
int i2c_master_bus_add_device(void *bus,const i2c_device_config_t *cfg,void **dev) {
 assert(bus && !critical && cfg->scl_speed_hz==400000);address=cfg->device_address;
 *dev=(void *)1;return 0;
}
int i2c_master_bus_rm_device(void *dev) {assert(dev && !critical);removed++;return 0;}
int i2c_master_transmit_receive(void *dev,const uint8_t *r,size_t rn,uint8_t *out,size_t n,int timeout) {
 assert(dev && rn==1 && timeout==10 && !critical);calls++;
 if(missing || *r==fail_reg)return -1;
 if(*r==0){*out=wrong_id?7:5;return 0;}
 memcpy(out,regs+*r,n);return 0;
}
int i2c_master_transmit(void *dev,const uint8_t *b,size_t n,int timeout) {
 assert(dev && n==2 && timeout==10 && !critical);calls++;writes++;
 if(b[0]==fail_reg)return -1;
 regs[b[0]]=b[1];return 0;
}
static void init(void) {
 assert(muse_qmi8658_init((void *)1));assert(delayed==20 && regs[2]==0x60 && regs[3]==0x17 && regs[6]==1 && regs[8]==0);
}
static void raw(int x,int y,int z) {
 int v[]={x,y,z};for(int i=0;i<3;i++){regs[0x35+i*2]=v[i]&255;regs[0x36+i*2]=(v[i]>>8)&255;}regs[0x2e]=1;
}
int main(int argc,char **argv) {
 assert(argc==2);int n=atoi(argv[1]);muse_motion_t s;
 if(n==0){wrong_id=1;assert(!muse_qmi8658_init((void *)1));assert(removed==2 && address==0x6b && writes==0);}
 if(n==1){missing=1;assert(!muse_qmi8658_init((void *)1));muse_qmi8658_request(true);muse_qmi8658_poll(100,true);assert(!muse_qmi8658_read(&s));}
 if(n==2){fail_reg=3;assert(!muse_qmi8658_init((void *)1));assert(removed==1 && regs[8]==0);}
 if(n==3){
  init();unsigned c=calls;for(unsigned i=0;i<100;i++)muse_qmi8658_poll(i*40,true);assert(calls==c);
  muse_qmi8658_request(true);assert(calls==c && !muse_qmi8658_read(&s));
  muse_qmi8658_poll(100,true);assert(regs[8]==1);raw(-4096,-8192,8192);
  muse_qmi8658_poll(140,true);assert(muse_qmi8658_read(&s));
  assert(s.x==1 && s.y==-0.5f && s.z==1 && s.at_ms==140);
  c=calls;muse_qmi8658_read(&s);assert(calls==c);
  regs[0x2e]=0;muse_qmi8658_poll(180,true);assert(muse_qmi8658_read(&s) && s.at_ms==140);
  muse_qmi8658_request(false);assert(!muse_qmi8658_read(&s));muse_qmi8658_poll(220,true);assert(regs[8]==0);
 }
 if(n==4){
  init();muse_qmi8658_request(true);muse_qmi8658_poll(100,true);raw(32767,-32768,8192);
  muse_qmi8658_poll(140,true);assert(muse_qmi8658_read(&s) && s.x==4 && s.y>3.9);
  muse_qmi8658_poll(180,false);assert(regs[8]==0 && !muse_qmi8658_read(&s));
 }
 if(n==5){
  init();muse_qmi8658_request(true);muse_qmi8658_poll(100,true);raw(0,0,8192);
  fail_reg=0x35;muse_qmi8658_poll(140,true);assert(!muse_qmi8658_read(&s));
  unsigned c=calls;for(unsigned t=180;t<1140;t+=40)muse_qmi8658_poll(t,true);assert(c==calls);
  fail_reg=-1;muse_qmi8658_poll(1140,true);assert(muse_qmi8658_read(&s) && s.at_ms==1140);
  // A failed stop is retried, not marked successfully asleep.
  fail_reg=8;muse_qmi8658_request(false);muse_qmi8658_poll(1180,true);assert(regs[8]==1);
  fail_reg=-1;muse_qmi8658_poll(2180,true);assert(regs[8]==0);
 }
 assert(!critical);
}
'''
class MotionDriverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='muse-motion-');r=Path(cls.tmp.name);cls.exe=r/'test'
        for d in ('driver','freertos'):(r/d).mkdir()
        (r/'driver/i2c_master.h').write_text(I2C)
        (r/'freertos/FreeRTOS.h').write_text('#pragma once\ntypedef int portMUX_TYPE;\n#define portMUX_INITIALIZER_UNLOCKED 0\nvoid enter(void);void leave(void);\n#define portENTER_CRITICAL(m) ((void)(m),enter())\n#define portEXIT_CRITICAL(m) ((void)(m),leave())\n#define pdMS_TO_TICKS(n) (n)\n')
        (r/'freertos/task.h').write_text('void vTaskDelay(unsigned);\n')
        (r/'esp_log.h').write_text('#define ESP_LOGI(...) ((void)0)\n')
        (r/'main.c').write_text(CORE)
        cmd=shlex.split(os.getenv('CC','cc'))+['-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(r),'-I',str(ROOT/'components/muse'),'-I',str(ROOT/'components/muse/boards'),str(r/'main.c'),str(ROOT/'components/muse/boards/muse_qmi8658.c'),'-o',str(cls.exe)]
        p=subprocess.run(cmd,capture_output=True,text=True);assert p.returncode==0,p.stdout+p.stderr
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_case(self,n):
        r=subprocess.run([str(self.exe),str(n)],capture_output=True,text=True,timeout=10)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
for i,name in enumerate(('wrong_identity','missing','config_failure','axes_and_standby','audio_preempts','bounded_io_failure')):
    setattr(MotionDriverTests,'test_'+name,lambda self,n=i:self.run_case(n))
if __name__=='__main__':unittest.main()
