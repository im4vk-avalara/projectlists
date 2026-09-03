#ifndef TASK_H
#define TASK_H

#include "types.h"

/* Cooperative kernel tasks: explicit task_yield() switches stacks, no
 * preemption. Task 0 is the kernel console loop. */

#define TASK_MAX 8

enum task_state {
    TASK_FREE = 0,
    TASK_READY,
    TASK_RUNNING,
    TASK_DEAD,      /* killed or exited; slot reused by the next create */
};

void task_init(void);
int  task_create(void (*entry)(void), const char *name);  /* id, or -1 */
void task_yield(void);
void task_exit(void);            /* current task only; never returns */
int  task_kill(u32 id);          /* mark a non-current task dead */
void task_ps(void);              /* print the task table */
u32  task_current(void);

#endif
