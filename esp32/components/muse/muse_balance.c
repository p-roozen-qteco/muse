/* SPDX-License-Identifier: Apache-2.0 */
#include "muse_balance.h"
#include <math.h>

static float clamp(float v,float lo,float hi) {return v<lo?lo:v>hi?hi:v;}
void muse_balance_start(muse_balance_t *g,uint64_t now,float width,float height)
{
    *g=(muse_balance_t){.phase=MUSE_BALANCE_CALIBRATING,.opened_ms=now,
        .last_ms=now,.last_good_ms=now,.half_w=clamp(width/2-16,20,500),
        .half_h=clamp(height/2-16,20,500)};
}
void muse_balance_cancel(muse_balance_t *g) {*g=(muse_balance_t){0};}
void muse_balance_tick(muse_balance_t *g,uint64_t now,const muse_motion_t *s)
{
    if(g->phase!=MUSE_BALANCE_CALIBRATING && g->phase!=MUSE_BALANCE_PLAYING) return;
    if(now<g->last_ms) {g->phase=MUSE_BALANCE_SENSOR_ERROR;return;}
    uint64_t delta=now-g->last_ms;g->last_ms=now;
    bool valid=s && isfinite(s->x) && isfinite(s->y) && isfinite(s->z) &&
        s->at_ms<=now && now-s->at_ms<=160 && s->at_ms>=g->opened_ms;
    float norm=valid?s->x*s->x+s->y*s->y+s->z*s->z:0;
    valid=valid && norm>0.36f && norm<2.56f;
    /* A stale sample freezes the ball and clock; it cannot fabricate a win.
     * Repeated cached data is not another calibration sample. */
    if(!valid || s->at_ms==g->last_sample_ms) {
        if(now-g->last_good_ms>800) g->phase=MUSE_BALANCE_SENSOR_ERROR;
        return;
    }
    g->last_sample_ms=s->at_ms;g->last_good_ms=now;
    if(g->phase==MUSE_BALANCE_CALIBRATING) {
        if(now-g->opened_ms>8000) {g->phase=MUSE_BALANCE_CALIBRATION_ERROR;return;}
        if(fabsf(s->z)<0.65f) {g->samples=0;return;}
        if(!g->samples) {
            g->min_x=g->max_x=s->x;g->min_y=g->max_y=s->y;
            g->sum_x=g->sum_y=0;g->stable_since_ms=now;
        }
        g->min_x=fminf(g->min_x,s->x);g->max_x=fmaxf(g->max_x,s->x);
        g->min_y=fminf(g->min_y,s->y);g->max_y=fmaxf(g->max_y,s->y);
        if(g->max_x-g->min_x>0.07f || g->max_y-g->min_y>0.07f) {g->samples=0;return;}
        g->sum_x+=s->x;g->sum_y+=s->y;++g->samples;
        if(g->samples>=20 && now-g->stable_since_ms>=1000) {
            g->zero_x=g->sum_x/g->samples;g->zero_y=g->sum_y/g->samples;
            g->phase=MUSE_BALANCE_PLAYING;g->vx=12;g->vy=-8;
        }
        return;
    }
    /* No catch-up after UI stalls; cap to 40 ms, substep at <=10 ms. */
    unsigned ms=delta>40?40:(unsigned)delta;
    if(!ms) return;
    float seconds=ms*0.001f,alpha=seconds/(0.12f+seconds);
    float tx=clamp(s->x-g->zero_x,-0.65f,0.65f),ty=clamp(s->y-g->zero_y,-0.65f,0.65f);
    if(fabsf(tx)<0.018f) tx=0;
    if(fabsf(ty)<0.018f) ty=0;
    g->filtered_x+=alpha*(tx-g->filtered_x);g->filtered_y+=alpha*(ty-g->filtered_y);
    unsigned steps=(ms+9)/10;float dt=seconds/steps;
    /* A gentle changing drift makes balancing a game even on a flat table. */
    float t=g->elapsed_ms*0.001f;
    float drift=10+g->elapsed_ms/3000.0f;
    for(unsigned i=0;i<steps;i++) {
        g->vx=clamp(g->vx+(g->filtered_x*420+drift*cosf(t*0.65f)-0.7f*g->vx)*dt,-180,180);
        g->vy=clamp(g->vy+(g->filtered_y*420+drift*sinf(t*0.51f)-0.7f*g->vy)*dt,-180,180);
        g->x+=g->vx*dt;g->y+=g->vy*dt;
        if(fabsf(g->x)>=g->half_w || fabsf(g->y)>=g->half_h) {
            g->x=clamp(g->x,-g->half_w,g->half_w);g->y=clamp(g->y,-g->half_h,g->half_h);
            g->phase=MUSE_BALANCE_LOST;return;
        }
    }
    g->elapsed_ms+=ms;
    if(g->elapsed_ms>=30000) {g->elapsed_ms=30000;g->phase=MUSE_BALANCE_WON;}
}
