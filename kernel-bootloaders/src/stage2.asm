; =============================================================================
;  PYRO OS - Stage 2: VGA fire animation + tiny real-mode shell
;  -----------------------------------------------------------------------------
;  Loaded at 0x0000:0x7E00 by the stage-1 boot sector.
;
;  Boot flow:
;    1. Switch to VGA mode 13h (320x200, 256 colour palette).
;    2. Install a black -> red -> orange -> yellow -> white fire palette.
;    3. Each frame:
;         seed the bottom row with hot pixels, propagate the fire upward
;         (one row up, with a small horizontal wobble + 1-step decay),
;         stamp the "PYRO" logo at row 150 (becomes a secondary heat seed),
;         then sleep ~16 ms via int 15h / AH=86h.
;    4. After a keypress or ~600 frames, switch back to text mode and run a
;       minimal shell with: help / about / clear / fire / echo / reboot.
; =============================================================================

[BITS 16]
[ORG 0x7E00]

VGA_SEG     equ 0xA000
SCR_W       equ 320
SCR_H       equ 200
FIRE_PIXELS equ SCR_W * SCR_H        ; 64000
LOGO_ROW    equ 150                  ; y of the burning "PYRO" logo

; =============================================================================
;  Entry point
; =============================================================================
stage2_entry:
    ; Re-establish a clean segment state. Stack stays where stage 1 set it.
    xor     ax, ax
    mov     ds, ax
    mov     ss, ax
    mov     sp, 0x7C00

    ; --- VGA mode 13h ---
    mov     ax, 0x0013
    int     0x10

    ; ES = VGA framebuffer
    mov     ax, VGA_SEG
    mov     es, ax

    call    setup_palette

    ; Zero the framebuffer
    xor     di, di
    xor     ax, ax
    mov     cx, FIRE_PIXELS / 2
    rep     stosw

    mov     word [frame_count], 0

; --- Main fire loop ----------------------------------------------------------
fire_loop:
    call    seed_bottom
    call    propagate
    call    stamp_logo
    call    frame_delay

    inc     word [frame_count]

    ; Non-blocking keyboard poll: BIOS sets ZF=1 if no key waiting.
    mov     ah, 0x01
    int     0x16
    jnz     .key

    ; Auto-exit after ~600 frames (~10 s at ~60 Hz).
    cmp     word [frame_count], 600
    jb      fire_loop
    jmp     fire_done

.key:
    mov     ah, 0x00
    int     0x16                     ; consume the keystroke

fire_done:
    ; Back to text mode 80x25, then drop into the shell.
    mov     ax, 0x0003
    int     0x10
    jmp     shell


; =============================================================================
;  setup_palette - install a fire gradient into the VGA DAC
;     idx   0..63   : black -> dark red       (R rising, G=0, B=0)
;     idx  64..127  : dark red -> orange      (R=63, G rising, B=0)
;     idx 128..191  : orange  -> yellow/white (R=63, G=63, B rising)
;     idx 192..255  : white -> white          (all 63, capped)
; =============================================================================
setup_palette:
    pusha
    mov     dx, 0x03C8               ; DAC write index
    xor     al, al
    out     dx, al
    mov     dx, 0x03C9               ; DAC data

    xor     cx, cx                   ; CX = palette index 0..255
.next:
    ; --- R ---
    mov     ax, cx
    cmp     ax, 64
    jb      .r_ok
    mov     al, 63
.r_ok:
    out     dx, al

    ; --- G ---
    mov     ax, cx
    cmp     ax, 64
    jb      .g_zero
    cmp     ax, 128
    jb      .g_mid
    mov     al, 63
    jmp     .g_out
.g_zero:
    xor     al, al
    jmp     .g_out
.g_mid:
    sub     al, 64
.g_out:
    out     dx, al

    ; --- B ---
    mov     ax, cx
    cmp     ax, 128
    jb      .b_zero
    cmp     ax, 192
    jb      .b_mid
    mov     al, 63
    jmp     .b_out
.b_zero:
    xor     al, al
    jmp     .b_out
.b_mid:
    sub     al, 128
.b_out:
    out     dx, al

    inc     cx
    cmp     cx, 256
    jb      .next
    popa
    ret


; =============================================================================
;  seed_bottom - set the bottom row (y=199) to flickering hot values 192..255
; =============================================================================
seed_bottom:
    pusha
    mov     di, (SCR_H - 1) * SCR_W
    mov     cx, SCR_W
.next:
    call    rand8
    and     al, 0x3F                 ; 0..63
    add     al, 192                  ; 192..255
    stosb
    loop    .next
    popa
    ret


