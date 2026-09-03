"""
ToyLang AST (Abstract Syntax Tree) Node Definitions

This module defines all AST node types for ToyLang.
The AST is the intermediate representation between parsing and code generation.

Educational notes:
- An AST represents the hierarchical structure of a program
- Each node type corresponds to a language construct
- The AST abstracts away syntactic details (parentheses, semicolons, etc.)
"""

from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum, auto


class NodeType(Enum):
    """All AST node types"""
    # Program
    PROGRAM = auto()
    FUNCTION = auto()
    
    # Statements
    BLOCK = auto()
    LET_STMT = auto()
    ASSIGN_STMT = auto()
    IF_STMT = auto()
    WHILE_STMT = auto()
    RETURN_STMT = auto()
    PRINT_STMT = auto()
    EXPR_STMT = auto()
    
    # Expressions
    BINARY_EXPR = auto()
    UNARY_EXPR = auto()
    CALL_EXPR = auto()
    IDENT_EXPR = auto()
    INT_LITERAL = auto()
    BOOL_LITERAL = auto()
    STRING_LITERAL = auto()


class BinaryOp(Enum):
    """Binary operators"""
    ADD = '+'
    SUB = '-'
    MUL = '*'
    DIV = '/'
    MOD = '%'
    EQ = '=='
    NE = '!='
    LT = '<'
    GT = '>'
    LE = '<='
    GE = '>='
    AND = '&&'
    OR = '||'


class UnaryOp(Enum):
    """Unary operators"""
    NEG = '-'
    NOT = '!'


@dataclass
class SourceLocation:
    """Source location for error reporting"""
    line: int
    column: int
    
    def __str__(self):
        return f"{self.line}:{self.column}"


# Base class for all AST nodes
@dataclass
class ASTNode:
    """Base class for all AST nodes"""
    loc: SourceLocation = field(default_factory=lambda: SourceLocation(0, 0))
    
    def accept(self, visitor):
        """Accept a visitor (for traversal patterns)"""
        method_name = f'visit_{self.__class__.__name__}'
        method = getattr(visitor, method_name, visitor.generic_visit)
        return method(self)


# ============ Expressions ============

@dataclass
class IntLiteral(ASTNode):
    """Integer literal (e.g., 42)"""
    value: int = 0


@dataclass
class BoolLiteral(ASTNode):
    """Boolean literal (true or false)"""
    value: bool = False


@dataclass
class StringLiteral(ASTNode):
    """String literal (e.g., "hello")"""
    value: str = ""


@dataclass
class Identifier(ASTNode):
    """Variable or function name reference"""
    name: str = ""


@dataclass
class BinaryExpr(ASTNode):
    """Binary expression (e.g., a + b)"""
    op: BinaryOp = BinaryOp.ADD
    left: ASTNode = None
    right: ASTNode = None


@dataclass
class UnaryExpr(ASTNode):
    """Unary expression (e.g., -x, !flag)"""
    op: UnaryOp = UnaryOp.NEG
    operand: ASTNode = None


@dataclass
class CallExpr(ASTNode):
    """Function call (e.g., foo(1, 2))"""
    callee: str = ""
    args: List[ASTNode] = field(default_factory=list)


# ============ Statements ============

@dataclass
class Block(ASTNode):
    """Block of statements { ... }"""
    statements: List[ASTNode] = field(default_factory=list)


@dataclass
class LetStmt(ASTNode):
    """Variable declaration (let x = expr;)"""
    name: str = ""
    init: ASTNode = None


@dataclass
class AssignStmt(ASTNode):
    """Variable assignment (x = expr;)"""
    name: str = ""
    value: ASTNode = None


@dataclass
class IfStmt(ASTNode):
    """If statement with optional else"""
    condition: ASTNode = None
    then_block: Block = None
    else_block: Optional[Block] = None


@dataclass
class WhileStmt(ASTNode):
    """While loop"""
    condition: ASTNode = None
    body: Block = None


@dataclass
class ReturnStmt(ASTNode):
    """Return statement (return expr; or return;)"""
    value: Optional[ASTNode] = None


@dataclass
class PrintStmt(ASTNode):
    """Print statement with multiple arguments"""
    args: List[ASTNode] = field(default_factory=list)


@dataclass
class ExprStmt(ASTNode):
    """Expression as statement (for function calls with side effects)"""
    expr: ASTNode = None


# ============ Top-level ============

