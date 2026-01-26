"""
Unit tests for the ToyLang lexer
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lexer import Lexer, TokenType, tokenize


def test_empty_input():
    """Empty input produces only EOF"""
    tokens, errors = tokenize("")
    assert len(tokens) == 1
    assert tokens[0].type == TokenType.EOF
    assert not errors


def test_simple_tokens():
    """Basic operators and delimiters"""
    source = "+ - * / % ( ) { } , ; = < >"
    tokens, errors = tokenize(source)
    
    expected = [
        TokenType.PLUS, TokenType.MINUS, TokenType.STAR, TokenType.SLASH,
        TokenType.PERCENT, TokenType.LPAREN, TokenType.RPAREN,
        TokenType.LBRACE, TokenType.RBRACE, TokenType.COMMA, TokenType.SEMI,
        TokenType.ASSIGN, TokenType.LT, TokenType.GT, TokenType.EOF
    ]
    
    assert len(tokens) == len(expected)
    for tok, exp in zip(tokens, expected):
        assert tok.type == exp, f"Expected {exp}, got {tok.type}"
    assert not errors


def test_two_char_operators():
    """Two-character operators"""
    source = "== != <= >= && ||"
    tokens, errors = tokenize(source)
    
    expected = [
        TokenType.EQ, TokenType.NE, TokenType.LE, TokenType.GE,
        TokenType.AND, TokenType.OR, TokenType.EOF
    ]
    
    assert len(tokens) == len(expected)
    for tok, exp in zip(tokens, expected):
        assert tok.type == exp
    assert not errors


def test_keywords():
    """All keywords are recognized"""
    source = "fn let if else while return print true false"
    tokens, errors = tokenize(source)
    
    expected = [
        TokenType.FN, TokenType.LET, TokenType.IF, TokenType.ELSE,
        TokenType.WHILE, TokenType.RETURN, TokenType.PRINT,
        TokenType.TRUE, TokenType.FALSE, TokenType.EOF
    ]
    
    assert len(tokens) == len(expected)
    for tok, exp in zip(tokens, expected):
        assert tok.type == exp
    assert not errors


def test_identifiers():
    """Identifiers that aren't keywords"""
    source = "foo bar _test test123 myVar"
    tokens, errors = tokenize(source)
    
    # All should be IDENT
    assert all(t.type == TokenType.IDENT for t in tokens[:-1])
    assert tokens[-1].type == TokenType.EOF
    
    values = [t.value for t in tokens[:-1]]
    assert values == ["foo", "bar", "_test", "test123", "myVar"]
    assert not errors


def test_integers():
    """Integer literals"""
    source = "0 42 123 999999"
    tokens, errors = tokenize(source)
    
    assert all(t.type == TokenType.INTEGER for t in tokens[:-1])
    values = [t.value for t in tokens[:-1]]
    assert values == ["0", "42", "123", "999999"]
    assert not errors


def test_strings():
    """String literals"""
    source = '"hello" "world" "with spaces"'
    tokens, errors = tokenize(source)
    
    assert all(t.type == TokenType.STRING for t in tokens[:-1])
    values = [t.value for t in tokens[:-1]]
    assert values == ["hello", "world", "with spaces"]
    assert not errors


def test_string_escapes():
    """Escape sequences in strings"""
    source = r'"hello\nworld" "tab\there" "quote\"here"'
    tokens, errors = tokenize(source)
    
    assert tokens[0].value == "hello\nworld"
    assert tokens[1].value == "tab\there"
    assert tokens[2].value == 'quote"here'
    assert not errors


def test_comments():
    """Single-line comments are skipped"""
    source = """
    let x = 5; // This is a comment
    // Another comment
    let y = 10;
    """
    tokens, errors = tokenize(source)
    
    types = [t.type for t in tokens]
    assert TokenType.LET in types
    assert types.count(TokenType.LET) == 2
    assert not errors


def test_line_tracking():
    """Line numbers are tracked correctly"""
    source = """fn main() {
    let x = 5;
}"""
    tokens, errors = tokenize(source)
    
    # 'fn' is on line 1
    assert tokens[0].line == 1
    # 'let' is on line 2
    let_token = [t for t in tokens if t.type == TokenType.LET][0]
    assert let_token.line == 2
    assert not errors


def test_column_tracking():
    """Column numbers are tracked correctly"""
    source = "fn main() {"
    tokens, errors = tokenize(source)
    
    # 'fn' starts at column 1
    assert tokens[0].column == 1
    # 'main' starts at column 4
    assert tokens[1].column == 4
    assert not errors


def test_unterminated_string():
    """Unterminated string produces error"""
    source = '"hello'
    tokens, errors = tokenize(source)
    
    assert len(errors) == 1
    assert "Unterminated" in str(errors[0])


def test_unexpected_character():
    """Unexpected characters produce errors"""
    source = "let x = @;"
    tokens, errors = tokenize(source)
    
    assert len(errors) == 1
    assert "Unexpected character" in str(errors[0])


def test_complete_function():
    """Tokenize a complete function"""
    source = """
fn add(a, b) {
    return a + b;
}
"""
    tokens, errors = tokenize(source)
    
    assert not errors
    types = [t.type for t in tokens]
    
    assert TokenType.FN in types
    assert TokenType.IDENT in types
    assert TokenType.LPAREN in types
    assert TokenType.RETURN in types
    assert TokenType.PLUS in types


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
