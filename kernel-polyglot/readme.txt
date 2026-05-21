kernel-polyglot - Stage 3 README

You opened this as a ZIP and it parsed.  The same
bytes are also a legacy-BIOS bootable MBR.  Try:

    qemu-system-i386 -drive format=raw,file=boot.img

A rainbow wave sweeps behind a static banner, all
in 16-bit real mode at 0x7C00.

Layout:
    0x000..0x1FF  boot sector (55 AA at 0x1FE)
    0x200..end    ZIP archive

PDF support arrives in Stage 4.
