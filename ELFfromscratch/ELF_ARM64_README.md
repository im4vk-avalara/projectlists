# Minimal ARM64 ELF Executable from Scratch

This project generates a minimal Linux AArch64 (ARM64) ELF executable by writing
raw bytes—no assembler, linker, or objcopy required.

## Quick Start

```bash
# Compile the generator
c++ -std=c++17 -o make_elf_arm64 make_elf_arm64.cpp

# Generate the ELF
./make_elf_arm64

# Test on ARM64 Linux
chmod +x mini_elf_arm64
./mini_elf_arm64 ; echo $?
# Expected output: 0
```

---

## 1. ELF File Layout

```
┌────────────────────────────────────────────────────────────────────────┐
│ Offset      Size    Content                                            │
├────────────────────────────────────────────────────────────────────────┤
│ 0x0000      64      Elf64_Ehdr (ELF header)                            │
│ 0x0040      56      Elf64_Phdr (single PT_LOAD program header)         │
│ 0x0078      3976    Zero padding (to reach 0x1000)                     │
│ 0x1000      12      AArch64 machine code: exit(0)                      │
├────────────────────────────────────────────────────────────────────────┤
│ Total:      4108 bytes (0x100C)                                        │
└────────────────────────────────────────────────────────────────────────┘
```

### Virtual Address Mapping

| File Offset | Virtual Address | Content           |
|-------------|-----------------|-------------------|
| 0x0000      | 0x400000        | ELF header        |
| 0x0040      | 0x400040        | Program header    |
| 0x1000      | 0x401000        | Code (entry point)|

---

## 2. ELF Header (Elf64_Ehdr) - 64 bytes

| Offset | Size | Field       | Value        | Description                     |
|--------|------|-------------|--------------|----------------------------------|
| 0x00   | 4    | e_ident[0-3]| 7F 45 4C 46  | "\x7FELF" magic                 |
| 0x04   | 1    | EI_CLASS    | 02           | ELFCLASS64 (64-bit)             |
| 0x05   | 1    | EI_DATA     | 01           | ELFDATA2LSB (little-endian)     |
| 0x06   | 1    | EI_VERSION  | 01           | EV_CURRENT                      |
| 0x07   | 1    | EI_OSABI    | 00           | ELFOSABI_NONE (System V)        |
| 0x08   | 8    | EI_PAD      | 00...        | Padding                         |
| 0x10   | 2    | e_type      | 02 00        | ET_EXEC (executable)            |
| 0x12   | 2    | e_machine   | B7 00        | EM_AARCH64 (183)                |
| 0x14   | 4    | e_version   | 01 00 00 00  | EV_CURRENT                      |
| 0x18   | 8    | e_entry     | 00 10 40 00 00 00 00 00 | Entry: 0x401000    |
| 0x20   | 8    | e_phoff     | 40 00 00 00 00 00 00 00 | Program hdr: 64    |
| 0x28   | 8    | e_shoff     | 00 00 00 00 00 00 00 00 | No section hdrs    |
| 0x30   | 4    | e_flags     | 00 00 00 00  | No flags                        |
| 0x34   | 2    | e_ehsize    | 40 00        | ELF header size: 64             |
| 0x36   | 2    | e_phentsize | 38 00        | Program hdr entry: 56           |
| 0x38   | 2    | e_phnum     | 01 00        | One program header              |
| 0x3A   | 2    | e_shentsize | 40 00        | Section hdr entry: 64           |
| 0x3C   | 2    | e_shnum     | 00 00        | No section headers              |
| 0x3E   | 2    | e_shstrndx  | 00 00        | No section name table           |

---

## 3. Program Header (Elf64_Phdr) - 56 bytes at offset 0x40

| Offset | Size | Field    | Value                    | Description           |
|--------|------|----------|--------------------------|------------------------|
| 0x40   | 4    | p_type   | 01 00 00 00              | PT_LOAD               |
| 0x44   | 4    | p_flags  | 05 00 00 00              | PF_R \| PF_X          |
| 0x48   | 8    | p_offset | 00 00 00 00 00 00 00 00  | File offset: 0        |
| 0x50   | 8    | p_vaddr  | 00 00 40 00 00 00 00 00  | VAddr: 0x400000       |
| 0x58   | 8    | p_paddr  | 00 00 40 00 00 00 00 00  | PAddr: 0x400000       |
| 0x60   | 8    | p_filesz | 0C 10 00 00 00 00 00 00  | File size: 0x100C     |
| 0x68   | 8    | p_memsz  | 0C 10 00 00 00 00 00 00  | Mem size: 0x100C      |
| 0x70   | 8    | p_align  | 00 10 00 00 00 00 00 00  | Align: 0x1000 (4KB)   |

---

## 4. AArch64 Machine Code - 12 bytes at offset 0x1000

| Bytes         | Instruction | Encoding Details                              |
|---------------|-------------|-----------------------------------------------|
| A8 0B 80 D2   | mov x8, #93 | MOVZ X8, #0x5D, LSL #0 → syscall exit        |
| 00 00 80 D2   | mov x0, #0  | MOVZ X0, #0, LSL #0 → exit status            |
| 01 00 00 D4   | svc #0      | Supervisor call to invoke kernel             |

