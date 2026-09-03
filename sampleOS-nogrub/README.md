# AIOS no-GRUB bootloader sample

A minimal 32-bit x86 hobby kernel project for QEMU on macOS. It uses a custom
boot sector instead of GRUB.

## Build options

You can build the kernel two ways. Both produce the same `AIOS.img` and use
QEMU on the host to run it.

| Option | Toolchain location | Best for |
| ------ | ------------------ | -------- |
| Docker (recommended) | Inside a container | Nothing extra installed on macOS |
| Native Homebrew      | Installed locally  | Faster builds, no Docker required |

QEMU always runs on the macOS host (Docker is build-only). On macOS, QEMU uses
Hypervisor.framework for acceleration, which doesn't work well inside containers.

```
┌─────────────────────── macOS host ───────────────────────┐
│                                                          │
│   ┌── Docker container (build-only) ──┐                  │
│   │ gcc-i686-linux-gnu                │  source files    │
│   │ binutils-i686-linux-gnu           │ ←→ bind mount    │
│   │ make                              │                  │
│   └───────────────────────────────────┘                  │
│              │                                           │
│              ▼  produces AIOS.img                      │
│                                                          │
│        qemu-system-i386  ──→  boots the image            │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

## Prerequisites

Both flows need QEMU on macOS:

```bash
brew install qemu
```

### Docker flow (recommended)

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) and
make sure it's running. The cross toolchain is installed inside the image, not
on your Mac.

### Native flow

```bash
brew install i686-elf-gcc i686-elf-binutils
```

## Build and run

### Docker flow

```bash
make docker-image      # one-time: builds the toolchain image (~250 MB)
make docker-run        # rebuilds the kernel in the container, then boots QEMU
```

Day-to-day cycle:

```bash
# edit source...
make docker-build      # compile inside container, writes AIOS.img
make run               # boot the existing image with host QEMU
```

`make docker-run` is just the combination: build in container, then run on host.

### Native flow

```bash
make clean
make
make run
```

## Expected output

A QEMU window opens showing VGA text mode, and the same text appears in your
terminal (the kernel mirrors output to COM1 via `-serial stdio`):

```text
AIOS kernel started
---------------------

Boot method: custom bootloader
CPU mode:    32-bit protected mode

Hello from AIOS!
```

Exit QEMU with **Ctrl+A** then **X** in the terminal, or close the QEMU window.

## Make targets

| Target          | What it does                                                                |
| --------------- | --------------------------------------------------------------------------- |
| `all` (default) | Build `AIOS.img` using the host toolchain                                 |
| `run`           | Boot `AIOS.img` in QEMU (rebuilds via host toolchain if sources changed)  |
| `clean`         | Remove build artifacts                                                      |
| `docker-image`  | Build the `aios-toolchain` Docker image                                   |
| `docker-build`  | Compile the kernel inside the container                                     |
| `docker-clean`  | Run `make clean` inside the container                                       |
| `docker-run`    | `docker-build`, then `qemu-system-i386` on the host                         |

When using the Docker flow, prefer `make docker-build` over plain `make` — the
plain target would try to invoke `i686-elf-gcc` on your Mac.

## Project layout

```
.
├── bootloader.s     16-bit boot sector: loads kernel via int 0x13, enters protected mode
├── loader.s         32-bit entry stub: sets up the kernel stack and calls kernel_main
├── kernelmain.c     C entry point
├── link.ld          Linker script (kernel runs at 0x10000)
├── include/
│   ├── asm.h        inb/outb/hlt/cli/sti inline helpers
│   ├── io.h         Terminal and serial API
│   └── types.h      u8/u16/u32, size_t, NULL
├── lib/
│   └── io.c         VGA text driver (0xB8000) and 8250 UART driver (COM1)
├── Dockerfile       Build environment: Debian + i686 cross toolchain
└── Makefile         Build rules (native + Docker targets)
```

## How the boot flow works

1. BIOS loads sector 0 (`bootloader.bin`) at `0x7C00` in 16-bit real mode.
2. The boot sector uses BIOS `int 0x13` / `AH=0x42` (LBA disk read) to copy
   128 sectors starting at LBA 1 into memory at `0x10000`.
3. It enables A20, loads a flat GDT (code `0x08`, data `0x10`), sets
   `CR0.PE = 1`, and far-jumps into 32-bit protected mode.
4. Execution jumps to `0x10000`, which is `loader.s`. It sets up a 16 KiB
   stack and calls `kernel_main`.
5. `kernel_main` initializes the COM1 UART, clears VGA text memory, prints the
   banner, and halts in a loop.

## Why output appears in both QEMU and your terminal

The kernel writes to two devices at once:

- **VGA text memory** at `0xB8000` — visible in the QEMU graphical window.
- **COM1 serial port** — wired to your terminal by QEMU's `-serial stdio` flag.

See `lib/io.c:76` — `terminal_putchar` calls `serial_write_char(c)` for every
character, so output is mirrored to both.

## Notes

- `bootloader.s` loads 128 sectors (= 64 KiB) after the boot sector — the
  kernel binary must stay under that limit, or it will be truncated.
- `link.ld` links the kernel to run at `0x10000`.
- Generated files: `bootloader.bin`, `kernel.elf`, `kernel.bin`, `AIOS.img`.
- The Docker toolchain uses `i686-linux-gnu-gcc` instead of `i686-elf-gcc` —
  functionally equivalent for `-ffreestanding -nostdlib` builds. The Makefile
  overrides `CC`, `AS`, `LD`, and `OBJCOPY` when building inside the container.
- No GRUB tools are required.
