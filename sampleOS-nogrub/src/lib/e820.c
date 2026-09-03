#include "e820.h"
#include "printf.h"

#define E820_COUNT_ADDR   0x8000
#define E820_ENTRIES_ADDR 0x8004
#define E820_MAX_ENTRIES  32

u32 e820_count(void)
{
    u32 n = *(volatile u32 *)E820_COUNT_ADDR;
    return n > E820_MAX_ENTRIES ? E820_MAX_ENTRIES : n;
}

const struct e820_entry *e820_get(u32 i)
{
    return (const struct e820_entry *)E820_ENTRIES_ADDR + i;
}

u32 e820_usable_top(void)
{
    u32 top = 0;
    for (u32 i = 0; i < e820_count(); i++) {
        const struct e820_entry *e = e820_get(i);
        if (e->type != E820_TYPE_USABLE) continue;
        if (e->base_hi) continue;               /* entirely above 4 GB */
        u32 end = e->base_lo + e->len_lo;
        if (e->len_hi || end < e->base_lo)      /* region crosses 4 GB: clamp */
            end = 0xFFFFFFFFu;
        if (end > top) top = end;
    }
    return top;
}

static const char *type_name(u32 t)
{
    switch (t) {
    case 1:  return "usable";
    case 2:  return "reserved";
    case 3:  return "ACPI reclaim";
    case 4:  return "ACPI NVS";
    case 5:  return "bad";
    default: return "unknown";
    }
}

void e820_print(void)
{
    u32 n = e820_count();
    if (n == 0) {
        kprintf("E820: no memory map from BIOS\n");
        return;
    }
    kprintf("E820 memory map (%u entries):\n", n);
    for (u32 i = 0; i < n; i++) {
        const struct e820_entry *e = e820_get(i);
        if (e->base_hi) {
            kprintf("  (above 4 GB)            %s\n", type_name(e->type));
            continue;
        }
        u32 end = e->base_lo + e->len_lo;
        if (e->len_hi || end < e->base_lo)
            end = 0xFFFFFFFFu;
        kprintf("  0x%x..0x%x %s\n", e->base_lo, end, type_name(e->type));
    }
}
