/* SPDX-License-Identifier: Apache-2.0 */
#include "muse_pet_store.h"
#include "muse_state.h"
#include "muse_voice.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "nvs.h"
#include <stdatomic.h>
#include <string.h>

static const char *TAG="muse_pet";
static nvs_handle_t s_nvs;
static QueueHandle_t s_queue;
static atomic_bool s_failed;

static void save_worker(void *arg)
{
    (void)arg;
    uint8_t record[MUSE_PET_RECORD_BYTES];
    int64_t last_attempt=-15000000;
    for (;;) {
        if (xQueueReceive(s_queue, record, portMAX_DELAY)!=pdTRUE) continue;
        /* Two quiet seconds coalesce rapid taps; at most one write per 15 s.
         * Keep the latest snapshot while voice owns the audio pipeline. */
        while (xQueueReceive(s_queue, record, pdMS_TO_TICKS(2000))==pdTRUE) {}
        for (;;) {
            while (xQueueReceive(s_queue, record, 0)==pdTRUE) {}
            if (muse_state_mode(NULL)==MUSE_MODE_IDLE && !muse_voice_in_call() &&
                esp_timer_get_time()-last_attempt>=15000000) break;
            vTaskDelay(pdMS_TO_TICKS(250));
        }
        last_attempt=esp_timer_get_time();
        esp_err_t err=nvs_set_blob(s_nvs,"state",record,sizeof(record));
        if (err==ESP_OK) err=nvs_commit(s_nvs);
        atomic_store(&s_failed,err!=ESP_OK);
        if (err!=ESP_OK) {
            ESP_LOGW(TAG,"progress save failed: %s",esp_err_to_name(err));
            /* Retry without putting an old record over a newer queued one. */
            vTaskDelay(pdMS_TO_TICKS(15000));
            uint8_t latest[MUSE_PET_RECORD_BYTES];
            if (xQueuePeek(s_queue,latest,0)!=pdTRUE) {
                (void)xQueueSend(s_queue,record,0);
            }
        }
    }
}

bool muse_pet_store_start(muse_pet_t *p, uint64_t now_ms)
{
    muse_pet_init(p,now_ms);
    atomic_store(&s_failed,true);
    esp_err_t err=nvs_open("muse_pet",NVS_READWRITE,&s_nvs);
    if (err!=ESP_OK) return false;
    uint8_t record[MUSE_PET_RECORD_BYTES]; size_t n=sizeof(record);
    err=nvs_get_blob(s_nvs,"state",record,&n);
    if (err!=ESP_ERR_NVS_NOT_FOUND && (err!=ESP_OK || !muse_pet_decode(p,record,n,now_ms))) {
        /* Preserve corrupt/future records for recovery instead of resetting
         * unrelated settings or silently overwriting a newer schema. */
        ESP_LOGW(TAG,"saved progress unavailable; keeping stored data intact");
        nvs_close(s_nvs); return false;
    }
    s_queue=xQueueCreate(1,sizeof(record));
    if (!s_queue || xTaskCreate(save_worker,"muse_pet_save",3072,NULL,1,NULL)!=pdPASS) {
        if (s_queue) vQueueDelete(s_queue);
        s_queue=NULL; nvs_close(s_nvs); return false;
    }
    atomic_store(&s_failed,false);
    ESP_LOGI(TAG,"progress ready: care=%u best=%u",(unsigned)p->care,(unsigned)p->best);
    return true;
}

void muse_pet_store_save(const muse_pet_t *p)
{
    if (!s_queue) return;
    uint8_t record[MUSE_PET_RECORD_BYTES]; muse_pet_encode(p,record);
    (void)xQueueOverwrite(s_queue,record);
}
bool muse_pet_store_failed(void) { return atomic_load(&s_failed); }
