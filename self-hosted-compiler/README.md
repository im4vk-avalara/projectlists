# ToyLang: Self-Hosted Compiler Demo

An educational demonstration of a self-hosted compiler. ToyLang is a small programming language that can compile itself.

## Quick Start

```bash
# Run the full bootstrap demo
./scripts/demo.sh

# Or compile a single program
python3 src/seed_compiler.py examples/hello.toy --run
```

## What is Self-Hosting?

A self-hosted compiler is a compiler written in the language it compiles. This creates a fascinating chicken-and-egg problem: how do you compile a compiler if you need the compiler to exist first?

The solution is **bootstrapping**:
1. Write a simple compiler in an existing language (the "seed")
2. Use the seed to compile a new compiler written in the new language
3. The new compiler can then compile itself!

## Project Structure

```
self-hosted-compiler/
├── src/
│   ├── seed_compiler.py    # Stage 0: Python-based seed compiler
│   ├── lexer.py            # Lexical analysis
│   ├── parser.py           # Parsing to AST
│   ├── ast_nodes.py        # AST node definitions
│   ├── analyzer.py         # Semantic analysis
│   ├── codegen.py          # C code generation
│   ├── toycc1.toy          # Stage 1: Compiler in ToyLang0
│   └── toycc2.toy          # Stage 2: Full ToyLang compiler
├── examples/
│   ├── hello.toy           # Hello World
│   ├── fibonacci.toy       # Fibonacci sequence
│   ├── factorial.toy       # Factorials
│   └── primes.toy          # Prime numbers
├── tests/
│   ├── test_lexer.py       # Lexer tests
│   ├── test_parser.py      # Parser tests
│   └── golden/             # Golden output tests
├── docs/
│   ├── SPEC.md             # Language specification
│   └── BOOTSTRAP.md        # Bootstrap process explained
├── scripts/
│   └── demo.sh             # Full bootstrap demo script
└── build/                  # Compiled artifacts
```

## The ToyLang Language

ToyLang is intentionally minimal but complete enough to write a compiler:

```toylang
// Functions
fn factorial(n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);
}

fn main() {
    let x = 5;
    print("Factorial of", x, "is", factorial(x));
}
```

### Features
- Integer variables and arithmetic (`+ - * / %`)
- Boolean expressions (`&& || ! == != < > <= >=`)
- Control flow (`if/else`, `while`)
- Functions with parameters and return values
- `print` statement for output
- `putchar`/`getchar` for character I/O

See [docs/SPEC.md](docs/SPEC.md) for the complete specification.

## Bootstrap Stages

| Stage | Compiler | Written In | Compiles |
|-------|----------|------------|----------|
| 0 | seed_compiler.py | Python | ToyLang0 |
| 1 | toycc1 | ToyLang0 | ToyLang0 |
| 2 | toycc2 | ToyLang | ToyLang |
| 3 | toycc2' (verify) | ToyLang | ToyLang |

See [docs/BOOTSTRAP.md](docs/BOOTSTRAP.md) for detailed explanation.

## Usage

### Compile a ToyLang program

```bash
# Generate C code
python3 src/seed_compiler.py examples/hello.toy

# Generate and compile to executable
python3 src/seed_compiler.py examples/hello.toy --compile -o hello

# Compile and run
python3 src/seed_compiler.py examples/hello.toy --run
```

### Run the bootstrap demo

```bash
./scripts/demo.sh
```

This will:
1. Use the Python seed compiler to compile ToyCC1
2. Use ToyCC1 to compile ToyCC2
3. Use ToyCC2 to compile itself (self-hosting!)
4. Verify the self-hosted compiler works

### Run tests

```bash
cd tests
python3 -m pytest
```

## How It Works

### Compilation Pipeline

```
ToyLang Source → Lexer → Parser → Analyzer → CodeGen → C Code → gcc → Executable
```

1. **Lexer**: Converts source text into tokens
2. **Parser**: Builds an Abstract Syntax Tree (AST)
3. **Analyzer**: Checks semantics (undefined variables, etc.)
4. **CodeGen**: Generates equivalent C code
5. **gcc/clang**: Compiles C to native executable

### The Bootstrap Challenge

ToyCC1 is written in ToyLang0, which has no strings or arrays. So how does it handle text processing?

- Characters are represented as integers (ASCII codes)
- Input is read character-by-character with `getchar()`
- Output is written character-by-character with `putchar()`
- State is passed through function parameters

This makes the code more complex but demonstrates that a minimal language can still be self-hosting.

## Educational Goals

This project demonstrates:

1. **Compiler Architecture**: The classic lexer → parser → analyzer → codegen pipeline
2. **Self-Hosting**: How a language can compile itself
3. **Bootstrapping**: The process of building compilers from scratch
4. **Language Design**: Trade-offs in keeping a language minimal yet powerful

## Requirements

- Python 3.9+ (for seed compiler)
- GCC or Clang (for compiling generated C code)
- Unix-like environment (macOS, Linux, WSL)

## License

MIT License - See LICENSE file

## Further Reading

- [Reflections on Trusting Trust](https://www.cs.cmu.edu/~rdriley/487/papers/Thompson_1984_ReflsctionsonTrustingTrust.pdf) - Ken Thompson's classic paper
- [Bootstrapping a Compiler](https://en.wikipedia.org/wiki/Bootstrapping_(compilers)) - Wikipedia
- [Crafting Interpreters](https://craftinginterpreters.com/) - Excellent book on language implementation
