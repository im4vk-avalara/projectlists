"""
Unit tests for the ToyLang code generator
"""

import sys
import os
import subprocess
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from parser import parse
from analyzer import analyze
from codegen import generate


def compile_and_run(toy_source: str) -> tuple[int, str]:
    """
    Compile ToyLang source to C, compile C, run, and return (exit_code, output).
    """
    ast, errors = parse(toy_source)
    if errors:
        raise Exception(f"Parse errors: {errors}")
    
    sem_errors = analyze(ast)
    if sem_errors:
        raise Exception(f"Semantic errors: {sem_errors}")
    
    c_code = generate(ast)
    
    # Write C to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False) as f:
        f.write(c_code)
        c_path = f.name
    
    try:
        # Compile C
        exe_path = c_path[:-2]  # Remove .c
        result = subprocess.run(
            ['cc', '-o', exe_path, c_path],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise Exception(f"C compilation failed: {result.stderr}")
        
        # Run executable
        result = subprocess.run(
            [exe_path],
            capture_output=True, text=True,
            timeout=5
        )
        
        return result.returncode, result.stdout
    
    finally:
        # Cleanup
        try:
            os.unlink(c_path)
            if os.path.exists(exe_path):
                os.unlink(exe_path)
        except:
            pass


def test_hello_world():
    """Simple print statement"""
    source = '''
fn main() {
    print("Hello");
}
'''
    exit_code, output = compile_and_run(source)
    assert exit_code == 0
    assert "Hello" in output


def test_return_value():
    """Return value from main becomes exit code"""
    source = '''
fn main() {
    return 42;
}
'''
    exit_code, output = compile_and_run(source)
    assert exit_code == 42


def test_arithmetic():
    """Basic arithmetic operations"""
    source = '''
fn main() {
    let x = 10 + 20;
    let y = x * 2;
    let z = y - 5;
    print(z);
}
'''
    exit_code, output = compile_and_run(source)
    assert exit_code == 0
    assert "55" in output  # (10+20)*2-5 = 55


def test_comparison():
    """Comparison operators"""
    source = '''
fn main() {
    if (5 < 10) {
        print(1);
    } else {
        print(0);
    }
}
'''
    exit_code, output = compile_and_run(source)
    assert "1" in output


def test_while_loop():
    """While loop"""
    source = '''
fn main() {
    let i = 0;
    let sum = 0;
    while (i < 5) {
        sum = sum + i;
        i = i + 1;
    }
    print(sum);
}
'''
    exit_code, output = compile_and_run(source)
    assert "10" in output  # 0+1+2+3+4 = 10


def test_function_call():
    """Function calls"""
    source = '''
fn double(x) {
    return x * 2;
}

fn main() {
    let y = double(21);
    print(y);
}
'''
    exit_code, output = compile_and_run(source)
    assert "42" in output


def test_recursion():
    """Recursive function"""
    source = '''
fn factorial(n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);
}

fn main() {
    print(factorial(5));
}
'''
    exit_code, output = compile_and_run(source)
    assert "120" in output  # 5! = 120


def test_logical_operators():
    """Logical AND and OR"""
    source = '''
fn main() {
    let a = 1;
    let b = 0;
    
    if (a && b) {
        print(1);
    } else {
        print(0);
    }
    
    if (a || b) {
        print(1);
    } else {
        print(0);
    }
}
'''
    exit_code, output = compile_and_run(source)
    lines = output.strip().split('\n')
    assert "0" in lines[0]  # 1 && 0 = false
    assert "1" in lines[1]  # 1 || 0 = true


def test_modulo():
    """Modulo operator"""
    source = '''
fn main() {
    print(17 % 5);
}
'''
    exit_code, output = compile_and_run(source)
    assert "2" in output  # 17 % 5 = 2


def test_unary_minus():
    """Unary negation"""
    source = '''
fn main() {
    let x = -42;
    print(x);
}
'''
    exit_code, output = compile_and_run(source)
    assert "-42" in output


def test_unary_not():
    """Logical NOT"""
    source = '''
fn main() {
    if (!0) {
        print(1);
    }
    if (!1) {
        print(0);
    }
}
'''
    exit_code, output = compile_and_run(source)
    # !0 = true, so we print 1
    # !1 = false, so we don't print 0
    assert "1" in output


def test_multiple_prints():
    """Multiple print arguments"""
    source = '''
fn main() {
    print("x =", 42);
}
'''
    exit_code, output = compile_and_run(source)
    assert "x =" in output
    assert "42" in output


def test_nested_if():
    """Nested if statements"""
    source = '''
fn main() {
    let x = 10;
    if (x > 5) {
        if (x < 15) {
            print("in range");
        }
    }
}
'''
    exit_code, output = compile_and_run(source)
    assert "in range" in output


def test_fibonacci():
    """Fibonacci sequence (integration test)"""
    source = '''
fn fib(n) {
    if (n <= 1) {
        return n;
    }
    return fib(n - 1) + fib(n - 2);
}

fn main() {
    print(fib(10));
}
'''
    exit_code, output = compile_and_run(source)
    assert "55" in output  # fib(10) = 55


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
