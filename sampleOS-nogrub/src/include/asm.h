#ifndef ASM_H
#define ASM_H

#include "types.h"

static inline void outb(u16 port, u8 value)
{
    __asm__ volatile ("outb %0, %1" : : "a"(value), "Nd"(port));
}

static inline u8 inb(u16 port)
{
    u8 value;
    __asm__ volatile ("inb %1, %0" : "=a"(value) : "Nd"(port));
    return value;
}

static inline void io_wait(void)
{
    outb(0x80, 0);
}

static inline void hlt(void)
{
    __asm__ volatile ("hlt");
}

static inline void cli(void)
{
    __asm__ volatile ("cli");
}

static inline void sti(void)
{
    __asm__ volatile ("sti");
}

#endif
