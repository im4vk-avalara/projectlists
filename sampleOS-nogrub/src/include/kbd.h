#ifndef KBD_H
#define KBD_H

#include "types.h"

#define KBD_LSHIFT 0x01
#define KBD_RSHIFT 0x02
#define KBD_SHIFT  (KBD_LSHIFT | KBD_RSHIFT)

void kbd_init(void);
int  kbd_has_data(void);
u8   kbd_read_scancode(void);
char kbd_getchar(void);

#endif
