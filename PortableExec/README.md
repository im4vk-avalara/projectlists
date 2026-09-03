# Portable Executable From Scratch

Create and parse Windows PE (Portable Executable) files from scratch without using any assembler or linker. This project demonstrates the complete PE format byte-by-byte.

## Overview

This project provides two tools:

1. **pe_writer** - Generate valid Windows .exe files from scratch
2. **pe_parser** - Parse and display the complete structure of any .exe file

Both tools work directly with the raw PE format, making every byte explicit for educational purposes.

## Quick Start

```bash
# Build the tools
make

# Create a minimal PE that exits with code 42
./pe_writer minimal.exe minimal

# Parse the generated PE to see its structure
./pe_parser minimal.exe

# Create a PE that shows a MessageBox
./pe_writer hello.exe msgbox

# Parse it with detailed import information
./pe_parser hello.exe -i

# Parse any Windows .exe file
./pe_parser /path/to/program.exe -a
```

---

## PE File Format

The Portable Executable format is Windows' native executable format, used for .exe, .dll, .sys, and other binary files.

### PE File Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ DOS Header (64 bytes)                                           │
│   - Magic: "MZ" (0x5A4D)                                        │
│   - e_lfanew: offset to PE signature                            │
├─────────────────────────────────────────────────────────────────┤
│ DOS Stub (variable, typically 64-128 bytes)                     │
│   - "This program cannot be run in DOS mode"                    │
│   - Executed on MS-DOS systems                                  │
├─────────────────────────────────────────────────────────────────┤
│ PE Signature (4 bytes)                                          │
│   - "PE\0\0" (0x00004550)                                       │
├─────────────────────────────────────────────────────────────────┤
│ COFF File Header (20 bytes)                                     │
│   - Machine type (x86, x64, ARM, ARM64)                         │
│   - Number of sections                                          │
│   - Timestamp, characteristics                                  │
├─────────────────────────────────────────────────────────────────┤
│ Optional Header (PE32: 224 bytes, PE32+: 240 bytes)             │
│   - Entry point RVA                                             │
│   - Image base, alignments                                      │
│   - Subsystem (Console, GUI, Driver)                            │
│   - Data Directories (16 entries)                               │
├─────────────────────────────────────────────────────────────────┤
│ Section Headers (40 bytes each)                                 │
│   - .text (code), .data, .rdata, .idata, etc.                   │
├─────────────────────────────────────────────────────────────────┤
│ Section Data                                                    │
│   - Aligned to FileAlignment (usually 512 bytes)                │
└─────────────────────────────────────────────────────────────────┘
```

### Key Concepts

| Term | Description |
|------|-------------|
| **RVA** | Relative Virtual Address - offset from ImageBase when loaded in memory |
| **VA** | Virtual Address - RVA + ImageBase |
| **File Offset** | Position in the file on disk |
| **Section Alignment** | Memory page alignment (usually 4096 bytes) |
| **File Alignment** | Disk sector alignment (usually 512 bytes) |

### PE32 vs PE32+

| Feature | PE32 (32-bit) | PE32+ (64-bit) |
|---------|---------------|----------------|
| Magic | 0x10B | 0x20B |
| ImageBase | 32-bit | 64-bit |
| Stack/Heap sizes | 32-bit | 64-bit |
| BaseOfData field | Present | Absent |
| Import thunks | 4 bytes | 8 bytes |

---

## Files

| File | Description |
|------|-------------|
| `pe_format.h` | PE structure definitions with detailed comments |
| `pe_writer.cpp` | Generates minimal PE files from scratch |
| `pe_parser.cpp` | Parses and displays PE file contents |
| `Makefile` | Build system |

---

## PE Writer

Creates valid Windows executables byte-by-byte.

### Minimal PE (exit with code 42)

```bash
./pe_writer minimal.exe minimal
```

This creates the smallest possible PE that:
1. Imports `ExitProcess` from `kernel32.dll`
2. Calls `ExitProcess(42)`
3. Exits with code 42

**Size: ~2KB**

### MessageBox PE

```bash
./pe_writer hello.exe msgbox
```

This creates a GUI PE that:
1. Imports `MessageBoxA` from `user32.dll`
2. Imports `ExitProcess` from `kernel32.dll`
3. Shows "Hello, World!" in a message box
4. Exits when the user clicks OK

**Size: ~3KB**

### Code Generation

The writer generates x86 machine code directly:

```asm
; Minimal PE - exit with code 42
push 42                     ; 6A 2A
call dword ptr [ExitProcess] ; FF 15 XX XX XX XX

