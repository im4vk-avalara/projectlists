.section .text
.code32

/* ---- GDT / TSS loaders ------------------------------------------------- */

/* void gdt_flush(u32 gdtr_addr) */
.global gdt_flush
gdt_flush:
    movl 4(%esp), %eax
    lgdt (%eax)
    movw $0x10, %ax          /* reload data segments with kernel data */
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %fs
    movw %ax, %gs
    movw %ax, %ss
    ljmp $0x08, $.flush_cs    /* far jump reloads CS = kernel code */
.flush_cs:
    ret

/* void tss_flush(void) */
.global tss_flush
tss_flush:
    movw $0x28, %ax           /* TSS selector */
    ltr %ax
    ret

/* ---- ring-3 transition ------------------------------------------------- */

/*
 * void usermode_run(u32 entry, u32 user_stack_top)
 *
 * Saves a kernel resume point, then iret's down to ring 3 at `entry` on a
 * fresh user stack. Returns (here) only when the task ends -- via sys_exit or
 * a contained fault calling usermode_exit().
 */
.global usermode_run
usermode_run:
    cli                       /* no IRQs mid-transition; iret restores IF=1 */
    pushl %ebp
    pushl %ebx
    pushl %esi
    pushl %edi
    movl %esp, kernel_resume_esp

    movl 20(%esp), %edx       /* arg1: entry (eip)            */
    movl 24(%esp), %ecx       /* arg2: user stack top (esp)   */

    movw $0x23, %ax           /* user data selector (RPL 3)   */
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %fs
    movw %ax, %gs

    pushl $0x23               /* ss     */
    pushl %ecx                /* esp    */
    pushl $0x202              /* eflags (IF set)              */
    pushl $0x1B               /* cs: user code selector (RPL 3) */
    pushl %edx                /* eip    */
    iret

/*
 * void usermode_exit(void)
 *
 * Tears down the running user task and resumes the kernel right after
 * usermode_run(). Called from ring 0 (syscall or fault handler). Does not
 * return to the caller.
 */
.global usermode_exit
usermode_exit:
    movl kernel_resume_esp, %esp
    popl %edi
    popl %esi
    popl %ebx
    popl %ebp
    sti                       /* restore interrupts for the kernel */
    ret

.section .bss
.align 4
kernel_resume_esp:
    .skip 4

.section .note.GNU-stack,"",@progbits
