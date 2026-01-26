"""
Mock LLM Backend Adapter

Provides a mock LLM backend for testing without API calls.
Returns configurable responses with simulated latency.

Paper Reference: Section 3.1 - LLM Core
"""

import asyncio
import random
import time
from typing import AsyncIterator, Dict, List, Optional

from aios.core.adapters.base import (
    LLMBackend,
    LLMGenerationConfig,
    LLMGenerationResult,
    LLMMessage,
    StreamChunk,
)


class MockAdapter(LLMBackend):
    """
    Mock LLM backend for testing.
    
    Provides configurable mock responses without making actual API calls.
    Useful for unit tests, development, and benchmarking without costs.
    
    Example:
        adapter = MockAdapter(
            model="mock-model",
            default_response="This is a mock response.",
            latency_ms=100
        )
        await adapter.initialize()
        result = await adapter.chat([
            LLMMessage(role="user", content="Hello!")
        ])
        assert result.content == "This is a mock response."
    """
    
    # Pre-defined responses for common patterns
    DEFAULT_RESPONSES: Dict[str, str] = {
        "hello": "Hello! I'm a mock LLM. How can I help you today?",
        "help": "I'm a mock LLM for testing purposes. I can respond to basic queries.",
        "weather": "I cannot check real weather, but the mock weather is always sunny!",
        "code": "```python\ndef hello():\n    print('Hello, World!')\n```",
        "math": "The answer to your math question is 42.",
        "default": "This is a mock response from the AIOS test LLM backend.",
    }
    
    def __init__(
        self,
        model: str = "mock-model",
        default_response: Optional[str] = None,
        latency_ms: float = 50,
        tokens_per_second: float = 100,
        error_rate: float = 0.0,
        responses: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """
        Initialize mock adapter.
        
        Args:
            model: Model name (for identification)
            default_response: Default response for all queries
            latency_ms: Simulated latency in milliseconds
            tokens_per_second: Simulated generation speed for streaming
            error_rate: Probability of raising an error (0.0-1.0)
            responses: Custom response mapping (keyword -> response)
            **kwargs: Additional configuration
        """
        super().__init__(model, **kwargs)
        self.default_response = default_response
        self.latency_ms = latency_ms
        self.tokens_per_second = tokens_per_second
        self.error_rate = error_rate
        self.responses = {**self.DEFAULT_RESPONSES, **(responses or {})}
        
        # Tracking for tests
        self.call_count = 0
        self.last_messages: List[LLMMessage] = []
        self.last_config: Optional[LLMGenerationConfig] = None
    
    async def initialize(self) -> None:
        """Initialize the mock adapter."""
        self._is_initialized = True
    
    async def shutdown(self) -> None:
        """Shutdown the mock adapter."""
        self._is_initialized = False
    
    def _get_response(self, prompt: str) -> str:
        """Get appropriate response based on prompt content."""
        prompt_lower = prompt.lower()
        
        # Check for keyword matches
        for keyword, response in self.responses.items():
            if keyword in prompt_lower:
                return response
        
        # Return default or fallback
        return self.default_response or self.responses["default"]
    
    def _maybe_raise_error(self) -> None:
        """Raise an error based on error_rate."""
        if self.error_rate > 0 and random.random() < self.error_rate:
            raise RuntimeError("Mock LLM simulated error")
    
    async def _simulate_latency(self) -> None:
        """Simulate API latency."""
        if self.latency_ms > 0:
            await asyncio.sleep(self.latency_ms / 1000)
    
    async def generate(
        self,
        prompt: str,
        config: Optional[LLMGenerationConfig] = None,
    ) -> LLMGenerationResult:
        """Generate text completion from a prompt."""
        messages = [LLMMessage(role="user", content=prompt)]
        return await self.chat(messages, config)
    
    async def chat(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMGenerationConfig] = None,
    ) -> LLMGenerationResult:
        """
        Generate mock chat completion.
        
        Args:
            messages: List of conversation messages
            config: Generation configuration
            
        Returns:
            LLMGenerationResult with mock response
        """
        self._maybe_raise_error()
        
        # Track call for testing
        self.call_count += 1
        self.last_messages = messages
        self.last_config = config
        
        # Simulate latency
        start_time = time.time()
        await self._simulate_latency()
        
        # Get response based on last user message
        user_messages = [m for m in messages if m.role == "user"]
        prompt = user_messages[-1].content if user_messages else ""
        response_text = self._get_response(prompt)
        
        # Respect max_tokens if set
        config = config or LLMGenerationConfig()
        tokens = response_text.split()
        max_tokens = config.max_tokens or len(tokens)
        if len(tokens) > max_tokens:
            response_text = " ".join(tokens[:max_tokens])
        
        generation_time_ms = (time.time() - start_time) * 1000
        
        # Simulate token counts
        prompt_tokens = sum(len(m.content.split()) for m in messages)
        completion_tokens = len(response_text.split())
        
        return LLMGenerationResult(
            content=response_text,
            finish_reason="stop",
            tool_calls=[],
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            model=self.model,
            generation_time_ms=generation_time_ms,
        )
    
    async def chat_stream(
        self,
        messages: List[LLMMessage],
        config: Optional[LLMGenerationConfig] = None,
    ) -> AsyncIterator[StreamChunk]:
        """
        Stream mock chat completion.
        
        Yields tokens one at a time with simulated delays.
        """
        self._maybe_raise_error()
        
        # Track call for testing
        self.call_count += 1
        self.last_messages = messages
        self.last_config = config
        
        # Initial latency
        await self._simulate_latency()
        
        # Get response
        user_messages = [m for m in messages if m.role == "user"]
        prompt = user_messages[-1].content if user_messages else ""
        response_text = self._get_response(prompt)
        
        # Stream tokens
        tokens = response_text.split()
        delay_per_token = 1.0 / self.tokens_per_second if self.tokens_per_second > 0 else 0
        
        for i, token in enumerate(tokens):
            is_final = i == len(tokens) - 1
            
            # Add space before token (except first)
            content = token if i == 0 else " " + token
            
            yield StreamChunk(
                content=content,
                is_final=is_final,
                finish_reason="stop" if is_final else None,
            )
            
            if not is_final and delay_per_token > 0:
                await asyncio.sleep(delay_per_token)
    
    async def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.
        
        Uses simple word-based tokenization for mock.
        """
        return len(text.split())
    
    def reset_tracking(self) -> None:
        """Reset call tracking for tests."""
        self.call_count = 0
        self.last_messages = []
        self.last_config = None

