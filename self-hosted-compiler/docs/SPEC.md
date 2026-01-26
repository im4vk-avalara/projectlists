# ToyLang Language Specification

**Version**: 1.0  
**Purpose**: Educational self-hosted compiler demonstration

---

## 1. Overview

ToyLang is a minimal imperative programming language designed to demonstrate self-hosting compilers. It supports:
- Integer variables and arithmetic
- Boolean expressions
- Control flow (if/else, while)
- Functions with parameters and return values
- Basic I/O (print)

---

## 2. Lexical Elements

### 2.1 Keywords
```
fn, let, if, else, while, return, print, true, false
```

### 2.2 Operators
```
Arithmetic:   +  -  *  /  %
Comparison:   ==  !=  <  >  <=  >=
Logical:      &&  ||  !
Assignment:   =
```

### 2.3 Delimiters
```
(  )  {  }  ,  ;
```

### 2.4 Literals
- **Integers**: Decimal integers (e.g., `42`, `0`, `-17`)
- **Strings**: Double-quoted strings for print only (e.g., `"Hello"`)
- **Booleans**: `true`, `false`

### 2.5 Identifiers
```
IDENT = [a-zA-Z_][a-zA-Z0-9_]*
```

### 2.6 Comments
```
// Single-line comment (to end of line)
```

### 2.7 Whitespace
Spaces, tabs, and newlines are ignored except as token separators.

---

## 3. Grammar (Full ToyLang - EBNF)

```ebnf
program        = { function } ;

function       = "fn" IDENT "(" [ param_list ] ")" block ;
param_list     = IDENT { "," IDENT } ;
block          = "{" { statement } "}" ;

statement      = let_stmt
               | assign_stmt
               | if_stmt
               | while_stmt
               | return_stmt
               | print_stmt
               | expr_stmt
               | block ;

let_stmt       = "let" IDENT "=" expr ";" ;
assign_stmt    = IDENT "=" expr ";" ;
if_stmt        = "if" "(" expr ")" block [ "else" block ] ;
while_stmt     = "while" "(" expr ")" block ;
return_stmt    = "return" [ expr ] ";" ;
print_stmt     = "print" "(" print_arg { "," print_arg } ")" ";" ;
print_arg      = expr | STRING ;
expr_stmt      = expr ";" ;

expr           = logic_or ;
logic_or       = logic_and { "||" logic_and } ;
logic_and      = equality { "&&" equality } ;
equality       = comparison { ( "==" | "!=" ) comparison } ;
comparison     = term { ( "<" | ">" | "<=" | ">=" ) term } ;
term           = factor { ( "+" | "-" ) factor } ;
factor         = unary { ( "*" | "/" | "%" ) unary } ;
unary          = ( "!" | "-" ) unary | primary ;
primary        = INTEGER
               | "true"
               | "false"
               | IDENT
               | call_expr
               | "(" expr ")" ;
call_expr      = IDENT "(" [ arg_list ] ")" ;
arg_list       = expr { "," expr } ;

INTEGER        = digit { digit } ;
STRING         = '"' { any_char_except_quote } '"' ;
IDENT          = letter { letter | digit | "_" } ;
letter         = "a" | ... | "z" | "A" | ... | "Z" | "_" ;
digit          = "0" | ... | "9" ;
```

---

## 4. ToyLang0 Subset (Bootstrap Language)

ToyLang0 is a **strict subset** of ToyLang used for the initial bootstrap stages. 
The seed compiler (Python) implements ToyLang0, and ToyCC1 is written in ToyLang0.

### 4.1 What's INCLUDED in ToyLang0

| Feature | Supported |
|---------|-----------|
| Integer variables (`let x = 5;`) | ✓ |
| Integer arithmetic (`+ - * / %`) | ✓ |
| Comparison operators (`== != < > <= >=`) | ✓ |
| Logical operators (`&& \|\| !`) | ✓ |
| Assignment (`x = 5;`) | ✓ |
| `if` / `else` statements | ✓ |
| `while` loops | ✓ |
| Functions with parameters | ✓ |
| `return` statements | ✓ |
| `print` with integers | ✓ |
| `print` with strings | ✓ |
| Single-line comments | ✓ |
| Function calls | ✓ |

