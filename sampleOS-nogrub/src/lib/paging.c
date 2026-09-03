#include "paging.h"
#include "string.h"
#include "frame.h"

/* New page tables come from the frame allocator (no static pool, no 16-PT
 * limit). The kernel writes PTs through the identity map, so only frames
 * below 4 MB qualify -- frames start at 1 MB, so up to 768 page tables.
 * Requires frame_init() before the first paging_map() of an unmapped region
 * (boot order in kernelmain.c guarantees this; paging_init itself uses only
 * the static first_page_table). */
#define IDENTITY_MAP_TOP (4u * 1024 * 1024)

static u32 page_directory[1024]   __attribute__((aligned(PAGE_SIZE)));
static u32 first_page_table[1024] __attribute__((aligned(PAGE_SIZE)));

static u32 *alloc_page_table(void)
{
    u32 ph = frame_alloc();
    if (!ph) return 0;
    if (ph + PAGE_SIZE > IDENTITY_MAP_TOP) {
        frame_free(ph);                /* unreachable via identity map */
        return 0;
    }
    u32 *pt = (u32 *)ph;
    memset(pt, 0, PAGE_SIZE);
    return pt;
}

void paging_init(void)
{
    memset(page_directory, 0, sizeof(page_directory));

    for (u32 i = 0; i < 1024; i++) {
        first_page_table[i] = (i * PAGE_SIZE) | PAGE_PRESENT | PAGE_RW;
    }

    page_directory[0] = ((u32)first_page_table) | PAGE_PRESENT | PAGE_RW;

    __asm__ volatile ("mov %0, %%cr3" : : "r"(page_directory));

    u32 cr0;
    __asm__ volatile ("mov %%cr0, %0" : "=r"(cr0));
    cr0 |= 0x80000000;
    __asm__ volatile ("mov %0, %%cr0" : : "r"(cr0));
}

u32 read_cr2(void)
{
    u32 v;
    __asm__ volatile ("mov %%cr2, %0" : "=r"(v));
    return v;
}

int paging_map(u32 virt, u32 phys, u32 flags)
{
    u32 pd_idx = virt >> 22;
    u32 pt_idx = (virt >> 12) & 0x3FF;

    u32 *pt;
    u32 pde = page_directory[pd_idx];
    if (pde & PAGE_PRESENT) {
        pt = (u32 *)(pde & ~0xFFFu);
    } else {
        pt = alloc_page_table();
        if (!pt) return -1;
        page_directory[pd_idx] = ((u32)pt) | PAGE_PRESENT | PAGE_RW;
    }

    pt[pt_idx] = (phys & ~0xFFFu) | (flags & 0xFFFu) | PAGE_PRESENT;
    __asm__ volatile ("invlpg (%0)" : : "r"(virt) : "memory");
    return 0;
}

void paging_enable_user_lowmem(void)
{
    page_directory[0] |= PAGE_USER;
    for (u32 i = 0; i < 1024; i++) {
        first_page_table[i] |= PAGE_USER;
    }
    __asm__ volatile ("mov %0, %%cr3" : : "r"(page_directory));   /* flush TLB */
}

void paging_unmap(u32 virt)
{
    u32 pd_idx = virt >> 22;
    u32 pt_idx = (virt >> 12) & 0x3FF;

    u32 pde = page_directory[pd_idx];
    if (!(pde & PAGE_PRESENT)) return;

    u32 *pt = (u32 *)(pde & ~0xFFFu);
    pt[pt_idx] = 0;
    __asm__ volatile ("invlpg (%0)" : : "r"(virt) : "memory");
}
