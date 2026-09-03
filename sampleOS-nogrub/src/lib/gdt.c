#include "gdt.h"
#include "string.h"

#define GDT_ENTRIES 6

struct gdt_entry {
    u16 limit_lo;
    u16 base_lo;
    u8  base_mid;
    u8  access;
    u8  gran;       /* high limit nibble + flags */
    u8  base_hi;
} __attribute__((packed));

struct gdt_ptr {
    u16 limit;
    u32 base;
} __attribute__((packed));

/* 32-bit hardware TSS layout (we only use ss0/esp0). */
struct tss_entry {
    u32 prev_tss;
    u32 esp0, ss0;
    u32 esp1, ss1, esp2, ss2;
    u32 cr3, eip, eflags;
    u32 eax, ecx, edx, ebx, esp, ebp, esi, edi;
    u32 es, cs, ss, ds, fs, gs;
    u32 ldt;
    u16 trap;
    u16 iomap_base;
} __attribute__((packed));

static struct gdt_entry gdt[GDT_ENTRIES];
static struct gdt_ptr   gdtr;
static struct tss_entry tss;

/* Ring-0 stack the CPU switches to when a ring-3 task traps in (syscall/IRQ). */
static u8 kernel_stack0[16384] __attribute__((aligned(16)));

extern void gdt_flush(u32 gdtr_addr);   /* lib/usermode.s */
extern void tss_flush(void);            /* lib/usermode.s */

static void gdt_set(int i, u32 base, u32 limit, u8 access, u8 gran)
{
    gdt[i].base_lo  = (u16)(base & 0xFFFF);
    gdt[i].base_mid = (u8)((base >> 16) & 0xFF);
    gdt[i].base_hi  = (u8)((base >> 24) & 0xFF);
    gdt[i].limit_lo = (u16)(limit & 0xFFFF);
    gdt[i].gran     = (u8)(((limit >> 16) & 0x0F) | (gran & 0xF0));
    gdt[i].access   = access;
}

void gdt_init(void)
{
    gdt_set(0, 0, 0,         0x00, 0x00);   /* 0x00 null                       */
    gdt_set(1, 0, 0xFFFFF,   0x9A, 0xCF);   /* 0x08 kernel code (DPL0)         */
    gdt_set(2, 0, 0xFFFFF,   0x92, 0xCF);   /* 0x10 kernel data (DPL0)         */
    gdt_set(3, 0, 0xFFFFF,   0xFA, 0xCF);   /* 0x18 user code   (DPL3)         */
    gdt_set(4, 0, 0xFFFFF,   0xF2, 0xCF);   /* 0x20 user data   (DPL3)         */

    memset(&tss, 0, sizeof(tss));
    tss.ss0        = 0x10;
    tss.esp0       = (u32)(kernel_stack0 + sizeof(kernel_stack0));
    tss.iomap_base = sizeof(tss);           /* no I/O permission bitmap        */
    gdt_set(5, (u32)&tss, sizeof(tss) - 1, 0x89, 0x00);  /* 0x28 TSS (avail)   */

    gdtr.limit = (u16)(sizeof(gdt) - 1);
    gdtr.base  = (u32)&gdt[0];

    gdt_flush((u32)&gdtr);
    tss_flush();
}

void tss_set_kernel_stack(u32 esp0)
{
    tss.esp0 = esp0;
}
