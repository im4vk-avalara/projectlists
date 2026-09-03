#ifndef KMALLOC_H
#define KMALLOC_H

#include "types.h"

void  kmalloc_init(void);
void *kmalloc(u32 size);
void  kfree(void *ptr);

u32   kmalloc_total(void);
u32   kmalloc_used(void);

#endif
