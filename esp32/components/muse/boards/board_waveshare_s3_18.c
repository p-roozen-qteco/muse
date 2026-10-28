/*
 * Copyright (c) Meta Platforms, Inc. and affiliates.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/*
 * Waveshare ESP32-S3-Touch-AMOLED-1.8, V2 revision only: 368x448 CO5300
 * AMOLED over QSPI with CST820 touch over I2C, ES8311 speaker + mic,
 * AXP2101 PMU, ESP32-S3R8 (8 MB octal PSRAM, 16 MB flash). BOOT (GPIO0)
 * talks; PWR reaches the ESP32 only through the AXP2101, so it is read
 * from the PMU's key latch. Native USB Serial/JTAG.
 *
 * Pin/fact sources (devices/AGENTS.md: cite, do not guess):
 *  - Waveshare wiki: https://docs.waveshare.com/ESP32-S3-Touch-AMOLED-1.8
 *    (V2 = CO5300 + CST820; V1 = SH8601 + FT3168, not this board).
 *  - Vendor repo waveshareteam/ESP32-S3-Touch-AMOLED-1.8,
 *    examples/arduino-v2/libraries/Mylibrary/pin_config.h (the V2 pin map:
 *    QSPI CS=12, SCLK=11, DATA0-3=4-7; touch I2C SDA=15, SCL=14, INT=21;
 *    I2S MCK=16, BCK=9, DIN=10, WS=45, DOUT=8, amp enable=46; SD
 *    CLK=2, CMD=1, DATA=3) and examples/esp-idf/12_i2s_codec (V2 touch
 *    probe at I2C address 0x15).
 *  - Vendor BSP waveshare/esp32_s3_touch_amoled_1_8 ^2.0.3
 *    (waveshareteam/Waveshare-ESP32-components, bsp/esp32_s3_touch_amoled_1_8):
 *    BSP_LCD_H_RES 368, BSP_LCD_V_RES 448, BSP_I2S_* pins as above,
 *    LCD_RST and TOUCH_RST are GPIO_NC (resets go through the TCA9554
 *    expander, not to ESP32 GPIOs), and the panel is always CO5300 in
 *    this BSP version. The BSP drives V2 touch through its CST816S
 *    driver (it probes the CST816S address, then falls back to FT5x06);
 *    the vendor README notes CST816x identifiers are used for the
 *    compatible V2 touch code.
 *  - Schematic: https://files.waveshare.com/wiki/ESP32-S3-Touch-AMOLED-1.8/ESP32-S3-Touch-AMOLED-1.8.pdf
 *    (QSPI/I2C/I2S nets agree with the pin map above).
 *
 * Deliberate non-changes, all unverified on hardware (see the pull
 * request): the AXP2101 rails are left as the BSP/factory defaults. The
 * vendor's AXP2101 example only reads rails, the BSP has no PMU code,
 * and the schematic text does not cleanly say which rail feeds
 * display/touch/audio, so no muse_pmu_keep_rails() mask is applied here
 * (unlike the 1.75C board, whose schematic leaves the rest
 * unconnected). Likewise display_pause, panel_sleep and draw_frame are
 * NULL: the BSP exposes no touch-sleep command or touch-reset GPIO
 * for this board, so the 1.75C's CST9217 sleep sequence and the
 * bands/TE path cannot be copied, and LVGL keeps running when the
 * screen is dark. The button hints are left unset: the wiki and
 * schematic do not settle the physical order of the PWR and BOOT side
 * buttons, and the 1.75C/C6 coordinates are for different boards.
 *
 * The BSP's bsp_display_start_with_config() ignores the runtime
 * buffer_size/double_buffer/flags: its LVGL buffer geometry comes from
 * CONFIG_BSP_DISPLAY_LVGL_BUF_HEIGHT (the overlay sets 10, the vendor
 * firmware's value). Only lvgl_port_cfg is passed here.
 */
#include "bsp/esp-bsp.h"
#include "bsp/display.h"
#include "esp_check.h"
#include "esp_log.h"

#include "muse_audio.h"
#include "muse_board.h"
#include "muse_pmu.h"

static const char *TAG = "board";

