.code16
.global _start

.set KERNEL_LOAD_SEGMENT, 0x1000
.set KERNEL_LOAD_OFFSET,  0x0000
.set KERNEL_ENTRY,        0x10000
.set KERNEL_SECTORS,      128

.set E820_COUNT_ADDR,   0x8000      # u32 entry count (kernel reads these)
.set E820_ENTRIES_ADDR, 0x8004      # 24-byte entries follow
.set E820_MAX_ENTRIES,  32
.set E820_MAGIC,        0x534D4150  # 'SMAP'

_start:
    cli

    xor %ax, %ax
    mov %ax, %ds
    mov %ax, %es
    mov %ax, %ss
    mov $0x7C00, %sp

    mov %dl, boot_drive

    call load_kernel
    call enable_a20
    call detect_memory

.ifdef DEMO
    mov $0x0013, %ax
    int $0x10
.endif

    cli
    lgdt gdt_descriptor

    mov %cr0, %eax
    or $1, %eax
    mov %eax, %cr0

    ljmp $0x08, $protected_mode

load_kernel:
    movw $KERNEL_LOAD_SEGMENT, load_segment
    movw $KERNEL_LOAD_OFFSET, load_offset
    movl $1, dap_lba_low

    mov $KERNEL_SECTORS, %cx

load_next_sector:
    push %cx

    movw load_offset, %ax
    movw %ax, dap_offset

    movw load_segment, %ax
    movw %ax, dap_segment

    movb boot_drive, %dl
    mov $dap, %si
    mov $0x42, %ah
    int $0x13

    jc disk_error

    addw $512, load_offset
    jnc no_segment_advance

    addw $0x20, load_segment

no_segment_advance:
    addl $1, dap_lba_low

    pop %cx
    loop load_next_sector

    ret

disk_error:
    hlt
    jmp disk_error

enable_a20:
    inb $0x92, %al
    orb $0x02, %al
    outb %al, $0x92
    ret

# BIOS int 0x15 / EAX=E820 memory map -> count @0x8000, entries @0x8004.
# BIOS failure just leaves count = 0; the kernel falls back to a safe default.
detect_memory:
    xor %ebx, %ebx
    movl $0, E820_COUNT_ADDR
    mov $E820_ENTRIES_ADDR, %di

e820_loop:
    mov $0xE820, %eax
    mov $24, %ecx
    mov $E820_MAGIC, %edx
    int $0x15
    jc e820_done
    cmp $E820_MAGIC, %eax
    jne e820_done

    incl E820_COUNT_ADDR
    add $24, %di

    test %ebx, %ebx
    jz e820_done
    cmpl $E820_MAX_ENTRIES, E820_COUNT_ADDR
    jb e820_loop

e820_done:
    ret

.code32

protected_mode:
    mov $0x10, %ax
    mov %ax, %ds
    mov %ax, %es
    mov %ax, %fs
    mov %ax, %gs
    mov %ax, %ss

    mov $0x90000, %esp

    mov $KERNEL_ENTRY, %eax
    jmp *%eax

halt:
    cli
    hlt
    jmp halt

.code16

boot_drive:
    .byte 0

load_segment:
    .word 0

load_offset:
    .word 0

.align 4
dap:
    .byte 0x10
    .byte 0x00
dap_count:
    .word 1
dap_offset:
    .word 0
dap_segment:
    .word 0
dap_lba_low:
    .long 1
dap_lba_high:
    .long 0

gdt_start:
gdt_null:
    .quad 0x0000000000000000

gdt_code:
    .quad 0x00CF9A000000FFFF

gdt_data:
    .quad 0x00CF92000000FFFF

gdt_end:

gdt_descriptor:
    .word gdt_end - gdt_start - 1
    .long gdt_start

.org 510
.word 0xAA55
