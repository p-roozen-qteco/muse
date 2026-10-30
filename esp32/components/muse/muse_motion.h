/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include <stdbool.h>
#include <stdint.h>

/* Gravity in g, in portrait screen axes (x right, y down, z normal).
 * at_ms is the monotonic acquisition time, never the time of a cache read. */
typedef struct { float x, y, z; uint64_t at_ms; } muse_motion_t;
