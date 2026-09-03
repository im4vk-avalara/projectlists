#ifndef E820_H
#define E820_H

#include "types.h"

/* BIOS int 0x15/EAX=E820 memory map, captured by the bootloader in real mode.
 * Count at 0x8000, 24-byte entries from 0x8004 (see bootloader.s). */

#define E820_TYPE_USABLE 1

struct e820_entry {
    u32 base_lo, base_hi;
    u32 len_lo,  len_hi;
    u32 type;
    u32 attr;     /* ACPI 3.0 extended attributes; may be stale, ignore */
} __attribute__((packed));

u32 e820_count(void);
const struct e820_entry *e820_get(u32 i);

/* End (exclusive) of the highest usable region below 4 GB, in bytes.
 * 0 if the BIOS gave no map (caller picks a fallback). */
u32 e820_usable_top(void);

void e820_print(void);

#endif
