.section .text
.code32

# void ctx_switch(u32 *save_esp, u32 load_esp)
#
# Saves the callee-saved registers + ESP of the current task, then loads the
# next task's ESP and pops its registers. cdecl: EAX/ECX/EDX are caller-saved,
# so only EBP/EBX/ESI/EDI need to live on the stack. A brand-new task's stack
# is prebuilt to match this layout (see task_create).
.global ctx_switch
ctx_switch:
    mov 4(%esp), %eax        # &current->esp
    mov 8(%esp), %edx        # next->esp

    push %ebp
    push %ebx
    push %esi
    push %edi

    mov %esp, (%eax)
    mov %edx, %esp

    pop %edi
    pop %esi
    pop %ebx
    pop %ebp
    ret

.section .note.GNU-stack,"",@progbits
