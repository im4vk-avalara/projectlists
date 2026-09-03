#include "io.h"
#include "asm.h"
#include "printf.h"
#include "string.h"
#include "types.h"

#ifdef DEMO_BUILD
#include "fb.h"
#include "anim.h"
#else
#include "kbd.h"
#include "idt.h"
#include "pic.h"
#include "pit.h"
#include "paging.h"
#include "e820.h"
#include "frame.h"
#include "kmalloc.h"
#include "gdt.h"
#include "usermode.h"
#include "bridge.h"
#include "task.h"
#include "intent.h"
#include "control.h"
#include "app.h"
#include "vfs.h"
#endif

#ifndef DEMO_BUILD
static volatile u32 zero = 0;

__attribute__((noinline))
static void trigger_divide_by_zero(void)
{
    volatile u32 x = 100;
    volatile u32 y = x / zero;
    (void)y;
}

/* Cooperative-multitasking demo: a background task that progresses while the
 * console waits for input (kbd_read_scancode yields), then exits. Each step
 * waits out ~50 yield rotations (~0.5 s: the console wakes at PIT 100 Hz). */
static void demo_task(void)
{
    u32 id = task_current();
    for (u32 step = 1; step <= 5; step++) {
        for (u32 i = 0; i < 50; i++)
            task_yield();
        kprintf("[task %u] step %u/5\n", id, step);
    }
    kprintf("[task %u] done\n", id);
}

/* ---- S2: AI console (line editor + '/' dev commands) ------------------ */

/* Read one line into buf (NUL-terminated). Echoes input, handles backspace. */
static void read_line(char *buf, u32 max)
{
    u32 len = 0;
    while (1) {
        char c = kbd_getchar();
        if (c == '\n') {
            terminal_putchar('\n');
            buf[len] = 0;
            return;
        }
        if (c == '\b') {
            if (len > 0) {
                len--;
                terminal_putchar('\b');
            }
            continue;
        }
        if (len + 1 < max) {            /* leave room for the NUL */
            buf[len++] = c;
            terminal_putchar(c);
        }
    }
}

static void dev_help(void)
{
    kprintf("dev commands (direct user action; the AI reaches the same verbs via intents):\n");
    kprintf("  /help     this list\n");
    kprintf("  /uptime   ms + ticks since boot\n");
    kprintf("  /meminfo  heap + frame usage\n");
    kprintf("  /map      map + write/read the test page\n");
    kprintf("  /unmap    unmap the test page\n");
    kprintf("  /peek     read the test vaddr (page-faults if unmapped)\n");
    kprintf("  /alloc    kmalloc(256) into a slot\n");
    kprintf("  /free     kfree the most recent slot\n");
    kprintf("  /frame    frame_alloc() one page\n");
    kprintf("  /unframe  frame_free the most recent frame\n");
    kprintf("  /spawn    spawn a background demo task (see it run: /ps)\n");
    kprintf("  /ps       list tasks\n");
    kprintf("  /ring3    re-run the ring-3 user demo\n");
    kprintf("  /panic    trigger divide-by-zero (kernel panic)\n");
    kprintf("  /grant    grant kernel_ctl so the AI may run mutating verbs\n");
    kprintf("  /revoke   revoke kernel_ctl (AI back to read-only)\n");
    kprintf("  /audit    list mutating actions the AI has performed\n");
    kprintf("kernel_ctl for the AI: %s\n", control_granted() ? "GRANTED" : "not granted");
    kprintf("plain text (no leading '/') is sent to the AI.\n");
}

/* Local developer commands = direct user action, so they are NOT gated by
 * kernel_ctl (the console user already has full authority). They call the same
 * control-surface functions the AI reaches through validated intents. */
static void dev_command(const char *line)
{
    if (strcmp(line, "/help") == 0)         dev_help();
    else if (strcmp(line, "/uptime") == 0)  ctl_uptime();
    else if (strcmp(line, "/meminfo") == 0) ctl_meminfo();
    else if (strcmp(line, "/map") == 0)     ctl_map();
    else if (strcmp(line, "/unmap") == 0)   ctl_unmap();
    else if (strcmp(line, "/peek") == 0)    ctl_peek_test();
    else if (strcmp(line, "/alloc") == 0)   ctl_alloc();
    else if (strcmp(line, "/free") == 0)    ctl_free();
    else if (strcmp(line, "/frame") == 0)   ctl_frame();
    else if (strcmp(line, "/unframe") == 0) ctl_unframe();
    else if (strcmp(line, "/spawn") == 0) {
        int id = task_create(demo_task, "demo");
        if (id < 0) kprintf("task_create failed (table full / no memory)\n");
        else        kprintf("spawned task %d; it runs while the console is idle\n", id);
    }
    else if (strcmp(line, "/ps") == 0)      ctl_ps();
    else if (strcmp(line, "/grant") == 0)   control_grant();
    else if (strcmp(line, "/revoke") == 0)  control_revoke();
    else if (strcmp(line, "/audit") == 0)   control_audit_list();
    else if (strcmp(line, "/ring3") == 0) {
        run_user_demo();
        kprintf("[kernel] ring-3 demo returned; kernel intact.\n");
    } else if (strcmp(line, "/panic") == 0) {
        kprintf("triggering divide-by-zero...\n");
        trigger_divide_by_zero();
    } else {
        kprintf("unknown command '%s' (try /help)\n", line);
    }
}

/* Plain (non-'/') lines go to the AI over the COM2 bridge to the host-local
 * model. Blocks (with timeout) for the reply. */