; =============================================================================
;  propagate - one frame of upward fire propagation.
;
;  For each pixel at offset DI (rows 0..198), read the source pixel one row
;  below ([DI + SCR_W + wobble]), decay by 1, store at DI. The wobble is a
;  cheap inline LCG: BX advances, low bits become a -1..+2 horizontal offset
;  on the source so the flames flicker sideways as they rise.
; =============================================================================
propagate:
    xor     di, di
    mov     cx, FIRE_PIXELS - SCR_W
    mov     bx, [rand_seed]          ; load the wobble state once per frame
.next:
    ; bx = bx * 25173 + 13849   (LCG step, inline)
    mov     ax, bx
    mov     dx, 25173
    mul     dx
    add     ax, 13849
    mov     bx, ax                   ; new state

    ; horizontal offset = (BX & 3) - 1  (so -1, 0, +1, or +2)
    mov     dx, bx
    and     dx, 3
    dec     dx

    ; source index = DI + SCR_W + DX
    mov     si, di
    add     si, SCR_W
    add     si, dx

    mov     al, [es:si]
    test    al, al
    jz      .write
    dec     al
.write:
    mov     [es:di], al

    inc     di
    loop    .next

    mov     [rand_seed], bx          ; save state for next frame
    ret


; =============================================================================
;  stamp_logo - imprint "PYRO" (4 letters, 8x8 source font, scaled 2x to
;  16x16 each = 64x16 total) at row LOGO_ROW, centered horizontally on x=128.
;  Lit pixels are written as colour 255 (max heat). Unlit pixels are skipped
;  so the surrounding fire shows through.
; =============================================================================
stamp_logo:
    pusha

    mov     bp, logo_bitmap          ; BP walks through 32 bytes of bitmap

    xor     bx, bx                   ; BX = letter index 0..3
.letter:
    mov     cx, 8                    ; 8 rows of bitmap per letter
    xor     dx, dx                   ; DX = bitmap-row index 0..7
.row:
    push    cx
    push    dx

    ; --- Compute framebuffer offset FIRST (clobbers AX, DX) ---
    ; screen_y = LOGO_ROW + dx*2
    mov     cx, dx
    shl     cx, 1
    add     cx, LOGO_ROW

    ; framebuffer offset = screen_y * SCR_W + x_start
    ; where x_start = 128 + letter*16
    mov     ax, cx
    mov     si, SCR_W
    mul     si                       ; DX:AX = screen_y * SCR_W

    mov     si, bx
    shl     si, 4                    ; letter*16
    add     si, 128
    add     ax, si
    mov     di, ax                   ; DI = byte offset into VGA segment

    ; --- NOW load the bitmap byte into DH (DX is already saved) ---
    mov     al, [bp]
    inc     bp
    mov     dh, al                   ; DH = 8-bit row pattern

    ; Draw 8 bits, MSB first; each lit bit becomes a 2x2 block.
    mov     cx, 8
.bit:
    test    dh, 0x80
    jz      .skip
    mov     byte [es:di],             255
    mov     byte [es:di + 1],         255
    mov     byte [es:di + SCR_W],     255
    mov     byte [es:di + SCR_W + 1], 255
.skip:
    shl     dh, 1
    add     di, 2
    loop    .bit

    pop     dx
    pop     cx
    inc     dx
    loop    .row

    inc     bx
    cmp     bx, 4
    jb      .letter

    popa
    ret


; =============================================================================
;  frame_delay - sleep ~16 ms via BIOS int 15h, AH=86h. CX:DX = microseconds.
; =============================================================================
frame_delay:
    push    ax
    push    cx
    push    dx
    mov     ah, 0x86
    xor     cx, cx
    mov     dx, 16667
    int     0x15
    pop     dx
    pop     cx
    pop     ax
    ret


; =============================================================================
;  rand8 - LCG returning a pseudo-random 16-bit value in AX
;          (caller can use AL or AH).
; =============================================================================
rand8:
    push    bx
    push    dx
    mov     ax, [rand_seed]
    mov     bx, 25173
    mul     bx                       ; DX:AX = AX * 25173
    add     ax, 13849
    mov     [rand_seed], ax
    pop     dx
    pop     bx
    ret


; =============================================================================
;  SHELL - tiny real-mode REPL using BIOS int 16h (keyboard) + int 10h (video)
; =============================================================================
shell:
    xor     ax, ax
    mov     ds, ax
    mov     es, ax
    call    cls

    mov     si, banner
    call    puts

