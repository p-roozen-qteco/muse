/* SPDX-License-Identifier: Apache-2.0 */
#include "muse_pet.h"
#include <string.h>

static uint8_t add(uint8_t a, unsigned b) { return a + b > 100 ? 100 : a + b; }
static uint8_t sub(uint8_t a, unsigned b) { return b > a ? 0 : a - b; }
static void earn(muse_pet_t *p, unsigned xp)
{
    p->xp = xp > UINT16_MAX - (unsigned)p->xp ? UINT16_MAX : p->xp + xp;
    if (p->care < UINT16_MAX) ++p->care;
}
void muse_pet_init(muse_pet_t *p, uint64_t now_ms)
{
    *p = (muse_pet_t){.food=75, .energy=80, .joy=70, .last_ms=now_ms};
}
bool muse_pet_tick(muse_pet_t *p, uint64_t now_ms)
{
    if (now_ms < p->last_ms) { p->last_ms = now_ms; return false; }
    uint64_t elapsed = (now_ms - p->last_ms) / 60000;
    if (!elapsed) return false;
    p->last_ms += elapsed * 60000;
    /* Bounded work even after a very large clock jump. No offline punishment:
     * boot starts a new monotonic epoch from the saved needs. */
    unsigned n = elapsed > 10080 ? 10080 : (unsigned)elapsed;
    p->food = sub(p->food, (p->minutes % 20 + n) / 20);
    p->joy = sub(p->joy, (p->minutes % 30 + n) / 30);
    if (p->resting) p->energy = add(p->energy, (p->minutes % 2 + n) / 2);
    else p->energy = sub(p->energy, (p->minutes % 15 + n) / 15);
    p->bonus_minutes = sub(p->bonus_minutes, n);
    p->minutes += n;
    return true;
}
bool muse_pet_feed(muse_pet_t *p)
{
    if (p->food >= 100) return false;
    p->food = add(p->food, 25); p->joy = add(p->joy, 5);
    p->playful = false; p->bonus_minutes = 15; earn(p, 2);
    return true;
}
bool muse_pet_pat(muse_pet_t *p)
{
    if (p->joy >= 100 || p->resting) return false;
    p->joy = add(p->joy, 3); p->playful = true; p->bonus_minutes = 5;
    earn(p, 1); return true;
}
void muse_pet_rest(muse_pet_t *p) { p->resting = !p->resting; }
muse_pet_mood_t muse_pet_mood(const muse_pet_t *p)
{
    if (p->resting) return MUSE_PET_RESTING;
    if (p->energy < 25) return MUSE_PET_SLEEPY;
    if (p->food < 25) return MUSE_PET_HUNGRY;
    if ((p->bonus_minutes && p->playful) || p->joy > 85) return MUSE_PET_PLAYFUL;
    return MUSE_PET_CONTENT;
}
const char *muse_pet_mood_name(muse_pet_mood_t mood)
{
    static const char *const names[] = {"Tevreden", "Speels", "Slaperig", "Een beetje trek", "Even uitrusten"};
    return mood <= MUSE_PET_RESTING && mood >= 0 ? names[mood] : names[0];
}
static uint32_t hash(const uint8_t *b, size_t n)
{
    uint32_t h = 2166136261u;
    for (size_t i=0; i<n; ++i) h = (h ^ b[i]) * 16777619u;
    return h;
}
static void put(uint8_t *b, uint32_t v, int n) { for(int i=0;i<n;i++) b[i]=(uint8_t)(v>>(8*i)); }
static uint32_t get(const uint8_t *b, int n) { uint32_t v=0; for(int i=0;i<n;i++) v|=(uint32_t)b[i]<<(8*i); return v; }
void muse_pet_encode(const muse_pet_t *p, uint8_t b[MUSE_PET_RECORD_BYTES])
{
    memcpy(b,"MPET",4); b[4]=1; b[5]=p->food; b[6]=p->energy; b[7]=p->joy;
    b[8]=p->resting; b[9]=p->playful; b[10]=p->bonus_minutes; b[11]=p->best;
    put(b+12,p->xp,2); put(b+14,p->minutes,4); put(b+18,p->care,2); put(b+20,hash(b,20),4);
}
bool muse_pet_decode(muse_pet_t *p, const uint8_t *b, size_t n, uint64_t now_ms)
{
    if (!b || n!=MUSE_PET_RECORD_BYTES || memcmp(b,"MPET",4) || b[4]!=1 ||
        b[5]>100 || b[6]>100 || b[7]>100 || b[8]>1 || b[9]>1 || b[10]>60 ||
        b[11]>99 || get(b+20,4)!=hash(b,20)) return false;
    *p=(muse_pet_t){.food=b[5],.energy=b[6],.joy=b[7],.resting=b[8],.playful=b[9],
        .bonus_minutes=b[10],.best=b[11],.xp=(uint16_t)get(b+12,2),.minutes=get(b+14,4),
        .care=(uint16_t)get(b+18,2),.last_ms=now_ms};
    return true;
}
void muse_pet_game_start(muse_pet_game_t *g, uint64_t now_ms, uint32_t seed)
{
    *g=(muse_pet_game_t){.active=true,.cell=4,.random=seed ? seed : 1,.end_ms=now_ms+20000};
}
bool muse_pet_game_hit(muse_pet_game_t *g, uint8_t cell, uint64_t now_ms)
{
    if (!g->active || now_ms>=g->end_ms || cell!=g->cell) return false;
    if(g->score<99) ++g->score;
    g->random=g->random*1664525u+1013904223u;
    g->cell=(g->cell+1+g->random%8)%9;
    return true;
}
bool muse_pet_game_finish(muse_pet_game_t *g, muse_pet_t *p, uint64_t now_ms)
{
    if (!g->active || now_ms<g->end_ms) return false;
    g->active=false; g->finished=true;
    if (!g->score) return false;
    unsigned reward=g->score>15 ? 15 : g->score;
    p->joy=add(p->joy,reward); p->energy=sub(p->energy,3); p->food=sub(p->food,2);
    p->playful=true; p->bonus_minutes=20; p->resting=false;
    if(g->score>p->best) p->best=g->score;
    earn(p,reward); return true;
}
void muse_pet_game_cancel(muse_pet_game_t *g) { *g=(muse_pet_game_t){0}; }
