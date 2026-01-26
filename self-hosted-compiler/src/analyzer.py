"""
ToyLang Semantic Analyzer - Validates semantics and builds symbol tables

This is part of the seed compiler (Stage 0) written in Python.
It performs semantic analysis after parsing, before code generation.

Educational notes:
- Semantic analysis catches errors that syntax can't detect
- We check: undefined variables, undefined functions, arity mismatches
- We also build a symbol table to help code generation
"""

from typing import Dict, List, Set, Optional
from ast_nodes import *


class SemanticError(Exception):
    """Exception raised for semantic errors with location info"""
    def __init__(self, message: str, loc: SourceLocation):
        self.message = message
        self.loc = loc
        super().__init__(f"Semantic error at {loc}: {message}")


class Scope:
    """
    Represents a lexical scope (function body, block, etc.)
    
    Each scope has:
    - A set of variable names defined in this scope
    - A parent scope (for lookups that escape this scope)
    """
    
    def __init__(self, parent: Optional['Scope'] = None):
        self.parent = parent
        self.variables: Set[str] = set()
    
    def define(self, name: str) -> bool:
        """
        Define a variable in this scope.
        Returns False if already defined in THIS scope (shadowing parent is ok).
        """
        if name in self.variables:
            return False
        self.variables.add(name)
        return True
    
    def lookup(self, name: str) -> bool:
        """Check if a variable is defined in this scope or any parent"""
        if name in self.variables:
            return True
        if self.parent:
            return self.parent.lookup(name)
        return False


class FunctionInfo:
    """Information about a function for semantic checking"""
    def __init__(self, name: str, arity: int, loc: SourceLocation):
        self.name = name
        self.arity = arity  # Number of parameters
        self.loc = loc


