#include "fb.h"
#include "asm.h"
#include "string.h"

static u8 *const FB = (u8 *)0xA0000;

#define VGA_DAC_INDEX 0x3C8
#define VGA_DAC_DATA  0x3C9

void fb_clear(u8 color_index)
{
    memset(FB, color_index, FB_PIXELS);
}

void fb_pixel(u32 x, u32 y, u8 color_index)
{
    if (x >= FB_WIDTH || y >= FB_HEIGHT) {
        return;
    }
    FB[y * FB_WIDTH + x] = color_index;
}

void fb_rect(u32 x, u32 y, u32 w, u32 h, u8 color_index)
{
    if (x >= FB_WIDTH || y >= FB_HEIGHT) {
        return;
    }
    if (x + w > FB_WIDTH)  w = FB_WIDTH  - x;
    if (y + h > FB_HEIGHT) h = FB_HEIGHT - y;

    for (u32 j = 0; j < h; j++) {
        memset(&FB[(y + j) * FB_WIDTH + x], color_index, w);
    }
}

void fb_set_palette_entry(u8 index, u8 r, u8 g, u8 b)
{
    outb(VGA_DAC_INDEX, index);
    outb(VGA_DAC_DATA, r & 0x3F);
    outb(VGA_DAC_DATA, g & 0x3F);
    outb(VGA_DAC_DATA, b & 0x3F);
}

void fb_set_palette(const fb_color_t *pal, u32 count)
{
    outb(VGA_DAC_INDEX, 0);
    for (u32 i = 0; i < count; i++) {
        outb(VGA_DAC_DATA, pal[i].r & 0x3F);
        outb(VGA_DAC_DATA, pal[i].g & 0x3F);
        outb(VGA_DAC_DATA, pal[i].b & 0x3F);
    }
}
