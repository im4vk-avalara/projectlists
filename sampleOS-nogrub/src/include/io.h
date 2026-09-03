#ifndef IO_H
#define IO_H

#include "types.h"

void terminal_clear(void);
void terminal_putchar(char c);
void terminal_write(const char *str);
void terminal_write_hex(u32 value);
void terminal_write_dec(u32 value);

void terminal_enable_cursor(u8 start_scanline, u8 end_scanline);
void terminal_disable_cursor(void);
void terminal_set_cursor(size_t x, size_t y);

/* Positioned, colored drawing (for TUI windows). color = fg | (bg << 4). */
void terminal_put_at(size_t x, size_t y, char c, u8 color);
void terminal_str_at(size_t x, size_t y, const char *s, u8 color);
void terminal_fill(size_t x, size_t y, size_t w, size_t h, char c, u8 color);
void terminal_box(size_t x, size_t y, size_t w, size_t h, u8 color);

void serial_init(void);
void serial_write_char(char c);
void serial_write(const char *str);

#endif
