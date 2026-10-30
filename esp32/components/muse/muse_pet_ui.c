/* SPDX-License-Identifier: Apache-2.0 */
#include "muse_pet_ui.h"
#include "muse_pet_store.h"
#include "muse_state.h"
#include "muse_ui.h"
#include "esp_timer.h"
#include <stdio.h>
#include <string.h>

static muse_pet_t s_pet;
static muse_pet_game_t s_game;
static lv_obj_t *s_hud,*s_panel,*s_labels[3],*s_bars[3],*s_hint,*s_rest_label;
static lv_obj_t *s_target,*s_score,*s_title,*s_again;
static int s_w,s_h,s_cell=-1;
static uint64_t s_checkpoint,s_next_pat,s_next_action,s_message_until;
static uintptr_t s_last_action;
static bool s_ready,s_dirty;
static char s_message[48];
static uint64_t now_ms(void) {return (uint64_t)esp_timer_get_time()/1000;}
static bool available(void) {return s_ready && muse_state_mode(NULL)==MUSE_MODE_IDLE && !muse_state_asleep();}
static void label_text(lv_obj_t *label,const char *text)
{
    if(strcmp(lv_label_get_text(label),text)) lv_label_set_text(label,text);
}
static lv_obj_t *label(lv_obj_t *parent,const char *text,int x,int y,int w,const lv_font_t *font,uint32_t color)
{
    lv_obj_t *o=lv_label_create(parent);
    lv_obj_set_pos(o,x,y);lv_obj_set_width(o,w);
    lv_obj_set_style_text_font(o,font,0);lv_obj_set_style_text_color(o,lv_color_hex(color),0);
    lv_obj_set_style_text_align(o,LV_TEXT_ALIGN_CENTER,0);
    lv_label_set_text(o,text);lv_obj_remove_flag(o,LV_OBJ_FLAG_CLICKABLE);
    return o;
}
static void remember(void)
{
    muse_pet_store_save(&s_pet);s_checkpoint=now_ms();s_dirty=false;
}
static void message(const char *text)
{
    snprintf(s_message,sizeof(s_message),"%s",text);s_message_until=now_ms()+3000;
}
static void close_game(void)
{
    muse_pet_game_cancel(&s_game);
    if(s_panel) lv_obj_add_flag(s_panel,LV_OBJ_FLAG_HIDDEN);
    muse_ui_set_swipe_enabled(true);
}
static void on_action(lv_event_t *e)
{
    if(!available()) return;
    lv_indev_t *indev=lv_event_get_indev(e);
    if(indev && lv_indev_get_type(indev)==LV_INDEV_TYPE_POINTER) {
        lv_point_t point;lv_indev_get_point(indev,&point);
        /* LVGL keeps the pressed object captured; releasing outside must not
         * activate it merely because scrolling is disabled for the button. */
        if(!lv_obj_hit_test(lv_event_get_target_obj(e),&point)) return;
    }
    uintptr_t action=(uintptr_t)lv_event_get_user_data(e);
    uint64_t now=now_ms();
    if(action==4 && lv_obj_has_flag(s_target,LV_OBJ_FLAG_HIDDEN)) return;
    /* Reject a duplicate contact, without swallowing a tap on another control. */
    if(action!=4 && action==s_last_action && now<s_next_action) return;
    if(action!=4) {s_last_action=action;s_next_action=now+160;}
    muse_state_poke();
    if(action==0) {
        if(muse_pet_feed(&s_pet)) {remember();message("Smakelijk!");muse_state_make_happy();}
        else message("Mijn buikje zit vol");
    } else if(action==1) {
        muse_pet_rest(&s_pet);remember();message(s_pet.resting ? "Even lekker uitrusten" : "Daar ben ik weer!");
    } else if(action==2) {
        muse_pet_game_start(&s_game,now,(uint32_t)now+s_pet.care);
        s_cell=-1;lv_obj_remove_flag(s_panel,LV_OBJ_FLAG_HIDDEN);
        lv_obj_remove_flag(s_target,LV_OBJ_FLAG_HIDDEN);lv_obj_add_flag(s_again,LV_OBJ_FLAG_HIDDEN);
        label_text(s_title,"Sterren vangen");muse_ui_set_swipe_enabled(false);
    } else if(action==3) close_game();
    else if(action==4 && muse_pet_game_hit(&s_game,s_game.cell,now)) {
        /* The target moves on the next UI tick; ignore repeat clicks at its
         * old position before then. */
        lv_obj_add_flag(s_target,LV_OBJ_FLAG_HIDDEN);
    }
}
static lv_obj_t *button(lv_obj_t *parent,const char *text,int x,int y,int w,uintptr_t action,uint32_t color,lv_obj_t **text_out)
{
    lv_obj_t *o=lv_button_create(parent);lv_obj_remove_style_all(o);
    lv_obj_set_pos(o,x,y);lv_obj_set_size(o,w,52);
    lv_obj_set_style_radius(o,17,0);lv_obj_set_style_bg_color(o,lv_color_hex(color),0);
    lv_obj_set_style_bg_opa(o,LV_OPA_COVER,0);
    lv_obj_set_style_bg_color(o,lv_color_lighten(lv_color_hex(color),55),LV_STATE_PRESSED);
    lv_obj_set_style_border_width(o,1,0);
    lv_obj_set_style_border_color(o,lv_color_lighten(lv_color_hex(color),25),0);
    /* A fingertip can drift while tapping. Don't turn that into a tile swipe;
     * swiping the face still navigates normally. Leaving the button cancels. */
    lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE|LV_OBJ_FLAG_SCROLL_CHAIN_HOR|
                         LV_OBJ_FLAG_SCROLL_CHAIN_VER|LV_OBJ_FLAG_GESTURE_BUBBLE);
    lv_obj_add_event_cb(o,on_action,LV_EVENT_CLICKED,(void *)action);
    lv_obj_t *l=label(o,text,0,0,w,&lv_font_montserrat_16,0xf5eadd);lv_obj_center(l);
    if(text_out) *text_out=l;
    return o;
}
void muse_pet_ui_build(lv_obj_t *face,int w,int h)
{
    s_w=w;s_h=h;
    uint64_t now=now_ms();
    (void)muse_pet_store_start(&s_pet,now);s_checkpoint=now;
    s_hud=lv_obj_create(face);lv_obj_remove_style_all(s_hud);
    lv_obj_set_pos(s_hud,0,h-136);lv_obj_set_size(s_hud,w,120);
    lv_obj_remove_flag(s_hud,LV_OBJ_FLAG_SCROLLABLE|LV_OBJ_FLAG_CLICKABLE);
    static const uint32_t colors[]={0xe7b996,0x8ed2c3,0xbca4e5};
    for(int i=0;i<3;i++) {
        int col=w/3,x=i*col;
        s_labels[i]=label(s_hud,"",x,0,col,&lv_font_montserrat_14,colors[i]);
        s_bars[i]=lv_bar_create(s_hud);lv_obj_set_pos(s_bars[i],x+16,22);lv_obj_set_size(s_bars[i],col-32,4);
        lv_bar_set_range(s_bars[i],0,100);lv_obj_set_style_bg_color(s_bars[i],lv_color_hex(0x24212b),LV_PART_MAIN);
        lv_obj_set_style_bg_color(s_bars[i],lv_color_hex(colors[i]),LV_PART_INDICATOR);
        lv_obj_remove_flag(s_bars[i],LV_OBJ_FLAG_CLICKABLE);
    }
    s_hint=label(s_hud,"",0,31,w,&lv_font_montserrat_14,0xa49cad);
    int gap=8,bw=(w-28-2*gap)/3;
    const char *names[]={"Eten","Rust","Spelen"};
    const uint32_t button_colors[]={0x49352a,0x24413d,0x423151};
    for(uintptr_t i=0;i<3;i++) {
        lv_obj_t *text;
        lv_obj_t *o=button(s_hud,names[i],14+(int)i*(bw+gap),56,bw,i,button_colors[i],&text);
        lv_obj_set_height(o,60);
        lv_obj_set_ext_click_area(o,4); /* adjacent hit areas remain disjoint */
        lv_obj_set_style_text_font(text,&lv_font_montserrat_20,0);
        lv_obj_center(text);
        if(i==1) s_rest_label=text;
    }
    s_panel=lv_obj_create(face);lv_obj_remove_style_all(s_panel);lv_obj_set_size(s_panel,w,h);
    lv_obj_set_style_bg_color(s_panel,lv_color_black(),0);lv_obj_set_style_bg_opa(s_panel,LV_OPA_COVER,0);
    lv_obj_remove_flag(s_panel,LV_OBJ_FLAG_SCROLLABLE|LV_OBJ_FLAG_SCROLL_CHAIN_HOR|LV_OBJ_FLAG_GESTURE_BUBBLE);
    s_title=label(s_panel,"Sterren vangen",0,28,w,&lv_font_montserrat_20,0xf3dcc1);
    label(s_panel,"Tik de ster aan. Je hebt 20 sec.",0,62,w,&lv_font_montserrat_14,0xa49cad);
    s_score=label(s_panel,"",0,91,w,&lv_font_montserrat_16,0xbca4e5);
    s_target=button(s_panel,"",0,0,56,4,0x2c2235,NULL);lv_obj_set_height(s_target,56);
    lv_obj_set_style_radius(s_target,LV_RADIUS_CIRCLE,0);
    static const lv_point_precise_t points[]={{28,6},{34,21},{50,22},{38,33},{42,49},{28,40},{14,49},{18,33},{6,22},{22,21},{28,6}};
    lv_obj_t *star=lv_line_create(s_target);lv_line_set_points(star,points,11);
    lv_obj_set_style_line_width(star,3,0);lv_obj_set_style_line_rounded(star,true,0);
    lv_obj_set_style_line_color(star,lv_color_hex(0xffdc8e),0);lv_obj_remove_flag(star,LV_OBJ_FLAG_CLICKABLE);
    button(s_panel,"Terug",18,h-64,130,3,0x282331,NULL);
    s_again=button(s_panel,"Nog eens",w-148,h-64,130,2,0x3c2b43,NULL);
    lv_obj_add_flag(s_panel,LV_OBJ_FLAG_HIDDEN);s_ready=true;
}
void muse_pet_ui_hide(void)
{
    if(!s_ready) return;
    lv_obj_add_flag(s_hud,LV_OBJ_FLAG_HIDDEN);
    if(muse_pet_ui_game_open()) close_game();
}
bool muse_pet_ui_game_open(void) {return s_ready && (s_game.active || s_game.finished);}
bool muse_pet_ui_tick(uint64_t now,bool visible)
{
    if(!s_ready) return false;
    if(muse_pet_tick(&s_pet,now)) s_dirty=true;
    if(s_dirty && now-s_checkpoint>=300000) remember();
    if(!visible) {muse_pet_ui_hide();return false;}
    lv_obj_remove_flag(s_hud,LV_OBJ_FLAG_HIDDEN);
    if(muse_pet_game_finish(&s_game,&s_pet,now)) {remember();muse_state_make_happy();}
    if(s_game.active) {
        if(s_cell!=s_game.cell) {
            s_cell=s_game.cell;lv_obj_set_pos(s_target,32+(s_cell%3)*(s_w-120)/2,117+(s_cell/3)*80);
            lv_obj_remove_flag(s_target,LV_OBJ_FLAG_HIDDEN);
        }
        unsigned seconds=(unsigned)((s_game.end_ms-now+999)/1000);
        char text[64];snprintf(text,sizeof(text),"%u sterren   |   %u sec",(unsigned)s_game.score,seconds);
        label_text(s_score,text);
    } else if(s_game.finished) {
        lv_obj_add_flag(s_target,LV_OBJ_FLAG_HIDDEN);lv_obj_remove_flag(s_again,LV_OBJ_FLAG_HIDDEN);
        label_text(s_title,s_game.score ? "Goed gespeeld!" : "Nog een keertje?");
        char text[64];snprintf(text,sizeof(text),"%u sterren   |   Record %u",(unsigned)s_game.score,(unsigned)s_pet.best);
        label_text(s_score,text);
    }
    static const char *const names[]={"Buik","Energie","Plezier"};
    const unsigned values[]={s_pet.food,s_pet.energy,s_pet.joy};
    char text[64];
    for(int i=0;i<3;i++) {
        snprintf(text,sizeof(text),"%s %u",names[i],values[i]);label_text(s_labels[i],text);
        if(lv_bar_get_value(s_bars[i])!=(int)values[i]) lv_bar_set_value(s_bars[i],values[i],LV_ANIM_OFF);
    }
    label_text(s_rest_label,s_pet.resting ? "Wakker" : "Rust");
    if(muse_pet_store_failed()) label_text(s_hint,"Voortgang bewaren lukt niet");
    else if(now<s_message_until) label_text(s_hint,s_message);
    else {snprintf(text,sizeof(text),"Band %u   |   Record %u",1u+s_pet.xp/25,(unsigned)s_pet.best);label_text(s_hint,text);}
    return muse_pet_ui_game_open();
}
void muse_pet_ui_pose(muse_pose_t *p)
{
    if(!s_ready) return;
    p->pet_mood=muse_pet_mood(&s_pet);
    if(s_pet.resting && p->mode==MUSE_MODE_IDLE) p->happy=0;
}
void muse_pet_ui_pat(uint64_t now)
{
    if(!available() || now<s_next_pat) return;
    s_next_pat=now+15000;
    if(muse_pet_pat(&s_pet)) remember();
}
const char *muse_pet_ui_name(void) {return muse_pet_mood_name(muse_pet_mood(&s_pet));}
void muse_pet_ui_snapshot(muse_pet_t *p,muse_pet_game_t *g) {if(p)*p=s_pet;if(g)*g=s_game;}
