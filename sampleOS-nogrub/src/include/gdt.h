#ifndef GDT_H
#define GDT_H

#include "types.h"

/*
 * Builds a full GDT in protected mode (replacing the bootloader's flat 3-entry
 * table): null, kernel code/data (0x08/0x10, unchanged), user code/data
 * (0x18/0x20, DPL 3), and a TSS (0x28) holding the ring-0 stack used when a
 * ring-3 task traps into the kernel.
 */
void gdt_init(void);

/* Set the ring-0 stack the CPU switches to on a ring3 -> ring0 transition. */
void tss_set_kernel_stack(u32 esp0);

#endif
