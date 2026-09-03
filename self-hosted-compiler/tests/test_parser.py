"""
Unit tests for the ToyLang parser
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from parser import parse
from ast_nodes import *


def test_empty_program():
    """Empty program parses but has semantic error (no main)"""
    ast, errors = parse("")
    assert isinstance(ast, Program)
    assert len(ast.functions) == 0
    # Parser succeeds, but analyzer would catch missing main


def test_simple_function():
    """Parse simple function definition"""
    source = "fn main() { }"
    ast, errors = parse(source)
    
    assert not errors
    assert len(ast.functions) == 1
    assert ast.functions[0].name == "main"
    assert ast.functions[0].params == []


def test_function_with_params():
    """Parse function with parameters"""
    source = "fn add(a, b) { return a; }"
    ast, errors = parse(source)
    
    assert not errors
    assert len(ast.functions) == 1
    assert ast.functions[0].name == "add"
    assert ast.functions[0].params == ["a", "b"]


def test_let_statement():
    """Parse variable declaration"""
    source = "fn main() { let x = 5; }"
    ast, errors = parse(source)
    
    assert not errors
    body = ast.functions[0].body
    assert len(body.statements) == 1
    
    stmt = body.statements[0]
    assert isinstance(stmt, LetStmt)
    assert stmt.name == "x"
    assert isinstance(stmt.init, IntLiteral)
    assert stmt.init.value == 5


def test_assignment():
    """Parse assignment statement"""
    source = "fn main() { let x = 0; x = 10; }"
    ast, errors = parse(source)
    
    assert not errors
    body = ast.functions[0].body
    assert len(body.statements) == 2
    
    stmt = body.statements[1]
    assert isinstance(stmt, AssignStmt)
    assert stmt.name == "x"


def test_if_statement():
    """Parse if statement"""
    source = "fn main() { if (x) { let y = 1; } }"
    ast, errors = parse(source)
    
    assert not errors
    stmt = ast.functions[0].body.statements[0]
    assert isinstance(stmt, IfStmt)
    assert stmt.else_block is None


def test_if_else_statement():
    """Parse if-else statement"""
    source = "fn main() { if (x) { let a = 1; } else { let b = 2; } }"
    ast, errors = parse(source)
    
    assert not errors
    stmt = ast.functions[0].body.statements[0]
    assert isinstance(stmt, IfStmt)
    assert stmt.else_block is not None


def test_while_statement():
    """Parse while loop"""
    source = "fn main() { while (x) { x = x - 1; } }"
    ast, errors = parse(source)
    
    assert not errors
    stmt = ast.functions[0].body.statements[0]
    assert isinstance(stmt, WhileStmt)


def test_return_statement():
    """Parse return statement"""
    source = "fn main() { return 42; }"
    ast, errors = parse(source)
    
    assert not errors
    stmt = ast.functions[0].body.statements[0]
    assert isinstance(stmt, ReturnStmt)
    assert isinstance(stmt.value, IntLiteral)
    assert stmt.value.value == 42


def test_return_void():
    """Parse void return statement"""
    source = "fn main() { return; }"
    ast, errors = parse(source)
    
    assert not errors
    stmt = ast.functions[0].body.statements[0]
    assert isinstance(stmt, ReturnStmt)
    assert stmt.value is None


def test_print_statement():
    """Parse print statement"""
    source = 'fn main() { print("hello", 42); }'
    ast, errors = parse(source)
    
    assert not errors
    stmt = ast.functions[0].body.statements[0]
    assert isinstance(stmt, PrintStmt)
    assert len(stmt.args) == 2


def test_binary_expressions():
    """Parse binary expressions with correct precedence"""
    source = "fn main() { let x = 1 + 2 * 3; }"
    ast, errors = parse(source)
    
    assert not errors
    init = ast.functions[0].body.statements[0].init
    
    # Should be (1 + (2 * 3)) due to precedence
    assert isinstance(init, BinaryExpr)
    assert init.op == BinaryOp.ADD
    assert isinstance(init.right, BinaryExpr)
    assert init.right.op == BinaryOp.MUL


def test_comparison_operators():
    """Parse comparison expressions"""
    source = "fn main() { let x = a < b; let y = c >= d; }"
    ast, errors = parse(source)
    
    assert not errors
    stmt1 = ast.functions[0].body.statements[0]
    stmt2 = ast.functions[0].body.statements[1]
    
    assert isinstance(stmt1.init, BinaryExpr)
    assert stmt1.init.op == BinaryOp.LT
    
    assert isinstance(stmt2.init, BinaryExpr)
    assert stmt2.init.op == BinaryOp.GE


def test_logical_operators():
    """Parse logical expressions"""
    source = "fn main() { let x = a && b || c; }"
    ast, errors = parse(source)
    
    assert not errors
    init = ast.functions[0].body.statements[0].init
    
    # Should be ((a && b) || c) due to precedence
    assert isinstance(init, BinaryExpr)
    assert init.op == BinaryOp.OR


def test_unary_expressions():
    """Parse unary expressions"""
    source = "fn main() { let x = -5; let y = !flag; }"
    ast, errors = parse(source)
    
    assert not errors
    stmt1 = ast.functions[0].body.statements[0]
    stmt2 = ast.functions[0].body.statements[1]
    
    assert isinstance(stmt1.init, UnaryExpr)
    assert stmt1.init.op == UnaryOp.NEG
    
    assert isinstance(stmt2.init, UnaryExpr)
    assert stmt2.init.op == UnaryOp.NOT


def test_function_call():
    """Parse function call expression"""
    source = "fn main() { let x = foo(1, 2); }"
    ast, errors = parse(source)
    
    assert not errors
    init = ast.functions[0].body.statements[0].init
    
    assert isinstance(init, CallExpr)
    assert init.callee == "foo"
    assert len(init.args) == 2


def test_parenthesized_expression():
    """Parse parenthesized expression"""
    source = "fn main() { let x = (1 + 2) * 3; }"
    ast, errors = parse(source)
    
    assert not errors
    init = ast.functions[0].body.statements[0].init
    
    # Should be ((1 + 2) * 3)
    assert isinstance(init, BinaryExpr)
    assert init.op == BinaryOp.MUL
    assert isinstance(init.left, BinaryExpr)
    assert init.left.op == BinaryOp.ADD


def test_boolean_literals():
    """Parse boolean literals"""
    source = "fn main() { let x = true; let y = false; }"
    ast, errors = parse(source)
    
    assert not errors
    stmt1 = ast.functions[0].body.statements[0]
    stmt2 = ast.functions[0].body.statements[1]
    
    assert isinstance(stmt1.init, BoolLiteral)
    assert stmt1.init.value == True
    
    assert isinstance(stmt2.init, BoolLiteral)
    assert stmt2.init.value == False


def test_missing_semicolon():
    """Missing semicolon produces error"""
    source = "fn main() { let x = 5 }"
    ast, errors = parse(source)
    
    assert len(errors) > 0


def test_missing_paren():
    """Missing parenthesis produces error"""
    source = "fn main() { if x { } }"
    ast, errors = parse(source)
    
    assert len(errors) > 0


def test_error_location():
    """Errors include line/column information"""
    source = """fn main() {
    let x = 5
    let y = 10;
}"""
    ast, errors = parse(source)
    
    assert len(errors) > 0
    # Error should be on line 2 (missing semicolon)
    assert errors[0].line == 2 or errors[0].line == 3


def test_multiple_functions():
    """Parse multiple function definitions"""
    source = """
fn foo() { return 1; }
fn bar() { return 2; }
fn main() { let x = foo(); }
"""
    ast, errors = parse(source)
    
    assert not errors
    assert len(ast.functions) == 3
    names = [f.name for f in ast.functions]
    assert "foo" in names
    assert "bar" in names
    assert "main" in names


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
