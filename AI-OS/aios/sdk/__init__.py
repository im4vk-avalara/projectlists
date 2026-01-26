"""
AIOS SDK (Cerebrum)

Provides the client-side interface for agents to communicate with the AIOS kernel.
Includes Query/Response models and API client.

Paper Reference: Section 3.2, Figure 9
"""

from aios.sdk.client import AIOSClient
from aios.sdk.models import (
    Query,
    Response,
    ResponseStatus,
    QueryType,
    LLMQuery,
    LLMResponse,
    MemoryQuery,
    MemoryResponse,
    MemoryOperation,
    StorageQuery,
    StorageResponse,
    StorageOperation,
    ToolQuery,
    ToolResponse,
    ToolOperation,
    ContextQuery,
    ContextResponse,
    ContextOperation,
    AccessQuery,
    AccessResponse,
    AccessOperation,
)

__all__ = [
    # Client
    "AIOSClient",
    # Base models
    "Query",
    "Response",
    "ResponseStatus",
    "QueryType",
    # LLM
    "LLMQuery",
    "LLMResponse",
    # Memory
    "MemoryQuery",
    "MemoryResponse",
    "MemoryOperation",
    # Storage
    "StorageQuery",
    "StorageResponse",
    "StorageOperation",
    # Tool
    "ToolQuery",
    "ToolResponse",
    "ToolOperation",
    # Context
    "ContextQuery",
    "ContextResponse",
    "ContextOperation",
    # Access
    "AccessQuery",
    "AccessResponse",
    "AccessOperation",
]

