# Copyright (c) 2026 Qteco
# SPDX-License-Identifier: Apache-2.0

"""Exercise the actual board's display setup against transport fakes.

The QSPI panel must never reach the BSP's RGB LVGL wrapper. Keep touch's
panel-gap setup before rendering and serialize brightness with pixel traffic.
These host checks do not emulate the physical panel or prove it cannot hang.
"""

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "components/muse/boards/board_waveshare_s3_18.c"


def function(source, name):
    match = re.search(r"^static [^\n]*\b" + name + r"\([^;]*?\)\n\{", source, re.M)
    if not match:
        raise AssertionError(f"Missing board function: {name}")
    brace = source.index("{", match.start())
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


FAKES = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#define ESP_OK 0
#define ESP_FAIL -1
#define MUSE_UI_CORE 1
#define MUSE_UI_PRIORITY 5
#define BSP_LCD_H_RES 368
#define BSP_LCD_V_RES 448
#define ESP_LV_ADAPTER_PANEL_IF_OTHER 1
#define ESP_LV_ADAPTER_ROTATE_0 0
#define ESP_LV_ADAPTER_TEAR_AVOID_MODE_NONE 0
#define LV_EVENT_INVALIDATE_AREA 1
#define ESP_LOGI(...) ((void)0)
typedef int lv_display_t;
typedef int lv_indev_t;
typedef void *esp_lcd_panel_handle_t;
typedef void *esp_lcd_panel_io_handle_t;
typedef void *esp_lcd_touch_handle_t;
typedef struct { int x1, y1, x2, y2; } lv_area_t;
typedef struct { lv_area_t *area; } lv_event_t;
static void *lv_event_get_param(lv_event_t *e) { return e->area; }
typedef struct { int task_core_id, task_priority; } esp_lv_adapter_config_t;
#define ESP_LV_ADAPTER_DEFAULT_CONFIG() ((esp_lv_adapter_config_t){0})
typedef struct { int max_transfer_sz; } bsp_display_config_t;
typedef struct {
    esp_lcd_panel_handle_t panel;
    esp_lcd_panel_io_handle_t panel_io;
    struct { int interface, rotation, hor_res, ver_res; } profile;
    int tear_avoid_mode;
} esp_lv_adapter_display_config_t;
typedef struct { lv_display_t *disp; esp_lcd_touch_handle_t tp; } esp_lv_adapter_touch_config_t;
#define ESP_LV_ADAPTER_TOUCH_DEFAULT_CONFIG(d,t) ((esp_lv_adapter_touch_config_t){d,t})
static lv_display_t display;
static lv_indev_t input;
static int panel, io, tp;
static esp_lcd_touch_handle_t s_tp;
static int fail_step, step, started, serialized, brightness, lock_timeout;
static int step_ok(void) { return ++step != fail_step; }
static int esp_lv_adapter_init(const esp_lv_adapter_config_t *cfg) {
    assert(cfg->task_core_id == MUSE_UI_CORE && cfg->task_priority == MUSE_UI_PRIORITY);
    return step_ok() ? ESP_OK : ESP_FAIL;
}
static int bsp_display_new(const bsp_display_config_t *cfg, void **p, void **i) {
    assert(cfg->max_transfer_sz > 0 && cfg->max_transfer_sz <= 8192);
    *p = &panel; *i = &io;
    return step_ok() ? ESP_OK : ESP_FAIL;
}
static int bsp_touch_new(const void *cfg, void **t) {
    assert(!cfg && !started && step == 2);
    *t = &tp; /* Real BSP also sets CO5300's x gap here. */
    return step_ok() ? ESP_OK : ESP_FAIL;
}
static int bsp_display_brightness_init(void) {
    assert(!started);
    return step_ok() ? ESP_OK : ESP_FAIL;
}
static lv_display_t *muse_lcd_bands_register(esp_lv_adapter_display_config_t cfg,
                                           int lines, size_t bytes) {
    assert(s_tp == &tp && step == 4);
    assert(cfg.panel == &panel && cfg.panel_io == &io);
    assert(cfg.profile.interface == ESP_LV_ADAPTER_PANEL_IF_OTHER);
    assert(cfg.profile.hor_res == 368 && cfg.profile.ver_res == 448);
    assert(cfg.profile.rotation == 0 && cfg.tear_avoid_mode == 0);
    assert(lines > 0 && !(lines & 1) && (448 + lines - 1) / lines <= 4);
    assert(bytes >= 368 * 2 * 2 && bytes <= 8192 && bytes % (368 * 2 * 2) == 0);
    return step_ok() ? &display : NULL;
}
static void (*rounder)(lv_event_t *);
static void lv_display_add_event_cb(lv_display_t *d, void (*cb)(lv_event_t *), int ev, void *ctx) {
    assert(d == &display && ev == LV_EVENT_INVALIDATE_AREA && !ctx);
    rounder = cb;
}
static lv_indev_t *esp_lv_adapter_register_touch(const esp_lv_adapter_touch_config_t *cfg) {
    assert(cfg->disp == &display && cfg->tp == &tp);
    return step_ok() ? &input : NULL;
}
static int esp_lv_adapter_start(void) {
    if (!step_ok()) return ESP_FAIL;
    started = 1;
    return ESP_OK;
}
static int esp_lv_adapter_lock(int timeout) {
    lock_timeout = timeout;
    return timeout == 7 ? ESP_FAIL : ESP_OK;
}
static int bsp_display_brightness_set(int pct) {
    assert(serialized && started);
    brightness = pct;
    return ESP_OK;
}
static void muse_lcd_bands_run(void (*fn)(void *), void *arg) {
    assert(!serialized);
    serialized = 1; fn(arg); serialized = 0;
}
'''

MAIN = r'''
int main(int argc, char **argv) {
    assert(argc == 2);
    fail_step = atoi(argv[1]);
    lv_indev_t *touch = NULL;
    lv_display_t *disp = display_start(&touch);
    if (fail_step) {
        assert(!disp && !started && step == fail_step);
        return 0;
    }
    assert(disp == &display && touch == &input && started && rounder);
    /* Every single pixel, including all four corners, expands to a valid
     * even-aligned window without crossing this panel's 368x448 edges. */
    for (int y = 0; y < 448; ++y) for (int x = 0; x < 368; ++x) {
        lv_area_t area = { x, y, x, y };
        lv_event_t event = { &area };
        rounder(&event);
        assert(area.x1 <= x && area.y1 <= y && area.x2 >= x && area.y2 >= y);
        assert(area.x1 >= 0 && area.y1 >= 0 && area.x2 < 368 && area.y2 < 448);
        assert(!(area.x1 & 1) && !(area.y1 & 1) && (area.x2 & 1) && (area.y2 & 1));
    }
    for (int pct = 0; pct <= 100; ++pct) {
        set_brightness(pct);
        assert(brightness == pct && !serialized);
    }
    assert(display_lock(-1) && lock_timeout == -1);
    assert(display_lock(0) && lock_timeout == 0);
    assert(!display_lock(7) && lock_timeout == 7);
    return 0;
}
'''


class WaveshareS318DisplayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        source = SOURCE.read_text()
        defines = "\n".join(re.findall(r"^#define (?:DRAW_BUF_LINES|LCD_CHUNK_BYTES) .*$", source, re.M))
        funcs = "\n".join(function(source, f) for f in
                          ("round_area", "display_start", "display_lock", "send_brightness", "set_brightness"))
        src = Path(cls.tmp.name) / "board.c"
        src.write_text(FAKES + "\n" + defines + "\n" + funcs + MAIN)
        cls.exe = Path(cls.tmp.name) / "board"
        subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(cls.exe)], check=True)

    def test_qspi_setup_touch_rounding_and_serialized_brightness(self):
        subprocess.run([str(self.exe), "0"], check=True)

    def test_failed_setup_never_starts_rendering(self):
        for step in range(1, 8):
            with self.subTest(step=step):
                subprocess.run([str(self.exe), str(step)], check=True)


if __name__ == "__main__":
    unittest.main()
