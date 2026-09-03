#ifndef IDT_H
#define IDT_H

#include "types.h"

struct idt_entry {
    u16 offset_lo;
    u16 selector;
    u8  zero;
    u8  type_attr;
    u16 offset_hi;
} __attribute__((packed));

struct idt_ptr {
    u16 limit;
    u32 base;
} __attribute__((packed));

struct regs {
    u32 gs, fs, es, ds;
    u32 edi, esi, ebp, esp_dummy, ebx, edx, ecx, eax;
    u32 vector, err_code;
    u32 eip, cs, eflags;
};

typedef void (*irq_handler_t)(struct regs *r);

/* Context of a contained ring-3 fault, for the AI first-responder (S8). */
struct fault_info {
    u32 vector;
    u32 err_code;
    u32 eip;
    u32 cr2;            /* faulting address (page faults only) */
    const char *name;
};

void idt_init(void);
void isr_dispatch(struct regs *r);
void irq_install(u8 irq, irq_handler_t fn);

/* If a ring-3 task faulted since the last call, copy its context to `out`,
 * clear the pending flag, and return 1; else return 0. */
int  fault_take(struct fault_info *out);

#endif
