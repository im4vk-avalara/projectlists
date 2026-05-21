; hello.asm — minimal x86_64 Linux "hello world" via direct syscalls.
; No libc. Assembled with NASM, linked with ld, run on Linux (x86_64).
;
; --- Linux x86_64 syscall ABI -------------------------------------------------
;   rax = syscall number
;   args, in order:  rdi, rsi, rdx, r10, r8, r9
;   instruction:     syscall
;   return value:    rax
;
;   sys_write (1): ssize_t write(int fd, const void *buf, size_t count)
;   sys_exit  (60): void exit(int status)
; -----------------------------------------------------------------------------

        section .data
msg:    db  "Hello, world", 10        ; the 10 is '\n' (LF)
msglen  equ $ - msg                   ; assembler computes length at assemble time

        section .text
        global _start                 ; ld's default entry symbol
_start:
        ; write(1, msg, msglen)
        mov     rax, 1                ; syscall #: sys_write
        mov     rdi, 1                ; fd = 1 (stdout)
        mov     rsi, msg              ; buf = address of msg
        mov     rdx, msglen           ; count = length
        syscall

        ; exit(0)
        mov     rax, 60               ; syscall #: sys_exit
        xor     rdi, rdi              ; status = 0 (xor reg,reg is the idiomatic zero)
        syscall
