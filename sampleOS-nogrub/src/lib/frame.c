#include "frame.h"
#include "string.h"

/* 32768 frames = 128 MB managed; bitmap is 4 KB of BSS. */
#define MAX_FRAMES 32768

/* Frames start at 1 MB: below that sit the kernel image (loaded at 0x10000,
 * BSS ends under 640 KB) and the 0xA0000-0xFFFFF VGA/ROM hole, which is not
 * RAM and must never be handed out. */
#define FRAME_BASE_MIN 0x100000

extern u8 _end[];

static u32 bitmap[MAX_FRAMES / 32];
static u32 base_phys;
static u32 total_count;
static u32 used_count;

static inline int bit_test(u32 i)
{
    return (bitmap[i >> 5] >> (i & 31)) & 1u;
}

static inline void bit_set(u32 i)
{
    bitmap[i >> 5] |= (1u << (i & 31));
}

static inline void bit_clear(u32 i)
{
    bitmap[i >> 5] &= ~(1u << (i & 31));
}

void frame_init(u32 mem_size_bytes)
{
    u32 kernel_end = (u32)_end;
    u32 start = (kernel_end + FRAME_SIZE - 1) & ~(FRAME_SIZE - 1);
    if (start < FRAME_BASE_MIN)
        start = FRAME_BASE_MIN;

    if (mem_size_bytes <= start) {
        total_count = 0;
        used_count = 0;
        return;
    }

    u32 frames_available = (mem_size_bytes - start) / FRAME_SIZE;
    if (frames_available > MAX_FRAMES) frames_available = MAX_FRAMES;

    base_phys = start;
    total_count = frames_available;
    used_count = 0;
    memset(bitmap, 0, sizeof(bitmap));
}

u32 frame_alloc(void)
{
    for (u32 i = 0; i < total_count; i++) {
        if (!bit_test(i)) {
            bit_set(i);
            used_count++;
            return base_phys + i * FRAME_SIZE;
        }
    }
    return 0;
}

void frame_free(u32 phys)
{
    if (phys < base_phys) return;
    u32 i = (phys - base_phys) / FRAME_SIZE;
    if (i >= total_count) return;
    if (bit_test(i)) {
        bit_clear(i);
        used_count--;
    }
}

u32 frame_total(void) { return total_count; }
u32 frame_used(void)  { return used_count; }
u32 frame_base(void)  { return base_phys; }
