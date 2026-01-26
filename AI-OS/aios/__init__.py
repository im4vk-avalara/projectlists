"""
AIOS: LLM Agent Operating System

A kernel-level architecture for managing LLM-based agents with:
- Centralized scheduling (FIFO/Round Robin)
- Context management for LLM generation
- Memory and storage management
- Tool orchestration
- Access control

Paper Reference: arXiv:2403.16971v5
"""

__version__ = "0.1.0"
__author__ = "AIOS Implementation"

from aios.sdk.client import AIOSClient
from aios.sdk.models import (
    Query,
    Response,
    LLMQuery,
    LLMResponse,
    MemoryQuery,
    MemoryResponse,
    StorageQuery,
    StorageResponse,
    ToolQuery,
    ToolResponse,
)

__all__ = [
    "AIOSClient",
    "Query",
    "Response",
    "LLMQuery",
    "LLMResponse",
    "MemoryQuery",
    "MemoryResponse",
    "StorageQuery",
    "StorageResponse",
    "ToolQuery",
    "ToolResponse",
]

