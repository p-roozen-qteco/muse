/* SPDX-License-Identifier: Apache-2.0 */
#pragma once
#include "driver/i2c_master.h"
#include "muse_motion.h"
/* S3 1.8 portrait orientation. Init once, poll only from the input task.
 * request/read are safe on the LVGL task and perform no bus transactions. */
bool muse_qmi8658_init(i2c_master_bus_handle_t bus);
void muse_qmi8658_request(bool on);
void muse_qmi8658_poll(uint64_t now_ms,bool allowed);
bool muse_qmi8658_read(muse_motion_t *out);