; MessageBox PE
push 0                      ; MB_OK
push offset title           ; 68 XX XX XX XX
push offset message         ; 68 XX XX XX XX
push 0                      ; NULL hwnd
call dword ptr [MessageBoxA] ; FF 15 XX XX XX XX
push eax                    ; 50 (use return as exit code)
call dword ptr [ExitProcess] ; FF 15 XX XX XX XX
```

---

## PE Parser

Analyzes and displays the complete structure of any PE file.

### Basic Usage

```bash
./pe_parser program.exe
```

### Options

| Option | Description |
|--------|-------------|
| `-v, --verbose` | Show detailed info including raw bytes |
| `-x, --hex` | Dump hex of all sections |
| `-i, --imports` | Show detailed import information |
| `-e, --exports` | Show detailed export information |
| `-a, --all` | Show everything |
| `-h, --help` | Show help |

### Example Output

```
══════════════════════════════════════════════════════════════════════════════
  PE FILE ANALYSIS
══════════════════════════════════════════════════════════════════════════════
  File: minimal.exe
  Size: 2048 bytes (2.00 KB)
  Type: PE32 (32-bit)

══════════════════════════════════════════════════════════════════════════════
  DOS HEADER (64 bytes @ offset 0x0000)
══════════════════════════════════════════════════════════════════════════════
  e_magic:      0x5a4d ('MZ')
  e_lfanew:     0x00000080 (offset to PE header)

══════════════════════════════════════════════════════════════════════════════
  COFF FILE HEADER (20 bytes)
══════════════════════════════════════════════════════════════════════════════
  Machine:              0x014c (Intel 386 (x86))
  NumberOfSections:     2
  Characteristics:      0x0103
    RELOCS_STRIPPED | EXECUTABLE | 32BIT_MACHINE

══════════════════════════════════════════════════════════════════════════════
  OPTIONAL HEADER - PE32 (224 bytes)
══════════════════════════════════════════════════════════════════════════════
  Magic:                       0x010b (PE32)
  AddressOfEntryPoint:         0x00001000 (RVA)
  ImageBase:                   0x00400000
  SectionAlignment:            0x00001000 (4096 bytes)
  FileAlignment:               0x00000200 (512 bytes)
  Subsystem:                   3 (Windows Console (CUI))

══════════════════════════════════════════════════════════════════════════════
  SECTION HEADERS
══════════════════════════════════════════════════════════════════════════════
  Name       VirtSize    VirtAddr    RawSize     RawPtr      Flags
  --------------------------------------------------------------------------------
  .text     0x00000100  0x00001000  0x00000200  0x00000400
    CODE | EXEC | READ
  .idata    0x00000200  0x00002000  0x00000200  0x00000600
    INIT_DATA | READ | WRITE

══════════════════════════════════════════════════════════════════════════════
  IMPORT TABLE
══════════════════════════════════════════════════════════════════════════════

  kernel32.dll
    OriginalFirstThunk (ILT): 0x00002060
    FirstThunk (IAT):         0x00002080
    Functions:
      [   0] ExitProcess
```

---

## How Imports Work

Windows PE files don't contain system code—they import functions from DLLs.

### Import Table Structure

```
Import Directory Table (array of ImportDescriptor)
│
├─ ImportDescriptor for kernel32.dll
│  ├─ OriginalFirstThunk → Import Lookup Table (ILT)
│  │                       ├─ Hint/Name: "ExitProcess"
│  │                       └─ NULL terminator
│  ├─ Name → "kernel32.dll"
│  └─ FirstThunk → Import Address Table (IAT)
│                  ├─ Initially same as ILT
│                  └─ Loader patches with actual addresses
│
├─ ImportDescriptor for user32.dll
│  └─ ...
│
└─ NULL ImportDescriptor (terminator)
```

### How the Loader Works

1. **Parse Import Directory** - Find which DLLs are needed
2. **Load DLLs** - Map kernel32.dll, user32.dll, etc.
3. **Resolve Functions** - Look up ExitProcess, MessageBoxA addresses
4. **Patch IAT** - Replace hint/name RVAs with actual function addresses
5. **Jump to Entry Point** - Start executing at AddressOfEntryPoint

### Calling Imported Functions

The code uses indirect calls through the IAT:

```asm
; At compile time, IAT contains RVA to "ExitProcess" hint/name
; At runtime, loader patches IAT with actual address

