; ============================================================================
; mandfix.asm — Stage 2 (naive): Mandelbrot via 32-bit Q16.16 fixed-point
; ============================================================================
; Build & run:
;     make run-mandfix
;
; Companion to mandfpu.asm. Same algorithm, same region, same output —
; but math is done in 32-bit integer fixed-point instead of x87 floats.
;
; ----------------------------------------------------------------------------
; Why "32-bit instructions in 16-bit real mode" is OK:
; ----------------------------------------------------------------------------
; Real mode means CS:IP segmented addressing and 1MB address space; it does
; NOT mean "no 32-bit registers." The 80386 introduced 32-bit register and
; operand-size variants that are usable in real mode via the 0x66 prefix
; byte. NASM inserts that byte automatically whenever you write `eax`,
; `dword`, etc. inside a BITS 16 program.
;
; The catch: each 32-bit instruction is 1 byte longer than its 16-bit
; equivalent (the 0x66 prefix). That's the byte-cost trade-off we're
; making to gain larger numeric range.
;
; ----------------------------------------------------------------------------
; Q16.16 fixed-point primer:
; ----------------------------------------------------------------------------
; A Q16.16 value is a 32-bit signed integer whose lower 16 bits are the
; fractional part. Conceptually: real_value = stored_int / 65536.
;
;   1.0   → 0x00010000
;   2.5   → 0x00028000
;   -2.5  → 0xFFFD8000   (two's complement)
;   4.0   → 0x00040000
;
; Range:  [-32768.0, +32768.0)   — way more than Mandelbrot needs
; Precision: 1/65536 ≈ 1.5×10⁻⁵ — much finer than 320×200 pixel grid
;
; Arithmetic rules:
;   ADD/SUB:  Q16.16 ± Q16.16 = Q16.16       — plain ADD/SUB, no rescaling
;   MUL:      Q16.16 × Q16.16 = Q32.32       — 64-bit intermediate!
;             To get back to Q16.16, shift right by 16.
;             On x86: IMUL (one-operand) gives EDX:EAX = EAX × operand
;             as a *signed* 64-bit result. SHRD EAX, EDX, 16 combines the
;             two halves into the middle 32 bits = our Q16.16 result.
;
;   INT→Q16.16: shift left by 16 (or multiply by 65536). E.g., screen-Y in
;               EAX → SHL EAX, 16 makes it Q16.16 with zero fraction.
;
; ----------------------------------------------------------------------------
; Sizecoding notes:
;   * Every 32-bit instruction costs +1 byte (the 0x66 prefix). Worth it
;     here for clarity at Stage 2. We'll narrow to 16-bit Q4.12 in Stage 3.
;   * `MOV EAX, [moffs32]` (opcode A1) and `MOV [moffs32], EAX` (opcode A3)
;     are the shortest 32-bit load/store forms — 4 bytes each in our case.
;     Other registers cost 5 bytes (mod-r/m form), so we route all loads
;     through EAX.
;   * `IMUL dword [mem]` (one-operand form) — signed multiply, full 64-bit
;     result in EDX:EAX. Followed by SHRD to scale back to Q16.16.
; ============================================================================

BITS 16
ORG  0x100

%define ITERS    32
%define ESCAPE_Q 0x00040000      ; 4.0 in Q16.16

start:
    ; ------------------------------------------------------------------
    ; Mode 13h, ES = VGA, DI = 0
    ; ------------------------------------------------------------------
    mov  al, 0x13
    int  0x10
    push 0xA000
    pop  es
    xor  di, di

    ; ------------------------------------------------------------------
    ; Outer loop: Y = 0..199 in BX
    ; ------------------------------------------------------------------
    xor  bx, bx
.y_loop:
    ; ci = y_min + Y * y_step    (Q16.16; Y is Q0 — just multiply directly)
    movzx eax, bx                ; EAX = Y (zero-extend; Y is small + positive)
    imul eax, [y_step]           ; EAX = Y * y_step    (32-bit truncated; safe)
    add  eax, [y_min]            ; + y_min
    mov  [c_imag], eax

    ; --------------------------------------------------------------
    ; Inner loop: X = 0..319 in SI
    ; --------------------------------------------------------------
    xor  si, si
.x_loop:
    ; cr = x_min + X * x_step
    movzx eax, si
    imul eax, [x_step]
    add  eax, [x_min]
    mov  [c_real], eax

    ; zr = zi = 0
    xor  eax, eax
    mov  [zr], eax
    mov  [zi], eax

    mov  cx, ITERS
.iter_loop:
    ; ----- zr_sq = zr*zr  (Q16.16) -----
    mov  eax, [zr]
    imul dword [zr]              ; EDX:EAX = zr*zr   (signed 64-bit)
    shrd eax, edx, 16            ; EAX = Q16.16 result
    mov  [zr_sq], eax

    ; ----- zi_sq = zi*zi -----
    mov  eax, [zi]
    imul dword [zi]
    shrd eax, edx, 16
    mov  [zi_sq], eax

    ; ----- escape: zr² + zi² > 4 ? -----
    add  eax, [zr_sq]            ; EAX = |z|² = zi_sq + zr_sq
    cmp  eax, ESCAPE_Q
    jge  .escape

    ; ----- zi_new = 2 * zr * zi + ci -----
    mov  eax, [zr]
    imul dword [zi]
    shrd eax, edx, 16            ; EAX = zr*zi  (Q16.16)
    add  eax, eax                 ; * 2
    add  eax, [c_imag]
    mov  [zi_new], eax

    ; ----- zr_new = zr² - zi² + cr -----
    mov  eax, [zr_sq]
    sub  eax, [zi_sq]
    add  eax, [c_real]
    mov  [zr], eax

    ; ----- zi ← zi_new -----
    mov  eax, [zi_new]
    mov  [zi], eax

    loop .iter_loop

    ; Fell through → in the set → black
    xor  al, al
    jmp  .plot
.escape:
    mov  al, cl
.plot:
    mov  [es:di], al
    inc  di

    inc  si
    cmp  si, 320
    jb   .x_loop

    inc  bx
    cmp  bx, 200
    jb   .y_loop

    xor  ah, ah
    int  0x16
    mov  ax, 0x0003
    int  0x10
    ret

; ============================================================================
; Data — Q16.16 fixed-point constants
;
;   value           Q16.16 (decimal)    Q16.16 (hex)
;   -2.5            -163840             0xFFFD8000
;   3.5 / 320       ≈ 716               0x000002CC
;   -1.0            -65536              0xFFFF0000
;   2.0 / 200       ≈ 655               0x0000028F
; ============================================================================
align 4
x_min:   dd -163840         ; -2.5
x_step:  dd 717             ; round(3.5/320 * 65536) = round(716.8)
y_min:   dd -65536          ; -1.0
y_step:  dd 655             ; round(2.0/200 * 65536) = round(655.36)
zr:      dd 0
zi:      dd 0
zr_sq:   dd 0
zi_sq:   dd 0
zi_new:  dd 0
c_real:  dd 0
c_imag:  dd 0