#define BOOT_GPIO GPIO_NUM_0    /* BOOT is GPIO0 on the ESP32-S3 */
#define PMU_KEY_EVERY 2         /* poll the PMU over I2C every 20 ms */

static muse_gpio_button_t s_boot;

static esp_err_t init(void)
{
    ESP_RETURN_ON_ERROR(bsp_i2c_init(), TAG, "i2c");
    ESP_RETURN_ON_ERROR(muse_gpio_button_init(&s_boot, BOOT_GPIO), TAG, "boot button");
    if (muse_pmu_init(bsp_i2c_get_handle(), true) != ESP_OK) {
        ESP_LOGW(TAG, "no PMU: PWR button and battery unavailable");
    }
    return ESP_OK;
}

static lv_display_t *display_start(lv_indev_t **touch)
{
    lvgl_port_cfg_t port_cfg = ESP_LVGL_PORT_INIT_CONFIG();
    port_cfg.task_stack = 8192;
    /* Only lvgl_port_cfg reaches the BSP: buffer geometry comes from
     * CONFIG_BSP_DISPLAY_LVGL_BUF_HEIGHT (see the overlay). */
    const bsp_display_cfg_t cfg = {
        .lvgl_port_cfg = port_cfg,
    };
    lv_display_t *disp = bsp_display_start_with_config(&cfg);
    *touch = bsp_display_get_input_dev();
    return disp;
}

static bool display_lock(int timeout_ms)
{
    /* The BSP takes 0 for an indefinite wait; muse passes -1 for that. */
    return bsp_display_lock(timeout_ms < 0 ? 0 : timeout_ms);
}

static void set_brightness(int pct)
{
    bsp_display_brightness_set(pct);
}

static esp_err_t audio_init(esp_codec_dev_handle_t *spk, esp_codec_dev_handle_t *mic)
{
    /* Set up I2S the way muse_audio opens it, instead of the BSP's mono 22 kHz default. */
    const i2s_std_config_t std_cfg = {
        .clk_cfg = I2S_STD_CLK_DEFAULT_CONFIG(MUSE_AUDIO_RATE),
        .slot_cfg = I2S_STD_PHILIPS_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO),
        .gpio_cfg = {
            .mclk = BSP_I2S_MCLK,
            .bclk = BSP_I2S_SCLK,
            .ws = BSP_I2S_LCLK,
            .dout = BSP_I2S_DOUT,
            .din = BSP_I2S_DSIN,
        },
    };
    ESP_RETURN_ON_ERROR(bsp_audio_init(&std_cfg), TAG, "i2s");
    *spk = bsp_audio_codec_speaker_init();
    *mic = bsp_audio_codec_microphone_init();
    return *spk && *mic ? ESP_OK : ESP_FAIL;
}

static unsigned poll_buttons(void)
{
    static unsigned tick;
    unsigned ev = muse_gpio_button_poll(&s_boot);
    if (tick++ % PMU_KEY_EVERY == 0) {
        unsigned key = muse_pmu_poll_key();
        ev |= (key & MUSE_PMU_KEY_PRESS ? MUSE_BTN_AUX_PRESS : 0) |
              (key & MUSE_PMU_KEY_RELEASE ? MUSE_BTN_AUX_RELEASE : 0);
    }
    return ev;
}

static const muse_board_t s_board = {
    .name = "Waveshare ESP32-S3-Touch-AMOLED-1.8",
    .width = BSP_LCD_H_RES,
    .height = BSP_LCD_V_RES,
    .round = false,
    .touch = true,
    .diagonal_in = 1.8f,
    .talk_button = "boot",
    .aux_button = "pwr",
    .frame_ms = 40,
    .init = init,
    .display_start = display_start,
    .display_lock = display_lock,
    .display_unlock = bsp_display_unlock,
    .set_brightness = set_brightness,
    .audio_init = audio_init,
    .mic_slot = 0,              /* one ES8311 mic, on the left slot */
    .poll_buttons = poll_buttons,
    .read_power = muse_pmu_read_power,
    .power_off = muse_pmu_power_off,
};

/* Home Link's app_main starts Muse with this board (main/main.c). */
const muse_board_t *muse_board_get(void)
{
    return &s_board;
}
