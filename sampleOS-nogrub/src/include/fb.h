#ifndef FB_H
#define FB_H

#include "types.h"

#define FB_WIDTH  320
#define FB_HEIGHT 200
#define FB_PIXELS (FB_WIDTH * FB_HEIGHT)

typedef struct {
    u8 r;
    u8 g;
    u8 b;
} fb_color_t;

void fb_clear(u8 color_index);
void fb_pixel(u32 x, u32 y, u8 color_index);
void fb_rect(u32 x, u32 y, u32 w, u32 h, u8 color_index);

void fb_set_palette_entry(u8 index, u8 r, u8 g, u8 b);
void fb_set_palette(const fb_color_t *pal, u32 count);

#endif
