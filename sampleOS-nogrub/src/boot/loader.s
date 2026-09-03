.section .text
.code32

.global _start
.extern kernel_main

_start:
    mov $stack_top, %esp

    push $0
    push $0

    call kernel_main

.hang:
    cli
    hlt
    jmp .hang

.section .bss
.align 16

stack_bottom:
    .skip 16384

stack_top:

.section .note.GNU-stack,"",@progbits
