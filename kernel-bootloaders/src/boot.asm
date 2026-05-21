; =============================================================================
;  PYRO OS - Stage 1 boot sector
;  -----------------------------------------------------------------------------
;  BIOS loads us at 0x0000:0x7C00. We set up a stack, then read STAGE2_SECTORS
;  sectors from the floppy (starting at LBA 1, i.e. the sector right after us)
;  into 0x0000:0x7E00 and jump there.
; =============================================================================

[BITS 16]
[ORG 0x7C00]

STAGE2_LOAD_SEG  equ 0x0000
STAGE2_LOAD_OFF  equ 0x7E00
STAGE2_SECTORS   equ 32              ; 16 KiB; way more than we need

start:
    cli
    xor     ax, ax
    mov     ds, ax
    mov     es, ax
    mov     ss, ax
    mov     sp, 0x7C00               ; stack grows down from where we live
    sti

    ; BIOS passes the boot drive number in DL - remember it.
    mov     [boot_drive], dl

    mov     si, msg_loading
    call    print

    ; INT 13h, AH=02h: read sectors into ES:BX.
    mov     ax, STAGE2_LOAD_SEG
    mov     es, ax
    mov     bx, STAGE2_LOAD_OFF

    mov     ah, 0x02
    mov     al, STAGE2_SECTORS
    mov     ch, 0                    ; cylinder 0
    mov     dh, 0                    ; head 0
    mov     cl, 2                    ; sector 2 (1-based; sector 1 is us)
    mov     dl, [boot_drive]
    int     0x13
    jc      disk_error

    ; Off to stage 2.
    jmp     STAGE2_LOAD_SEG:STAGE2_LOAD_OFF

; -----------------------------------------------------------------------------
; print: write null-terminated string DS:SI via BIOS teletype (int 10h / AH=0Eh)
; -----------------------------------------------------------------------------
print:
    pusha
.next:
    lodsb
    test    al, al
    jz      .done
    mov     ah, 0x0E
    mov     bh, 0
    mov     bl, 0x07
    int     0x10
    jmp     .next
.done:
    popa
    ret

disk_error:
    mov     si, msg_err
    call    print
.halt:
    cli
    hlt
    jmp     .halt

msg_loading: db "PYRO: loading stage 2...", 13, 10, 0
msg_err:     db "PYRO: disk read failed.", 13, 10, 0
boot_drive:  db 0

times 510-($-$$) db 0
dw 0xAA55
