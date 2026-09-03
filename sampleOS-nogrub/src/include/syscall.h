#ifndef SYSCALL_H
#define SYSCALL_H

#include "idt.h"

/* ABI: eax = syscall number, args in ebx/ecx/edx, return value in eax. */
enum {
    SYS_EXIT   = 0,   /* (code)              -> never returns */
    SYS_WRITE  = 1,   /* (fd, buf, len)      -> bytes written */
    SYS_READ   = 2,   /* (fd, buf, len)      -> bytes read    */
    SYS_YIELD  = 3,   /* ()                  -> 0             */
    SYS_GETPID = 4,   /* ()                  -> pid           */
};

/* Dispatch an int 0x80 trap. Reads/writes registers via the trap frame. */
void syscall_dispatch(struct regs *r);

#endif
