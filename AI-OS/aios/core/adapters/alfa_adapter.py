"""
Alfa LLM Adapter

Adapter for Alfa LLM proxy service.
Uses OpenAI-compatible API with custom base URL.

Configuration:
    - ALFA_CLAIM: Project UUID from Alfa onboarding
    - ALFA_ENV: Environment (qa, prod, etc.) - defaults to "qa"
"""

import os
import logging
from typing import Any, Dict, List, Optional

from aios.core.adapters.base import LLMBackend

logger = logging.getLogger(__name__)


class AlfaAdapter(LLMBackend):
    """
    Adapter for Alfa LLM proxy.
    
    Alfa is internal LLM proxy that provides access to
    various models (Claude, GPT, etc.) through an OpenAI-compatible API.
    
    Example:
        adapter = AlfaAdapter(
            model="claude-4-sonnet",
            alfa_claim="your-project-uuid",
            alfa_env="qa",
        )
        await adapter.initialize()
        result = await adapter.generate("Hello!")
    """
    
    # Available models via Alfa
    SUPPORTED_MODELS = [
        "claude-4-sonnet",
        "claude-3-5-sonnet",
        "claude-3-opus",
        "gpt-5",
        "gpt-4o",
        "gpt-4o-mini",
    ]
    
    def __init__(
        self,
        model: str = "claude-4-sonnet",
        alfa_claim: Optional[str] = None,
        alfa_env: str = "qa",
        **kwargs,
    ):
        """
        Initialize Alfa adapter.
        
        Args:
            model: Model name (e.g., "claude-4-sonnet", "gpt-5")
            alfa_claim: Alfa project UUID (or set ALFA_CLAIM env var)
            alfa_env: Alfa environment (qa, prod, etc.)
            **kwargs: Additional OpenAI client options
        """
        self.model = model
        self.alfa_claim = alfa_claim or os.getenv("ALFA_CLAIM")
        self.alfa_env = alfa_env
        self.kwargs = kwargs
        
        self._client = None
        self._initialized = False
        self._request_count = 0
        self._total_tokens = 0
    
    @property
    def base_url(self) -> str:
        """Get the Alfa proxy URL."""
        return f"http://alfa.gamma.{self.alfa_env}.us-west-2.aws.<company>.io"
    
    async def initialize(self) -> None:
        """Initialize the OpenAI client with Alfa configuration."""
        if self._initialized:
            return
        
        if not self.alfa_claim:
            raise ValueError(
                "ALFA_CLAIM not set. Provide alfa_claim parameter or set ALFA_CLAIM env var."
            )
        
        try:
            import openai
            
            self._client = openai.AsyncOpenAI(
                api_key=f"sk-{self.alfa_claim}",
                base_url=self.base_url,
                **self.kwargs,
            )
            
            self._initialized = True
            logger.info(
                f"Alfa adapter initialized: model={self.model}, env={self.alfa_env}"
            )
            
        except ImportError:
            raise ImportError("openai package required. Install with: pip install openai")
    
    async def generate(
        self,
        prompt: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        stop: Optional[List[str]] = None,
        **kwargs,
    ) -> str:
        """Generate text completion via Alfa."""
        if not self._initialized:
            await self.initialize()
        
        messages = [{"role": "user", "content": prompt}]
        
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            params["max_tokens"] = max_tokens
        if stop:
            params["stop"] = stop
        
        params.update(kwargs)
        
        try:
            response = await self._client.chat.completions.create(**params)
            
            self._request_count += 1
            if response.usage:
                self._total_tokens += response.usage.total_tokens
            
            return response.choices[0].message.content or ""
            
        except Exception as e:
            logger.error(f"Alfa generate error: {e}")
            raise
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Chat completion via Alfa."""
        if not self._initialized:
            await self.initialize()
        
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            params["max_tokens"] = max_tokens
        if tools:
            params["tools"] = tools
        
        params.update(kwargs)
        
        try:
            response = await self._client.chat.completions.create(**params)
            
            self._request_count += 1
            if response.usage:
                self._total_tokens += response.usage.total_tokens
            
            choice = response.choices[0]
            result = {
                "content": choice.message.content or "",
                "role": choice.message.role,
                "finish_reason": choice.finish_reason,
            }
            
            # Handle tool calls if present
            if choice.message.tool_calls:
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": tc.type,
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in choice.message.tool_calls
                ]
            
            return result
            
        except Exception as e:
            logger.error(f"Alfa chat error: {e}")
            raise
    
    async def count_tokens(self, text: str) -> int:
        """Estimate token count."""
        # Rough estimation: ~4 characters per token
        return len(text) // 4
    
    def get_stats(self) -> Dict[str, Any]:
        """Get adapter statistics."""
        return {
            "model": self.model,
            "backend": "alfa",
            "environment": self.alfa_env,
            "base_url": self.base_url,
            "initialized": self._initialized,
            "request_count": self._request_count,
            "total_tokens": self._total_tokens,
        }
    
    async def shutdown(self) -> None:
        """Shutdown the adapter."""
        if self._client:
            await self._client.close()
        self._initialized = False
        logger.info("Alfa adapter shut down")
    
    def __repr__(self) -> str:
        return f"AlfaAdapter(model='{self.model}', env='{self.alfa_env}')"

