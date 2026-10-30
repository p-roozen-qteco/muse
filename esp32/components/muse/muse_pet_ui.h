/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include "lvgl.h"
#include "muse_pixel.h"
#include "muse_pet.h"
#include "muse_balance.h"
/* All calls belong to the LVGL task. Audio/storage never mutate this state. */
void muse_pet_ui_build(lv_obj_t *face,int width,int height);
bool muse_pet_ui_tick(uint64_t now_ms,bool visible);
void muse_pet_ui_hide(void);
bool muse_pet_ui_game_open(void);
void muse_pet_ui_pose(muse_pose_t *pose);
void muse_pet_ui_pat(uint64_t now_ms);
const char *muse_pet_ui_name(void);
/* Simulator/bench observers run on the same UI task; no cross-task access. */
void muse_pet_ui_snapshot(muse_pet_t *pet,muse_pet_game_t *game);

void muse_pet_ui_balance_snapshot(muse_balance_t *balance);
