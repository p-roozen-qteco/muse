/* SPDX-License-Identifier: Apache-2.0 */
/* Simulator-only storage adapter. Production uses the tested queued NVS worker. */
#include "muse_pet_store.h"
#include <stdio.h>
#include <stdlib.h>
static bool s_failed;
static const char *s_path;
bool muse_pet_store_start(muse_pet_t *p,uint64_t now)
{
    muse_pet_init(p,now);s_path=getenv("MUSE_SIM_PET_STATE_FILE");s_failed=false;
    if(!s_path) return true;
    FILE *f=fopen(s_path,"rb");
    if(!f) return true;
    uint8_t data[MUSE_PET_RECORD_BYTES+1];size_t n=fread(data,1,sizeof(data),f);fclose(f);
    s_failed=!muse_pet_decode(p,data,n,now);
    return !s_failed;
}
void muse_pet_store_save(const muse_pet_t *p)
{
    if(!s_path || s_failed) return;
    uint8_t data[MUSE_PET_RECORD_BYTES];muse_pet_encode(p,data);
    FILE *f=fopen(s_path,"wb");if(!f) {s_failed=true;return;}
    bool ok=fwrite(data,1,sizeof(data),f)==sizeof(data);
    if(fclose(f)) ok=false;
    s_failed=!ok;
}
bool muse_pet_store_failed(void) {return s_failed;}
