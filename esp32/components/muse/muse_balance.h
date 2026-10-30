/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include "muse_motion.h"

typedef enum {
    MUSE_BALANCE_OFF, MUSE_BALANCE_CALIBRATING, MUSE_BALANCE_PLAYING,
    MUSE_BALANCE_LOST, MUSE_BALANCE_WON, MUSE_BALANCE_SENSOR_ERROR,
    MUSE_BALANCE_CALIBRATION_ERROR
} muse_balance_phase_t;
typedef struct {
    muse_balance_phase_t phase;
    float x,y,vx,vy,half_w,half_h,zero_x,zero_y,filtered_x,filtered_y;
    float sum_x,sum_y,min_x,max_x,min_y,max_y;
    unsigned samples,elapsed_ms;
    uint64_t opened_ms,last_ms,last_sample_ms,last_good_ms,stable_since_ms;
} muse_balance_t;

/* Pure bounded physics; no allocations, persistence, I/O or wall-clock waits. */
void muse_balance_start(muse_balance_t *g,uint64_t now,float width,float height);
void muse_balance_tick(muse_balance_t *g,uint64_t now,const muse_motion_t *sample);
void muse_balance_cancel(muse_balance_t *g);
