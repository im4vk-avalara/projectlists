#include "idt.h"
#include "asm.h"
#include "pic.h"
#include "paging.h"
#include "printf.h"
#include "string.h"
#include "syscall.h"
#include "usermode.h"
#include "bridge.h"

#define IDT_ENTRIES 256
#define KERNEL_CS   0x08
#define IDT_TYPE_INT32      0x8E   /* 32-bit interrupt gate, DPL 0 */
#define IDT_TYPE_INT32_USER 0xEE   /* 32-bit interrupt gate, DPL 3 (syscall) */
#define SYSCALL_VECTOR      0x80

static struct idt_entry idt[IDT_ENTRIES];
static struct idt_ptr   idtr;

extern void isr0(void);  extern void isr1(void);  extern void isr2(void);  extern void isr3(void);
extern void isr4(void);  extern void isr5(void);  extern void isr6(void);  extern void isr7(void);
extern void isr8(void);  extern void isr9(void);  extern void isr10(void); extern void isr11(void);
extern void isr12(void); extern void isr13(void); extern void isr14(void); extern void isr15(void);
extern void isr16(void); extern void isr17(void); extern void isr18(void); extern void isr19(void);
extern void isr20(void); extern void isr21(void); extern void isr22(void); extern void isr23(void);
extern void isr24(void); extern void isr25(void); extern void isr26(void); extern void isr27(void);
extern void isr28(void); extern void isr29(void); extern void isr30(void); extern void isr31(void);

extern void irq0(void);  extern void irq1(void);  extern void irq2(void);  extern void irq3(void);
extern void irq4(void);  extern void irq5(void);  extern void irq6(void);  extern void irq7(void);
extern void irq8(void);  extern void irq9(void);  extern void irq10(void); extern void irq11(void);
extern void irq12(void); extern void irq13(void); extern void irq14(void); extern void irq15(void);

extern void isr128(void);   /* int 0x80 syscall stub */

static void (*const isr_stubs[32])(void) = {
    isr0,  isr1,  isr2,  isr3,  isr4,  isr5,  isr6,  isr7,
    isr8,  isr9,  isr10, isr11, isr12, isr13, isr14, isr15,
    isr16, isr17, isr18, isr19, isr20, isr21, isr22, isr23,
    isr24, isr25, isr26, isr27, isr28, isr29, isr30, isr31,
};

static void (*const irq_stubs[16])(void) = {
    irq0,  irq1,  irq2,  irq3,  irq4,  irq5,  irq6,  irq7,
    irq8,  irq9,  irq10, irq11, irq12, irq13, irq14, irq15,
};

static irq_handler_t irq_handlers[16] = { 0 };

static const char *exception_names[32] = {
    "Divide-by-zero",
    "Debug",
    "Non-maskable Interrupt",
    "Breakpoint",
    "Overflow",
    "BOUND Range Exceeded",
    "Invalid Opcode",
    "Device Not Available",
    "Double Fault",
    "Coprocessor Segment Overrun",
    "Invalid TSS",
    "Segment Not Present",
    "Stack-Segment Fault",
    "General Protection Fault",
    "Page Fault",
    "Reserved",
    "x87 Floating-Point Exception",
    "Alignment Check",
    "Machine Check",
    "SIMD Floating-Point Exception",
    "Virtualization Exception",
    "Control Protection Exception",
    "Reserved", "Reserved", "Reserved", "Reserved",
    "Reserved", "Reserved", "Reserved", "Reserved",
    "Reserved", "Reserved",
};

static void idt_set_gate(u8 vector, void (*handler)(void), u16 selector, u8 type_attr)
{
    u32 addr = (u32)handler;
    idt[vector].offset_lo = (u16)(addr & 0xFFFF);
    idt[vector].offset_hi = (u16)((addr >> 16) & 0xFFFF);
    idt[vector].selector  = selector;
    idt[vector].zero      = 0;
    idt[vector].type_attr = type_attr;
}

