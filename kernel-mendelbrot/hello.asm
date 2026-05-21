; ============================================================================
; hello.asm — smallest "Hi" DOS .COM file
; ============================================================================
; Build & run:
;     make run-hello
;
; Expected output: prints "Hi" then returns to DOS prompt.
; ============================================================================
;
; .COM file primer (for beginners):
; ---------------------------------
; A .COM file is a flat 16-bit real-mode DOS executable. No header, no
; relocation table — DOS just loads the file bytes into memory starting at
; offset 0x100 of a fresh segment, sets CS=DS=ES=SS to that segment, points
; SP to the top of the segment, then jumps to CS:0100.
;
; That is why we use `ORG 0x100`: NASM needs to know the runtime address of
; the first byte so it can compute correct absolute addresses for labels.
;
; On .COM entry, several useful invariants hold (we'll exploit these later
; for byte savings):
;   - CS = DS = ES = SS (one segment, "tiny" memory model)
;   - IP  = 0x0100      (entry point)
;   - SP  = 0xFFFE      (stack at top, grows down)
;   - AX  = 0x0000      (drive validity flags, effectively zero for our use)
;   - CX  = 0x00FF
;   - DX  = CS
;   - SI  = 0x0100
;   - DI  = 0xFFFE
;   - BP  = 0x091C      (varies; not reliable across DOS versions)
;
; Calling DOS:
; ------------
; Software interrupt 0x21 is the DOS API. AH selects the function:
;   AH=09h  Print $-terminated string at DS:DX
;   AH=4Ch  Terminate process; AL = exit code
;
; ============================================================================

BITS 16              ; emit 16-bit instructions
ORG  0x100           ; .COM load address

start:
    mov  ah, 0x09    ; 2 bytes (B4 09)    DOS: print $-terminated string
    mov  dx, msg     ; 3 bytes (BA xx xx) DS:DX -> message (DS already = CS)
    int  0x21        ; 2 bytes (CD 21)    invoke DOS

    mov  ah, 0x4C    ; 2 bytes (B4 4C)    DOS: terminate
    int  0x21        ; 2 bytes (CD 21)    AL still 0 -> exit code 0

msg: db 'Hi', 0x0D, 0x0A, '$'  ; 5 bytes  text + CR + LF + DOS terminator

; ---------------------------------------------------------------------------
; Expected total size: 16 bytes
;   instructions:  2 + 3 + 2 + 2 + 2 = 11
;   data:                              5
;   total:                            16
; We'll confirm with `ls -l HELLO.COM` after assembling.
; ---------------------------------------------------------------------------