### 4.2 What's EXCLUDED from ToyLang0 (added in full ToyLang)

| Feature | ToyLang0 | Full ToyLang |
|---------|----------|--------------|
| String variables | ✗ | ✓ |
| Arrays | ✗ | ✓ |
| Nested functions | ✗ | ✓ |
| String concatenation | ✗ | ✓ |
| Character literals | ✗ | ✓ |
| `getchar()` input | ✗ | ✓ |

### 4.3 ToyLang0 Design Rationale

ToyLang0 is deliberately minimal but **sufficient to write a compiler**:
- Integers are enough for token types, character codes, and AST node IDs
- `print` handles output (including generated code)
- Functions enable modular compiler structure
- Control flow enables parsing logic and code generation loops

---

## 5. Semantic Rules

### 5.1 Scoping
- **Global scope**: Functions are visible throughout the program
- **Local scope**: Variables declared with `let` are local to their enclosing block
- **Shadowing**: Inner variables can shadow outer variables with the same name

### 5.2 Type System
ToyLang0 has a single type: **integer** (64-bit signed).
- Boolean expressions evaluate to integers: `false` = 0, `true` = 1
- Comparison and logical operators return 0 or 1

### 5.3 Entry Point
Every program must have a `fn main()` function. Execution starts there.

### 5.4 Return Values
- Functions return 0 by default if no `return` statement is executed
- `main()` return value becomes the program exit code

---

## 6. Built-in Functions

### 6.1 ToyLang0 Built-ins

| Function | Description |
|----------|-------------|
| `print(...)` | Print integers and string literals, separated by spaces |
| `putchar(c)` | Print character with ASCII code `c` |
| `getchar()` | Read one character, return ASCII code (-1 on EOF) |

### 6.2 Full ToyLang Built-ins (added later)

| Function | Description |
|----------|-------------|
| `strlen(s)` | Return length of string |
| `exit(code)` | Terminate with exit code |

---

## 7. Example Programs

### 7.1 Hello World
```toylang
fn main() {
    print("Hello, World!");
}
```

### 7.2 Fibonacci
```toylang
fn fib(n) {
    if (n <= 1) {
        return n;
    }
    return fib(n - 1) + fib(n - 2);
}

fn main() {
    let i = 0;
    while (i < 10) {
        print(fib(i));
        i = i + 1;
    }
}
```

### 7.3 Factorial
```toylang
fn factorial(n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);
}

fn main() {
    print("5! =", factorial(5));
}
```

---

## 8. Error Handling

The compiler must report clear errors with line and column numbers:

### 8.1 Lexer Errors
- Unexpected character
- Unterminated string literal
- Invalid number format

### 8.2 Parser Errors  
- Unexpected token (expected X, got Y)
- Missing semicolon
- Unmatched parentheses/braces
- Invalid expression

### 8.3 Semantic Errors
- Undefined variable
- Undefined function
- Wrong number of arguments
- Duplicate function definition
- Duplicate variable in same scope

---

## 9. Code Generation Target

**Default**: C code generation (most portable)

The generated C code:
- Uses `int64_t` for all values
- Includes `<stdio.h>` and `<stdint.h>`
- Maps ToyLang functions directly to C functions
- Uses standard C control structures

Example translation:
```toylang
fn add(a, b) {
    return a + b;
}
```

Generates:
```c
int64_t add(int64_t a, int64_t b) {
    return a + b;
}
```

---

## 10. Bootstrap Stages

| Stage | Compiler | Written In | Compiles | Output |
|-------|----------|------------|----------|--------|
| 0 | seed_compiler | Python | ToyLang0 | C code |
| 1 | ToyCC1 | ToyLang0 | ToyLang0 | C code |
| 2 | ToyCC2 | ToyLang | ToyLang | C code |
| 3 | ToyCC2' | ToyLang (via ToyCC2) | ToyLang | C code |

Self-hosting is proven when ToyCC2' produces identical output to ToyCC2.