.prompt:
    mov     si, prompt_str
    call    puts

    mov     di, input_buffer
    call    readline

    call    execute_cmd
    jmp     .prompt


; --- Re-enter fire effect from the shell --------------------------------------
fire_relaunch:
    mov     ax, 0x0013
    int     0x10
    mov     ax, VGA_SEG
    mov     es, ax
    call    setup_palette

    xor     di, di
    xor     ax, ax
    mov     cx, FIRE_PIXELS / 2
    rep     stosw

    mov     word [frame_count], 0
    jmp     fire_loop


; =============================================================================
;  cls - clear text-mode screen and reset cursor to (0,0)
; =============================================================================
cls:
    pusha
    mov     ax, 0x0600               ; scroll up entire window (AL=0 clears)
    mov     bh, 0x07                 ; light grey on black
    xor     cx, cx                   ; (0,0)
    mov     dx, 0x184F               ; (24,79)
    int     0x10
    mov     ah, 0x02                 ; set cursor pos
    xor     bh, bh
    xor     dx, dx
    int     0x10
    popa
    ret


; =============================================================================
;  puts - print null-terminated DS:SI; LF is translated to CRLF on the fly
; =============================================================================
puts:
    pusha
.next:
    lodsb
    test    al, al
    jz      .done
    cmp     al, 10
    jne     .write
    mov     ah, 0x0E                 ; emit CR before LF
    mov     al, 13
    mov     bh, 0
    int     0x10
    mov     al, 10
.write:
    mov     ah, 0x0E
    mov     bh, 0
    mov     bl, 0x07
    int     0x10
    jmp     .next
.done:
    popa
    ret


; --- Print single AL char -----------------------------------------------------
putchar:
    pusha
    mov     ah, 0x0E
    mov     bh, 0
    mov     bl, 0x07
    int     0x10
    popa
    ret


; =============================================================================
;  readline - read a line of input (max 63 chars) into ES:DI, null-terminated.
;  Echoes characters; handles backspace and Enter.
; =============================================================================
readline:
    pusha
    mov     bx, di                   ; remember start
.loop:
    mov     ah, 0x00                 ; blocking keyboard read
    int     0x16

    cmp     al, 13                   ; Enter
    je      .done
    cmp     al, 8                    ; Backspace
    je      .backspace
    cmp     al, 32                   ; non-printable below space
    jb      .loop
    cmp     al, 126
    ja      .loop

    ; bounds check: 63 chars max
    mov     cx, di
    sub     cx, bx
    cmp     cx, 63
    jae     .loop

    stosb
    call    putchar
    jmp     .loop

.backspace:
    cmp     di, bx
    jbe     .loop                    ; nothing to erase
    dec     di
    mov     al, 8
    call    putchar
    mov     al, ' '
    call    putchar
    mov     al, 8
    call    putchar
    jmp     .loop

.done:
    xor     al, al
    stosb
    mov     al, 13
    call    putchar
    mov     al, 10
    call    putchar
    popa
    ret


; =============================================================================
;  execute_cmd - dispatch the command currently in input_buffer
; =============================================================================
execute_cmd:
    pusha
    mov     si, input_buffer
    call    skip_spaces

    cmp     byte [si], 0
    je      .done                    ; empty input

    push    si
    mov     di, cmd_help
    call    streq
    pop     si
    je      .do_help

    push    si
    mov     di, cmd_about
    call    streq
    pop     si
    je      .do_about

    push    si
    mov     di, cmd_clear
    call    streq
    pop     si
    je      .do_clear

    push    si
    mov     di, cmd_cls
    call    streq
    pop     si
    je      .do_clear

    push    si
    mov     di, cmd_fire
    call    streq
    pop     si
    je      .do_fire

    push    si
    mov     di, cmd_reboot
    call    streq
    pop     si
    je      .do_reboot

    push    si
    mov     di, cmd_echo
    call    streq_prefix
    pop     si
    je      .do_echo

    mov     si, msg_unknown
    call    puts
    jmp     .done

.do_help:
    mov     si, msg_help
    call    puts
    jmp     .done

.do_about:
    mov     si, msg_about
    call    puts
    jmp     .done

.do_clear:
    call    cls
    jmp     .done

.do_fire:
    popa                             ; we won't return; clean the stack
    jmp     fire_relaunch

.do_echo:
    add     si, 4                    ; skip "echo"
    cmp     byte [si], ' '
    jne     .echo_print
    inc     si
.echo_print:
    call    puts
    mov     al, 13
    call    putchar
    mov     al, 10
    call    putchar
    jmp     .done

