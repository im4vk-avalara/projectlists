; ============================================================================
; mandq12.asm — Stage 4 (post-passes 2-4): Q4.12 Mandelbrot, register-resident
;                                          incremental cr/ci, countdown loops
; ============================================================================
; Build & run:
;     make run-mandq12
;
; Pipeline of optimizations applied to the Stage 3 baseline (202 B):
;
;   Pass 1: STOSB instead of mov/inc, merged in-set/escape paths,
;           CMP DH,4 instead of CMP DX,0x400.                      (-10 B)
;
;   Pass 2a: IMUL AX (squaring via implicit AX*AX) instead of
;            IMUL WORD [zr]/[zi] — 2 B vs 4 B encoding.            (-4 B)
;
;   Pass 2b: Reorder iter body so zi_new is written directly to
;            [zi] while old zi is still in memory (its last use
;            was the IMUL above). Eliminates the zi_new buffer.    (-8 B)
;
;   Pass 3:  Incremental cr/ci. The slow code path was per-pixel
;                cr = x_min + X · x_step    (mov-imul-add-mov ≈ 13 B)
;            Replaced with single
;                ADD WORD [c_real], imm8    (5 B per use)
;            Pre-decrement at row-start so the first ADD lands at
;            x_min. Same trick for ci.                             (-14 B)
;
;   Pass 4:  Countdown loops. MOV CX,200/DEC/JNZ replaces
;            XOR CX,CX/INC/CMP imm16/JB — drops the explicit CMP.  (-6 B)
;
;   Bonus:   Drop x_step / y_step data — the constants live inside
;            the ADD instructions now (sign-extended imm8 forms).  (-4 B)
;
; ----------------------------------------------------------------------------
; Q4.12 invariants (unchanged from before):
;
;     value:   stored / 4096        range:   [-8.0, +8.0)
;     1.0      0x1000               escape:  |z|² ≥ 4 (= 0x4000)
;    -2.5      0xD800               overflow guard: DH ≥ 4 after IMUL
;
; ----------------------------------------------------------------------------
; Register map (inside the inner iter loop):
;
;     AX        working / IMUL result low half
;     DX        IMUL result high half (also: overflow detect via DH)
;     CX        iteration countdown (32 → 0); also serves as color on exit
;     BX        Y-row countdown (200 → 0)
;     SI        X-column countdown (320 → 0)
;     DI        VGA framebuffer pointer (auto-advanced by STOSB)
;     ES        0xA000 (VGA segment)
;
; ============================================================================

BITS 16
ORG  0x100

%define ITERS    32
%define X_STEP   45             ; round(3.5/320 · 4096)
%define Y_STEP   41             ; round(2.0/200 · 4096)

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
    ; Pre-decrement c_imag by Y_STEP so the first ADD at the top of
    ; .y_loop lands exactly at y_min.
    ; ------------------------------------------------------------------
    mov  ax, [y_min]
    sub  ax, Y_STEP
    mov  [c_imag], ax

    mov  bx, 200                ; Y countdown
.y_loop:
    add  word [c_imag], Y_STEP

    ; Reset c_real for this row: same pre-decrement trick.
    mov  ax, [x_min]
    sub  ax, X_STEP
    mov  [c_real], ax

    mov  si, 320                ; X countdown
.x_loop:
    add  word [c_real], X_STEP

    ; ------------------------------------------------------------------
    ; Per-pixel state: zr = zi = 0
    ; ------------------------------------------------------------------
    xor  ax, ax
    mov  [zr], ax
    mov  [zi], ax

    mov  cx, ITERS
.iter_loop:
    ; ----- zr² with overflow guard -----
    mov  ax, [zr]
    imul ax                     ; DX:AX = AX·AX = zr·zr  (2 B form)
    cmp  dh, 4
    jae  .escape
    shrd ax, dx, 12
    mov  [zr_sq], ax

    ; ----- zi² with overflow guard -----
    mov  ax, [zi]
    imul ax
    cmp  dh, 4
    jae  .escape
    shrd ax, dx, 12
    mov  [zi_sq], ax

    ; ----- |z|² = zr_sq + zi_sq, unsigned compare against 4.0 -----
    add  ax, [zr_sq]
    cmp  ax, 0x4000
    jae  .escape

    ; ----- zi_new = 2·zr·zi + ci, written directly to [zi] -----
    ; (Order matters: zr is read from memory here, BEFORE zr_new is
    ;  written below. zi's last memory-read is the IMUL on this line.)
    mov  ax, [zr]
    imul word [zi]
    shrd ax, dx, 12
    add  ax, ax
    add  ax, [c_imag]
    mov  [zi], ax               ; clobbers old zi — no longer needed

    ; ----- zr_new = zr² − zi² + cr -----
    mov  ax, [zr_sq]
    sub  ax, [zi_sq]
    add  ax, [c_real]
    mov  [zr], ax

    loop .iter_loop
    ; Fall-through: CX=0 ⇒ "in set" ⇒ AL=0 (black). Escape branch arrives
    ; here too, with CX = remaining iteration count (brightness).
.escape:
    mov  al, cl
    stosb                       ; ES:[DI++] = AL

    dec  si
    jnz  .x_loop

    dec  bx
    jnz  .y_loop

    ; ------------------------------------------------------------------
    ; Wait for keypress, restore text mode, return to DOS
    ; ------------------------------------------------------------------
    xor  ah, ah
    int  0x16
    mov  ax, 0x0003
    int  0x10
    ret

; ============================================================================
; Data — Q4.12 origins only (steps are baked into the ADD imm8 instructions)
; ============================================================================
align 2
x_min:   dw -10240             ; -2.5 · 4096
y_min:   dw -4096              ; -1.0 · 4096
zr:      dw 0
zi:      dw 0
zr_sq:   dw 0
zi_sq:   dw 0
c_real:  dw 0
c_imag:  dw 0
