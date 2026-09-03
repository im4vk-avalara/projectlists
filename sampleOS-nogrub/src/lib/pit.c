#include "pit.h"
#include "asm.h"
#include "idt.h"

#define PIT_CH0       0x40
#define PIT_CMD       0x43
#define PIT_FREQ_HZ   1193182

static volatile u32 ticks    = 0;
static u32          tick_hz  = 100;
static u32          ms_per_tick = 10;

static void timer_irq(struct regs *r)
{
    (void)r;
    ticks++;
}

void pit_init(u32 hz)
{
    if (hz == 0) hz = 100;
    tick_hz = hz;
    ms_per_tick = 1000 / hz;

    u32 divisor = PIT_FREQ_HZ / hz;
    if (divisor > 0xFFFF) divisor = 0xFFFF;

    outb(PIT_CMD, 0x36);
    outb(PIT_CH0, (u8)(divisor & 0xFF));
    outb(PIT_CH0, (u8)((divisor >> 8) & 0xFF));

    irq_install(0, timer_irq);
}

u32 timer_ticks(void)
{
    return ticks;
}

u32 timer_uptime_ms(void)
{
    return ticks * ms_per_tick;
}

void msleep(u32 ms)
{
    u32 target = ticks + (ms + ms_per_tick - 1) / ms_per_tick;
    while (ticks < target) {
        __asm__ volatile ("hlt");
    }
}