### Instruction Encoding Breakdown

**MOVZ (Move Wide with Zero)**
```
31   30-29  28-23   22-21  20-5      4-0
sf   opc    100101  hw     imm16     Rd
```

For `mov x8, #93`:
- sf=1 (64-bit), opc=10, hw=00, imm16=93 (0x5D), Rd=8
- Binary: 1101_0010_1000_0000_0000_1011_1010_1000 = 0xD2800BA8

**SVC (Supervisor Call)**
```
31-24       23-21  20-5    4-0
11010100    000    imm16   00001
```

For `svc #0`:
- imm16=0
- Binary: 1101_0100_0000_0000_0000_0000_0000_0001 = 0xD4000001

---

## 5. Verification Checklist

### Using `file` command:
```bash
$ file mini_elf_arm64
mini_elf_arm64: ELF 64-bit LSB executable, ARM aarch64, version 1 (SYSV), statically linked, no section header
```

### Using `readelf -h` (on Linux):
```bash
$ readelf -h mini_elf_arm64
ELF Header:
  Magic:   7f 45 4c 46 02 01 01 00 00 00 00 00 00 00 00 00
  Class:                             ELF64
  Data:                              2's complement, little endian
  Version:                           1 (current)
  OS/ABI:                            UNIX - System V
  ABI Version:                       0
  Type:                              EXEC (Executable file)
  Machine:                           AArch64
  Version:                           0x1
  Entry point address:               0x401000
  Start of program headers:          64 (bytes into file)
  Start of section headers:          0 (bytes into file)
  Flags:                             0x0
  Size of this header:               64 (bytes)
  Size of program headers:           56 (bytes)
  Number of program headers:         1
  Size of section headers:           64 (bytes)
  Number of section headers:         0
  Section header string table index: 0
```

### Using `readelf -l` (on Linux):
```bash
$ readelf -l mini_elf_arm64

Elf file type is EXEC (Executable file)
Entry point 0x401000
There is 1 program header, starting at offset 64

Program Headers:
  Type           Offset             VirtAddr           PhysAddr
                 FileSiz            MemSiz              Flags  Align
  LOAD           0x0000000000000000 0x0000000000400000 0x0000000000400000
                 0x000000000000100c 0x000000000000100c  R E    0x1000
```

### Using `xxd` to verify code bytes:
```bash
$ xxd -s 0x1000 -l 12 mini_elf_arm64
00001000: a80b 80d2 0000 80d2 0100 00d4            ............
```

### Running on ARM64 Linux:
```bash
$ chmod +x mini_elf_arm64
$ ./mini_elf_arm64
$ echo $?
0
```

---

## 6. Common Pitfalls

### Alignment Issues
- **p_align must be 0x1000** (4KB page size) for loadable segments
- **p_vaddr and p_offset must have the same alignment modulo p_align**
  - Here: 0x400000 % 0x1000 = 0 and 0x0 % 0x1000 = 0 ✓

### Entry Point
- **e_entry must point to valid, mapped executable memory**
- Entry = BASE_VADDR + CODE_OFFSET = 0x400000 + 0x1000 = 0x401000
- This address is within the PT_LOAD segment (0x400000 to 0x40100C)

### File Size vs Memory Size
- **p_filesz ≤ p_memsz** (always)
- If p_memsz > p_filesz, the kernel zero-fills the difference (for BSS)
- Here they're equal since we have no uninitialized data

### Endianness
- **All multi-byte values must be little-endian** (ELFDATA2LSB)
- Use explicit byte-by-byte writers to avoid host endianness issues

### Machine Type
- **e_machine = 183 (0xB7)** for AArch64
- Not 62 (EM_X86_64) or 40 (EM_ARM for 32-bit)

### Syscall Numbers
- **ARM64 Linux syscall numbers differ from x86-64**
- exit is 93 on ARM64 (60 on x86-64)
- Syscall ABI: x8 = syscall number, x0-x5 = arguments

### No Section Headers Required
- The kernel loader only needs program headers (PT_LOAD segments)
- Section headers are for linkers/debuggers, not runtime execution
- Setting e_shoff=0, e_shnum=0, e_shstrndx=0 is perfectly valid

---

## 7. ET_EXEC vs ET_DYN (PIE)

This generator uses **ET_EXEC** (type=2) with a fixed base address (0x400000).

| Aspect           | ET_EXEC                  | ET_DYN (PIE)                    |
|------------------|--------------------------|----------------------------------|
| Base address     | Fixed (e.g., 0x400000)   | Relocatable (kernel chooses)    |
| ASLR             | Not possible             | Fully supported                  |
| Complexity       | Simpler                  | Requires GOT/PLT for symbols    |
| Use case         | Static, simple programs  | Security-hardened executables   |

For this minimal example, ET_EXEC is simpler and sufficient.

---

## 8. Testing with QEMU (on non-ARM64 systems)

If you're on x86-64 and want to test:

```bash
# Install QEMU user-mode emulator
# On Ubuntu/Debian:
sudo apt install qemu-user-static

# Run the ARM64 binary
qemu-aarch64-static ./mini_elf_arm64
echo $?
# Should print: 0
```
