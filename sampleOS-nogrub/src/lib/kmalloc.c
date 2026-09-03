#include "kmalloc.h"
#include "string.h"

#define HEAP_SIZE   (256 * 1024)
#define ALIGN       16
#define MIN_PAYLOAD ALIGN

typedef struct block {
    u32 size;
    u32 used;
} block_t;

static u8 heap[HEAP_SIZE] __attribute__((aligned(ALIGN)));
static u32 heap_used = 0;

static u32 align_up(u32 v)
{
    return (v + (ALIGN - 1)) & ~(ALIGN - 1u);
}

void kmalloc_init(void)
{
    block_t *first = (block_t *)heap;
    first->size = HEAP_SIZE - sizeof(block_t);
    first->used = 0;
    heap_used = 0;
}

void *kmalloc(u32 size)
{
    if (size == 0) return 0;
    size = align_up(size);

    u8 *p = heap;
    u8 *end = heap + HEAP_SIZE;

    while (p < end) {
        block_t *b = (block_t *)p;

        if (!b->used && b->size >= size) {
            u32 leftover = b->size - size;
            if (leftover >= sizeof(block_t) + MIN_PAYLOAD) {
                block_t *next = (block_t *)(p + sizeof(block_t) + size);
                next->size = leftover - sizeof(block_t);
                next->used = 0;
                b->size = size;
            }
            b->used = 1;
            heap_used += sizeof(block_t) + b->size;
            return p + sizeof(block_t);
        }

        p += sizeof(block_t) + b->size;
    }
    return 0;
}

void kfree(void *ptr)
{
    if (!ptr) return;

    block_t *b = (block_t *)((u8 *)ptr - sizeof(block_t));
    if (!b->used) return;

    b->used = 0;
    heap_used -= sizeof(block_t) + b->size;

    u8 *p = heap;
    u8 *end = heap + HEAP_SIZE;
    block_t *prev = 0;
    while (p < end) {
        block_t *cur = (block_t *)p;
        if (prev && !prev->used && !cur->used) {
            prev->size += sizeof(block_t) + cur->size;
        } else {
            prev = cur;
        }
        p = (u8 *)cur + sizeof(block_t) + cur->size;
    }
}

u32 kmalloc_total(void) { return HEAP_SIZE; }
u32 kmalloc_used(void)  { return heap_used; }
