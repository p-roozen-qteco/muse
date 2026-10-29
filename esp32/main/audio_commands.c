/* Copyright (c) Meta Platforms, Inc. and affiliates.
 * SPDX-License-Identifier: Apache-2.0 */
#include "audio_commands.h"
#include "muse_voice.h"
#include <stdlib.h>
#include <string.h>

typedef struct {
    noise_ctrl_session_generation_t generation;
    char id[64];
} audio_result_ctx_t;

static cJSON *failure(const char *code, const char *message)
{
    cJSON *r = cJSON_CreateObject();
    cJSON_AddBoolToObject(r, "ok", false);
    cJSON *e = cJSON_AddObjectToObject(r, "error");
    cJSON_AddStringToObject(e, "code", code);
    cJSON_AddStringToObject(e, "message", message);
    return r;
}

static cJSON *parameter(const char *description)
{
    cJSON *p = cJSON_CreateObject();
    cJSON_AddStringToObject(p, "type", "string");
    cJSON_AddStringToObject(p, "description", description);
    return p;
}

static void add_audio_command(cJSON *commands, const char *name, const char *description,
                               const char *key, const char *target_description)
{
    cJSON *c = cJSON_AddObjectToObject(commands, name);
    cJSON_AddStringToObject(c, "description", description);
    cJSON *required = cJSON_AddObjectToObject(c, "required");
    if (key) cJSON_AddItemToObject(required, key, parameter(target_description));
    cJSON *optional = cJSON_AddObjectToObject(c, "optional");
    if (key) cJSON_AddItemToObject(optional, "text", parameter("Optional transcript to show with audio; at most 1023 UTF-8 bytes."));
    cJSON_AddNumberToObject(c, "timeout_ms", key ? 300000 : 10000);
}

void audio_commands_register(cJSON *commands)
{
    if (!muse_voice_audio_ready()) return;
    add_audio_command(commands, "audio.play_file",
        "Play an MP3 file from this VM on the gadget speaker, with optional text captions. "
        "Fetches the private file over the authenticated VM connection. To speak text, first "
        "create an MP3 using the VM's speech tools, then pass its path; the gadget has no local TTS. "
        "MP3 only (convert WAV/Opus to MP3 first). Maximum playback three minutes, mono 16 kHz. "
        "Respects mute and volume. Replies only after playback finishes or fails; BOOT interrupts it.",
        "path", "VM file path as accepted by its file API, e.g. workspace/reply.mp3; under 512 UTF-8 bytes.");
    add_audio_command(commands, "audio.play_reply",
        "Play the existing MP3 of a Muse voice-modality assistant message by its message ID. "
        "Only works when Muse has generated audio for that message; it does not synthesize a "
        "text-only message. For a standalone audio file use audio.play_file. Optional text is "
        "shown as captions. Respects mute and volume; BOOT interrupts. Replies after playback or failure.",
        "message_id", "ID of an assistant message that already has generated voice audio; under 512 bytes.");
    add_audio_command(commands, "audio.stop", "Stop a queued or playing gadget audio message.", NULL, NULL);
}

bool audio_commands_handles(const char *command)
{
    return !strcmp(command, "audio.play_file") || !strcmp(command, "audio.play_reply") || !strcmp(command, "audio.stop");
}

static void audio_done(const muse_audio_message_result_t *played, void *user)
{
    audio_result_ctx_t *ctx = user;
    cJSON *r;
    if (played->error[0] || !played->frames) {
        r = failure("audio_playback_failed", played->error[0] ? played->error : "No audio played");
    } else {
        r = cJSON_CreateObject();
        cJSON_AddBoolToObject(r, "ok", true);
        cJSON *p = cJSON_AddObjectToObject(r, "payload");
        cJSON_AddBoolToObject(p, "played", true);
        cJSON_AddNumberToObject(p, "duration_ms", (double)played->frames / 16);
        cJSON_AddNumberToObject(p, "sample_rate_hz", 16000);
    }
    noise_ctrl_send_command_result(ctx->generation, ctx->id, r);
    free(ctx);
}

cJSON *audio_commands_handle(const char *command, cJSON *params, const char *request_id,
                             noise_ctrl_session_generation_t generation)
{
    if (!audio_commands_handles(command)) return failure("unknown_command", "Unknown audio command");
    if (!strcmp(command, "audio.stop")) {
        muse_voice_stop_message();
        cJSON *r = cJSON_CreateObject();
        cJSON_AddBoolToObject(r, "ok", true);
        return r;
    }
    bool file = !strcmp(command, "audio.play_file");
    const cJSON *target = cJSON_GetObjectItemCaseSensitive(params, file ? "path" : "message_id");
    const cJSON *text = cJSON_GetObjectItemCaseSensitive(params, "text");
    if (!cJSON_IsString(target) || !target->valuestring[0] || strlen(target->valuestring) >= 512 ||
        (text && (!cJSON_IsString(text) || strlen(text->valuestring) >= 1024))) {
        return failure("invalid_params", "Nonempty path/message_id under 512 bytes and optional text under 1024 bytes required");
    }
    if (!request_id || !*request_id || strlen(request_id) >= 64) return failure("invalid_params", "Invalid request ID");
    audio_result_ctx_t *ctx = calloc(1, sizeof(*ctx));
    muse_audio_message_t *request = calloc(1, sizeof(*request));
    cJSON *async = cJSON_CreateObject();
    if (!ctx || !request || !async || !cJSON_AddBoolToObject(async, "_async", true)) {
        free(ctx); free(request); cJSON_Delete(async);
        return failure("out_of_memory", "Audio request could not be allocated");
    }
    ctx->generation = generation;
    strcpy(ctx->id, request_id);
    request->source = file ? MUSE_AUDIO_FILE : MUSE_AUDIO_REPLY;
    strcpy(request->target, target->valuestring);
    if (text) strcpy(request->text, text->valuestring);
    const char *error = NULL;
    bool queued = muse_voice_play_message(request, audio_done, ctx, &error);
    free(request);
    if (!queued) {
        free(ctx); cJSON_Delete(async);
        return failure("audio_unavailable", error ? error : "Audio unavailable");
    }
    return async;
}
