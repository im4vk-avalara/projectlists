; ============================================================================
; mandfpu.asm — Stage 2 (naive): Mandelbrot set via x87 FPU, memory variables
; ============================================================================
; Build & run:
;     make run-mandfpu
;
; Goal of Stage 2: get a *correct, recognizable* Mandelbrot rendered. Not
; optimized. We will tighten in Stages 3–5.
;
; ----------------------------------------------------------------------------
; x87 FPU primer (for beginners):
; ----------------------------------------------------------------------------
; The x87 is a *stack machine* with 8 register slots: ST(0) (top) through
; ST(7). Almost every instruction reads / writes the top of the stack.
;
;   FLD  src       Push: pushes src (memory float or another ST reg) onto the
;                  stack. After FLD, the old ST(0) becomes ST(1), etc.
;   FSTP dst       Pop: store ST(0) into dst, then pop the stack.
;   FST  dst       Store ST(0) into dst (no pop — value stays on stack).
;   FLDZ           Push +0.0.
;   FADD/FSUB/FMUL/FDIV  with two operands: normal binary ops.
;     `fmul st0, st0`     ST(0) = ST(0) * ST(0)   (squaring)
;     `fmul dword [v]`    ST(0) *= *v             (mem operand)
;   FADDP/FSUBP/FMULP    `Op-and-pop`: ST(1) = ST(1) op ST(0), then pop.
;     Used to combine the top two stack values into one.
;   FCOMIP st(i)   Compare ST(0) to ST(i), set EFLAGS just like CMP, then
;                  pop ST(0). After this, JB/JA/JE work normally.
;
; Float constants live in memory as 32-bit IEEE-754 ("dword floats" / dd).
; NASM lets us write them in decimal: `dd -2.5` becomes 0xC0200000 at
; assemble time.
;
; ----------------------------------------------------------------------------
; Algorithm (the canonical escape-time Mandelbrot):
; ----------------------------------------------------------------------------
;   for (Y = 0; Y < 200; Y++):
;       ci = -1.0 + Y * (2.0 / 200)            -- map screen-Y → imag axis
;       for (X = 0; X < 320; X++):
;           cr = -2.5 + X * (3.5 / 320)        -- map screen-X → real axis
;           zr = zi = 0
;           for (k = ITERS; k > 0; k--):
;               if (zr² + zi² > 4) goto plot_escape
;               zi_new = 2 * zr * zi + ci
;               zr_new = zr² − zi² + cr
;               zr, zi = zr_new, zi_new
;           color = 0                           -- "inside the set" → black
;           goto plot
;       plot_escape: color = k                 -- early escape = bright
;       plot: VGA[Y*320+X] = color
;
; Coloring scheme: counter CX walks from ITERS down to 0. CX = 0 means the
; iteration loop ran to completion → point is in the Mandelbrot set → black.
; Any escape leaves CX > 0, so CX = brightness (early escape = bright color).
;
; ----------------------------------------------------------------------------
; Sizecoding techniques reused from earlier stages:
;   * MOV AL,0x13 instead of MOV AX,0x0013   (initial AX=0)
;   * PUSH 0xA000 / POP ES                   (stack-load segment)
;   * RET as program exit                    (PSP 0x0000 = INT 20h)
;   * LOOP for the iteration counter         (1-instr DEC CX + JNZ)
; New for this stage:
;   * FILD word [mem] / FMUL / FADD          (FPU does int→float coercion)
;   * FCOMIP st1 + JB                        (FPU compare → CPU flags)
; ============================================================================

BITS 16
ORG  0x100

%define ITERS 32                  ; iteration cap per pixel

start:
    ; ------------------------------------------------------------------
    ; Mode 13h, point ES at VGA, DI = 0
    ; ------------------------------------------------------------------
    mov  al, 0x13           ; AH already 0 on entry
    int  0x10
    push 0xA000
    pop  es
    xor  di, di

    ; ------------------------------------------------------------------
    ; Outer loop: Y = 0..199 in BX
    ; ------------------------------------------------------------------
    xor  bx, bx
