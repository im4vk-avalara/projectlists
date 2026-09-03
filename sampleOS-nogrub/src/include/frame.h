#ifndef FRAME_H
#define FRAME_H

#include "types.h"

#define FRAME_SIZE 4096

void frame_init(u32 mem_size_bytes);
u32  frame_alloc(void);
void frame_free(u32 phys);
u32  frame_total(void);
u32  frame_used(void);
u32  frame_base(void);

#endif
