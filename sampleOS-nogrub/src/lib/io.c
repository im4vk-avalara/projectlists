#include "io.h"
#include "asm.h"

#define VGA_WIDTH  80
#define VGA_HEIGHT 25
#define VGA_MEMORY ((u16 *)0xB8000)

#define VGA_CRTC_INDEX 0x3D4
#define VGA_CRTC_DATA  0x3D5

#define COM1 0x3F8

static size_t terminal_row = 0;
static size_t terminal_column = 0;
static u8 terminal_color = 0x0F;

static u16 vga_entry(char c, u8 color)
{
    return (u16)c | ((u16)color << 8);
}

void terminal_enable_cursor(u8 start_scanline, u8 end_scanline)
{
    outb(VGA_CRTC_INDEX, 0x0A);
    outb(VGA_CRTC_DATA, (inb(VGA_CRTC_DATA) & 0xC0) | (start_scanline & 0x1F));

    outb(VGA_CRTC_INDEX, 0x0B);
    outb(VGA_CRTC_DATA, (inb(VGA_CRTC_DATA) & 0xE0) | (end_scanline & 0x1F));
}

void terminal_disable_cursor(void)
{
    outb(VGA_CRTC_INDEX, 0x0A);
    outb(VGA_CRTC_DATA, 0x20);
}

void terminal_set_cursor(size_t x, size_t y)
{
    u16 pos = (u16)(y * VGA_WIDTH + x);

    outb(VGA_CRTC_INDEX, 0x0F);
    outb(VGA_CRTC_DATA, (u8)(pos & 0xFF));
    outb(VGA_CRTC_INDEX, 0x0E);
    outb(VGA_CRTC_DATA, (u8)((pos >> 8) & 0xFF));
}

static void terminal_scroll(void)
{
    for (size_t y = 1; y < VGA_HEIGHT; y++) {
        for (size_t x = 0; x < VGA_WIDTH; x++) {
            VGA_MEMORY[(y - 1) * VGA_WIDTH + x] =
                VGA_MEMORY[y * VGA_WIDTH + x];
        }
    }

    for (size_t x = 0; x < VGA_WIDTH; x++) {
        VGA_MEMORY[(VGA_HEIGHT - 1) * VGA_WIDTH + x] =
            vga_entry(' ', terminal_color);
    }

    terminal_row = VGA_HEIGHT - 1;
}

void terminal_clear(void)
{
    for (size_t y = 0; y < VGA_HEIGHT; y++) {
        for (size_t x = 0; x < VGA_WIDTH; x++) {
            VGA_MEMORY[y * VGA_WIDTH + x] = vga_entry(' ', terminal_color);
        }
    }

    terminal_row = 0;
    terminal_column = 0;
    terminal_enable_cursor(14, 15);
    terminal_set_cursor(0, 0);
}

/* ---- positioned, colored drawing (TUI) -------------------------------- */

static void put_cell(size_t x, size_t y, u8 ch, u8 color)
{
    if (x < VGA_WIDTH && y < VGA_HEIGHT)
        VGA_MEMORY[y * VGA_WIDTH + x] = (u16)ch | ((u16)color << 8);
}

void terminal_put_at(size_t x, size_t y, char c, u8 color)
{
    put_cell(x, y, (u8)c, color);
}

void terminal_str_at(size_t x, size_t y, const char *s, u8 color)
{
    while (*s) put_cell(x++, y, (u8)*s++, color);
}

void terminal_fill(size_t x, size_t y, size_t w, size_t h, char c, u8 color)
{
    for (size_t j = 0; j < h; j++)
        for (size_t i = 0; i < w; i++)
            put_cell(x + i, y + j, (u8)c, color);
}

/* Double-line box using CP437 box-drawing characters. */
void terminal_box(size_t x, size_t y, size_t w, size_t h, u8 color)
{
    if (w < 2 || h < 2) return;
    put_cell(x, y, 0xC9, color);                 /* top-left  */
    put_cell(x + w - 1, y, 0xBB, color);         /* top-right */
    put_cell(x, y + h - 1, 0xC8, color);         /* bot-left  */
    put_cell(x + w - 1, y + h - 1, 0xBC, color); /* bot-right */
    for (size_t i = 1; i < w - 1; i++) {
        put_cell(x + i, y, 0xCD, color);
        put_cell(x + i, y + h - 1, 0xCD, color);
    }
    for (size_t j = 1; j < h - 1; j++) {
        put_cell(x, y + j, 0xBA, color);
        put_cell(x + w - 1, y + j, 0xBA, color);
    }
}

void terminal_putchar(char c)
{
    if (c == '\n') {
        terminal_column = 0;
        terminal_row++;

        if (terminal_row >= VGA_HEIGHT) {
            terminal_scroll();
        }

        terminal_set_cursor(terminal_column, terminal_row);
        serial_write_char(c);
        return;
    }

    if (c == '\b') {
        if (terminal_column > 0) {
            terminal_column--;
            VGA_MEMORY[terminal_row * VGA_WIDTH + terminal_column] =
                vga_entry(' ', terminal_color);
        }
        terminal_set_cursor(terminal_column, terminal_row);
        serial_write_char(c);
        return;
    }

    VGA_MEMORY[terminal_row * VGA_WIDTH + terminal_column] =
        vga_entry(c, terminal_color);

    terminal_column++;

    if (terminal_column >= VGA_WIDTH) {
        terminal_column = 0;
        terminal_row++;

        if (terminal_row >= VGA_HEIGHT) {
            terminal_scroll();
        }
    }

    terminal_set_cursor(terminal_column, terminal_row);
    serial_write_char(c);
}

void terminal_write(const char *str)
{
    while (*str) {
        terminal_putchar(*str++);
    }
}

void terminal_write_hex(u32 value)
{
    const char *hex = "0123456789ABCDEF";

    terminal_write("0x");

    for (int i = 28; i >= 0; i -= 4) {
        terminal_putchar(hex[(value >> i) & 0xF]);
    }
}

void terminal_write_dec(u32 value)
{
    char buffer[16];
    int i = 0;

    if (value == 0) {
        terminal_putchar('0');
        return;
    }

    while (value > 0) {
        buffer[i++] = '0' + value % 10;
        value /= 10;
    }

    while (i > 0) {
        terminal_putchar(buffer[--i]);
    }
}

void serial_init(void)
{
    outb(COM1 + 1, 0x00);
    outb(COM1 + 3, 0x80);
    outb(COM1 + 0, 0x03);
    outb(COM1 + 1, 0x00);
    outb(COM1 + 3, 0x03);
    outb(COM1 + 2, 0xC7);
    outb(COM1 + 4, 0x0B);
}

static int serial_is_transmit_empty(void)
{
    return inb(COM1 + 5) & 0x20;
}

void serial_write_char(char c)
{
    while (!serial_is_transmit_empty()) {
    }

    outb(COM1, c);
}

void serial_write(const char *str)
{
    while (*str) {
        serial_write_char(*str++);
    }
}
