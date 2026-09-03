#include "control.h"
#include "printf.h"
#include "string.h"
#include "pit.h"
#include "kmalloc.h"
#include "frame.h"
#include "paging.h"
#include "task.h"

#define MAX_SLOTS  8
#define TEST_VIRT  0x80000000u
#define PEEK_LIMIT 0x400000u

static u8    test_page[4096] __attribute__((aligned(4096)));
static void *kmalloc_slots[MAX_SLOTS];
static u32   kmalloc_slot_count;
static u32   frame_slots[MAX_SLOTS];
static u32   frame_slot_count;

static int   granted;

/* ---- audit log (ring of recent mutating actions) ---------------------- */

#define AUDIT_MAX 16
#define AUDIT_LEN 96
static char audit_buf[AUDIT_MAX][AUDIT_LEN];
static u32  audit_count;   /* total ever recorded */
static u32  audit_head;    /* next write slot      */

void control_init(void)
{
    kmalloc_slot_count = 0;
    frame_slot_count = 0;
    granted = 0;
    audit_count = 0;
    audit_head = 0;
}

void control_grant(void)
{
    granted = 1;
    kprintf("[kernel] kernel_ctl GRANTED for this session "
            "(the AI may now run mutating verbs)\n");
}

void control_revoke(void)
{
    granted = 0;
    kprintf("[kernel] kernel_ctl REVOKED (the AI is read-only again)\n");
}

int control_granted(void)
{
    return granted;
}

void control_audit(const char *verb, const char *reason)
{
    char *s = audit_buf[audit_head];
    u32 i = 0;
    for (const char *p = verb; *p && i < AUDIT_LEN - 1; p++) s[i++] = *p;
    if (reason && reason[0]) {
        for (const char *p = " :: "; *p && i < AUDIT_LEN - 1; p++) s[i++] = *p;
        for (const char *p = reason; *p && i < AUDIT_LEN - 1; p++) s[i++] = *p;
    }
    s[i] = 0;
    audit_head = (audit_head + 1) % AUDIT_MAX;
    audit_count++;
    kprintf("[audit] %s\n", s);
}

void control_audit_list(void)
{
    if (audit_count == 0) {
        kprintf("(no AI control actions recorded this session)\n");
        return;
    }
    u32 n = (audit_count < AUDIT_MAX) ? audit_count : AUDIT_MAX;
    kprintf("AI control actions (%u most recent, oldest first):\n", n);
    u32 start = (audit_head + AUDIT_MAX - n) % AUDIT_MAX;
    for (u32 k = 0; k < n; k++) {
        kprintf("  %u: %s\n", k, audit_buf[(start + k) % AUDIT_MAX]);
    }
}

/* ---- read verbs -------------------------------------------------------- */

void ctl_uptime(void)
{
    kprintf("[ai] uptime %u ms (%u ticks)\n", timer_uptime_ms(), timer_ticks());
}

void ctl_meminfo(void)
{
    kprintf("[ai] heap   : %u / %u bytes used\n", kmalloc_used(), kmalloc_total());
    kprintf("[ai] frames : %u / %u pages used\n", frame_used(), frame_total());
}

void ctl_ps(void)
{
    task_ps();
}

int ctl_peek(u32 addr)
{
    if (addr > PEEK_LIMIT - 4) {
        kprintf("[intent] rejected: addr 0x%x outside safe range (<0x%x)\n",
                addr, PEEK_LIMIT);
        return -1;
    }
    u32 v = *(volatile u32 *)addr;
    kprintf("[ai] peek 0x%x = 0x%x\n", addr, v);
    return 0;
}

void ctl_peek_test(void)
{
    kprintf("reading 0x%x ...\n", TEST_VIRT);
    volatile u32 v = *(volatile u32 *)TEST_VIRT;   /* faults if unmapped */
    kprintf("  value = 0x%x\n", v);
}

/* ---- calc: deterministic integer arithmetic (the kernel does the math, not
 *      the LLM) -- recursive descent over + - * / and parentheses ---------- */

static const char *calc_p;
static int calc_err;

static int calc_e(void);