.y_loop:
    ; ci = y_min + Y * y_step      (computed once per row)
    mov  [tmp], bx
    fild word [tmp]              ; ST = (float)Y
    fmul dword [y_step]          ; ST = Y * y_step
    fadd dword [y_min]           ; ST = y_min + Y*y_step
    fstp dword [c_imag]          ; store, pop

    ; --------------------------------------------------------------
    ; Inner loop: X = 0..319 in SI
    ; --------------------------------------------------------------
    xor  si, si
.x_loop:
    ; cr = x_min + X * x_step
    mov  [tmp], si
    fild word [tmp]
    fmul dword [x_step]
    fadd dword [x_min]
    fstp dword [c_real]

    ; zr = zi = 0   (one FLDZ + FST + FSTP writes 0 to both)
    fldz
    fst  dword [zr]
    fstp dword [zi]

    mov  cx, ITERS               ; iteration counter
.iter_loop:
    ; ----- escape check: zr² + zi² > 4 ? -----
    fld  dword [zr]              ; ST = zr
    fmul st0, st0                ; ST = zr²
    fld  dword [zi]              ; ST = zi, ST(1) = zr²
    fmul st0, st0                ; ST = zi², ST(1) = zr²
    faddp                        ; ST = zr²+zi² = |z|²   (one pop)
    fld  dword [four]            ; ST = 4, ST(1) = |z|²
    fcomip st1                   ; compare 4 vs |z|² ; pops ST = 4
    ; CF=1 iff 4 < |z|²   (i.e., escape)
    fstp st0                     ; discard |z|² (FSTP doesn't touch CF)
    jb   .escape                 ; jump if CF=1  → escape happened

    ; ----- zi_new = 2*zr*zi + ci -----
    fld  dword [zr]
    fmul dword [zi]              ; ST = zr*zi
    fadd st0, st0                ; ST = 2*zr*zi  (cheaper than `fmul two`)
    fadd dword [c_imag]          ; ST = 2*zr*zi + ci
    fstp dword [zi_new]          ; save temporarily

    ; ----- zr_new = zr² - zi² + cr -----
    fld  dword [zr]
    fmul st0, st0                ; ST = zr²
    fld  dword [zi]
    fmul st0, st0                ; ST = zi², ST(1)=zr²
    fsubp                        ; ST = zr² - zi²
    fadd dword [c_real]          ; ST = zr² - zi² + cr
    fstp dword [zr]              ; commit new zr

    ; ----- zi = zi_new -----
    fld  dword [zi_new]
    fstp dword [zi]

    loop .iter_loop              ; CX--; if non-zero, iterate

    ; Fell through → never escaped → "inside the set" → color 0 (black)
    xor  al, al
    jmp  .plot
.escape:
    ; CX holds (ITERS - k) where k = iterations before escape
    ; Larger CX = escaped sooner = brighter color
    mov  al, cl
.plot:
    mov  [es:di], al             ; write pixel
    inc  di                       ; advance framebuffer ptr

    inc  si
    cmp  si, 320
    jb   .x_loop

    inc  bx
    cmp  bx, 200
    jb   .y_loop

    ; ------------------------------------------------------------------
    ; Wait for keypress, restore text mode, return
    ; ------------------------------------------------------------------
    xor  ah, ah
    int  0x16
    mov  ax, 0x0003
    int  0x10
    ret

; ============================================================================
; Data — placed after code so labels resolve. All variables 32-bit floats
; except `tmp` which is a scratch word for the FILD int→float dance.
; ============================================================================
align 2
tmp:     dw 0
x_min:   dd -2.5
x_step:  dd 0.0109375        ; 3.5 / 320.0  (width / pixel)
y_min:   dd -1.0
y_step:  dd 0.01              ; 2.0 / 200.0  (height / pixel)
four:    dd 4.0
zr:      dd 0.0
zi:      dd 0.0
zi_new:  dd 0.0
c_real:  dd 0.0
c_imag:  dd 0.0
