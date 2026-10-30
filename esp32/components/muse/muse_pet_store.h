/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include "muse_pet.h"
/* Once at UI startup, after the app has initialized NVS. Never erases NVS. */
bool muse_pet_store_start(muse_pet_t *p, uint64_t now_ms);
/* Copies a bounded snapshot into a one-item overwrite queue; never blocks UI. */
void muse_pet_store_save(const muse_pet_t *p);
bool muse_pet_store_failed(void);