call dword ptr [0x00402080]  ; Call through IAT
```

---

## x86 Instruction Encodings

| Instruction | Bytes | Description |
|-------------|-------|-------------|
| `push imm8` | `6A XX` | Push 8-bit immediate |
| `push imm32` | `68 XX XX XX XX` | Push 32-bit immediate |
| `push reg` | `50+r` | Push register (EAX=50, ECX=51, ...) |
| `call [mem32]` | `FF 15 XX XX XX XX` | Indirect call through memory |
| `int 3` | `CC` | Breakpoint (padding) |

---

## Testing

### Generate and Parse

```bash
make demo
```

### Full Test Suite

```bash
make test
```

### Parse External PE

```bash
# Parse a Windows executable
./pe_parser notepad.exe -a

# Using make
make parse FILE=/path/to/program.exe
```

---

## Building

### Requirements

- C++17 compiler (clang++ or g++)
- Make

### Build

```bash
make
```

### Clean

```bash
make clean
```

---

## Running on Windows

The generated PE files are valid Windows executables:

```cmd
# Run minimal.exe
minimal.exe
echo %ERRORLEVEL%
# Output: 42

# Run msgbox.exe
msgbox.exe
# Shows MessageBox with "Hello, World!"
```

### Testing on macOS/Linux

You can use Wine to test:

```bash
wine minimal.exe
echo $?
# Output: 42

wine msgbox.exe
# Shows MessageBox dialog
```

Or use a Windows VM / container.

---

## Common PE Sections

| Section | Purpose |
|---------|---------|
| `.text` | Executable code |
| `.data` | Initialized read-write data |
| `.rdata` | Read-only data (strings, constants) |
| `.bss` | Uninitialized data |
| `.idata` | Import tables |
| `.edata` | Export tables |
| `.rsrc` | Resources (icons, dialogs, etc.) |
| `.reloc` | Base relocations for ASLR |
| `.pdata` | Exception handling (x64) |

---

## Security Features in PE

| Feature | DllCharacteristic Flag | Description |
|---------|------------------------|-------------|
| **ASLR** | `DYNAMIC_BASE` (0x40) | Randomize image base |
| **DEP/NX** | `NX_COMPAT` (0x100) | Mark stack as non-executable |
| **CFG** | `GUARD_CF` (0x4000) | Control Flow Guard |
| **High Entropy** | `HIGH_ENTROPY_VA` (0x20) | 64-bit ASLR with more bits |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                          pe_format.h                            │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │
│  │  DOSHeader    │  │  COFFHeader   │  │ SectionHeader │       │
│  └───────────────┘  └───────────────┘  └───────────────┘       │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐       │
│  │OptionalHeader │  │DataDirectory  │  │ImportDescriptor│      │
│  │    32/64      │  │               │  │               │       │
│  └───────────────┘  └───────────────┘  └───────────────┘       │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
     ┌─────────────────┐             ┌─────────────────┐
     │   pe_writer.cpp │             │  pe_parser.cpp  │
     ├─────────────────┤             ├─────────────────┤
     │ createMinimalPE │             │ parse()         │
     │ createMessageBox│             │ analyze()       │
     │ PE              │             │ printAll()      │
     └─────────────────┘             └─────────────────┘
              │                               │
              ▼                               ▼
        minimal.exe                    Formatted output
        msgbox.exe                     of PE structure
```

---

## Educational Value

This project demonstrates:

1. **Binary file formats** - Understanding how executables are structured
2. **Memory layout** - RVAs, sections, alignment
3. **Dynamic linking** - Import tables, IAT patching
4. **Machine code** - x86 instruction encoding
5. **OS loading** - How Windows loads and runs executables
6. **Reverse engineering** - Parsing and understanding binaries

---

## References

- [PE Format - Microsoft Docs](https://docs.microsoft.com/en-us/windows/win32/debug/pe-format)
- [PE101 - A Windows Executable Walkthrough](https://github.com/corkami/pics/blob/master/binary/pe101/pe101.pdf)
- [An In-Depth Look into the Win32 PE File Format](https://docs.microsoft.com/en-us/archive/msdn-magazine/2002/february/inside-windows-win32-portable-executable-file-format-in-detail)

---

## License

Educational use. Understand how Windows executables work—use responsibly.
