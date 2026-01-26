# ELF From Scratch - ARM64 Toolchain

Build minimal ARM64 ELF executables, pack them with runtime decryption, and compile 
a toy language directly to native code—all without using an assembler or linker!

## Overview

This project demonstrates three key low-level concepts:

1. **ELF generation from scratch** - Write valid ARM64 ELF binaries byte-by-byte
2. **Binary packing/protection** - XOR-encrypt code with runtime decryption stub
3. **Compiler backend** - Compile TinyLang to ARM64 ELF directly (no assembler/linker)

## Quick Start

```bash
# Build all tools
make

# === 1. Generate minimal exit(0) ELF ===
./make_elf_arm64

# === 2. Pack it with XOR encryption ===
./packer mini_elf_arm64 packed_elf 0x5A

# === 3. Compile TinyLang to native ARM64 ===
echo 'let x = 6 * 7
exit x' > answer.tiny
./compiler answer.tiny answer_bin

# Test everything (on ARM64 Linux or Docker)
docker run --rm --platform linux/arm64 -v "$(pwd):/work" alpine sh -c "
    chmod +x /work/packed_elf /work/answer_bin
    /work/packed_elf; echo 'packed_elf exit:' \$?
    /work/answer_bin; echo 'answer_bin exit:' \$?
"
# Output: packed_elf exit: 0
#         answer_bin exit: 42
```

---

## Files

| File | Description |
|------|-------------|
| `make_elf_arm64.cpp` | Generates minimal ARM64 ELF that calls exit(0) |
| `packer.cpp` | XOR packer with runtime decryption stub |
| `compiler.cpp` | TinyLang → ARM64 ELF compiler |
| `mini_elf_arm64` | Generated minimal ELF (4108 bytes) |
| `packed_elf` | Packed/protected ELF with encrypted payload |
| `examples/` | TinyLang example programs |

---

## TinyLang Compiler

A complete compiler that takes a simple language and emits native ARM64 ELF 
executables directly—no assembler or linker required!

### Language Features

```python
# Comments start with #
let x = 10              # Variable declaration
let y = x + 5           # Expressions with variables
let z = (x + y) * 2     # Parentheses for grouping

# Arithmetic: + - * / %
let sum = a + b
let remainder = a % b

# Comparisons (return 0 or 1)
let equal = x == y
let less = x < y

# Control flow
if x > 0 {
    let positive = 1
}

while x > 0 {
    let x = x - 1
}

exit result             # Exit with value as status code
```

### Compilation Pipeline

```
  Source Code (.tiny)
        ↓
  ┌─────────────┐
  │   Lexer     │  → Tokens (LET, IDENTIFIER, INTEGER, PLUS, ...)
  └─────────────┘
        ↓
  ┌─────────────┐
  │   Parser    │  → AST (Abstract Syntax Tree)
  └─────────────┘
        ↓
  ┌─────────────┐
  │  CodeGen    │  → ARM64 Machine Code (raw bytes)
  └─────────────┘
        ↓
  ┌─────────────┐
  │ ELF Emitter │  → Executable Binary
  └─────────────┘
```

### Example: Compile and Run

```bash
# Create a program
cat > factorial.tiny << 'EOF'
# Compute 5! = 120
let n = 5
let result = 1
while n > 0 {
    let result = result * n
    let n = n - 1
}
exit result
EOF

# Compile it
./compiler factorial.tiny factorial_bin

# Run it
docker run --rm --platform linux/arm64 -v "$(pwd):/work" alpine sh -c \
    "chmod +x /work/factorial_bin && /work/factorial_bin; echo \$?"
# Output: 120
```

### Test Suite

```bash
make test-compiler
# Output:
# hello.tiny:      42 (expected: 42)
# arithmetic.tiny: 54 (expected: 54)
# expression.tiny: 25 (expected: 25)
# negative.tiny:   5  (expected: 5)
```

---

## How the Packer Works

### 1. Input Processing
The packer reads an ELF executable and extracts its code section (or treats raw input as shellcode).

### 2. XOR Encryption
```
Original:  A8 0B 80 D2  00 00 80 D2  01 00 00 D4
XOR 0x5A:  F2 51 DA 88  5A 5A DA 88  5B 5A 5A 8E
```

### 3. Stub Generation
The packer generates ARM64 machine code that:
1. Uses `mmap()` to allocate RWX memory
2. XOR-decrypts the payload into the allocated region
3. Jumps to the decrypted code

### 4. Packed ELF Layout
```
┌────────────────────────────────────────────────────────────────┐
│ 0x0000  ELF Header (64 bytes)                                  │
├────────────────────────────────────────────────────────────────┤
│ 0x0040  Program Header - PT_LOAD RWX (56 bytes)                │
├────────────────────────────────────────────────────────────────┤
│ 0x0078  Padding (zeros)                                        │
├────────────────────────────────────────────────────────────────┤
│ 0x1000  Decryption Stub (80 bytes, 20 instructions)            │
│         ├─ ADR x10, payload      ; Get payload address         │
│         ├─ MOV x1, #size         ; Payload size                │
│         ├─ mmap syscall          ; Allocate RWX memory         │
│         ├─ XOR decrypt loop      ; Decrypt into mmap region    │
│         └─ BR x9                 ; Jump to decrypted code      │
├────────────────────────────────────────────────────────────────┤
│ 0x1050  Encrypted Payload (XOR'd original code)                │
└────────────────────────────────────────────────────────────────┘
```

---

## Decryption Stub (ARM64 Assembly)

