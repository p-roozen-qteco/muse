/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include "muse_pixel.h"

/* UI-task owned, allocation-free interaction. Coordinates are -1..1 across
 * the face canvas; times are monotonic seconds. Navigation always wins. */
typedef struct {
    bool down;
    float x, y, origin_x, origin_y, pressed_at, attention_until, wink_at, happy_until;
} muse_companion_t;

void muse_companion_cancel(muse_companion_t *c);
void muse_companion_press(muse_companion_t *c, float x, float y, float now);
void muse_companion_move(muse_companion_t *c, float x, float y, float now);
void muse_companion_release(muse_companion_t *c, float now);
/* Call only for LVGL's validated CLICKED event, never on a navigation gesture. */
void muse_companion_tap(muse_companion_t *c, float now);
void muse_companion_pose(muse_companion_t *c, muse_pose_t *pose);
