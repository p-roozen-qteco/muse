/* SPDX-License-Identifier: Apache-2.0 */
/* Register facts and screen axes from Waveshare's S3 1.8 vendor repository
 * at 78e13f852929c2ab4f9d5e0ad1c50ea378dbf2b4:
 * examples/esp-idf/92_qmi8658_imu (reset, shared SDA15/SCL14, 0x6a/0x6b),
 * examples/arduino-v2/libraries/SensorLib/src/{SensorQMI8658.hpp,
 * REG/QMI8658Constants.h} (identity 5, +/-4g, 62.5Hz, little endian),
 * firmware/brookesia/components/Gravitysphere/Gravitysphere.cpp
 * (portrait screen x=-accel_y, y=accel_x; accelerometer only while playing).
 * QMI8658A Datasheet Rev A, Table 22, printed p.30: CTRL1 bit5 (BE)
 * must be zero for the little-endian decode below. The vendor's 0x60
 * example value sets BE; use 0x40 and verify readback instead.
 * This small driver does not copy vendor implementation code.
 * IDF 6.0.1 serializes synchronous transactions with its bus semaphore.
 * No bus access from LVGL, no new task, no gyro drift, no unbounded waits. */
#include "muse_qmi8658.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_log.h"
#include <stdatomic.h>

static i2c_master_dev_handle_t s_dev;
static atomic_bool s_requested;
static bool s_on,s_valid,s_log_first;
static uint64_t s_next;
static muse_motion_t s_sample;
static portMUX_TYPE s_mux=portMUX_INITIALIZER_UNLOCKED;
static esp_err_t rd(uint8_t reg,uint8_t *data,size_t n)
{return i2c_master_transmit_receive(s_dev,&reg,1,data,n,10);}
static esp_err_t wr(uint8_t reg,uint8_t value)
{uint8_t b[]={reg,value};return i2c_master_transmit(s_dev,b,2,10);}
static void invalidate(void)
{portENTER_CRITICAL(&s_mux);s_valid=false;portEXIT_CRITICAL(&s_mux);}

bool muse_qmi8658_init(i2c_master_bus_handle_t bus)
{
    if(s_dev) return true;
    for(unsigned address=0x6a;address<=0x6b;address++) {
        i2c_device_config_t cfg={.dev_addr_length=I2C_ADDR_BIT_LEN_7,
            .device_address=address,.scl_speed_hz=400000};
        if(i2c_master_bus_add_device(bus,&cfg,&s_dev)!=ESP_OK) {s_dev=NULL;continue;}
        uint8_t id=0;
        if(rd(0,&id,1)==ESP_OK && id==5) break;
        i2c_master_bus_rm_device(s_dev);s_dev=NULL;
    }
    if(!s_dev) return false;
    if(wr(0x60,0xb0)!=ESP_OK) goto fail;
    vTaskDelay(pdMS_TO_TICKS(20));
    /* Auto-increment AND little endian; 0x60 would silently byte-swap
     * every axis while still passing a one-byte WHO_AM_I probe. */
    if(wr(2,0x40)!=ESP_OK || wr(8,0)!=ESP_OK || wr(3,0x17)!=ESP_OK || wr(6,1)!=ESP_OK) goto fail;
    uint8_t ctrl1=0,ctrl2=0;
    if(rd(2,&ctrl1,1)!=ESP_OK || (ctrl1&0x60)!=0x40 ||
       rd(3,&ctrl2,1)!=ESP_OK || ctrl2!=0x17) goto fail;
    ESP_LOGI("muse_motion","QMI8658 ready; little-endian readback verified; idle sensors off");
    return true;
fail:
    (void)wr(8,0);i2c_master_bus_rm_device(s_dev);s_dev=NULL;return false;
}
void muse_qmi8658_request(bool on) {atomic_store(&s_requested,on);}
bool muse_qmi8658_read(muse_motion_t *out)
{
    if(!out || !atomic_load(&s_requested)) return false;
    portENTER_CRITICAL(&s_mux);
    bool ok=s_valid;if(ok) *out=s_sample;
    portEXIT_CRITICAL(&s_mux);return ok;
}
void muse_qmi8658_poll(uint64_t now,bool allowed)
{
    if(!s_dev) return;
    bool want=allowed && atomic_load(&s_requested);
    if(now<s_next) return;
    if(want!=s_on) {
        invalidate();
        if(wr(8,want?1:0)!=ESP_OK) {s_next=now+1000;return;}
        s_on=want;s_log_first=want;s_next=now+40;return;
    }
    if(!s_on) return;
    s_next=now+40;
    uint8_t status=0,b[6];
    if(rd(0x2e,&status,1)!=ESP_OK) {invalidate();s_next=now+1000;return;}
    if(!(status&1)) return; /* don't give stale sensor data a fresh timestamp */
    if(rd(0x35,b,sizeof(b))!=ESP_OK) {invalidate();s_next=now+1000;return;}
    int16_t ax=(int16_t)((unsigned)b[0]|(unsigned)b[1]<<8);
    int16_t ay=(int16_t)((unsigned)b[2]|(unsigned)b[3]<<8);
    int16_t az=(int16_t)((unsigned)b[4]|(unsigned)b[5]<<8);
    muse_motion_t sample={.x=-ay/8192.0f,.y=ax/8192.0f,.z=az/8192.0f,.at_ms=now};
    portENTER_CRITICAL(&s_mux);s_sample=sample;s_valid=true;portEXIT_CRITICAL(&s_mux);
    if(s_log_first) {
        s_log_first=false;
        ESP_LOGI("muse_motion","first gravity sample (mg): x=%d y=%d z=%d",
            (int)(sample.x*1000),(int)(sample.y*1000),(int)(sample.z*1000));
    }
}
