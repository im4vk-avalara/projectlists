#ifndef PIC_H
#define PIC_H

#include "types.h"

#define PIC_VECTOR_BASE 0x20
#define IRQ_VECTOR(irq) (PIC_VECTOR_BASE + (irq))

void pic_init(void);
void pic_mask(u8 irq);
void pic_unmask(u8 irq);
void pic_eoi(u8 irq);

#endif
