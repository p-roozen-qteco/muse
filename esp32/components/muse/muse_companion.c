/* SPDX-License-Identifier: Apache-2.0 */
#include "muse_companion.h"
#include <math.h>
#include <string.h>

static float unit(float v) { return fminf(1, fmaxf(0, v)); }
static float coord(float v) { return fminf(1, fmaxf(-1, v)); }

void muse_companion_cancel(muse_companion_t *c)
{
    memset(c, 0, sizeof(*c));
}

void muse_companion_press(muse_companion_t *c, float x, float y, float now)
{
    muse_companion_cancel(c);
    c->down = true;
    c->x = c->origin_x = coord(x);
    c->y = c->origin_y = coord(y);
    c->pressed_at = now;
    c->attention_until = now + 1.2f;
}

void muse_companion_move(muse_companion_t *c, float x, float y, float now)
{
    if (!c->down) return;
    /* Horizontal swipes open Settings; a large drag is not a pet. */
    if (fabsf(x - c->origin_x) > 0.22f || fabsf(y - c->origin_y) > 0.65f) {
        muse_companion_cancel(c);
        return;
    }
    c->x = coord(x);
    c->y = coord(y);
    c->attention_until = now + 1.2f;
}

void muse_companion_release(muse_companion_t *c, float now)
{
    if (!c->down) return;
    if (now - c->pressed_at >= 0.6f) c->happy_until = now + 1.8f;
    c->down = false;
    c->attention_until = now + 1.2f;
}

void muse_companion_tap(muse_companion_t *c, float now)
{
    /* release precedes CLICKED. A cancelled gesture has no attention left. */
    if (c->attention_until <= now || now - c->pressed_at >= 0.6f) return;
    c->wink_at = now;
    c->happy_until = now + 1.4f;
}

void muse_companion_pose(muse_companion_t *c, muse_pose_t *p)
{
    p->attention = p->gaze_x = p->gaze_y = p->wink = 0;
    if (p->mode != MUSE_MODE_IDLE) {
        muse_companion_cancel(c);
        return;
    }
    float now = p->t;
    p->attention = c->down ? 1 : unit((c->attention_until - now) / 1.2f);
    p->gaze_x = c->x;
    p->gaze_y = c->y;
    float wt = now - c->wink_at;
    if (c->wink_at > 0 && wt >= 0 && wt < 0.5f) p->wink = sinf(wt * 6.2831853f);
    float held = c->down ? unit((now - c->pressed_at - 0.6f) / 0.8f) : 0;
    float happy = fmaxf(held, unit((c->happy_until - now) / 1.8f));
    p->happy = fmaxf(p->happy, happy);
}
