/* SPDX-License-Identifier: Apache-2.0 */
/* A small, soft-shaded procedural companion. One 64 KiB PSRAM raster, no
 * per-frame allocation. The existing strip decoder/display transport stays. */
#include "muse_pixel.h"
#include "muse_pet.h"
#include <math.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
#include "esp_log.h"
#endif

#define N 128
static uint32_t *s_fb;
static int s_n=N, s_size=288;
#ifdef ESP_PLATFORM
static uint32_t s_fallback[32*32];
#else
static uint32_t s_host[N*N];
#endif
static float s_gx,s_gy,s_last;
static float clamp(float x,float lo,float hi) { return fminf(hi,fmaxf(lo,x)); }
static uint16_t pack(unsigned r,unsigned g,unsigned b) { return (uint16_t)(((r>>3)<<11)|((g>>2)<<5)|(b>>3)); }
static unsigned red(uint32_t c) {return (c>>16)&255;}
static unsigned green(uint32_t c) {return (c>>8)&255;}
static unsigned blue(uint32_t c) {return c&255;}
static uint32_t mix(uint32_t a,uint32_t b,unsigned t)
{
    unsigned r=(red(a)*(256-t)+red(b)*t)>>8;
    unsigned g=(green(a)*(256-t)+green(b)*t)>>8;
    unsigned v=(blue(a)*(256-t)+blue(b)*t)>>8;
    return (r<<16)|(g<<8)|v;
}
static uint32_t rgb(uint32_t c) {return c;}
static unsigned channel(int value) {return value<0 ? 0 : value>255 ? 255 : (unsigned)value;}
static uint16_t display_color(uint32_t c,int x,int y)
{
    /* Preserve gradients until final RGB565 output. Screen-anchored dither
     * prevents colour bands and gives identical full-frame/strip output. */
    static const int d[4][4]={{0,8,2,10},{12,4,14,6},{3,11,1,9},{15,7,13,5}};
    int noise=d[y&3][x&3]-8;
    return pack(channel((int)red(c)+noise/2),channel((int)green(c)+noise/4),channel((int)blue(c)+noise/2));
}

void muse_pixel_set_size(int px)
{
    s_size=px<1 ? 1 : px>512 ? 512 : px;
    if (s_fb) return;
#ifdef ESP_PLATFORM
    s_fb=heap_caps_calloc(N*N,sizeof(*s_fb),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!s_fb) {
        s_fb=s_fallback; s_n=32;
        ESP_LOGW("muse_soft","PSRAM raster unavailable; using compact fallback");
    }
#else
    s_fb=s_host;
#endif
}

/* Antialiased ellipses with a vertical soft gradient. Work is bounded by each
 * shape's clipped box, never by a full-size 368x448 framebuffer. */