@dataclass
class Function(ASTNode):
    """Function definition"""
    name: str = ""
    params: List[str] = field(default_factory=list)
    body: Block = None


@dataclass
class Program(ASTNode):
    """Top-level program (list of functions)"""
    functions: List[Function] = field(default_factory=list)


# ============ Visitor Base Class ============

class ASTVisitor:
    """
    Base class for AST visitors.
    Override visit_* methods for specific node types.
    """
    
    def visit(self, node: ASTNode):
        """Visit a node by dispatching to the appropriate method"""
        method_name = f'visit_{node.__class__.__name__}'
        method = getattr(self, method_name, self.generic_visit)
        return method(node)
    
    def generic_visit(self, node: ASTNode):
        """Default visitor - raises error for unhandled nodes"""
        raise NotImplementedError(f"No visit method for {node.__class__.__name__}")


class ASTPrinter(ASTVisitor):
    """Pretty-prints an AST for debugging"""
    
    def __init__(self):
        self.indent = 0
    
    def _print(self, text: str):
        print("  " * self.indent + text)
    
    def visit_Program(self, node: Program):
        self._print("Program:")
        self.indent += 1
        for func in node.functions:
            self.visit(func)
        self.indent -= 1
    
    def visit_Function(self, node: Function):
        params = ", ".join(node.params)
        self._print(f"Function {node.name}({params}):")
        self.indent += 1
        self.visit(node.body)
        self.indent -= 1
    
    def visit_Block(self, node: Block):
        self._print("Block:")
        self.indent += 1
        for stmt in node.statements:
            self.visit(stmt)
        self.indent -= 1
    
    def visit_LetStmt(self, node: LetStmt):
        self._print(f"Let {node.name} =")
        self.indent += 1
        self.visit(node.init)
        self.indent -= 1
    
    def visit_AssignStmt(self, node: AssignStmt):
        self._print(f"Assign {node.name} =")
        self.indent += 1
        self.visit(node.value)
        self.indent -= 1
    
    def visit_IfStmt(self, node: IfStmt):
        self._print("If:")
        self.indent += 1
        self._print("Condition:")
        self.indent += 1
        self.visit(node.condition)
        self.indent -= 1
        self._print("Then:")
        self.visit(node.then_block)
        if node.else_block:
            self._print("Else:")
            self.visit(node.else_block)
        self.indent -= 1
    
    def visit_WhileStmt(self, node: WhileStmt):
        self._print("While:")
        self.indent += 1
        self._print("Condition:")
        self.indent += 1
        self.visit(node.condition)
        self.indent -= 1
        self._print("Body:")
        self.visit(node.body)
        self.indent -= 1
    
    def visit_ReturnStmt(self, node: ReturnStmt):
        if node.value:
            self._print("Return:")
            self.indent += 1
            self.visit(node.value)
            self.indent -= 1
        else:
            self._print("Return (void)")
    
    def visit_PrintStmt(self, node: PrintStmt):
        self._print("Print:")
        self.indent += 1
        for arg in node.args:
            self.visit(arg)
        self.indent -= 1
    
    def visit_ExprStmt(self, node: ExprStmt):
        self._print("ExprStmt:")
        self.indent += 1
        self.visit(node.expr)
        self.indent -= 1
    
    def visit_BinaryExpr(self, node: BinaryExpr):
        self._print(f"BinaryExpr ({node.op.value}):")
        self.indent += 1
        self.visit(node.left)
        self.visit(node.right)
        self.indent -= 1
    
    def visit_UnaryExpr(self, node: UnaryExpr):
        self._print(f"UnaryExpr ({node.op.value}):")
        self.indent += 1
        self.visit(node.operand)
        self.indent -= 1
    
    def visit_CallExpr(self, node: CallExpr):
        self._print(f"Call {node.callee}:")
        self.indent += 1
        for arg in node.args:
            self.visit(arg)
        self.indent -= 1
    
    def visit_Identifier(self, node: Identifier):
        self._print(f"Ident: {node.name}")
    
    def visit_IntLiteral(self, node: IntLiteral):
        self._print(f"Int: {node.value}")
    
    def visit_BoolLiteral(self, node: BoolLiteral):
        self._print(f"Bool: {node.value}")
    
    def visit_StringLiteral(self, node: StringLiteral):
        self._print(f"String: {node.value!r}")


def print_ast(node: ASTNode):
    """Pretty-print an AST tree"""
    printer = ASTPrinter()
    printer.visit(node)
