/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum { MUSE_PET_CONTENT, MUSE_PET_PLAYFUL, MUSE_PET_SLEEPY,
               MUSE_PET_HUNGRY, MUSE_PET_RESTING } muse_pet_mood_t;
typedef struct {
    uint8_t food, energy, joy, bonus_minutes, best;
    bool resting, playful;
    uint16_t xp, care;
    uint32_t minutes;
    uint64_t last_ms;
} muse_pet_t;
typedef struct {
    bool active, finished;
    uint8_t cell, score;
    uint32_t random;
    uint64_t end_ms;
} muse_pet_game_t;

#define MUSE_PET_RECORD_BYTES 24
void muse_pet_init(muse_pet_t *p, uint64_t now_ms);
bool muse_pet_tick(muse_pet_t *p, uint64_t now_ms);
bool muse_pet_feed(muse_pet_t *p);
bool muse_pet_pat(muse_pet_t *p);
void muse_pet_rest(muse_pet_t *p);
muse_pet_mood_t muse_pet_mood(const muse_pet_t *p);
const char *muse_pet_mood_name(muse_pet_mood_t mood);
void muse_pet_encode(const muse_pet_t *p, uint8_t out[MUSE_PET_RECORD_BYTES]);
/* Invalid or future records are rejected without modifying the destination. */
bool muse_pet_decode(muse_pet_t *p, const uint8_t *data, size_t n, uint64_t now_ms);
void muse_pet_game_start(muse_pet_game_t *g, uint64_t now_ms, uint32_t seed);
bool muse_pet_game_hit(muse_pet_game_t *g, uint8_t cell, uint64_t now_ms);
bool muse_pet_game_finish(muse_pet_game_t *g, muse_pet_t *p, uint64_t now_ms);
void muse_pet_game_cancel(muse_pet_game_t *g);
