"""
LLM Client wrapper for Alfa proxy.
Provides a clean interface for chat completions using the Alfa gateway.
"""

from typing import Optional, List, Dict, Any
import openai
from ..config import config


class LLMClient:
    """
    LLM client that uses Alfa proxy for chat completions.
    Supports Claude and GPT models through the unified interface.
    """
    
    def __init__(self, model: Optional[str] = None):
        """
        Initialize LLM client.
        
        Args:
            model: Model to use. Defaults to config.default_model.
        """
        self.model = model or config.default_model
        self._client = openai.OpenAI(
            api_key=config.alfa.api_key,
            base_url=config.alfa.base_url
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Send a chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature (0-1).
            max_tokens: Maximum tokens in response.
            **kwargs: Additional parameters passed to the API.
            
        Returns:
            The assistant's response content.
        """
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            **kwargs
        }
        if max_tokens:
            params["max_tokens"] = max_tokens
            
        response = self._client.chat.completions.create(**params)
        return response.choices[0].message.content
    
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """
        Simple completion with a single prompt.
        
        Args:
            prompt: The user prompt.
            system_prompt: Optional system prompt.
            temperature: Sampling temperature.
            **kwargs: Additional parameters.
            
        Returns:
            The assistant's response content.
        """
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        return self.chat(messages, temperature=temperature, **kwargs)
    
    def complete_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3,
        **kwargs
    ) -> str:
        """
        Completion expecting JSON output. Uses lower temperature for consistency.
        
        Args:
            prompt: The user prompt (should ask for JSON output).
            system_prompt: Optional system prompt.
            temperature: Sampling temperature (default lower for JSON).
            **kwargs: Additional parameters.
            
        Returns:
            The assistant's response (should be JSON string).
        """
        json_system = (system_prompt or "") + (
            "\n\nYou must respond with valid JSON only. "
            "No markdown, no explanation, just the JSON object."
        )
        return self.complete(
            prompt, 
            system_prompt=json_system.strip(),
            temperature=temperature,
            **kwargs
        )


# Convenience function for quick completions
def quick_complete(prompt: str, model: Optional[str] = None) -> str:
    """Quick one-off completion without creating a client instance."""
    client = LLMClient(model=model)
    return client.complete(prompt)