static void ai_send(const char *line)
{
    static char reply[2048];
    int n = bridge_request(line, (u32)strlen(line), reply, sizeof(reply));
    if (n == -1) {
        kprintf("[ai] no reply -- is the host ai-bridge running? "
                "(see host/ai-bridge/bridge.py)\n");
    } else if (n == -2) {
        kprintf("[ai] backend error: %s\n", reply);
    } else if (intent_looks_like(reply)) {
        intent_execute(reply);          /* AI is acting on the machine */
    } else if (app_looks_like(reply)) {
        app_run(reply);                 /* AI generated an app: validate + run */
    } else {
        kprintf("[ai] %s\n", reply);
    }
}

/* S8: a ring-3 task faulted -- ask the AI to explain it (event-driven, not a
 * request). Runs in console context (interrupts on), never in the handler. */
static void ai_fault_report(const struct fault_info *fi)
{
    static char prompt[384];
    if (fi->vector == 14) {
        ksnprintf(prompt, sizeof(prompt),
            "A user task in AIOS just crashed and the kernel terminated it. Fault: "
            "page fault (exception 14) at eip=0x%x, faulting address cr2=0x%x, error=0x%x. "
            "In 1-2 short, friendly sentences tell the user what likely went wrong and "
            "that you stopped the task. Plain text only, no JSON.",
            fi->eip, fi->cr2, fi->err_code);
    } else {
        ksnprintf(prompt, sizeof(prompt),
            "A user task in AIOS just crashed and the kernel terminated it. Fault: "
            "%s (exception %u) at eip=0x%x, error=0x%x. "
            "In 1-2 short, friendly sentences tell the user what likely went wrong and "
            "that you stopped the task. Plain text only, no JSON.",
            fi->name, fi->vector, fi->eip, fi->err_code);
    }
    static char reply[1024];
    int n = bridge_request(prompt, (u32)strlen(prompt), reply, sizeof(reply));
    if (n > 0)
        kprintf("[ai] %s\n", reply);
}
#endif

void kernel_main(u32 boot_magic, u32 boot_info)
{
    (void)boot_magic;
    (void)boot_info;

#ifdef DEMO_BUILD

    fb_clear(15);

    for (volatile u32 i = 0; i < 200000000; i++) {
        __asm__ volatile ("nop");
    }

    plasma_init();
    plasma_run_forever();

#else

    serial_init();
    terminal_clear();

    gdt_init();

    kprintf("AIOS kernel started\n");
    kprintf("---------------------\n\n");

    kprintf("Boot method: %s\n", "custom bootloader");
    kprintf("CPU mode:    %s\n\n", "32-bit protected mode");

    kprintf("kprintf demo:\n");
    kprintf("  char    : %c\n", 'Z');
    kprintf("  string  : %s\n", "hello, AIOS");
    kprintf("  int     : %d\n", -12345);
    kprintf("  uint    : %u\n", 4000000000u);
    kprintf("  hex     : %x   HEX: %X\n", 0xDEADBEEFu, 0xCAFEBABEu);
    kprintf("  pointer : %p\n", (void *)&kernel_main);
    kprintf("  literal : 100%% done\n\n");

    char buf[16];
    memset(buf, 'A', 5);
    buf[5] = 0;
    kprintf("  memset  : \"%s\" (len=%u)\n\n", buf, (u32)strlen(buf));

    idt_init();
    paging_init();
    pic_init();
    pit_init(100);
    kbd_init();
    bridge_init();
    sti();

    e820_print();
    u32 mem_top = e820_usable_top();
    if (mem_top == 0) {
        kprintf("E820 empty -- falling back to 4 MB\n");
        mem_top = 4 * 1024 * 1024;
    }
    frame_init(mem_top);
    kmalloc_init();
    control_init();
    vfs_init();
    task_init();

    kprintf("IDT + paging + PIC + PIT + IRQ keyboard installed.\n");
    kprintf("Heap : %u bytes (used %u)\n", kmalloc_total(), kmalloc_used());
    kprintf("RAM  : %u MB usable (E820)\n", mem_top >> 20);
    kprintf("Frames: %u total (used %u) @ phys [0x%x..0x%x)\n\n",
            frame_total(), frame_used(), frame_base(),
            frame_base() + frame_total() * 4096);

    /* S1: drop to ring 3 and run the user-mode demo, then return to kernel. */
    paging_enable_user_lowmem();
    kprintf("Entering ring 3 (user mode) demo...\n");
    run_user_demo();
    kprintf("[kernel] back in ring 0, user task contained. Continuing.\n\n");

    kprintf("AIOS console ready. Type a request in plain English, or /help.\n");

    /* Discard the boot demo's fault: don't auto-report it (and don't block on
     * the bridge at boot when it isn't connected). Only interactive faults
     * trigger the AI first-responder. */
    {
        struct fault_info discard;
        fault_take(&discard);
    }

    char line[128];
    while (1) {
        /* S8: if a ring-3 task faulted, the AI responds before the next prompt. */
        struct fault_info fi;
        if (fault_take(&fi)) {
            kprintf("\n[kernel] a task faulted -- asking the AI...\n");
            ai_fault_report(&fi);
        }
        kprintf("aios> ");
        read_line(line, sizeof(line));
        if (line[0] == '/') {
            dev_command(line);
        } else if (line[0] != 0) {
            ai_send(line);
        }
    }

#endif

    while (1) {
        hlt();
    }
}