static void oval(float cx,float cy,float rx,float ry,uint32_t top,uint32_t bottom,float alpha)
{
    float scale=(float)s_n/N;
    cx*=scale; cy*=scale; rx*=scale; ry*=scale;
    if(rx<=0 || ry<=0 || alpha<=0) return;
    int x0=(int)fmaxf(0,floorf(cx-rx-1)),x1=(int)fminf(s_n-1,ceilf(cx+rx+1));
    int y0=(int)fmaxf(0,floorf(cy-ry-1)),y1=(int)fminf(s_n-1,ceilf(cy+ry+1));
    float edge=fminf(rx,ry)*.55f;
    uint32_t a=rgb(top),b=rgb(bottom);
    for(int y=y0;y<=y1;y++) {
        float dy=(y+.5f-cy)/ry;
        uint32_t color=mix(a,b,(unsigned)(clamp((dy+1)*.5f,0,1)*256));
        for(int x=x0;x<=x1;x++) {
            float dx=(x+.5f-cx)/rx;
            float cover=clamp((1-dx*dx-dy*dy)*edge+.5f,0,1)*alpha;
            if(cover>0) {
                uint32_t *dst=&s_fb[y*s_n+x];
                *dst=mix(*dst,color,(unsigned)(clamp(cover,0,1)*256));
            }
        }
    }
}
static void stroke(float x1,float y1,float x2,float y2,float radius,uint32_t color)
{
    float dx=x2-x1,dy=y2-y1;
    int steps=(int)fmaxf(fabsf(dx),fabsf(dy))+1;
    for(int i=0;i<=steps;i++) {
        float f=(float)i/steps;
        oval(x1+dx*f,y1+dy*f,radius,radius,color,color,1);
    }
}
static void smile(float x,float y,float w,float depth,uint32_t color)
{
    for(int i=0;i<12;i++) {
        float a=-1+(float)i/6,b=a+1.0f/6;
        stroke(x+a*w,y+depth*(1-a*a),x+b*w,y+depth*(1-b*b),.85f,color);
    }
}
static void sparkle(float x,float y,float size,uint32_t color,float alpha)
{
    oval(x,y,size,.7f,color,color,alpha);
    oval(x,y,.7f,size,color,color,alpha);
}
static void heart(float x,float y,float size,float alpha)
{
    oval(x-size*.45f,y,size*.65f,size*.65f,0xffbdca,0xef7da6,alpha);
    oval(x+size*.45f,y,size*.65f,size*.65f,0xffbdca,0xef7da6,alpha);
    oval(x,y+size*.5f,size*.73f,size*.8f,0xf9a2b9,0xe777a0,alpha);
}
uint32_t muse_pixel_accent(muse_mode_t mode)
{
    static const uint32_t c[]={0xf5c99b,0xeec9a7,0x85e0d5,0xb7adff,0x85e0d5,0xf0a0ab,0xa9b6d6};
    return c[(unsigned)mode<MUSE_MODE_COUNT ? mode : MUSE_MODE_IDLE];
}
void muse_pixel_render(const muse_pose_t *p)
{
    if(!s_fb) muse_pixel_set_size(s_size);
    memset(s_fb,0,(size_t)s_n*s_n*sizeof(*s_fb));
    float t=p->t,dt=s_last>0 ? clamp(t-s_last,0,.12f) : .04f;
    s_last=t;
    bool idle=p->mode==MUSE_MODE_IDLE;
    bool sleep=p->mode==MUSE_MODE_OFF || (idle && p->pet_mood==MUSE_PET_RESTING);
    bool sleepy=idle && p->pet_mood==MUSE_PET_SLEEPY;
    bool playful=idle && p->pet_mood==MUSE_PET_PLAYFUL;
    float happy=idle ? clamp(p->happy,0,1) : 0;
    float attention=idle ? clamp(p->attention,0,1) : 0;
    float gx=sinf(t*.43f)*.35f,gy=sinf(t*.31f)*.15f;
    if(p->mode==MUSE_MODE_THINKING) {gx=.6f;gy=-.6f;}
    if(p->mode==MUSE_MODE_LISTENING || p->mode==MUSE_MODE_SPEAKING) {gx=0;gy=0;}
    gx+=(clamp(p->gaze_x,-1,1)-gx)*attention;
    gy+=(clamp(p->gaze_y,-1,1)-gy)*attention;
    float k=1-expf(-dt*12);
    s_gx+=(gx-s_gx)*k; s_gy+=(gy-s_gy)*k;
    float bob=sinf(t*(sleep ? 1.2f : 2.0f))*(sleep ? .7f : 1.2f);
    float hop=happy*fabsf(sinf(t*7))*2.5f;
    float cx=64+s_gx*attention*2,cy=67+bob-hop;
    float breath=1+sinf(t*(sleep ? 1.4f : 2.3f))*.018f;
    float level=(p->mode==MUSE_MODE_SPEAKING || p->mode==MUSE_MODE_LISTENING) ? clamp(p->level,0,1) : 0;
    uint32_t accent=muse_pixel_accent(p->mode);
    /* Dim coloured aura, black outside. */
    oval(64,71,51+level*3,48,accent,0x11121d,.065f);
    oval(64,117,30-hop,3,0x7d688c,0x151221,.4f);
    for(int i=0;i<4;i++) {
        float phase=t*.6f+i*1.7f;
        sparkle(13+i*34,24+(i%2)*16+sinf(phase)*3,1.4f,accent,.3f+.15f*sinf(phase));
    }
    /* Rounded feet, ears, paws and a cream mochi body. */
    oval(cx-15,109+bob-hop,12,7,0xf7dfc8,0xcba99c,1);
    oval(cx+15,109+bob-hop,12,7,0xf7dfc8,0xcba99c,1);
    oval(cx-25,35+bob-hop,12,16,0xffecd6,0xd4b7a6,1);
    oval(cx+25,35+bob-hop,12,16,0xffecd6,0xd4b7a6,1);
    oval(cx-25,34+bob-hop,6,10,0xf9cfca,0xe8b5b1,.75f);
    oval(cx+25,34+bob-hop,6,10,0xf9cfca,0xe8b5b1,.75f);
    float paw=happy ? -14-sinf(t*10)*3 : p->mode==MUSE_MODE_LISTENING ? -12 : -level*5;
    oval(cx-35,80+paw+bob-hop,9,14,0xffe9d2,0xd6b5a6,1);
    oval(cx+35,80+paw+bob-hop,9,14,0xffe9d2,0xd6b5a6,1);
    oval(cx,cy,36*breath,41/breath,0xfff4df,0xdac0ad,1);
    oval(cx,cy-4,28,29,0xfff7e8,0xf3deca,.68f);
    oval(cx-9,cy-26,14,6,0xfffdf3,0xfff9eb,.3f);
    float ey=cy-10;
    float blink_t=fmodf(t+1.1f,4.7f);
    float blink=blink_t<.18f ? 1-fabsf(blink_t/.09f-1) : 0;
    float openness=sleep ? 0 : (sleepy ? .45f : 1)*(1-blink);
    if(p->mode==MUSE_MODE_BOOT) openness=clamp((p->mode_t-.4f)/.6f,0,1);
    for(int i=0;i<2;i++) {
        float x=cx+(i ? 13 : -13);
        float open=openness*(i && idle ? 1-clamp(p->wink,0,1) : 1);
        if(open<.18f) {
            smile(x,ey,5,sleep ? 1.3f : -2.1f,0x624c4a);
        } else {
            oval(x,ey,5.8f,8*open,0x69544f,0x2c2630,1);
            oval(x+s_gx*1.8f,ey+s_gy*1.2f+1,4.2f,5.5f*open,0x3b2b33,0x28222b,1);
            oval(x-1.6f+s_gx,ey-2.8f*open+s_gy,1.9f,2.2f*open,0xfff9ed,0xffffff,1);
            oval(x+2,ey+3*open,1,1,0xf8dec9,0xf8dec9,.7f);
        }
    }
    oval(cx-24,ey+12,7,3.8f,0xffb4bf,0xf2abb0,.6f+happy*.25f);
    oval(cx+24,ey+12,7,3.8f,0xffb4bf,0xf2abb0,.6f+happy*.25f);
    oval(cx,ey+8,2.1f,1.4f,0x9d7567,0x795d55,1);
    if(p->mode==MUSE_MODE_SPEAKING) {
        float opening=2+level*6;
        oval(cx,ey+17,5.4f,opening,0x63424b,0x3f2c3b,1);
        oval(cx,ey+17+opening*.5f,3.8f,opening*.3f,0xf1a6ae,0xdf8d9a,1);
    } else if(p->mode==MUSE_MODE_ERROR) {
        stroke(cx-4,ey+17,cx+4,ey+17,.8f,0x785951);
    } else if(p->mode==MUSE_MODE_LISTENING || (idle && p->pet_mood==MUSE_PET_HUNGRY)) {
        oval(cx,ey+16,2.6f,3.5f,0x795453,0x5b4148,1);
    } else smile(cx,ey+14,happy>0 || playful ? 7 : 5,sleep ? 1.5f : 3.2f,0x795453);
    if(p->mode==MUSE_MODE_THINKING) {
        for(int i=0;i<3;i++) oval(99+i*6,36-i*7,1.7f+i*.5f,1.7f+i*.5f,accent,accent,.6f);
    }
    if(sleep) {
        oval(105,29,7,7,0xc1d4ed,0x8a9db7,.8f);
        oval(108,26,6,6,0x000000,0x000000,1);
    }
    if(happy>0) {
        heart(24,29-fmodf(t*8,12),3,happy);
        heart(104,46-fmodf(t*7,14),2.5f,happy);
    }
}
void muse_pixel_scale(uint16_t *dst,int stride,int x0,int x1,int y0,int y1)
{
    if(!s_fb || !dst || x0<0 || y0<0 || x1>=s_size || y1>=s_size || x1<x0 || y1<y0 || stride<x1-x0+1) return;
    for(int y=y0;y<=y1;y++) {
        unsigned fy=s_size>1 ? (unsigned)y*(s_n-1)*256/(s_size-1) : 0;
        unsigned iy=fy>>8,ny=iy+1<(unsigned)s_n ? iy+1 : iy;
        uint16_t *row=dst+(y-y0)*stride;
        for(int x=x0;x<=x1;x++) {
            unsigned fx=s_size>1 ? (unsigned)x*(s_n-1)*256/(s_size-1) : 0;
            unsigned ix=fx>>8,nx=ix+1<(unsigned)s_n ? ix+1 : ix;
            uint32_t a=mix(s_fb[iy*s_n+ix],s_fb[iy*s_n+nx],fx&255);
            uint32_t b=mix(s_fb[ny*s_n+ix],s_fb[ny*s_n+nx],fx&255);
            row[x-x0]=display_color(mix(a,b,fy&255),x,y);
        }
    }
}
