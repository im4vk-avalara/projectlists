.section .text
.code32

.macro ISR_NOERR n
.global isr\n
isr\n:
    pushl $0
    pushl $\n
    jmp isr_common
.endm

.macro ISR_ERR n
.global isr\n
isr\n:
    pushl $\n
    jmp isr_common
.endm

ISR_NOERR 0
ISR_NOERR 1
ISR_NOERR 2
ISR_NOERR 3
ISR_NOERR 4
ISR_NOERR 5
ISR_NOERR 6
ISR_NOERR 7
ISR_ERR   8
ISR_NOERR 9
ISR_ERR   10
ISR_ERR   11
ISR_ERR   12
ISR_ERR   13
ISR_ERR   14
ISR_NOERR 15
ISR_NOERR 16
ISR_ERR   17
ISR_NOERR 18
ISR_NOERR 19
ISR_NOERR 20
ISR_ERR   21
ISR_NOERR 22
ISR_NOERR 23
ISR_NOERR 24
ISR_NOERR 25
ISR_NOERR 26
ISR_NOERR 27
ISR_NOERR 28
ISR_NOERR 29
ISR_ERR   30
ISR_NOERR 31

.macro IRQ_STUB num
.global irq\num
irq\num:
    pushl $0
    pushl $(32 + \num)
    jmp isr_common
.endm

IRQ_STUB 0
IRQ_STUB 1
IRQ_STUB 2
IRQ_STUB 3
IRQ_STUB 4
IRQ_STUB 5
IRQ_STUB 6
IRQ_STUB 7
IRQ_STUB 8
IRQ_STUB 9
IRQ_STUB 10
IRQ_STUB 11
IRQ_STUB 12
IRQ_STUB 13
IRQ_STUB 14
IRQ_STUB 15

/* syscall entry: int 0x80 (vector 128), reuses the common path */
.global isr128
isr128:
    pushl $0
    pushl $128
    jmp isr_common

.extern isr_dispatch

isr_common:
    pusha

    pushl %ds
    pushl %es
    pushl %fs
    pushl %gs

    movw $0x10, %ax
    movw %ax, %ds
    movw %ax, %es
    movw %ax, %fs
    movw %ax, %gs

    pushl %esp
    call isr_dispatch
    addl $4, %esp

    popl %gs
    popl %fs
    popl %es
    popl %ds

    popa

    addl $8, %esp

    iret

.section .note.GNU-stack,"",@progbits
