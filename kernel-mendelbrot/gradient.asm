; ============================================================================
; gradient.asm — Stage 1: VGA mode 13h initialization + gradient fill
; ============================================================================
; Build & run:
;     make run-gradient
;
; What it does:
;   1. Switch the display to mode 13h (320x200, 256 colors, linear 8bpp at A000:0).
;   2. Fill the entire framebuffer (64000 bytes — yes, 64000, not 65536; mode 13h
;      addresses 320*200 = 64000 visible pixels) with an incrementing color byte.
;   3. Wait for a key press so the picture doesn't vanish instantly.
;   4. Restore text mode (mode 03h).
;   5. Return to DOS cleanly via RET.
;
; Visual result: smooth diagonal "barber-pole" gradient across the screen,
;                colors cycling 0..255 every 256 pixels (= every 256 byte
;                offsets in the framebuffer). VGA's default palette goes from
;                black through blues, greens, browns, grays — you'll see
;                horizontal-ish bands that drift downward.
;
; This is NOT a Mandelbrot yet — its only job is to prove our VGA pipeline:
;   * Mode-switch works (INT 10h, BIOS video services)
;   * Direct A000-segment writes light up pixels
;   * Keyboard wait works (INT 16h)
;   * Mode-restore + clean DOS exit works
;
; ----------------------------------------------------------------------------
; Sizecoding notes (techniques used and *why* they save bytes):
; ----------------------------------------------------------------------------
;
; * "MOV AL,0x13" instead of "MOV AX,0x0013".
;   - .COM entry sets AX=0, so AH is already 0; we only need to load AL.
;   - 2 bytes (B0 13) vs 3 bytes (B8 13 00). Saves 1 byte.
;   - Sizecoding trick: "exploit initial register state."
;
; * "PUSH 0xA000 / POP ES" instead of "MOV AX,0xA000 / MOV ES,AX".
;   - There is no MOV ES,imm16 instruction in x86 — you must go through a GPR.
;   - The mov-via-AX path is 5 bytes (B8 00 A0 8E C0).
;   - PUSH imm16 + POP ES is 3 + 1 = 4 bytes (68 00 A0 07). Saves 1 byte.
;   - Sizecoding trick: "stack abuse for segment loads."
;
; * "INC AX" (1-byte opcode 0x40) inside the fill loop instead of "INC AL"
;   (2 bytes: FE C0). STOSB only consumes AL, so we don't care that AH walks
;   too. Saves 1 byte per use.
;
; * Implicit "STOSB" (1 byte AA) — writes [ES:DI] = AL and increments DI.
;   Replaces explicit MOV/INC patterns; classic sizecoding workhorse.
;
; * "LOOP .fill" (2 bytes E2 disp8) — combined "DEC CX + JNZ short" in one
;   instruction. Faithful to CX as a counter; saves 2 bytes vs the manual
;   "DEC CX / JNZ" pair.
;
; * "RET" as program exit (1 byte C3). When a .COM is launched, DOS sets up
;   the stack so the top word is 0x0000. RET pops that 0 into IP, jumping
;   to CS:0000 which holds an INT 20h instruction (the program-terminate
;   service, written there by DOS as part of the PSP). Saves bytes vs the
;   explicit "MOV AH,0x4C / INT 21h" exit (4 bytes).
;
; ============================================================================

BITS 16
ORG  0x100

start:
    ; ------------------------------------------------------------------
    ; 1. Set video mode 13h (320x200, 256-color, linear)
    ; ------------------------------------------------------------------
    ; INT 10h with AH=0 selects "Set Video Mode". AL = mode number.
    ; Mode 13h is the canonical "fast 256-color graphics" mode.
    ; AX=0 on .COM entry → AH already 0 → only need to set AL.
    mov  al, 0x13       ; 2 bytes (B0 13)    AL = 13h (graphics mode)
    int  0x10           ; 2 bytes (CD 10)    BIOS video service

    ; ------------------------------------------------------------------
    ; 2. Point ES at VGA framebuffer (segment 0xA000)
    ; ------------------------------------------------------------------
    ; ES:DI is the destination for STOSB. The framebuffer lives at
    ; physical address 0xA0000 = segment 0xA000, offset 0.
    push word 0xA000    ; 3 bytes (68 00 A0)
    pop  es             ; 1 byte  (07)
    xor  di, di         ; 2 bytes (31 FF)    DI = 0 (start of framebuffer)

    ; ------------------------------------------------------------------
    ; 3. Fill 64000 bytes with an incrementing AL
    ; ------------------------------------------------------------------
    ; CX = 64000 = 0xFA00 = number of visible pixels in mode 13h.
    ; AL starts arbitrary (BIOS clobbered it), so we zero it for a clean
    ; gradient start. Each iteration: write AL, AL++, decrement CX, loop.
    mov  cx, 64000      ; 3 bytes (B9 00 FA)
    xor  al, al         ; 2 bytes (30 C0)    AL = 0 (gradient start color)
.fill:
    stosb               ; 1 byte  (AA)       [ES:DI++] = AL
    inc  ax             ; 1 byte  (40)       AL++ (AH may roll, we don't care)
    loop .fill          ; 2 bytes (E2 FC)    --CX; if non-zero, jump back

    ; ------------------------------------------------------------------
    ; 4. Wait for a key press so the gradient stays on screen
    ; ------------------------------------------------------------------
    ; INT 16h with AH=0 = "Read keystroke" — blocks until a key is pressed.
    xor  ah, ah         ; 2 bytes (30 E4)    AH = 0
    int  0x16           ; 2 bytes (CD 16)    BIOS keyboard wait

    ; ------------------------------------------------------------------
    ; 5. Restore text mode (mode 03h = 80x25 color text)
    ; ------------------------------------------------------------------
    ; Need AX = 0x0003 (AH=0 "Set Mode", AL=3 "text mode"). AH is non-zero
    ; from prior calls, so we load the full word here.
    mov  ax, 0x0003     ; 3 bytes (B8 03 00)
    int  0x10           ; 2 bytes (CD 10)

    ; ------------------------------------------------------------------
    ; 6. Exit to DOS via RET (see Sizecoding notes above for why this works)
    ; ------------------------------------------------------------------
    ret                 ; 1 byte  (C3)

; ============================================================================
; Predicted total: 29 bytes
;   2+2 +3+1+2 +3+2+1+1+2 +2+2 +3+2 +1 = 29
; ============================================================================
