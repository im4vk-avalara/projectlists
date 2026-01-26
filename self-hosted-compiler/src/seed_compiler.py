#!/usr/bin/env python3
"""
ToyLang Seed Compiler (Stage 0)

This is the initial "seed" compiler written in Python.
It compiles ToyLang0 programs to C code, which can then be compiled with gcc/clang.

Usage:
    python seed_compiler.py input.toy [-o output.c] [--run]

Educational notes:
- This is Stage 0 of the bootstrap process
- It's written in a high-level language (Python) for ease of development
- It will be used to compile ToyCC1 (the first self-hosted compiler)
"""

import sys
import os
import argparse
import subprocess
import tempfile

# Add src directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lexer import Lexer
from parser import Parser
from analyzer import Analyzer
from codegen import CodeGenerator


def compile_toylang(source: str, filename: str = "<stdin>") -> tuple[str, list]:
    """
    Compile ToyLang source to C code.
    
    Args:
        source: ToyLang source code
        filename: Source filename for error messages
    
    Returns:
        Tuple of (C code string, list of error messages)
    """
    errors = []
    
    # Phase 1: Lexical analysis
    lexer = Lexer(source, filename)
    tokens = lexer.tokenize()
    
    if lexer.has_errors():
        return "", [str(e) for e in lexer.errors]
    
    # Phase 2: Parsing
    parser = Parser(tokens, filename)
    ast = parser.parse()
    
    if parser.has_errors():
        return "", [str(e) for e in parser.errors]
    
    # Phase 3: Semantic analysis
    analyzer = Analyzer(filename)
    semantic_errors = analyzer.analyze(ast)
    
    if semantic_errors:
        return "", [str(e) for e in semantic_errors]
    
    # Phase 4: Code generation
    gen = CodeGenerator()
    c_code = gen.generate(ast)
    
    return c_code, []


def main():
    parser = argparse.ArgumentParser(
        description="ToyLang Seed Compiler - Compiles ToyLang to C",
        epilog="Part of the self-hosted compiler demo"
    )
    
    parser.add_argument(
        'input',
        help="Input ToyLang source file (.toy)"
    )
    
    parser.add_argument(
        '-o', '--output',
        help="Output file (default: stdout for .c, input.c for compilation)"
    )
    
    parser.add_argument(
        '-c', '--compile',
        action='store_true',
        help="Compile to executable (requires gcc/clang)"
    )
    
    parser.add_argument(
        '--run',
        action='store_true',
        help="Compile and run the program"
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help="Show verbose output"
    )
    
    parser.add_argument(
        '--emit-c',
        action='store_true',
        help="Emit C code to file even when compiling"
    )
    
    parser.add_argument(
        '--cc',
        default='cc',
        help="C compiler to use (default: cc)"
    )
    
    args = parser.parse_args()
    
    # Read input file
    try:
        with open(args.input, 'r') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    except IOError as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Compile to C
    if args.verbose:
        print(f"Compiling {args.input}...", file=sys.stderr)
    
    c_code, errors = compile_toylang(source, args.input)
    
    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        sys.exit(1)
    
    if args.verbose:
        print("Compilation successful!", file=sys.stderr)
    
    # Determine output handling
    if args.compile or args.run:
        # Compile to executable
        
        # Determine output filename
        if args.output:
            exe_path = args.output
        else:
            base = os.path.splitext(args.input)[0]
            exe_path = base
        
        # Write C to temp file (or keep if --emit-c)
        if args.emit_c:
            c_path = os.path.splitext(args.input)[0] + '.c'
            with open(c_path, 'w') as f:
                f.write(c_code)
            if args.verbose:
                print(f"Generated C code: {c_path}", file=sys.stderr)
        else:
            # Use temp file
            fd, c_path = tempfile.mkstemp(suffix='.c')
            os.write(fd, c_code.encode())
            os.close(fd)
        
        # Compile with C compiler
        try:
            cmd = [args.cc, '-o', exe_path, c_path, '-O2']
            if args.verbose:
                print(f"Running: {' '.join(cmd)}", file=sys.stderr)
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"C compilation failed:", file=sys.stderr)
                print(result.stderr, file=sys.stderr)
                sys.exit(1)
            
            if args.verbose:
                print(f"Created executable: {exe_path}", file=sys.stderr)
            
        finally:
            # Clean up temp file
            if not args.emit_c:
                os.unlink(c_path)
        
        # Run if requested
        if args.run:
            if args.verbose:
                print(f"\nRunning {exe_path}:", file=sys.stderr)
                print("-" * 40, file=sys.stderr)
            
            result = subprocess.run([exe_path])
            sys.exit(result.returncode)
    
    else:
        # Just output C code
        if args.output:
            with open(args.output, 'w') as f:
                f.write(c_code)
            if args.verbose:
                print(f"Wrote C code to: {args.output}", file=sys.stderr)
        else:
            print(c_code)


if __name__ == "__main__":
    main()