.do_reboot:
    jmp     0xFFFF:0x0000            ; BIOS cold-boot vector

.done:
    popa
    ret


; --- skip_spaces: advance DS:SI past any spaces -------------------------------
skip_spaces:
    cmp     byte [si], ' '
    jne     .done
    inc     si
    jmp     skip_spaces
.done:
    ret


; =============================================================================
;  streq - compare null-terminated strings at DS:SI and DS:DI.
;          Returns ZF=1 if equal, ZF=0 otherwise. Clobbers AL, BL.
; =============================================================================
streq:
    push    si
    push    di
.loop:
    mov     al, [si]
    mov     bl, [di]
    cmp     al, bl
    jne     .neq
    test    al, al
    jz      .eq
    inc     si
    inc     di
    jmp     .loop
.eq:
    pop     di
    pop     si
    xor     al, al                   ; ZF=1
    ret
.neq:
    pop     di
    pop     si
    or      al, 1                    ; ZF=0
    ret


; =============================================================================
;  streq_prefix - returns ZF=1 if DS:SI starts with the null-terminated
;                 prefix at DS:DI. Clobbers AL, BL.
; =============================================================================
streq_prefix:
    push    si
    push    di
.loop:
    mov     al, [di]
    test    al, al
    jz      .match
    mov     bl, [si]
    cmp     al, bl
    jne     .nomatch
    inc     si
    inc     di
    jmp     .loop
.match:
    pop     di
    pop     si
    xor     al, al
    ret
.nomatch:
    pop     di
    pop     si
    or      al, 1
    ret


; =============================================================================
;  Read-only data
; =============================================================================
rand_seed:   dw 0xACE1
frame_count: dw 0

; "PYRO" font - 8 bytes per letter, 8 rows of 8 bits each (1 = lit).
logo_bitmap:
    ; P
    db 11111100b
    db 11000110b
    db 11000110b
    db 11111100b
    db 11000000b
    db 11000000b
    db 11000000b
    db 00000000b
    ; Y
    db 11000011b
    db 11000011b
    db 01100110b
    db 00111100b
    db 00011000b
    db 00011000b
    db 00011000b
    db 00000000b
    ; R
    db 11111100b
    db 11000110b
    db 11000110b
    db 11111100b
    db 11011000b
    db 11001100b
    db 11000110b
    db 00000000b
    ; O
    db 01111100b
    db 11000110b
    db 11000110b
    db 11000110b
    db 11000110b
    db 11000110b
    db 01111100b
    db 00000000b

cmd_help:    db "help", 0
cmd_about:   db "about", 0
cmd_clear:   db "clear", 0
cmd_cls:     db "cls", 0
cmd_fire:    db "fire", 0
cmd_reboot:  db "reboot", 0
cmd_echo:    db "echo", 0

prompt_str:  db "pyro> ", 0

banner:
    db 13, 10
    db "  ____  __     __  _____    ____  ", 13, 10
    db " |  _ \\ \\ \\   / / |  __ \\  / __ \\ ", 13, 10
    db " | |_) | \\ \\_/ /  | |__) || |  | |", 13, 10
    db " |  __/   \\   /   |  _  / | |  | |", 13, 10
    db " | |       | |    | | \\ \\ | |__| |", 13, 10
    db " |_|       |_|    |_|  \\_\\ \\____/ ", 13, 10
    db 13, 10
    db " PYRO OS  v0.1  -  real-mode boot demo", 13, 10
    db " Type 'help' for commands.", 13, 10
    db 13, 10, 0

msg_help:
    db "Commands:", 13, 10
    db "  help        - this list", 13, 10
    db "  about       - what is this?", 13, 10
    db "  clear / cls - clear the screen", 13, 10
    db "  fire        - replay the boot animation", 13, 10
    db "  echo TEXT   - print TEXT", 13, 10
    db "  reboot      - restart the machine", 13, 10, 0

msg_about:
    db "PYRO OS - a tiny x86 real-mode demo.", 13, 10
    db "Stage-1 boot sector loads a stage-2 'kernel' that renders the", 13, 10
    db "classic DOOM fire effect in VGA mode 13h, then drops to this shell.", 13, 10
    db "Written entirely in NASM, ~3 KB of code. Boots on QEMU or any PC BIOS.", 13, 10, 0

msg_unknown:
    db "Unknown command. Type 'help'.", 13, 10, 0

input_buffer: times 80 db 0

; Pad stage 2 out to a sector boundary so the floppy image dd's cleanly.
times (512 * 32) - ($-$$) db 0
