/*
 * S1 ring-3 demo program. Runs entirely in user mode: it can only reach the
 * kernel through `int 0x80`. It exercises a few syscalls, shows that a bad
 * syscall is handled gracefully, and finally executes a privileged instruction
 * to prove the kernel contains a faulting user task instead of crashing.
 *
 * NOTE: for S1 the program is compiled into the kernel image and run in place
 * (the low 4 MB identity map is made user-accessible). Real per-task address
 * spaces / memory isolation are deferred -- see DESIGN.md (sandbox model).
 */
#include "types.h"
#include "syscall.h"
#include "usermode.h"

#define USTACK_SIZE 8192
static u8 user_stack[USTACK_SIZE] __attribute__((aligned(16)));

static inline int usys(int num, u32 a, u32 b, u32 c)
{
    int ret;
    __asm__ volatile ("int $0x80"
                      : "=a"(ret)
                      : "a"(num), "b"(a), "c"(b), "d"(c)
                      : "memory");
    return ret;
}

static inline void uwrite(const char *s)
{
    u32 n = 0;
    while (s[n]) n++;
    usys(SYS_WRITE, 1, (u32)s, n);
}

__attribute__((noinline))
static void user_program(void)
{
    uwrite("Hello from ring 3 (user mode)!\n");

    int pid = usys(SYS_GETPID, 0, 0, 0);
    char msg[8];
    msg[0] = 'p'; msg[1] = 'i'; msg[2] = 'd'; msg[3] = '=';
    msg[4] = (char)('0' + (pid % 10));
    msg[5] = '\n'; msg[6] = 0;
    uwrite(msg);

    int rc = usys(99, 0, 0, 0);     /* bogus syscall number */
    if (rc == -1) {
        uwrite("survived a bad syscall (got -1)\n");
    }

    uwrite("triggering a privileged instruction (should be contained)...\n");
    __asm__ volatile ("hlt");       /* privileged -> #GP from ring 3 */

    uwrite("this line should never run\n");
    usys(SYS_EXIT, 0, 0, 0);
}

void run_user_demo(void)
{
    usermode_run((u32)&user_program, (u32)(user_stack + USTACK_SIZE));
}
