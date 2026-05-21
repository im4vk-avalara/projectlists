; quine.asm - x86_64 Linux quine, NASM.
; Variant B: data[] holds every byte of this source, with the one line
; "        db <numbers>" represented by a single 0 byte (SENTINEL).
; At runtime: walk data, build the entire output in outbuf (substituting
; a regenerated db line where the SENTINEL appears), then emit outbuf
; in a single write syscall. Total syscalls: 2 (write, exit).

        section .data
data:
        db __BYTES__
data_len equ $-data

        section .bss
outbuf: resb 16384

        section .text
        global _start

itoa_byte:
        movzx rax, al
        cmp rax, 100
        jae .three
        cmp rax, 10
        jae .two
        add al, '0'
        mov [rdi], al
        inc rdi
        ret
.two:
        mov rcx, 10
        xor rdx, rdx
        div rcx
        add al, '0'
        mov [rdi], al
        add dl, '0'
        mov [rdi+1], dl
        add rdi, 2
        ret
.three:
        mov rcx, 100
        xor rdx, rdx
        div rcx
        add al, '0'
        mov [rdi], al
        mov rax, rdx
        mov rcx, 10
        xor rdx, rdx
        div rcx
        add al, '0'
        mov [rdi+1], al
        add dl, '0'
        mov [rdi+2], dl
        add rdi, 3
        ret

emit_db_to_buf:
        mov rax, '        '
        mov [rdi], rax
        mov word [rdi+8], 'db'
        mov byte [rdi+10], ' '
        add rdi, 11
        xor r14, r14
.bloop:
        cmp r14, data_len
        je .end
        test r14, r14
        jz .nosep
        mov word [rdi], ', '
        add rdi, 2
.nosep:
        movzx rax, byte [data + r14]
        call itoa_byte
        inc r14
        jmp .bloop
.end:
        mov byte [rdi], 10
        inc rdi
        ret

_start:
        mov rdi, outbuf
        xor r13, r13
.cloop:
        cmp r13, data_len
        je .write
        mov al, [data + r13]
        test al, al
        jz .esubst
        mov [rdi], al
        inc rdi
        inc r13
        jmp .cloop
.esubst:
        call emit_db_to_buf
        inc r13
        jmp .cloop
.write:
        mov rdx, rdi
        sub rdx, outbuf
        mov rsi, outbuf
        mov rax, 1
        mov rdi, 1
        syscall
        mov rax, 60
        xor rdi, rdi
        syscall