class Analyzer(ASTVisitor):
    """
    Semantic analyzer for ToyLang.
    
    Checks:
    1. All variables are defined before use
    2. All functions are defined before calling
    3. Function calls have correct number of arguments
    4. No duplicate function definitions
    5. No duplicate variable definitions in same scope
    6. main() function exists
    
    Usage:
        analyzer = Analyzer()
        errors = analyzer.analyze(ast)
    """
    
    # Built-in functions and their arities
    BUILTINS = {
        'putchar': 1,
        'getchar': 0,
    }
    
    def __init__(self, filename: str = "<stdin>"):
        self.filename = filename
        self.errors: List[SemanticError] = []
        self.functions: Dict[str, FunctionInfo] = {}
        self.current_scope: Optional[Scope] = None
        self.current_function: Optional[str] = None
    
    def error(self, message: str, loc: SourceLocation):
        """Record a semantic error"""
        self.errors.append(SemanticError(message, loc))
    
    def push_scope(self):
        """Enter a new scope"""
        self.current_scope = Scope(self.current_scope)
    
    def pop_scope(self):
        """Exit current scope"""
        if self.current_scope:
            self.current_scope = self.current_scope.parent
    
    def define_variable(self, name: str, loc: SourceLocation):
        """Define a variable in current scope"""
        if not self.current_scope.define(name):
            self.error(f"Variable '{name}' already defined in this scope", loc)
    
    def lookup_variable(self, name: str, loc: SourceLocation) -> bool:
        """Check if variable is defined"""
        if not self.current_scope.lookup(name):
            self.error(f"Undefined variable '{name}'", loc)
            return False
        return True
    
    def analyze(self, program: Program) -> List[SemanticError]:
        """
        Analyze the program and return list of errors.
        """
        self.errors = []
        self.functions = {}
        
        # First pass: collect all function declarations
        for func in program.functions:
            if func.name in self.functions:
                self.error(f"Function '{func.name}' already defined", func.loc)
            else:
                self.functions[func.name] = FunctionInfo(
                    func.name, len(func.params), func.loc
                )
        
        # Check for main function
        if 'main' not in self.functions:
            self.error("No 'main' function defined", SourceLocation(1, 1))
        
        # Second pass: analyze function bodies
        for func in program.functions:
            self.analyze_function(func)
        
        return self.errors
    
    def analyze_function(self, func: Function):
        """Analyze a function definition"""
        self.current_function = func.name
        self.push_scope()
        
        # Add parameters to scope
        seen_params = set()
        for param in func.params:
            if param in seen_params:
                self.error(f"Duplicate parameter name '{param}'", func.loc)
            seen_params.add(param)
            self.current_scope.define(param)
        
        # Analyze body
        self.visit(func.body)
        
        self.pop_scope()
        self.current_function = None
    
    def visit_Block(self, node: Block):
        """Analyze a block (new scope for nested blocks)"""
        # Note: function body creates its own scope in analyze_function
        # Nested blocks within a function share the same scope for simplicity
        for stmt in node.statements:
            self.visit(stmt)
    
    def visit_LetStmt(self, node: LetStmt):
        """Analyze variable declaration"""
        # First evaluate the initializer (can reference prior variables)
        self.visit(node.init)
        # Then define the new variable
        self.define_variable(node.name, node.loc)
    
    def visit_AssignStmt(self, node: AssignStmt):
        """Analyze assignment"""
        # Variable must be defined
        self.lookup_variable(node.name, node.loc)
        # Analyze the value
        self.visit(node.value)
    
    def visit_IfStmt(self, node: IfStmt):
        """Analyze if statement"""
        self.visit(node.condition)
        self.visit(node.then_block)
        if node.else_block:
            self.visit(node.else_block)
    
    def visit_WhileStmt(self, node: WhileStmt):
        """Analyze while statement"""
        self.visit(node.condition)
        self.visit(node.body)
    
    def visit_ReturnStmt(self, node: ReturnStmt):
        """Analyze return statement"""
        if node.value:
            self.visit(node.value)
    
    def visit_PrintStmt(self, node: PrintStmt):
        """Analyze print statement"""
        for arg in node.args:
            self.visit(arg)
    
    def visit_ExprStmt(self, node: ExprStmt):
        """Analyze expression statement"""
        self.visit(node.expr)
    
    def visit_BinaryExpr(self, node: BinaryExpr):
        """Analyze binary expression"""
        self.visit(node.left)
        self.visit(node.right)
    
    def visit_UnaryExpr(self, node: UnaryExpr):
        """Analyze unary expression"""
        self.visit(node.operand)
    
    def visit_CallExpr(self, node: CallExpr):
        """Analyze function call"""
        # Check if function exists
        if node.callee in self.BUILTINS:
            expected_arity = self.BUILTINS[node.callee]
            if len(node.args) != expected_arity:
                self.error(
                    f"Built-in '{node.callee}' expects {expected_arity} argument(s), got {len(node.args)}",
                    node.loc
                )
        elif node.callee in self.functions:
            func_info = self.functions[node.callee]
            if len(node.args) != func_info.arity:
                self.error(
                    f"Function '{node.callee}' expects {func_info.arity} argument(s), got {len(node.args)}",
                    node.loc
                )
        else:
            self.error(f"Undefined function '{node.callee}'", node.loc)
        
        # Analyze arguments
        for arg in node.args:
            self.visit(arg)
    
    def visit_Identifier(self, node: Identifier):
        """Analyze identifier (variable reference)"""
        self.lookup_variable(node.name, node.loc)
    
    def visit_IntLiteral(self, node: IntLiteral):
        """Integer literals are always valid"""
        pass
    
    def visit_BoolLiteral(self, node: BoolLiteral):
        """Boolean literals are always valid"""
        pass
    
    def visit_StringLiteral(self, node: StringLiteral):
        """String literals are always valid"""
        pass
    
    def has_errors(self) -> bool:
        """Check if any errors occurred"""
        return len(self.errors) > 0
    
    def format_errors(self) -> str:
        """Format all errors for display"""
        lines = []
        for err in self.errors:
            lines.append(f"{self.filename}:{err.loc}: error: {err.message}")
        return '\n'.join(lines)


def analyze(program: Program, filename: str = "<stdin>") -> List[SemanticError]:
    """
    Convenience function to analyze a program.
    
    Returns:
        List of semantic errors (empty if valid)
    """
    analyzer = Analyzer(filename)
    return analyzer.analyze(program)


# For testing
if __name__ == "__main__":
    from parser import parse
    
    # Test with various error cases
    test_cases = [
        # Undefined variable
        ('fn main() { x = 5; }', "Undefined variable"),
        
        # Duplicate variable
        ('fn main() { let x = 1; let x = 2; }', "Already defined"),
        
        # Undefined function
        ('fn main() { foo(); }', "Undefined function"),
        
        # Wrong arity
        ('fn foo(a, b) { } fn main() { foo(1); }', "Wrong arity"),
        
        # No main
        ('fn foo() { }', "No main"),
        
        # Valid program
        ('fn main() { let x = 5; print(x); }', "Should be valid"),
    ]
    
    for source, description in test_cases:
        print(f"\nTest: {description}")
        print(f"Source: {source}")
        ast, parse_errors = parse(source)
        if parse_errors:
            print(f"Parse errors: {parse_errors}")
        else:
            errors = analyze(ast)
            if errors:
                for e in errors:
                    print(f"  Error: {e.message}")
            else:
                print("  OK")
