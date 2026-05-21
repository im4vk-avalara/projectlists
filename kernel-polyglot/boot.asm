; ============================================================================
; kernel-polyglot — Stage 2: Animated rainbow MBR
; ----------------------------------------------------------------------------
; A 512-byte MBR that:
;   1. Clears the VGA text-mode screen (80x25, segment 0xB800).
;   2. Draws "* kernel-polyglot - Stage 2 *" centred on row 12.
;   3. Continuously animates the *attribute* byte of every cell so a
;      background-colour wave sweeps across the entire screen.
;      Foreground is forced to white, so the banner stays readable
;      through every colour of the cycle.
;
; All hot-path visual output goes through direct memory writes to the VGA
; text buffer at 0xB8000 — INT 10h is not used. INT 15h AH=86h gives us
; per-frame pacing (~33 fps).
;
; Comment convention:  ; OPCODE  (N)  — purpose
;   where N is the byte count for the sizecoding budget.
; ============================================================================

bits 16                  ; real-mode 16-bit instruction encoding
org  0x7C00              ; BIOS loads sector 0 at linear 0x0000:7C00

; ---------------------------------------------------------------------------
; Segment + stack setup
; ---------------------------------------------------------------------------
start:
    cli                  ; FA       (1) — IRQs off across SS/SP write
    xor   ax, ax         ; 31 C0    (2)
    mov   ds, ax         ; 8E D8    (2) — DS=0 so `lodsb` reads banner at
                         ;                linear 0x7C0xx
    mov   ss, ax         ; 8E D0    (2)
    mov   sp, 0x7C00     ; BC 00 7C (3) — stack grows down from 0x7C00
                         ;                (below our code, safe)
    sti                  ; FB       (1)

    mov   ax, 0xB800     ; B8 00 B8 (3) — VGA text framebuffer segment
    mov   es, ax         ; 8E C0    (2) — ES=0xB800 (stosw/stosb target)

; ---------------------------------------------------------------------------
; Step 1 — clear screen: 2000 cells of (' ', attr=0x0F)
; rep stosw is the canonical fastest fill — 2 bytes of instruction, copies
; AX into ES:DI[CX times], post-incrementing DI by 2 and decrementing CX.
; ---------------------------------------------------------------------------
    mov   ax, 0x0F20     ; B8 20 0F (3) — AH=0x0F (white/black), AL=0x20 (' ')
    mov   cx, 80*25      ; B9 D0 07 (3) — 2000 cells
    xor   di, di         ; 31 FF    (2) — start of framebuffer (ES:0000)
    rep   stosw          ; F3 AB    (2) — fill

; ---------------------------------------------------------------------------
; Step 2 — draw the static banner at row 12, col 25
; Offset within ES = (row * 80 + col) * 2  =  (12*80 + 25) * 2  =  1970 (0x7B2)
; ---------------------------------------------------------------------------
    mov   si, banner     ; BE xx xx (3) — DS:SI -> banner string
    mov   di, (12*80+25)*2  ; BF B2 07 (3) — ES:DI -> first banner cell
    mov   ah, 0x0F       ; B4 0F    (2) — banner attr: white on black
.draw_loop:
    lodsb                ; AC       (1) — AL := DS:[SI]; SI++
    test  al, al         ; 84 C0    (2) — NUL terminator?
    jz    .anim_init     ; 74 ??    (2) — done drawing banner
    stosw                ; AB       (1) — write (AL=char, AH=attr); DI+=2
    jmp   .draw_loop     ; EB ??    (2)

; ---------------------------------------------------------------------------
; Step 3 — animation
; Each frame, walk every attribute byte (1, 3, 5, ..., 3999) and set
;   attr = 0x0F | ((offset + frame_counter) & 0x70)
; Foreground bits = 0x0F (white, banner always readable).
; Background bits = (offset+frame) mod 8, so the bg sweeps through the 8
; "non-blink" background colours.  Blink bit (0x80) is masked off.
; ---------------------------------------------------------------------------
.anim_init:
    xor   bp, bp         ; 31 ED    (2) — BP = frame counter (0 to start)

.frame:
    inc   bp             ; 45       (1) — next frame
    mov   di, 1          ; BF 01 00 (3) — first ATTRIBUTE byte (skip char @0)
    mov   cx, 80*25      ; B9 D0 07 (3) — 2000 cells

.cycle:
    mov   ax, di         ; 89 F8    (2) — AX = byte offset (odd: 1,3,5,...)
    add   ax, bp         ; 01 E8    (2) — animate with frame counter
    and   al, 0x70       ; 24 70    (2) — keep only background-colour bits
    or    al, 0x0F       ; 0C 0F    (2) — force white foreground
    stosb                ; AA       (1) — ES:[DI] := AL; DI++
    inc   di             ; 47       (1) — skip the character byte
    loop  .cycle         ; E2 ??    (2) — CX--; if CX != 0, jmp .cycle

    ; per-frame pause via BIOS — INT 15h AH=86h, CX:DX = µs to wait
    mov   ah, 0x86       ; B4 86    (2)
    xor   cx, cx         ; 31 C9    (2)
    mov   dx, 30000      ; BA 30 75 (3) — 30 ms ≈ 33 frames/sec
    int   0x15           ; CD 15    (2)

    jmp   .frame         ; EB ??    (2)

; ---------------------------------------------------------------------------
; Data — banner string (NUL-terminated). 30 bytes including the NUL.
; ---------------------------------------------------------------------------
banner: db "* kernel-polyglot - Stage 2 *", 0

; ---------------------------------------------------------------------------
; Pad to 510, then signature. Zero-pad is temporary: Stage 3 fills these
; bytes with ZIP structure, Stage 4 with PDF structure.
; ---------------------------------------------------------------------------
times 510 - ($-$$) db 0
dw    0xAA55             ; 55 AA at 0x1FE..0x1FF — boot signature
