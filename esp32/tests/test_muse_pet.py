# SPDX-License-Identifier: Apache-2.0
"""Persistent pet/game invariants and the real soft renderer under sanitizers."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
CORE=r'''
#include "muse_pet.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void same(const muse_pet_t *a,const muse_pet_t *b) {
 uint8_t x[24],y[24];muse_pet_encode(a,x);muse_pet_encode(b,y);assert(!memcmp(x,y,24));
}
int main(int argc,char **argv) {
 assert(argc==2);muse_pet_t p,q;uint8_t b[24];muse_pet_game_t g;
 muse_pet_init(&p,1000);int test=atoi(argv[1]);
 if(test==0) {assert(p.food==75 && p.joy==70 && p.energy==80);assert(muse_pet_mood(&p)==MUSE_PET_CONTENT);}
 if(test==1) {
  assert(muse_pet_feed(&p));assert(p.food==100 && p.xp==2);assert(!muse_pet_feed(&p));
  muse_pet_rest(&p);assert(muse_pet_mood(&p)==MUSE_PET_RESTING);assert(!muse_pet_pat(&p));
  muse_pet_rest(&p);assert(muse_pet_pat(&p));assert(muse_pet_mood(&p)==MUSE_PET_PLAYFUL);
  p.energy=10;assert(muse_pet_mood(&p)==MUSE_PET_SLEEPY);p.energy=80;p.food=10;
  assert(muse_pet_mood(&p)==MUSE_PET_HUNGRY);
 }
 if(test==2) {
  q=p;for(unsigned i=1;i<=240;i++)muse_pet_tick(&p,1000+i*60000ull);
  muse_pet_tick(&q,1000+240*60000ull);same(&p,&q);assert(p.food==63 && p.energy==64 && p.joy==62);
  p.resting=true;p.energy=20;muse_pet_tick(&p,p.last_ms+20*60000);assert(p.energy==30);
 }
 if(test==3) {
  muse_pet_pat(&p);muse_pet_tick(&p,1000+6*60000);assert(p.bonus_minutes==0 && muse_pet_mood(&p)==MUSE_PET_CONTENT);
  p.energy=1;p.food=1;p.joy=1;muse_pet_tick(&p,UINT64_MAX);assert(p.energy==0 && p.food==0 && p.joy==0);
  muse_pet_tick(&p,10);assert(p.last_ms==10);p.resting=true;muse_pet_tick(&p,1000000000);assert(p.energy==100);
 }
 if(test==4) {
  muse_pet_feed(&p);muse_pet_rest(&p);p.best=9;p.care=123;p.xp=456;p.minutes=99;
  muse_pet_encode(&p,b);muse_pet_init(&q,2);assert(muse_pet_decode(&q,b,24,2));same(&p,&q);assert(q.last_ms==2);
  assert(!muse_pet_tick(&q,50000));assert(muse_pet_mood(&q)==MUSE_PET_RESTING);
 }
 if(test==5) {
  muse_pet_encode(&p,b);q=p;
  for(int i=0;i<24;i++){b[i]^=1;assert(!muse_pet_decode(&q,b,24,3));same(&p,&q);b[i]^=1;}
  for(size_t n=0;n<50;n++)if(n!=24)assert(!muse_pet_decode(&q,b,n,4));
  assert(!muse_pet_decode(&q,NULL,24,4));
 }
 if(test==6) {
  muse_pet_game_start(&g,1000,7);uint8_t old=g.cell;
  assert(!muse_pet_game_hit(&g,(old+1)%9,1100));assert(muse_pet_game_hit(&g,old,1100));assert(g.cell!=old);
  assert(!muse_pet_game_hit(&g,old,1101));assert(!muse_pet_game_hit(&g,g.cell,21000));
  assert(!muse_pet_game_finish(&g,&p,20999));assert(muse_pet_game_finish(&g,&p,21000));
  q=p;assert(!muse_pet_game_finish(&g,&p,99999));same(&p,&q);assert(p.best==1 && p.xp==1);
 }
 if(test==7) {
  q=p;muse_pet_game_start(&g,1,2);muse_pet_game_hit(&g,g.cell,2);muse_pet_game_cancel(&g);
  assert(!muse_pet_game_finish(&g,&p,40000));same(&p,&q);
  muse_pet_game_start(&g,1,0);assert(!muse_pet_game_finish(&g,&p,40000));same(&p,&q);assert(g.finished);
 }
 if(test==8) {
  p.xp=65530;p.care=65535;muse_pet_game_start(&g,0,1);
  for(int i=0;i<1000;i++)assert(muse_pet_game_hit(&g,g.cell,i+1));
  assert(g.score==99);assert(muse_pet_game_finish(&g,&p,20000));assert(p.xp==65535 && p.care==65535 && p.best==99);
 }
 if(test==9) {
  for(unsigned i=0;i<100000;i++){
   muse_pet_tick(&p,1000+i*60000ull);if(i%5==0)muse_pet_feed(&p);if(i%7==0)muse_pet_rest(&p);muse_pet_pat(&p);
   muse_pet_encode(&p,b);assert(muse_pet_decode(&q,b,24,p.last_ms));same(&p,&q);
   assert(p.food<=100 && p.joy<=100 && p.energy<=100 && p.bonus_minutes<=60);
  }
 }
}
'''
SOFT=r'''
#include "muse_pixel.h"
#include "muse_pet.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int allocations;
void *heap_caps_calloc(size_t n,size_t size,unsigned caps) {
 (void)caps;allocations++;return getenv("FAIL_RASTER") ? NULL : calloc(n,size);
}
int main(int argc,char **argv) {
 assert(argc==2);int test=atoi(argv[1]);
 muse_pose_t p={.mode=MUSE_MODE_IDLE,.t=10,.mode_t=2};muse_pixel_set_size(288);muse_pixel_render(&p);
 if(test==0) {
  uint16_t *full=calloc(288*288,sizeof(uint16_t)),*strips=calloc(288*288,sizeof(uint16_t));
  muse_pixel_scale(full,288,0,287,0,287);
  for(int y=0;y<288;y+=8)muse_pixel_scale(strips+y*288,288,0,287,y,y+7);
  assert(!memcmp(full,strips,288*288*2));
  int changed=0;for(int i=0;i<288*288;i++)changed+=full[i]!=0;assert(changed>10000);
  uint16_t guarded[100];for(int i=0;i<100;i++)guarded[i]=0xa55a;
  muse_pixel_scale(guarded+1,10,43,50,62,69);
  assert(guarded[0]==0xa55a && guarded[81]==0xa55a);
  for(int y=0;y<8;y++)for(int x=0;x<8;x++)assert(guarded[1+y*10+x]==full[(62+y)*288+43+x]);
  free(full);free(strips);
 } else if(test==1) {
  for(int i=0;i<1000;i++){
   p.t+=.04f;p.mode=(muse_mode_t)(i%MUSE_MODE_COUNT);p.level=(i%10)/10.f;p.pet_mood=i%5;
   p.happy=1;p.attention=1;p.gaze_x=i%2 ? 1 : -1;p.wink=.5f;
   muse_pixel_set_size(64+i%449);muse_pixel_render(&p);
  }
  assert(allocations==1);
 } else {
  p.mode=(muse_mode_t)(test-2);p.level=.8f;
  if(getenv("PET")){p.pet_mood=MUSE_PET_RESTING;p.happy=1;p.wink=1;p.attention=1;p.gaze_x=1;}
  muse_pixel_render(&p);uint16_t pixels[128*128];muse_pixel_set_size(128);muse_pixel_scale(pixels,128,0,127,0,127);
  fwrite(pixels,1,sizeof(pixels),stdout);
 }
}
'''
class Pet(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.tmp.cleanup);path=Path(cls.tmp.name)
  cls.binaries={}
  (path/'esp_heap_caps.h').write_text('#include <stddef.h>\n#define MALLOC_CAP_SPIRAM 1\n#define MALLOC_CAP_8BIT 2\nvoid *heap_caps_calloc(size_t,size_t,unsigned);\n')
  (path/'esp_log.h').write_text('#define ESP_LOGW(tag,...) ((void)(tag))\n')
  for name,code,source in [('core',CORE,'components/muse/muse_pet.c'),('soft',SOFT,'avatar/muse_soft.c')]:
   (path/(name+'.c')).write_text(code);binary=path/name
   flags=['-DESP_PLATFORM=1'] if name=='soft' else []
   cmd=[*shlex.split(os.environ.get('CC','cc')),'-std=c11','-Wall','-Wextra','-Werror','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',*flags,'-I',str(path),'-I',str(ROOT/'components/muse'),str(path/(name+'.c')),str(ROOT/source),'-lm','-o',str(binary)]
   r=subprocess.run(cmd,capture_output=True,text=True)
   if r.returncode:raise AssertionError(r.stderr)
   cls.binaries[name]=binary
 def run_case(self,name,n,**extra):
  env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1',**extra}
  r=subprocess.run([str(self.binaries[name]),str(n)],capture_output=True,env=env)
  self.assertEqual(r.returncode,0,r.stderr.decode());return r.stdout
 def test_defaults(self):self.run_case('core',0)
 def test_care_and_mood_priority(self):self.run_case('core',1)
 def test_time_batching_matches_minute_steps(self):self.run_case('core',2)
 def test_clock_jumps_and_need_bounds(self):self.run_case('core',3)
 def test_progress_survives_restart(self):self.run_case('core',4)
 def test_corrupt_or_unknown_records_are_rejected(self):self.run_case('core',5)
 def test_game_hit_deadline_and_reward_once(self):self.run_case('core',6)
 def test_cancelled_and_empty_games_give_no_reward(self):self.run_case('core',7)
 def test_score_and_progress_saturate(self):self.run_case('core',8)
 def test_100000_state_save_restore_cycles(self):self.run_case('core',9)
 def test_renderer_strips_match_full_image(self):self.run_case('soft',0)
 def test_renderer_low_memory_fallback(self):self.run_case('soft',0,FAIL_RASTER='1')
 def test_renderer_allocates_once_and_handles_all_modes(self):self.run_case('soft',1)
 def test_renderer_fallback_remains_stable(self):self.run_case('soft',1,FAIL_RASTER='1')
 def test_pet_state_cannot_override_busy_expression(self):
  for mode in (0,2,3,4,5,6):
   with self.subTest(mode=mode):self.assertEqual(self.run_case('soft',mode+2),self.run_case('soft',mode+2,PET='1'))