static int calc_f(void)
{
    while (*calc_p == ' ') calc_p++;
    int s = 1;
    while (*calc_p == '+' || *calc_p == '-') {
        if (*calc_p == '-') s = -s;
        calc_p++;
        while (*calc_p == ' ') calc_p++;
    }
    if (*calc_p == '(') {
        calc_p++;
        int v = calc_e();
        while (*calc_p == ' ') calc_p++;
        if (*calc_p == ')') calc_p++; else calc_err = 1;
        return s * v;
    }
    if (*calc_p < '0' || *calc_p > '9') { calc_err = 1; return 0; }
    int v = 0;
    while (*calc_p >= '0' && *calc_p <= '9') { v = v * 10 + (*calc_p - '0'); calc_p++; }
    return s * v;
}

static int calc_t(void)
{
    int v = calc_f();
    for (;;) {
        while (*calc_p == ' ') calc_p++;
        char o = *calc_p;
        if (o != '*' && o != '/') break;
        calc_p++;
        int r = calc_f();
        if (o == '*') v *= r;
        else { if (r == 0) { calc_err = 1; return 0; } v /= r; }
    }
    return v;
}

static int calc_e(void)
{
    int v = calc_t();
    for (;;) {
        while (*calc_p == ' ') calc_p++;
        char o = *calc_p;
        if (o != '+' && o != '-') break;
        calc_p++;
        int r = calc_t();
        v += (o == '+') ? r : -r;
    }
    return v;
}

int ctl_calc(const char *expr)
{
    calc_p = expr;
    calc_err = 0;
    int v = calc_e();
    while (*calc_p == ' ') calc_p++;
    if (calc_err || *calc_p) {
        kprintf("[ai] calc: cannot evaluate '%s'\n", expr);
        return -1;
    }
    kprintf("[ai] calc %s = %d\n", expr, v);
    return 0;
}

/* ---- mutating verbs ---------------------------------------------------- */

int ctl_map(void)
{
    u32 phys = (u32)test_page;
    paging_map(TEST_VIRT, phys, PAGE_PRESENT | PAGE_RW);
    *(volatile u32 *)TEST_VIRT = 0xDEADBEEF;
    u32 v = *(volatile u32 *)TEST_VIRT;
    kprintf("[ai] mapped 0x%x -> phys 0x%x, wrote/read 0x%x\n", TEST_VIRT, phys, v);
    return 0;
}

int ctl_unmap(void)
{
    paging_unmap(TEST_VIRT);
    kprintf("[ai] unmapped 0x%x\n", TEST_VIRT);
    return 0;
}

int ctl_alloc(void)
{
    if (kmalloc_slot_count >= MAX_SLOTS) {
        kprintf("[ai] kmalloc slots full\n");
        return -1;
    }
    void *p = kmalloc(256);
    if (!p) {
        kprintf("[ai] kmalloc(256) failed\n");
        return -1;
    }
    memset(p, 0xAB, 256);
    kmalloc_slots[kmalloc_slot_count++] = p;
    kprintf("[ai] kmalloc(256) = %p [slot %u]\n", p, kmalloc_slot_count - 1);
    return 0;
}

int ctl_free(void)
{
    if (kmalloc_slot_count == 0) {
        kprintf("[ai] nothing to free\n");
        return -1;
    }
    void *p = kmalloc_slots[--kmalloc_slot_count];
    kfree(p);
    kprintf("[ai] kfree(%p) [slot %u]\n", p, kmalloc_slot_count);
    return 0;
}

int ctl_frame(void)
{
    if (frame_slot_count >= MAX_SLOTS) {
        kprintf("[ai] frame slots full\n");
        return -1;
    }
    u32 ph = frame_alloc();
    if (!ph) {
        kprintf("[ai] frame_alloc failed\n");
        return -1;
    }
    frame_slots[frame_slot_count++] = ph;
    kprintf("[ai] frame_alloc = 0x%x [slot %u]\n", ph, frame_slot_count - 1);
    return 0;
}

int ctl_unframe(void)
{
    if (frame_slot_count == 0) {
        kprintf("[ai] no frame to free\n");
        return -1;
    }
    u32 ph = frame_slots[--frame_slot_count];
    frame_free(ph);
    kprintf("[ai] frame_free(0x%x) [slot %u]\n", ph, frame_slot_count);
    return 0;
}

int ctl_kill(u32 id)
{
    if (id == 0) {
        kprintf("[ai] refusing to kill task 0 (the kernel)\n");
        return -1;
    }
    if (task_kill(id) != 0) {
        kprintf("[ai] no killable task %u (must exist and be ready)\n", id);
        return -1;
    }
    kprintf("[ai] task %u killed\n", id);
    return 0;
}
