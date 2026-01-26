# ToyLang Bootstrap Process

This document explains how the ToyLang compiler achieves self-hosting through a multi-stage bootstrap process.

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        BOOTSTRAP CHAIN                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Stage 0          Stage 1          Stage 2          Stage 3                │
│   ────────         ────────         ────────         ────────               │
│                                                                              │
│   ┌─────────┐      ┌─────────┐      ┌─────────┐      ┌─────────┐           │
│   │  seed   │      │ toycc1  │      │ toycc2  │      │ toycc2' │           │
│   │compiler │─────▶│  .toy   │─────▶│  .toy   │─────▶│(verify) │           │
│   │(Python) │      │         │      │         │      │         │           │
│   └─────────┘      └─────────┘      └─────────┘      └─────────┘           │
│       │                │                │                │                  │
│       │ compiles       │ compiles       │ compiles       │ compiles        │
│       ▼                ▼                ▼                ▼                  │
│   ToyLang0         ToyLang0         ToyLang          ToyLang               │
│   programs         programs         programs         programs              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Stages Explained

### Stage 0: Seed Compiler (Python)

**Location**: `src/seed_compiler.py`  
**Input**: ToyLang0 source code  
**Output**: C code (compiled with gcc/clang)

The seed compiler is written in Python, an existing high-level language. This "breaks the chicken-and-egg problem" - we need some compiler to start with, and Python is already installed on most systems.

The seed compiler:
- Is fully featured for ToyLang0 (the language subset)
- Implements all phases: lexer, parser, analyzer, codegen
- Produces human-readable C code
- Has good error messages

### Stage 1: ToyCC1 (ToyLang0)

**Location**: `src/toycc1.toy`  
**Written in**: ToyLang0  
**Compiled by**: Seed compiler  
**Input**: ToyLang0 source code  
**Output**: C code

ToyCC1 is the first compiler written in ToyLang itself. It can only compile ToyLang0 (the subset), because that's the language it's written in.

Key challenges solved:
- No string variables → use character-by-character processing
- No arrays → use individual variables or parameter passing
- Integer-only → represent everything as numbers (ASCII codes, etc.)

```
seed_compiler.py + toycc1.toy → toycc1 (executable)
```

### Stage 2: ToyCC2 (Full ToyLang)

**Location**: `src/toycc2.toy`  
**Written in**: Full ToyLang (but compilable by ToyCC1's output capabilities)  
**Compiled by**: ToyCC1  
**Input**: Full ToyLang source code  
**Output**: C code

ToyCC2 extends the compiler to handle full ToyLang, including:
- String variables (future)
- Arrays (future)
- Additional features

```
toycc1 + toycc2.toy → toycc2 (executable)
```

### Stage 3: Self-Hosting Verification

The final stage proves that the compiler is truly self-hosting:

```
toycc2 + toycc2.toy → toycc2' (recompiled)
```

We verify that:
1. `toycc2'` works correctly (compiles test programs)
2. `toycc2` and `toycc2'` produce identical output for the same input
3. The chain is stable (compiling again produces same result)

## Why This Works

### The Bootstrap Principle

1. **Language Subset**: ToyLang0 is a strict subset of ToyLang. Any valid ToyLang0 program is also a valid ToyLang program.

2. **Compiler Written in Subset**: ToyCC1 is written entirely in ToyLang0, so:
   - The seed compiler can compile it (Python understands ToyLang0)
   - The resulting ToyCC1 can compile ToyLang0 programs
   - Including compiling itself!

3. **Gradual Enhancement**: Each stage adds capabilities:
   - Stage 0: External compiler (Python)
   - Stage 1: Self-contained but limited (ToyLang0 only)
   - Stage 2: Full language support

### Trust Chain

```
Python interpreter (trusted)
    ↓
seed_compiler.py (we wrote it, can verify)
    ↓
toycc1.toy → toycc1 (compiled by trusted chain)
    ↓
toycc2.toy → toycc2 (compiled by toycc1)
    ↓
toycc2.toy → toycc2' (compiled by toycc2)
```

If `toycc2` and `toycc2'` behave identically, we've proven the compiler is correct at least for compiling itself.

## Running the Bootstrap

```bash
# Full bootstrap sequence
./scripts/demo.sh

# Or manually:

# Stage 0: Build seed compiler output
python3 src/seed_compiler.py src/toycc1.toy -o build/toycc1.c

# Stage 1: Compile ToyCC1
cc -o build/toycc1 build/toycc1.c

# Stage 2: Use ToyCC1 to compile ToyCC2
./build/toycc1 < src/toycc2.toy > build/toycc2.c
cc -o build/toycc2 build/toycc2.c

# Stage 3: Self-host verification
./build/toycc2 < src/toycc2.toy > build/toycc2_recompiled.c
cc -o build/toycc2_recompiled build/toycc2_recompiled.c

# Verify identical behavior
./build/toycc2 < examples/hello.toy > /tmp/out1.c
./build/toycc2_recompiled < examples/hello.toy > /tmp/out2.c
diff /tmp/out1.c /tmp/out2.c && echo "Self-hosting verified!"
```

## Diagram: Compilation Flow

```
                 ToyLang Source (.toy)
                         │
                         ▼
         ┌───────────────────────────────┐
         │           LEXER               │
         │   Source → Token Stream       │
         │   "let x = 5" → [LET][x][=][5]│
         └───────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │           PARSER              │
         │   Tokens → AST                │
         │   [LET][x][=][5] → LetStmt(x,5)│
         └───────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │         ANALYZER              │
         │   Check semantics             │
         │   Variables defined?          │
         │   Functions exist?            │
         └───────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │         CODE GEN              │
         │   AST → C Code                │
         │   LetStmt(x,5) → "int64_t x=5"│
         └───────────────────────────────┘
                         │
                         ▼
                    C Source Code
                         │
                         ▼
         ┌───────────────────────────────┐
         │         GCC/CLANG             │
         │   C → Native Executable       │
         └───────────────────────────────┘
                         │
                         ▼
                   Executable Binary
```

## Files Produced

| File | Description |
|------|-------------|
| `build/toycc1.c` | C code generated from toycc1.toy by seed compiler |
| `build/toycc1` | Executable ToyCC1 compiler |
| `build/toycc2.c` | C code generated from toycc2.toy by toycc1 |
| `build/toycc2` | Executable ToyCC2 compiler (full ToyLang) |
| `build/toycc2_recompiled.c` | C code from toycc2.toy compiled by toycc2 itself |
| `build/toycc2_recompiled` | Re-compiled ToyCC2 (should behave identically) |

## Historical Context

This bootstrap process mirrors how real compilers were developed:

- **C**: Originally written in B, then rewritten in C and self-hosted
- **Go**: First compiler written in C, later rewritten in Go
- **Rust**: Originally compiled by OCaml, now self-hosted
- **GCC**: Requires a C compiler to build (uses previous GCC version)

The ability to self-host is a rite of passage for programming languages!
