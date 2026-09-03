#ifndef USERMODE_H
#define USERMODE_H

#include "types.h"

/* Enter ring 3 at `entry` with the given user stack; returns when the task
 * ends. See lib/usermode.s. */
void usermode_run(u32 entry, u32 user_stack_top);

/* Terminate the current user task and resume the kernel after usermode_run().
 * Called from ring 0 (syscall/fault handler); does not return. */
void usermode_exit(void);

/* S1 demo: run the bundled ring-3 test program. See lib/usertest.c. */
void run_user_demo(void);

#endif
