"""
ToyLang Compiler - A self-hosted compiler demonstration

This package contains the seed compiler written in Python.
It compiles ToyLang source code to C code.
"""

from .lexer import Lexer, Token, TokenType, tokenize
from .parser import Parser, parse
from .ast_nodes import *
from .analyzer import Analyzer, analyze
from .codegen import CodeGenerator, generate

__all__ = [
    'Lexer', 'Token', 'TokenType', 'tokenize',
    'Parser', 'parse',
    'Analyzer', 'analyze',
    'CodeGenerator', 'generate',
]
