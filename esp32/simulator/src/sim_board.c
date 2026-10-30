/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "sim_board.h"
#include "sim_platform.h"
#include "sdkconfig.h"
#include <string.h>

#include "src/drivers/sdl/lv_sdl_mouse.h"
#include "src/drivers/sdl/lv_sdl_window.h"

#define WATCHER_RESOLUTION 412

static lv_display_t *s_display;
static bool s_s3_18;
static bool s_motion_on,s_motion_valid=true,s_motion_stale;
static muse_motion_t s_motion={.z=1};
void sim_board_motion(float x,float y,float z,bool valid,bool stale)
{s_motion.x=x;s_motion.y=y;s_motion.z=z;s_motion_valid=valid;s_motion_stale=stale;}
bool sim_board_motion_enabled(void) {return s_motion_on;}
#if CONFIG_MUSE_PET
static void sim_motion_enable(bool on) {s_motion_on=on;}
static bool sim_motion_read(muse_motion_t *out)
{
    if(!s_motion_on || !s_motion_valid) return false;
    if(!s_motion_stale) s_motion.at_ms=sim_time_tick_ms();
    *out=s_motion;return true;
}
#endif

/* muse_ui.c reads the selected board through this production global. */
const muse_board_t *muse_board;

static esp_err_t sim_init(void)
{
    return ESP_OK;
}

static lv_display_t *sim_display_start(lv_indev_t **touch)
{
    s_display = lv_sdl_window_create(muse_board->width, muse_board->height);
    if (!s_display) {
        return NULL;
    }
    /* The SDL driver installs SDL_GetTicks. Use the simulator clock instead so
     * scripted runs can advance time without sleeping and render repeatably. */
    lv_tick_set_cb(sim_time_tick_ms);
    lv_sdl_window_set_title(s_display, muse_board->name);
    lv_sdl_window_set_resizeable(s_display, false);
    if (touch) {
        *touch = lv_sdl_mouse_create();
    }
    return s_display;
}

static bool sim_display_lock(int timeout_ms)
{
    (void)timeout_ms;
    return true;
}

static void sim_display_unlock(void)
{
}

static void sim_set_brightness(int pct)
{
    (void)pct;
}

static void sim_panel_sleep(bool sleep)
{
    (void)sleep;
}

static esp_err_t sim_power_off(void)
{
    return ESP_FAIL;
}

static const muse_board_t s_sim_board = {
    .name = "SenseCAP Watcher Simulator",
    .width = WATCHER_RESOLUTION,
    .height = WATCHER_RESOLUTION,
    .round = true,
    .touch = true,
    .diagonal_in = 1.45f,
    .talk_button = "wheel",
    .aux_button = "scroll",
    .talk_hint = { LV_ALIGN_CENTER, 100, -143 },
    .frame_ms = 40,
    .init = sim_init,
    .display_start = sim_display_start,
    .display_lock = sim_display_lock,
    .display_unlock = sim_display_unlock,
    .set_brightness = sim_set_brightness,
    .panel_sleep = sim_panel_sleep,
    .power_off = sim_power_off,
};

#if CONFIG_MUSE_PET
/* Advertise audio capability for reply-layout preview only. No audio device
 * is created and the simulator never records or plays sound. */
static esp_err_t sim_audio_unavailable(esp_codec_dev_handle_t *spk, esp_codec_dev_handle_t *mic)
{
    *spk = NULL;
    *mic = NULL;
    return ESP_FAIL;
}
#endif

const muse_board_t *sim_board_get(void)
{
    if (s_s3_18) {
        static muse_board_t board;
        board = s_sim_board;
        board.name = "Waveshare S3 AMOLED 1.8 Simulator";
        board.width = 368;
        board.height = 448;
        board.round = false;
        board.diagonal_in = 1.8f;
#if CONFIG_MUSE_PET
        board.audio_init = sim_audio_unavailable;
        board.motion_enable=sim_motion_enable;board.motion_read=sim_motion_read;
#endif
        board.talk_button = "boot";
        board.aux_button = "pwr";
        board.talk_hint = (muse_button_hint_t){0};
        return &board;
    }
    return &s_sim_board;
}

bool sim_board_select(const char *name)
{
    if (strcmp(name, "watcher") && strcmp(name, "s3-18")) return false;
    s_s3_18 = !strcmp(name, "s3-18");
    return true;
}

lv_display_t *sim_board_display(void)
{
    return s_display;
}
