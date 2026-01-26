"""
Abstract LLM Backend Interface

Provides the base class for all LLM backend implementations.
This abstraction allows AIOS to work with different LLM providers
(OpenAI, HuggingFace, local models, etc.) through a unified interface.

Paper Reference: Section 3.1 - LLM Core
Design Decision: Assumption A2 in Assumptions.md
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional, Union
from enum import Enum
import time


class MessageRole(str, Enum):
    """Roles for chat messages."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class LLMMessage:
    """
    A single message in a chat conversation.
    
    Attributes:
        role: The role of the message sender
        content: The text content of the message
        name: Optional name for the sender (used with tool messages)
        tool_calls: Optional list of tool calls made by the assistant
        tool_call_id: ID of the tool call this message responds to
    """
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls."""
        result = {
            "role": self.role.value if isinstance(self.role, MessageRole) else self.role,
            "content": self.content,
        }
        if self.name:
            result["name"] = self.name
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMMessage":
        """Create from dictionary."""
        role = data.get("role", "user")
        if isinstance(role, str):
            try:
                role = MessageRole(role)
            except ValueError:
                role = MessageRole.USER
        return cls(
            role=role,
            content=data.get("content", ""),
            name=data.get("name"),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
        )


@dataclass
class LLMGenerationConfig:
    """
    Configuration for LLM text generation.
    
    Attributes:
        max_tokens: Maximum number of tokens to generate
        temperature: Sampling temperature (0.0 = deterministic, 1.0+ = creative)
        top_p: Nucleus sampling parameter
        stop_sequences: Sequences that stop generation
        stream: Whether to stream tokens as they're generated
    """
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 1.0
    stop_sequences: List[str] = field(default_factory=list)
    stream: bool = False
    tools: List[Dict[str, Any]] = field(default_factory=list)
    tool_choice: Optional[str] = None  # "auto", "none", or specific tool name


@dataclass
class LLMGenerationResult:
    """
    Result of LLM text generation.
    
    Attributes:
        content: The generated text
        finish_reason: Why generation stopped (stop, length, tool_calls)
        tool_calls: Any tool calls made by the model
        usage: Token usage statistics
        model: The model that generated this response
        generation_time_ms: Time taken to generate
    """
    content: str
    finish_reason: str = "stop"
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    generation_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "finish_reason": self.finish_reason,
            "tool_calls": self.tool_calls,
            "usage": self.usage,
            "model": self.model,
            "generation_time_ms": self.generation_time_ms,
        }


@dataclass
class StreamChunk:
    """A chunk of streamed generation output."""
    content: str
    is_final: bool = False
    finish_reason: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None


class LLMBackend(ABC):
    """
    Abstract base class for LLM backends.
    
    All LLM providers (OpenAI, HuggingFace, local models) implement this
    interface to provide consistent behavior across the AIOS kernel.
    
    Paper Reference: Section 3.1 - LLM cores abstract LLM as resources
    """
    
    def __init__(self, model: str, **kwargs):
        """
        Initialize the backend.
        
        Args:
            model: The model identifier (e.g., "gpt-4", "llama-2-7b")
            **kwargs: Backend-specific configuration
        """
        self.model = model
        self.config = kwargs
        self._is_initialized = False
    
    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the backend (load model, connect to API, etc.).
        Called once when the LLM core starts.
        """
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """
        Shutdown the backend (unload model, close connections, etc.).
        Called when the LLM core stops.
        """
        pass
    
    @abstractmethod
    async def generate(
        self,
        prompt: str,
        config: Optional[LLMGenerationConfig] = None,
    ) -> LLMGenerationResult:
        """
        Generate text completion from a prompt.
        
        Args:
            prompt: The input prompt text
            config: Generation configuration
            
        Returns:
            LLMGenerationResult with generated text
        """
        pass
    
    @abstractmethod
    async def chat(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMGenerationConfig] = None,
    ) -> LLMGenerationResult:
        """
        Generate a chat completion from a conversation.
        
        Args:
            messages: List of conversation messages
            config: Generation configuration
            
        Returns:
            LLMGenerationResult with assistant's response
        """
        pass
    
    async def generate_stream(
        self,
        prompt: str,
        config: Optional[LLMGenerationConfig] = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream text generation from a prompt.
        
        Default implementation calls generate() and yields the result.
        Backends can override for true streaming support.
        
        Args:
            prompt: The input prompt text
            config: Generation configuration
            
        Yields:
            StreamChunk with generated tokens
        """
        result = await self.generate(prompt, config)
        yield StreamChunk(
            content=result.content,
            is_final=True,
            finish_reason=result.finish_reason,
        )
    
    async def chat_stream(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMGenerationConfig] = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream chat completion from a conversation.
        
        Default implementation calls chat() and yields the result.
        Backends can override for true streaming support.
        
        Args:
            messages: List of conversation messages
            config: Generation configuration
            
        Yields:
            StreamChunk with generated tokens
        """
        result = await self.chat(messages, config)
        yield StreamChunk(
            content=result.content,
            is_final=True,
            finish_reason=result.finish_reason,
            tool_calls=result.tool_calls if result.tool_calls else None,
        )
    
    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in a text.
        
        Args:
            text: The text to tokenize
            
        Returns:
            Number of tokens
        """
        pass
    
    @property
    def is_initialized(self) -> bool:
        """Whether the backend has been initialized."""
        return self._is_initialized
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model={self.model!r})"

