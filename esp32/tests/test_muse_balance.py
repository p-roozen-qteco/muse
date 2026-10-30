# SPDX-License-Identifier: Apache-2.0
"""Balance physics under sanitizers, including noisy/stale sensors and long runs."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
CORE=r'''
#include "muse_balance.h"
#include <assert.h>
#include <math.h>
#include <stdlib.h>
static void step(muse_balance_t *g,unsigned now,float x,float y,float z) {
 muse_motion_t s={x,y,z,now};muse_balance_tick(g,now,&s);
}
static void ready(muse_balance_t *g) {
 muse_balance_start(g,100,332,244);
 for(unsigned i=140;i<=1220;i+=40) step(g,i,0,0,1);
 assert(g->phase==MUSE_BALANCE_PLAYING);
}
int main(int argc,char **argv) {
 assert(argc==2);int n=atoi(argv[1]);muse_balance_t g;
 if(n==0) {ready(&g);assert(g.elapsed_ms==80);assert(fabsf(g.x)<2);}
 if(n==1) {
  ready(&g);for(unsigned t=1260;t<10000 && g.phase==MUSE_BALANCE_PLAYING;t+=40) step(&g,t,0.5,0,0.86);
  assert(g.phase==MUSE_BALANCE_LOST && g.x>140 && fabsf(g.y)<100);
  ready(&g);for(unsigned t=1260;t<10000 && g.phase==MUSE_BALANCE_PLAYING;t+=40) step(&g,t,0,-0.5,0.86);
  assert(g.phase==MUSE_BALANCE_LOST && g.y< -100);
 }
 if(n==2) {
  muse_balance_start(&g,100,332,244);
  for(unsigned t=140;t<=8300;t+=40) step(&g,t,(t/40)%2?0.2:-0.2,0,1);
  assert(g.phase==MUSE_BALANCE_CALIBRATION_ERROR);
  muse_balance_start(&g,100,332,244);
  for(unsigned t=140;t<=8300;t+=40) step(&g,t,0,1,0);
  assert(g.phase==MUSE_BALANCE_CALIBRATION_ERROR);
 }
 if(n==3) {
  ready(&g);unsigned elapsed=g.elapsed_ms;float x=g.x;
  for(unsigned t=1260;t<2300;t+=40)muse_balance_tick(&g,t,NULL);
  assert(g.phase==MUSE_BALANCE_SENSOR_ERROR && g.x==x && g.elapsed_ms==elapsed);
  ready(&g);muse_motion_t s={0,0,1,1220};
  for(unsigned t=1260;t<2300;t+=40)muse_balance_tick(&g,t,&s);
  assert(g.phase==MUSE_BALANCE_SENSOR_ERROR && g.elapsed_ms==elapsed);
 }
 if(n==4) {
  ready(&g);muse_motion_t s={NAN,0,1,1260};muse_balance_tick(&g,1260,&s);
  s=(muse_motion_t){INFINITY,0,1,1300};muse_balance_tick(&g,1300,&s);
  s=(muse_motion_t){0,0,0,1340};muse_balance_tick(&g,1340,&s);
  s=(muse_motion_t){0,0,1,999999};muse_balance_tick(&g,1380,&s);
  assert(g.elapsed_ms==80 && isfinite(g.x));
  muse_balance_tick(&g,1390,NULL);step(&g,1420,0,0,1);assert(g.phase==MUSE_BALANCE_PLAYING);
  step(&g,1400,0,0,1);assert(g.phase==MUSE_BALANCE_SENSOR_ERROR);
 }
 if(n==5) {
  ready(&g);step(&g,999999,0,0,1);assert(g.elapsed_ms==120 && fabsf(g.x)<5);
  muse_balance_cancel(&g);step(&g,1000100,1,0,0);assert(g.phase==MUSE_BALANCE_OFF && g.elapsed_ms==0);
 }
 if(n==6) {
  ready(&g);
  // Closed-loop simulated player corrects gravity to keep the ball centered.
  for(unsigned t=1260;t<35000 && g.phase==MUSE_BALANCE_PLAYING;t+=40) {
   float x=(-g.x*2-g.vx*3)/420,y=(-g.y*2-g.vy*3)/420;
   step(&g,t,x,y,1);
  }
  assert(g.phase==MUSE_BALANCE_WON && g.elapsed_ms==30000);
  float x=g.x;step(&g,99999,1,1,1);assert(g.x==x && g.elapsed_ms==30000);
 }
 if(n==7) {
  for(unsigned round=0;round<2000;round++) {
   ready(&g);
   for(unsigned t=1260;t<12000 && g.phase==MUSE_BALANCE_PLAYING;t+=40) {
    float x=sinf(t*0.0004f+round)*0.2f,y=cosf(t*0.0007f+round)*0.2f;
    step(&g,t,x,y,1);assert(isfinite(g.x) && isfinite(g.y));
    assert(fabsf(g.x)<=g.half_w && fabsf(g.y)<=g.half_h);
   }
   muse_balance_cancel(&g);
  }
 }
}
'''
class BalanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='muse-balance-');cls.root=Path(cls.tmp.name)
        (cls.root/'main.c').write_text(CORE);cls.exe=cls.root/'test'
        subprocess.run(shlex.split(os.getenv('CC','cc'))+['-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(ROOT/'components/muse'),str(cls.root/'main.c'),str(ROOT/'components/muse/muse_balance.c'),'-lm','-o',str(cls.exe)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_case(self,n):
        r=subprocess.run([str(self.exe),str(n)],capture_output=True,text=True,timeout=20)
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
for i,name in enumerate(('calibration','axes_and_loss','motion_and_upright_rejected','missing_and_stale','invalid_inputs','clock_stalls_and_cancel','win_once','repeat_stress')):
    setattr(BalanceTests,'test_'+name,lambda self,n=i:self.run_case(n))
if __name__=='__main__':unittest.main()
