/* Copyright (c) Meta Platforms, Inc. and affiliates.
 * SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include "cJSON.h"
#include "noise_control.h"
void audio_commands_register(cJSON *commands);
bool audio_commands_handles(const char *command);
cJSON *audio_commands_handle(const char *command, cJSON *params, const char *request_id,
                             noise_ctrl_session_generation_t generation);
