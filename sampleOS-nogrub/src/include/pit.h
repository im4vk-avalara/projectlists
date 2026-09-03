#ifndef PIT_H
#define PIT_H

#include "types.h"

void pit_init(u32 hz);
u32  timer_uptime_ms(void);
u32  timer_ticks(void);
void msleep(u32 ms);

#endif
