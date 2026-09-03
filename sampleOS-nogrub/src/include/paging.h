#ifndef PAGING_H
#define PAGING_H

#include "types.h"

#define PAGE_SIZE     4096
#define PAGE_PRESENT  0x001
#define PAGE_RW       0x002
#define PAGE_USER     0x004

void paging_init(void);
int  paging_map(u32 virt, u32 phys, u32 flags);
void paging_unmap(u32 virt);
u32  read_cr2(void);

/* S1 shortcut: make the identity-mapped low 4 MB user-accessible so a ring-3
 * task can execute in place. This also exposes kernel memory to ring 3 -- real
 * per-task isolation is deferred (see DESIGN.md sandbox model). */
void paging_enable_user_lowmem(void);

#endif
