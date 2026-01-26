"""
LLM Backend Adapters

Provides unified interface for different LLM backends.
Paper Reference: Section 3.1
"""

from aios.core.adapters.base import LLMBackend, LLMMessage, LLMGenerationConfig
from aios.core.adapters.openai_adapter import OpenAIAdapter
from aios.core.adapters.mock_adapter import MockAdapter
from aios.core.adapters.alfa_adapter import AlfaAdapter

__all__ = [
    "LLMBackend",
    "LLMMessage",
    "LLMGenerationConfig",
    "OpenAIAdapter",
    "MockAdapter",
    "AlfaAdapter",
]

