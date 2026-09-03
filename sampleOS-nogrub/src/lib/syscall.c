#include "syscall.h"
#include "io.h"
#include "printf.h"
#include "usermode.h"

static int sys_write(u32 fd, const char *buf, u32 len)
{
    (void)fd;                       /* S1: single console; fd ignored */
    if (!buf) return -1;
    for (u32 i = 0; i < len; i++) {
        terminal_putchar(buf[i]);
    }
    return (int)len;
}

void syscall_dispatch(struct regs *r)
{
    switch (r->eax) {
    case SYS_EXIT:
        kprintf("\n[kernel] user task exited (code=%u)\n", r->ebx);
        usermode_exit();            /* tears down task, does not return */
        break;

    case SYS_WRITE:
        r->eax = (u32)sys_write(r->ebx, (const char *)r->ecx, r->edx);
        break;

    case SYS_YIELD:                 /* S1: no scheduler yet, no-op */
        r->eax = 0;
        break;

    case SYS_GETPID:
        r->eax = 1;
        break;

    default:
        kprintf("\n[kernel] unknown syscall %u -> -1\n", r->eax);
        r->eax = (u32)(-1);
        break;
    }
}
