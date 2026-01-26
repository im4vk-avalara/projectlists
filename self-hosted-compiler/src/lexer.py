"""
ToyLang Lexer - Tokenizes ToyLang source code

This is part of the seed compiler (Stage 0) written in Python.
It implements lexical analysis for both ToyLang0 and full ToyLang.

Educational notes:
- A lexer converts source text into a stream of tokens
- Each token has a type, value, and source location (line, column)
- The lexer handles whitespace, comments, and error reporting
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import List, Optional


class TokenType(Enum):
    """All token types in ToyLang"""
    # Literals
    INTEGER = auto()
    STRING = auto()
    TRUE = auto()
    FALSE = auto()
    
    # Keywords
    FN = auto()
    LET = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    RETURN = auto()
    PRINT = auto()
    
    # Identifiers
    IDENT = auto()
    
    # Operators
    PLUS = auto()       # +
    MINUS = auto()      # -
    STAR = auto()       # *
    SLASH = auto()      # /
    PERCENT = auto()    # %
    EQ = auto()         # ==
    NE = auto()         # !=
    LT = auto()         # <
    GT = auto()         # >
    LE = auto()         # <=
    GE = auto()         # >=
    AND = auto()        # &&
    OR = auto()         # ||
    NOT = auto()        # !
    ASSIGN = auto()     # =
    
    # Delimiters
    LPAREN = auto()     # (
    RPAREN = auto()     # )
    LBRACE = auto()     # {
    RBRACE = auto()     # }
    COMMA = auto()      # ,
    SEMI = auto()       # ;
    
    # Special
    EOF = auto()
    ERROR = auto()


@dataclass
class Token:
    """
    A token produced by the lexer.
    
    Attributes:
        type: The type of token (keyword, operator, literal, etc.)
        value: The string value of the token
        line: 1-based line number in source
        column: 1-based column number in source
    """
    type: TokenType
    value: str
    line: int
    column: int
    
    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"


# Keywords mapping
KEYWORDS = {
    'fn': TokenType.FN,
    'let': TokenType.LET,
    'if': TokenType.IF,
    'else': TokenType.ELSE,
    'while': TokenType.WHILE,
    'return': TokenType.RETURN,
    'print': TokenType.PRINT,
    'true': TokenType.TRUE,
    'false': TokenType.FALSE,
}


class LexerError(Exception):
    """Exception raised for lexer errors with location info"""
    def __init__(self, message: str, line: int, column: int):
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"Lexer error at {line}:{column}: {message}")


class Lexer:
    """
    Lexer for ToyLang source code.
    
    Converts source text into a stream of tokens.
    Tracks line/column for error reporting.
    
    Usage:
        lexer = Lexer(source_code)
        tokens = lexer.tokenize()
    """
    
    def __init__(self, source: str, filename: str = "<stdin>"):
        self.source = source
        self.filename = filename
        self.pos = 0          # Current position in source
        self.line = 1         # Current line (1-based)
        self.column = 1       # Current column (1-based)
        self.tokens: List[Token] = []
        self.errors: List[LexerError] = []
    
    def peek(self, offset: int = 0) -> str:
        """Look at character at current position + offset, or '' if past end"""
        idx = self.pos + offset
        if idx < len(self.source):
            return self.source[idx]
        return ''
    
    def advance(self) -> str:
        """Consume and return current character, updating position"""
        if self.pos >= len(self.source):
            return ''
        
        ch = self.source[self.pos]
        self.pos += 1
        
        # Update line/column tracking
        if ch == '\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        
        return ch
    
    def skip_whitespace(self):
        """Skip spaces, tabs, and newlines"""
        while self.peek() != '' and self.peek() in ' \t\n\r':
            self.advance()
    
    def skip_comment(self):
        """Skip single-line comment (// to end of line)"""
        # Already consumed the first '/'
        if self.peek() == '/':
            self.advance()  # consume second '/'
            while self.peek() not in ('', '\n'):
                self.advance()
            return True
        return False
    
    def make_token(self, token_type: TokenType, value: str, start_line: int, start_col: int) -> Token:
        """Create a token with given type and source location"""
        return Token(token_type, value, start_line, start_col)
    
    def read_number(self) -> Token:
        """Read an integer literal"""
        start_line, start_col = self.line, self.column
        value = ''
        
        while self.peek().isdigit():
            value += self.advance()
        
        return self.make_token(TokenType.INTEGER, value, start_line, start_col)
    
    def read_string(self) -> Token:
        """Read a string literal (double-quoted)"""
        start_line, start_col = self.line, self.column
        self.advance()  # consume opening quote
        value = ''
        
        while True:
            ch = self.peek()
            if ch == '':
                self.errors.append(LexerError("Unterminated string literal", start_line, start_col))
                return self.make_token(TokenType.ERROR, value, start_line, start_col)
            if ch == '"':
                self.advance()  # consume closing quote
                break
            if ch == '\n':
                self.errors.append(LexerError("Newline in string literal", self.line, self.column))
                return self.make_token(TokenType.ERROR, value, start_line, start_col)
            if ch == '\\':
                self.advance()  # consume backslash
                escape = self.advance()
                if escape == 'n':
                    value += '\n'
                elif escape == 't':
                    value += '\t'
                elif escape == '"':
                    value += '"'
                elif escape == '\\':
                    value += '\\'
                else:
                    value += escape
            else:
                value += self.advance()
        
        return self.make_token(TokenType.STRING, value, start_line, start_col)
    
    def read_identifier(self) -> Token:
        """Read an identifier or keyword"""
        start_line, start_col = self.line, self.column
        value = ''
        
        while True:
            ch = self.peek()
            if ch.isalnum() or ch == '_':
                value += self.advance()
            else:
                break
        
        # Check if it's a keyword
        token_type = KEYWORDS.get(value, TokenType.IDENT)
        return self.make_token(token_type, value, start_line, start_col)
    
    def next_token(self) -> Optional[Token]:
        """Read and return the next token, or None if at end"""
        self.skip_whitespace()
        
        if self.pos >= len(self.source):
            return None
        
        start_line, start_col = self.line, self.column
        ch = self.peek()
        
        # Numbers
        if ch.isdigit():
            return self.read_number()
        
        # Strings
        if ch == '"':
            return self.read_string()
        
        # Identifiers and keywords
        if ch.isalpha() or ch == '_':
            return self.read_identifier()
        
        # Two-character operators
        ch2 = self.peek(1)
        two_char = ch + ch2
        
        if two_char == '//':
            self.advance()  # consume first '/'
            self.skip_comment()
            return self.next_token()  # Recurse to get next real token
        
        two_char_ops = {
            '==': TokenType.EQ,
            '!=': TokenType.NE,
            '<=': TokenType.LE,
            '>=': TokenType.GE,
            '&&': TokenType.AND,
            '||': TokenType.OR,
        }
        
        if two_char in two_char_ops:
            self.advance()
            self.advance()
            return self.make_token(two_char_ops[two_char], two_char, start_line, start_col)
        
        # Single-character tokens
        single_char_ops = {
            '+': TokenType.PLUS,
            '-': TokenType.MINUS,
            '*': TokenType.STAR,
            '/': TokenType.SLASH,
            '%': TokenType.PERCENT,
            '<': TokenType.LT,
            '>': TokenType.GT,
            '!': TokenType.NOT,
            '=': TokenType.ASSIGN,
            '(': TokenType.LPAREN,
            ')': TokenType.RPAREN,
            '{': TokenType.LBRACE,
            '}': TokenType.RBRACE,
            ',': TokenType.COMMA,
            ';': TokenType.SEMI,
        }
        
        if ch in single_char_ops:
            self.advance()
            return self.make_token(single_char_ops[ch], ch, start_line, start_col)
        
        # Unknown character
        self.advance()
        self.errors.append(LexerError(f"Unexpected character: {ch!r}", start_line, start_col))
        return self.make_token(TokenType.ERROR, ch, start_line, start_col)
    
    def tokenize(self) -> List[Token]:
        """
        Tokenize the entire source and return list of tokens.
        The list always ends with an EOF token.
        """
        self.tokens = []
        self.errors = []
        
        while True:
            token = self.next_token()
            if token is None:
                break
            if token.type != TokenType.ERROR:
                self.tokens.append(token)
        
        # Add EOF token
        self.tokens.append(Token(TokenType.EOF, '', self.line, self.column))
        
        return self.tokens
    
    def has_errors(self) -> bool:
        """Check if any errors occurred during tokenization"""
        return len(self.errors) > 0
    
    def format_errors(self) -> str:
        """Format all errors for display"""
        lines = []
        for err in self.errors:
            lines.append(f"{self.filename}:{err.line}:{err.column}: error: {err.message}")
        return '\n'.join(lines)


def tokenize(source: str, filename: str = "<stdin>") -> tuple[List[Token], List[LexerError]]:
    """
    Convenience function to tokenize source code.
    
    Returns:
        Tuple of (tokens, errors)
    """
    lexer = Lexer(source, filename)
    tokens = lexer.tokenize()
    return tokens, lexer.errors


# For testing
if __name__ == "__main__":
    test_source = '''
fn main() {
    let x = 42;
    print("Hello", x);
    // This is a comment
    if (x > 0) {
        print("positive");
    }
}
'''
    tokens, errors = tokenize(test_source)
    for tok in tokens:
        print(tok)
    if errors:
        print("\nErrors:")
        for err in errors:
            print(f"  {err}")
