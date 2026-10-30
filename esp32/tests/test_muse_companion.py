# SPDX-License-Identifier: Apache-2.0
"""Touch state and actual renderer, including audio priority and bounded memory."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CODE = r'''
#include "muse_companion.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static muse_pose_t pose(muse_companion_t *c, float t, muse_mode_t mode) {
    muse_pose_t p = {.mode=mode,.t=t,.mode_t=2,.level=.8f};
    muse_companion_pose(c,&p); return p;
}
int main(int argc,char **argv) {
    assert(argc==2);
    muse_companion_t c={0};
    muse_pose_t p;
    if (!strcmp(argv[1],"tap")) {
        muse_companion_press(&c,-.8f,.4f,10);
        p=pose(&c,10.1f,MUSE_MODE_IDLE);
        assert(p.attention==1 && p.gaze_x==-.8f && p.gaze_y==.4f && !p.happy);
        muse_companion_release(&c,10.15f); muse_companion_tap(&c,10.15f);
        p=pose(&c,10.4f,MUSE_MODE_IDLE); assert(p.wink>.99f && p.happy>0);
        p=pose(&c,13,MUSE_MODE_IDLE); assert(!p.attention && !p.happy && !p.wink);
    } else if (!strcmp(argv[1],"hold")) {
        muse_companion_press(&c,.8f,-.5f,10);
        muse_companion_move(&c,.75f,-.3f,10.4f);
        p=pose(&c,11.5f,MUSE_MODE_IDLE); assert(p.happy==1 && p.attention==1);
        muse_companion_release(&c,11.6f); muse_companion_tap(&c,11.6f);
        p=pose(&c,11.8f,MUSE_MODE_IDLE); assert(p.happy>.8f && !p.wink);
    } else if (!strcmp(argv[1],"cancel")) {
        for(int i=0;i<3;i++) {
            muse_companion_press(&c,0,0,10);
            if(i==0) muse_companion_move(&c,.4f,0,10.2f);
            if(i==1) muse_companion_move(&c,0,.8f,10.2f);
            if(i==2) muse_companion_cancel(&c);
            muse_companion_release(&c,10.3f); muse_companion_tap(&c,10.3f);
            p=pose(&c,10.5f,MUSE_MODE_IDLE);
            assert(!c.down && !p.happy && !p.attention && !p.wink);
        }
    } else if (!strcmp(argv[1],"priority")) {
        for(int mode=0;mode<MUSE_MODE_COUNT;mode++) {
            if(mode==MUSE_MODE_IDLE) continue;
            muse_companion_press(&c,1,1,10);
            p=pose(&c,12,(muse_mode_t)mode);
            assert(!c.down && !p.attention && !p.wink && !p.happy && p.level==.8f);
            p=pose(&c,12.1f,MUSE_MODE_IDLE); assert(!p.happy && !p.attention);
        }
    } else if (!strcmp(argv[1],"stress")) {
        for(int i=0;i<100000;i++) {
            float t=1+i*.04f;
            if(i%31==0) muse_companion_press(&c,10,-10,t);
            if(i%31==1) muse_companion_release(&c,t);
            if(i%31==2) muse_companion_tap(&c,t);
            p=pose(&c,t,(muse_mode_t)(i%MUSE_MODE_COUNT));
            assert(isfinite(p.happy) && p.happy>=0 && p.happy<=1);
            assert(p.attention>=0 && p.attention<=1 && fabsf(p.gaze_x)<=1 && fabsf(p.gaze_y)<=1);
        }
    } else {
        int mode=atoi(argv[1]);
        p=(muse_pose_t){.mode=(muse_mode_t)mode,.t=10,.mode_t=2,.level=.8f};
        if(getenv("PET")) {p.happy=1; p.wink=1; p.attention=1;p.gaze_x=1;}
        muse_pixel_set_size(64); muse_pixel_render(&p);
        uint16_t pixels[64*64]; muse_pixel_scale(pixels,64,0,63,0,63);
        fwrite(pixels,1,sizeof(pixels),stdout);
    }
}
'''

class Companion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(); cls.addClassCleanup(cls.tmp.cleanup)
        path=Path(cls.tmp.name); (path/'test.c').write_text(CODE); cls.binary=path/'test'
        cmd=[*shlex.split(os.environ.get('CC','cc')), '-std=c11','-Wall','-Wextra','-Werror',
             '-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',
             '-I',str(ROOT/'components/muse'),str(path/'test.c'),
             str(ROOT/'components/muse/muse_companion.c'), str(ROOT/'avatar/muse_pixel.c'),
             '-lm','-o',str(cls.binary)]
        proc=subprocess.run(cmd,capture_output=True,text=True)
        if proc.returncode: raise AssertionError(proc.stderr)

    def run_case(self,case,pet=False):
        env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1'}
        if pet: env['PET']='1'
        else: env.pop('PET',None)
        r=subprocess.run([str(self.binary),str(case)],capture_output=True,env=env)
        self.assertEqual(r.returncode,0,r.stderr.decode()); return r.stdout

    def test_tap_gaze_wink_and_decay(self): self.run_case('tap')
    def test_hold_and_release(self): self.run_case('hold')
    def test_navigation_and_lost_touch_cancel(self): self.run_case('cancel')
    def test_audio_and_other_modes_cancel_reaction(self): self.run_case('priority')
    def test_100000_transitions_are_bounded(self): self.run_case('stress')
    def test_renderer_preserves_all_nonidle_expressions(self):
        for mode in (0,2,3,4,5,6):
            with self.subTest(mode=mode): self.assertEqual(self.run_case(mode),self.run_case(mode,True))
    def test_idle_reaction_changes_actual_pixels(self): self.assertNotEqual(self.run_case(1),self.run_case(1,True))
