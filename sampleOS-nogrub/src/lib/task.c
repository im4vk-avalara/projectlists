#include "task.h"
#include "kmalloc.h"
#include "printf.h"

#define TASK_STACK_SIZE 8192

struct task {
    u32 esp;
    enum task_state state;
    const char *name;
    u8 *stack;            /* kmalloc'd; NULL for task 0 (boot stack) */
};

static struct task tasks[TASK_MAX];
static u32 current;

extern void ctx_switch(u32 *save_esp, u32 load_esp);

void task_init(void)
{
    tasks[0].state = TASK_RUNNING;
    tasks[0].name  = "kernel";
    tasks[0].stack = 0;
    current = 0;
}

u32 task_current(void)
{
    return current;
}

int task_create(void (*entry)(void), const char *name)
{
    u32 id;
    for (id = 1; id < TASK_MAX; id++) {
        if (tasks[id].state == TASK_FREE || tasks[id].state == TASK_DEAD)
            break;
    }
    if (id == TASK_MAX) return -1;

    if (tasks[id].stack)                  /* reclaim a dead task's stack */
        kfree(tasks[id].stack);
    u8 *stack = kmalloc(TASK_STACK_SIZE);
    if (!stack) return -1;

    /* Prebuild the stack to match ctx_switch's pops: four callee-saved
     * registers, the entry as its ret target, and task_exit as the address
     * entry returns to. */
    u32 *sp = (u32 *)(stack + TASK_STACK_SIZE);
    *--sp = (u32)task_exit;
    *--sp = (u32)entry;
    *--sp = 0;                            /* ebp */
    *--sp = 0;                            /* ebx */
    *--sp = 0;                            /* esi */
    *--sp = 0;                            /* edi */

    tasks[id].esp   = (u32)sp;
    tasks[id].state = TASK_READY;
    tasks[id].name  = name;
    tasks[id].stack = stack;
    return (int)id;
}

void task_yield(void)
{
    u32 next = current;
    for (u32 i = 1; i <= TASK_MAX; i++) {
        u32 cand = (current + i) % TASK_MAX;
        if (tasks[cand].state == TASK_READY) {
            next = cand;
            break;
        }
    }
    if (next == current) return;          /* nothing else runnable */

    struct task *prev = &tasks[current];
    if (prev->state == TASK_RUNNING)      /* a dead task stays dead */
        prev->state = TASK_READY;
    tasks[next].state = TASK_RUNNING;
    current = next;
    ctx_switch(&prev->esp, tasks[next].esp);
}

void task_exit(void)
{
    tasks[current].state = TASK_DEAD;     /* stack reclaimed on slot reuse */
    while (1)
        task_yield();                     /* task 0 is always there to run */
}

int task_kill(u32 id)
{
    if (id == 0 || id == current || id >= TASK_MAX) return -1;
    if (tasks[id].state != TASK_READY) return -1;
    tasks[id].state = TASK_DEAD;
    return 0;
}

void task_ps(void)
{
    static const char *state_names[] = { "free", "ready", "running", "dead" };
    for (u32 i = 0; i < TASK_MAX; i++) {
        if (tasks[i].state == TASK_FREE) continue;
        kprintf("[ai] task [%u] %s (%s)\n",
                i, tasks[i].name, state_names[tasks[i].state]);
    }
}