```asm
_start:
    adr     x10, payload            // Get encrypted payload address
    mov     x1, #PAYLOAD_SIZE       // Size (patched by packer)
    
    // mmap(NULL, size, PROT_RWX, MAP_PRIVATE|MAP_ANON, -1, 0)
    mov     x0, #0                  // addr = NULL
    mov     x2, #7                  // PROT_READ|PROT_WRITE|PROT_EXEC
    mov     x3, #0x22               // MAP_PRIVATE|MAP_ANONYMOUS
    mov     x4, #-1                 // fd = -1
    mov     x5, #0                  // offset = 0
    mov     x8, #222                // __NR_mmap
    svc     #0                      // syscall
    
    // Setup decrypt loop
    mov     x9, x0                  // Save mmap address for jump
    mov     x11, x0                 // Write pointer
    mov     x12, x10                // Read pointer (encrypted)
    mov     x13, x1                 // Bytes remaining
    mov     x14, #XOR_KEY           // XOR key (patched)
    
loop:
    ldrb    w15, [x12], #1          // Load encrypted byte
    eor     w15, w15, w14           // XOR decrypt
    strb    w15, [x11], #1          // Store decrypted byte
    subs    x13, x13, #1            // Decrement counter
    b.ne    loop                    // Continue if not zero
    
    br      x9                      // Jump to decrypted code!

payload:
    .byte   <encrypted bytes...>
```

---

## ARM64 Instruction Encodings

| Instruction | Encoding | Hex |
|-------------|----------|-----|
| `adr x10, +80` | PC-relative address | `0x1000028A` |
| `mov x0, #0` | MOVZ X0, #0 | `0xD2800000` |
| `mov x8, #222` | MOVZ X8, #222 | `0xD2801BC8` |
| `svc #0` | Supervisor call | `0xD4000001` |
| `ldrb w15, [x12], #1` | Post-index load | `0x3840158F` |
| `eor w15, w15, w14` | XOR | `0x4A0E01EF` |
| `strb w15, [x11], #1` | Post-index store | `0x3800156F` |
| `subs x13, x13, #1` | Subtract, set flags | `0xF10005AD` |
| `b.ne loop` | Branch if not equal | `0x54FFFF81` |
| `br x9` | Branch to register | `0xD61F0120` |

---

## Usage

### Basic Packing
```bash
./packer <input> <output> [xor_key]

# Examples:
./packer mini_elf_arm64 packed_elf           # Default key 0x42
./packer mini_elf_arm64 packed_elf 0xFF      # Custom key
./packer shellcode.bin packed_elf 0xAB       # Pack raw shellcode
```

### Testing with Docker
```bash
# On macOS/x86, use Docker with ARM64 emulation
docker run --rm --platform linux/arm64 \
    -v "$(pwd):/work" alpine:latest \
    sh -c "chmod +x /work/packed_elf && /work/packed_elf; echo \$?"
```

---

## Anti-Analysis Features

This packer demonstrates basic protection techniques:

| Feature | Description |
|---------|-------------|
| **Code encryption** | Original code not visible in static analysis |
| **Runtime decryption** | Code only exists decrypted in memory |
| **No symbols** | No section headers, no symbol table |
| **Dynamic allocation** | Uses mmap for unpacked code (different address each run with ASLR) |

### What a reverse engineer sees

**Before (original):**
```
00001000: mov x8, #93      ; Clearly shows exit syscall
00001004: mov x0, #0
00001008: svc #0
```

**After (packed):**
```
00001000: adr x10, 0x1050  ; Decryption stub (what does this do?)
00001004: mov x1, #12
...
00001050: f2 51 da 88 5a 5a da 88 5b 5a 5a 8e  ; Garbage bytes?
```

---

## Extending the Packer

### Ideas for Enhancement

1. **Multiple encryption layers**
   - Chain XOR → ROL → XOR with different keys

2. **Anti-debugging**
   - Check for ptrace attachment before decrypting
   - Time-based checks (debuggers slow execution)

3. **Polymorphic stub**
   - Randomize register allocation
   - Insert junk instructions
   - Reorder independent instructions

4. **Compressed payloads**
   - Use LZSS or similar before encryption
   - Smaller packed binary, harder to analyze

5. **Environment keying**
   - Derive XOR key from hardware ID
   - Only runs on specific machines

---

## Syscall Reference (ARM64 Linux)

| Syscall | Number | Arguments |
|---------|--------|-----------|
| exit | 93 | x0=status |
| mmap | 222 | x0=addr, x1=len, x2=prot, x3=flags, x4=fd, x5=off |
| mprotect | 226 | x0=addr, x1=len, x2=prot |
| munmap | 215 | x0=addr, x1=len |

---

## Building

### Requirements
- C++17 compiler (clang++ or g++)
- Docker (for testing on non-ARM64 systems)

### Makefile
```makefile
CXX = c++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2

all: make_elf_arm64 packer

make_elf_arm64: make_elf_arm64.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

packer: packer.cpp
	$(CXX) $(CXXFLAGS) -o $@ $<

test: all
	./make_elf_arm64
	./packer mini_elf_arm64 packed_elf 0x5A
	docker run --rm --platform linux/arm64 -v "$$(pwd):/work" alpine \
		sh -c "chmod +x /work/packed_elf && /work/packed_elf; echo \$$?"

clean:
	rm -f make_elf_arm64 packer mini_elf_arm64 packed_elf

.PHONY: all test clean
```

---

## License

Educational use. Understand how binary protection works—use responsibly.
