"""
ToyLang Parser - Parses tokens into an AST

This is part of the seed compiler (Stage 0) written in Python.
It implements a recursive descent parser for ToyLang.

Educational notes:
- A parser transforms a flat token stream into a hierarchical AST
- Recursive descent: each grammar rule becomes a function
- Operator precedence is handled by nesting expression rules
- Good error messages include location and expected tokens
"""

from typing import List, Optional, Set
from lexer import Token, TokenType, Lexer, tokenize
from ast_nodes import *


class ParseError(Exception):
    """Exception raised for parser errors with location info"""
    def __init__(self, message: str, token: Token):
        self.message = message
        self.token = token
        self.line = token.line
        self.column = token.column
        super().__init__(f"Parse error at {token.line}:{token.column}: {message}")


class Parser:
    """
    Recursive descent parser for ToyLang.
    
    Grammar implemented (simplified):
        program     = { function }
        function    = "fn" IDENT "(" [params] ")" block
        block       = "{" { statement } "}"
        statement   = let | assign | if | while | return | print | expr_stmt
        ...
    
    Usage:
        parser = Parser(tokens)
        ast = parser.parse()
    """
    
    def __init__(self, tokens: List[Token], filename: str = "<stdin>"):
        self.tokens = tokens
        self.filename = filename
        self.pos = 0
        self.errors: List[ParseError] = []
    
    # ============ Token handling ============
    
    def current(self) -> Token:
        """Get current token"""
        if self.pos < len(self.tokens):
            return self.tokens[self.pos]
        return self.tokens[-1]  # Return EOF
    
    def peek(self, offset: int = 0) -> Token:
        """Look ahead at token"""
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]
    
    def check(self, *types: TokenType) -> bool:
        """Check if current token is one of the given types"""
        return self.current().type in types
    
    def match(self, *types: TokenType) -> Optional[Token]:
        """If current token matches, consume and return it"""
        if self.check(*types):
            token = self.current()
            self.pos += 1
            return token
        return None
    
    def expect(self, token_type: TokenType, message: str = None) -> Token:
        """Expect a specific token type, raise error if not found"""
        if self.check(token_type):
            token = self.current()
            self.pos += 1
            return token
        
        if message is None:
            message = f"Expected {token_type.name}, got {self.current().type.name}"
        
        raise ParseError(message, self.current())
    
    def make_loc(self, token: Token) -> SourceLocation:
        """Create source location from token"""
        return SourceLocation(token.line, token.column)
    
    # ============ Error recovery ============
    
    def synchronize(self):
        """Skip tokens until we find a safe point to resume parsing"""
        self.pos += 1
        
        while not self.check(TokenType.EOF):
            # Statement boundary
            if self.peek(-1).type == TokenType.SEMI:
                return
            
            # Start of new statement/declaration
            if self.check(TokenType.FN, TokenType.LET, TokenType.IF, 
                         TokenType.WHILE, TokenType.RETURN, TokenType.PRINT):
                return
            
            self.pos += 1
    
    # ============ Parsing rules ============
    
    def parse(self) -> Program:
        """Parse entire program"""
        functions = []
        
        while not self.check(TokenType.EOF):
            try:
                func = self.parse_function()
                functions.append(func)
            except ParseError as e:
                self.errors.append(e)
                self.synchronize()
        
        return Program(functions=functions, loc=SourceLocation(1, 1))
    
    def parse_function(self) -> Function:
        """Parse function definition: fn name(params) { body }"""
        start = self.expect(TokenType.FN, "Expected 'fn' keyword")
        
        name_token = self.expect(TokenType.IDENT, "Expected function name")
        name = name_token.value
        
        self.expect(TokenType.LPAREN, "Expected '(' after function name")
        
        params = []
        if not self.check(TokenType.RPAREN):
            params = self.parse_param_list()
        
        self.expect(TokenType.RPAREN, "Expected ')' after parameters")
        
        body = self.parse_block()
        
        return Function(name=name, params=params, body=body, loc=self.make_loc(start))
    
    def parse_param_list(self) -> List[str]:
        """Parse parameter list: ident, ident, ..."""
        params = []
        
        param = self.expect(TokenType.IDENT, "Expected parameter name")
        params.append(param.value)
        
        while self.match(TokenType.COMMA):
            param = self.expect(TokenType.IDENT, "Expected parameter name")
            params.append(param.value)
        
        return params
    
    def parse_block(self) -> Block:
        """Parse block: { statements }"""
        start = self.expect(TokenType.LBRACE, "Expected '{'")
        
        statements = []
        while not self.check(TokenType.RBRACE, TokenType.EOF):
            try:
                stmt = self.parse_statement()
                statements.append(stmt)
            except ParseError as e:
                self.errors.append(e)
                self.synchronize()
        
        self.expect(TokenType.RBRACE, "Expected '}'")
        
        return Block(statements=statements, loc=self.make_loc(start))
    
    def parse_statement(self) -> ASTNode:
        """Parse a statement"""
        if self.check(TokenType.LET):
            return self.parse_let_stmt()
        if self.check(TokenType.IF):
            return self.parse_if_stmt()
        if self.check(TokenType.WHILE):
            return self.parse_while_stmt()
        if self.check(TokenType.RETURN):
            return self.parse_return_stmt()
        if self.check(TokenType.PRINT):
            return self.parse_print_stmt()
        if self.check(TokenType.LBRACE):
            return self.parse_block()
        
        # Assignment or expression statement
        # Look ahead to see if this is an assignment
        if self.check(TokenType.IDENT) and self.peek(1).type == TokenType.ASSIGN:
            return self.parse_assign_stmt()
        
        return self.parse_expr_stmt()
    
    def parse_let_stmt(self) -> LetStmt:
        """Parse: let name = expr;"""
        start = self.expect(TokenType.LET)
        name_token = self.expect(TokenType.IDENT, "Expected variable name")
        self.expect(TokenType.ASSIGN, "Expected '=' after variable name")
        init = self.parse_expression()
        self.expect(TokenType.SEMI, "Expected ';' after variable declaration")
        
        return LetStmt(name=name_token.value, init=init, loc=self.make_loc(start))
    
    def parse_assign_stmt(self) -> AssignStmt:
        """Parse: name = expr;"""
        name_token = self.expect(TokenType.IDENT)
        start = name_token
        self.expect(TokenType.ASSIGN)
        value = self.parse_expression()
        self.expect(TokenType.SEMI, "Expected ';' after assignment")
        
        return AssignStmt(name=name_token.value, value=value, loc=self.make_loc(start))
    
    def parse_if_stmt(self) -> IfStmt:
        """Parse: if (cond) block [else block | else if ...]"""
        start = self.expect(TokenType.IF)
        self.expect(TokenType.LPAREN, "Expected '(' after 'if'")
        condition = self.parse_expression()
        self.expect(TokenType.RPAREN, "Expected ')' after condition")
        
        then_block = self.parse_block()
        
        else_block = None
        if self.match(TokenType.ELSE):
            # Support "else if" by wrapping it in a synthetic block
            if self.check(TokenType.IF):
                inner_if = self.parse_if_stmt()
                else_block = Block(statements=[inner_if], loc=inner_if.loc)
            else:
                else_block = self.parse_block()
        
        return IfStmt(condition=condition, then_block=then_block, 
                     else_block=else_block, loc=self.make_loc(start))
    
    def parse_while_stmt(self) -> WhileStmt:
        """Parse: while (cond) block"""
        start = self.expect(TokenType.WHILE)
        self.expect(TokenType.LPAREN, "Expected '(' after 'while'")
        condition = self.parse_expression()
        self.expect(TokenType.RPAREN, "Expected ')' after condition")
        
        body = self.parse_block()
        
        return WhileStmt(condition=condition, body=body, loc=self.make_loc(start))
    
    def parse_return_stmt(self) -> ReturnStmt:
        """Parse: return [expr];"""
        start = self.expect(TokenType.RETURN)
        
        value = None
        if not self.check(TokenType.SEMI):
            value = self.parse_expression()
        
        self.expect(TokenType.SEMI, "Expected ';' after return statement")
        
        return ReturnStmt(value=value, loc=self.make_loc(start))
    
    def parse_print_stmt(self) -> PrintStmt:
        """Parse: print(args);"""
        start = self.expect(TokenType.PRINT)
        self.expect(TokenType.LPAREN, "Expected '(' after 'print'")
        
        args = []
        if not self.check(TokenType.RPAREN):
            args = self.parse_print_args()
        
        self.expect(TokenType.RPAREN, "Expected ')' after print arguments")
        self.expect(TokenType.SEMI, "Expected ';' after print statement")
        
        return PrintStmt(args=args, loc=self.make_loc(start))
    
    def parse_print_args(self) -> List[ASTNode]:
        """Parse print arguments (expressions or strings)"""
        args = []
        args.append(self.parse_expression())
        
        while self.match(TokenType.COMMA):
            args.append(self.parse_expression())
        
        return args
    
    def parse_expr_stmt(self) -> ExprStmt:
        """Parse expression as statement"""
        expr = self.parse_expression()
        start_loc = expr.loc
        self.expect(TokenType.SEMI, "Expected ';' after expression")
        return ExprStmt(expr=expr, loc=start_loc)
    
    # ============ Expression parsing (precedence climbing) ============
    
    def parse_expression(self) -> ASTNode:
        """Parse expression (entry point)"""
        return self.parse_or()
    
    def parse_or(self) -> ASTNode:
        """Parse: expr || expr"""
        left = self.parse_and()
        
        while self.match(TokenType.OR):
            right = self.parse_and()
            left = BinaryExpr(op=BinaryOp.OR, left=left, right=right, loc=left.loc)
        
        return left
    
    def parse_and(self) -> ASTNode:
        """Parse: expr && expr"""
        left = self.parse_equality()
        
        while self.match(TokenType.AND):
            right = self.parse_equality()
            left = BinaryExpr(op=BinaryOp.AND, left=left, right=right, loc=left.loc)
        
        return left
    
    def parse_equality(self) -> ASTNode:
        """Parse: expr == expr | expr != expr"""
        left = self.parse_comparison()
        
        while True:
            if self.match(TokenType.EQ):
                right = self.parse_comparison()
                left = BinaryExpr(op=BinaryOp.EQ, left=left, right=right, loc=left.loc)
            elif self.match(TokenType.NE):
                right = self.parse_comparison()
                left = BinaryExpr(op=BinaryOp.NE, left=left, right=right, loc=left.loc)
            else:
                break
        
        return left
    
    def parse_comparison(self) -> ASTNode:
        """Parse: expr < expr | expr > expr | expr <= expr | expr >= expr"""
        left = self.parse_term()
        
        while True:
            if self.match(TokenType.LT):
                right = self.parse_term()
                left = BinaryExpr(op=BinaryOp.LT, left=left, right=right, loc=left.loc)
            elif self.match(TokenType.GT):
                right = self.parse_term()
                left = BinaryExpr(op=BinaryOp.GT, left=left, right=right, loc=left.loc)
            elif self.match(TokenType.LE):
                right = self.parse_term()
                left = BinaryExpr(op=BinaryOp.LE, left=left, right=right, loc=left.loc)
            elif self.match(TokenType.GE):
                right = self.parse_term()
                left = BinaryExpr(op=BinaryOp.GE, left=left, right=right, loc=left.loc)
            else:
                break
        
        return left
    
    def parse_term(self) -> ASTNode:
        """Parse: expr + expr | expr - expr"""
        left = self.parse_factor()
        
        while True:
            if self.match(TokenType.PLUS):
                right = self.parse_factor()
                left = BinaryExpr(op=BinaryOp.ADD, left=left, right=right, loc=left.loc)
            elif self.match(TokenType.MINUS):
                right = self.parse_factor()
                left = BinaryExpr(op=BinaryOp.SUB, left=left, right=right, loc=left.loc)
            else:
                break
        
        return left
    
    def parse_factor(self) -> ASTNode:
        """Parse: expr * expr | expr / expr | expr % expr"""
        left = self.parse_unary()
        
        while True:
            if self.match(TokenType.STAR):
                right = self.parse_unary()
                left = BinaryExpr(op=BinaryOp.MUL, left=left, right=right, loc=left.loc)
            elif self.match(TokenType.SLASH):
                right = self.parse_unary()
                left = BinaryExpr(op=BinaryOp.DIV, left=left, right=right, loc=left.loc)
            elif self.match(TokenType.PERCENT):
                right = self.parse_unary()
                left = BinaryExpr(op=BinaryOp.MOD, left=left, right=right, loc=left.loc)
            else:
                break
        
        return left
    
    def parse_unary(self) -> ASTNode:
        """Parse: -expr | !expr | primary"""
        if self.match(TokenType.MINUS):
            start = self.peek(-1)
            operand = self.parse_unary()
            return UnaryExpr(op=UnaryOp.NEG, operand=operand, loc=self.make_loc(start))
        
        if self.match(TokenType.NOT):
            start = self.peek(-1)
            operand = self.parse_unary()
            return UnaryExpr(op=UnaryOp.NOT, operand=operand, loc=self.make_loc(start))
        
        return self.parse_primary()
    
    def parse_primary(self) -> ASTNode:
        """Parse primary expressions: literals, identifiers, calls, grouping"""
        token = self.current()
        
        # Integer literal
        if self.match(TokenType.INTEGER):
            return IntLiteral(value=int(token.value), loc=self.make_loc(token))
        
        # Boolean literals
        if self.match(TokenType.TRUE):
            return BoolLiteral(value=True, loc=self.make_loc(token))
        if self.match(TokenType.FALSE):
            return BoolLiteral(value=False, loc=self.make_loc(token))
        
        # String literal
        if self.match(TokenType.STRING):
            return StringLiteral(value=token.value, loc=self.make_loc(token))
        
        # Identifier or function call
        if self.match(TokenType.IDENT):
            name = token.value
            
            # Check for function call
            if self.match(TokenType.LPAREN):
                args = []
                if not self.check(TokenType.RPAREN):
                    args.append(self.parse_expression())
                    while self.match(TokenType.COMMA):
                        args.append(self.parse_expression())
                self.expect(TokenType.RPAREN, "Expected ')' after arguments")
                return CallExpr(callee=name, args=args, loc=self.make_loc(token))
            
            return Identifier(name=name, loc=self.make_loc(token))
        
        # Grouped expression
        if self.match(TokenType.LPAREN):
            expr = self.parse_expression()
            self.expect(TokenType.RPAREN, "Expected ')' after expression")
            return expr
        
        raise ParseError(f"Unexpected token: {token.value!r}", token)
    
    # ============ Public interface ============
    
    def has_errors(self) -> bool:
        """Check if any errors occurred during parsing"""
        return len(self.errors) > 0
    
    def format_errors(self) -> str:
        """Format all errors for display"""
        lines = []
        for err in self.errors:
            lines.append(f"{self.filename}:{err.line}:{err.column}: error: {err.message}")
        return '\n'.join(lines)


def parse(source: str, filename: str = "<stdin>") -> tuple[Program, List[ParseError]]:
    """
    Convenience function to parse source code.
    
    Returns:
        Tuple of (AST, errors)
    """
    from lexer import Lexer
    
    lexer = Lexer(source, filename)
    tokens = lexer.tokenize()
    
    if lexer.has_errors():
        # Convert lexer errors to parse errors for uniform handling
        parse_errors = [ParseError(e.message, Token(TokenType.ERROR, '', e.line, e.column)) 
                       for e in lexer.errors]
        return Program(functions=[]), parse_errors
    
    parser = Parser(tokens, filename)
    ast = parser.parse()
    
    return ast, parser.errors


# For testing
if __name__ == "__main__":
    test_source = '''
fn factorial(n) {
    if (n <= 1) {
        return 1;
    }
    return n * factorial(n - 1);
}

fn main() {
    let x = 5;
    let result = factorial(x);
    print("Factorial of", x, "is", result);
}
'''
    ast, errors = parse(test_source)
    
    if errors:
        print("Errors:")
        for err in errors:
            print(f"  {err}")
    else:
        print("Parsing successful!")
        from ast_nodes import print_ast
        print_ast(ast)
