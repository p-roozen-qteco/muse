/* Copyright (c) Meta Platforms, Inc. and affiliates.
 * SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Download only from the authenticated Muse VM. No arbitrary remote URLs. */
typedef enum { MUSE_AUDIO_FILE = 1, MUSE_AUDIO_REPLY = 2 } muse_audio_source_t;
typedef struct {
    muse_audio_source_t source;
    char target[512];
    char text[1024];
} muse_audio_message_t;
typedef struct {
    size_t frames;
    char error[96];
} muse_audio_message_result_t;
typedef void (*muse_audio_message_done_t)(const muse_audio_message_result_t *, void *);

static inline bool muse_audio_message_path(muse_audio_source_t source, const char *target,
                                           bool legacy, char *out, size_t cap)
{
    if (!target || !*target || strlen(target) >= 512) return false;
    const char *prefix;
    if (source == MUSE_AUDIO_FILE) {
        if (legacy) return false;
        while (*target == '/') target++;
        if (!*target) return false;
        prefix = "/fs/raw/";
    } else if (source == MUSE_AUDIO_REPLY) {
        prefix = legacy ? "/voice/tts-stream?message_id=" : "/api/voice/tts-stream?message_id=";
    } else return false;
    size_t n = strlen(prefix);
    if (n >= cap) return false;
    memcpy(out, prefix, n);
    for (const unsigned char *c = (const unsigned char *)target; *c; c++) {
        bool plain = (*c >= 'a' && *c <= 'z') || (*c >= 'A' && *c <= 'Z') ||
            (*c >= '0' && *c <= '9') || strchr("-._~", *c) || (source == MUSE_AUDIO_FILE && *c == '/');
        if (n + (plain ? 1 : 3) >= cap) return false;
        if (plain) out[n++] = *c;
        else { out[n++] = '%'; out[n++] = "0123456789ABCDEF"[*c >> 4]; out[n++] = "0123456789ABCDEF"[*c & 15]; }
    }
    out[n] = 0;
    return true;
}
