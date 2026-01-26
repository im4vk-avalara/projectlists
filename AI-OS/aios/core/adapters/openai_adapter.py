"""
OpenAI Backend Adapter

Implements the LLMBackend interface for OpenAI's API.
Supports GPT-4, GPT-3.5, and other OpenAI models.

Paper Reference: Section 3.1 - LLM Core
"""

import os
import time
from typing import AsyncIterator, List, Optional

from aios.core.adapters.base import (
    LLMBackend,
    LLMGenerationConfig,
    LLMGenerationResult,
    LLMMessage,
    StreamChunk,
)

try:
    import openai
    from openai import AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class OpenAIAdapter(LLMBackend):
    """
    OpenAI API backend adapter.
    
    Provides access to OpenAI's GPT models through the AIOS LLM Core interface.
    
    Example:
        adapter = OpenAIAdapter(model="gpt-4o-mini")
        await adapter.initialize()
        result = await adapter.chat([
            LLMMessage(role="user", content="Hello!")
        ])
        print(result.content)
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize OpenAI adapter.
        
        Args:
            model: OpenAI model name (e.g., "gpt-4", "gpt-4o-mini")
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            base_url: Custom API base URL (for compatible APIs)
            organization: OpenAI organization ID
            **kwargs: Additional configuration
        """
        super().__init__(model, **kwargs)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url
        self.organization = organization
        self._client: Optional[AsyncOpenAI] = None
    
    async def initialize(self) -> None:
        """Initialize the OpenAI client."""
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai package not installed. Install with: pip install openai"
            )
        
        if not self.api_key:
            raise ValueError(
                "OpenAI API key not provided. Set OPENAI_API_KEY environment variable "
                "or pass api_key to constructor."
            )
        
        self._client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            organization=self.organization,
        )
        self._is_initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown the OpenAI client."""
        if self._client:
            await self._client.close()
        self._client = None
        self._is_initialized = False
    
    async def generate(
        self,
        prompt: str,
        config: Optional[LLMGenerationConfig] = None,
    ) -> LLMGenerationResult:
        """
        Generate text completion from a prompt.
        
        Uses chat completions API with a single user message.
        """
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat(messages, config)
    
    async def chat(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMGenerationConfig] = None,
    ) -> LLMGenerationResult:
        """
        Generate chat completion from a conversation.
        
        Args:
            messages: List of conversation messages
            config: Generation configuration
            
        Returns:
            LLMGenerationResult with assistant's response
        """
        if not self._client:
            raise RuntimeError("OpenAI adapter not initialized. Call initialize() first.")
        
        config = config or LLMGenerationConfig()
        
        # Convert messages to OpenAI format
        openai_messages = [msg.to_dict() for msg in messages]
        
        # Build request parameters
        request_params = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
        }
        
        if config.stop_sequences:
            request_params["stop"] = config.stop_sequences
        
        if config.tools:
            request_params["tools"] = config.tools
            if config.tool_choice:
                request_params["tool_choice"] = config.tool_choice
        
        # Make API call
        start_time = time.time()
        response = await self._client.chat.completions.create(**request_params)
        generation_time_ms = (time.time() - start_time) * 1000
        
        # Extract response
        choice = response.choices[0]
        message = choice.message
        
        # Extract tool calls if present
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append({
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                })
        
        return LLMGenerationResult(
            content=message.content or "",
            finish_reason=choice.finish_reason or "stop",
            tool_calls=tool_calls,
            usage={
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            model=response.model,
            generation_time_ms=generation_time_ms,
        )
    
    async def chat_stream(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMGenerationConfig] = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream chat completion from a conversation.
        
        Yields tokens as they are generated by the model.
        """
        if not self._client:
            raise RuntimeError("OpenAI adapter not initialized. Call initialize() first.")
        
        config = config or LLMGenerationConfig()
        
        # Convert messages to OpenAI format
        openai_messages = [msg.to_dict() for msg in messages]
        
        # Build request parameters
        request_params = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
            "top_p": config.top_p,
            "stream": True,
        }
        
        if config.stop_sequences:
            request_params["stop"] = config.stop_sequences
        
        # Make streaming API call
        stream = await self._client.chat.completions.create(**request_params)
        
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta:
                delta = chunk.choices[0].delta
                content = delta.content or ""
                finish_reason = chunk.choices[0].finish_reason
                
                yield StreamChunk(
                    content=content,
                    is_final=finish_reason is not None,
                    finish_reason=finish_reason,
                )
    
    async def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.
        
        Uses tiktoken for accurate token counting.
        """
        try:
            import tiktoken
            
            # Get encoding for the model
            try:
                encoding = tiktoken.encoding_for_model(self.model)
            except KeyError:
                # Fallback to cl100k_base for unknown models
                encoding = tiktoken.get_encoding("cl100k_base")
            
            return len(encoding.encode(text))
        except ImportError:
            # Rough estimate if tiktoken not available
            return len(text) // 4