void idt_init(void)
{
    memset(idt, 0, sizeof(idt));

    for (int v = 0; v < 32; v++) {
        idt_set_gate((u8)v, isr_stubs[v], KERNEL_CS, IDT_TYPE_INT32);
    }

    for (int i = 0; i < 16; i++) {
        idt_set_gate((u8)(32 + i), irq_stubs[i], KERNEL_CS, IDT_TYPE_INT32);
    }

    /* Syscall gate: callable from ring 3 (DPL 3). */
    idt_set_gate(SYSCALL_VECTOR, isr128, KERNEL_CS, IDT_TYPE_INT32_USER);

    idtr.limit = (u16)(sizeof(idt) - 1);
    idtr.base  = (u32)&idt[0];

    __asm__ volatile ("lidt (%0)" : : "r"(&idtr));
}

void irq_install(u8 irq, irq_handler_t fn)
{
    if (irq >= 16) return;
    irq_handlers[irq] = fn;
    pic_unmask(irq);
}

/* ---- S8: contained ring-3 fault record (for the AI first-responder) ---- */
static struct fault_info g_fault;
static int g_fault_pending;

int fault_take(struct fault_info *out)
{
    if (!g_fault_pending) return 0;
    *out = g_fault;
    g_fault_pending = 0;
    return 1;
}

void isr_dispatch(struct regs *r)
{
    if (r->vector == SYSCALL_VECTOR) {
        syscall_dispatch(r);
        return;
    }

    if (r->vector >= 32 && r->vector < 48) {
        u8 irq = (u8)(r->vector - 32);
        if (irq_handlers[irq]) {
            irq_handlers[irq](r);
        }
        pic_eoi(irq);
        return;
    }

    const char *name = (r->vector < 32) ? exception_names[r->vector] : "Unknown";

    /* Fault that originated in ring 3: contain the task, keep the kernel alive,
     * and record the context so the AI can respond to it (S8). */
    if ((r->cs & 3) == 3) {
        g_fault.vector   = r->vector;
        g_fault.err_code = r->err_code;
        g_fault.eip      = r->eip;
        g_fault.cr2      = (r->vector == 14) ? read_cr2() : 0;
        g_fault.name     = name;
        g_fault_pending  = 1;
        kprintf("\n[kernel] user task fault: exception %u (%s) -- task terminated\n",
                r->vector, name);
        usermode_exit();   /* resumes kernel after usermode_run(); not reached */
        return;
    }

    kprintf("\n\n*** KERNEL PANIC ***\n");
    kprintf("Exception %u: %s\n", r->vector, name);
    if (r->vector == 14) {
        kprintf("  cr2=0x%x (faulting address)\n", read_cr2());
    }
    kprintf("  err=0x%x  eip=0x%x  cs=0x%x  eflags=0x%x\n",
            r->err_code, r->eip, r->cs, r->eflags);
    kprintf("  eax=0x%x ebx=0x%x ecx=0x%x edx=0x%x\n",
            r->eax, r->ebx, r->ecx, r->edx);
    kprintf("  esi=0x%x edi=0x%x ebp=0x%x\n",
            r->esi, r->edi, r->ebp);
    kprintf("  ds=0x%x es=0x%x fs=0x%x gs=0x%x\n",
            r->ds, r->es, r->fs, r->gs);

    /* S8b: best-effort AI diagnosis before halting. Guarded against recursion
     * (a fault during the bridge call must not re-enter this). sti() lets the
     * PIT tick so the bridge timeout works; we halt right after either way. */
    static int in_panic;
    if (!in_panic) {
        in_panic = 1;
        static char prompt[384], reply[1024];
        u32 cr2 = (r->vector == 14) ? read_cr2() : 0;
        ksnprintf(prompt, sizeof(prompt),
            "The AIOS kernel hit a FATAL fault and must halt. Fault: %s (exception %u), "
            "eip=0x%x err=0x%x cr2=0x%x. In 1-2 short sentences, tell the user what this "
            "kernel panic most likely means. Plain text only, no JSON.",
            name, r->vector, r->eip, r->err_code, cr2);
        sti();
        int n = bridge_request(prompt, (u32)strlen(prompt), reply, sizeof(reply));
        cli();
        if (n > 0) kprintf("\n[ai] %s\n", reply);
    }

    kprintf("System halted.\n");

    cli();
    while (1) {
        hlt();
    }
}
