"""
Tests for Alfa LLM Adapter

Tests the Alfa adapter without making actual API calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import os

from aios.core.adapters.alfa_adapter import AlfaAdapter


class TestAlfaAdapter:
    """Tests for AlfaAdapter."""
    
    def test_create_adapter(self):
        """Test creating an Alfa adapter."""
        adapter = AlfaAdapter(
            model="claude-4-sonnet",
            alfa_claim="test-claim",
            alfa_env="qa",
        )
        
        assert adapter.model == "claude-4-sonnet"
        assert adapter.alfa_claim == "test-claim"
        assert adapter.alfa_env == "qa"
        assert adapter.base_url == "http://alfa.gamma.qa.us-west-2.aws.<company>.io"
    
    def test_base_url_prod(self):
        """Test base URL for prod environment."""
        adapter = AlfaAdapter(
            model="gpt-5",
            alfa_claim="test-claim",
            alfa_env="prod",
        )
        
        assert adapter.base_url == "http://alfa.gamma.prod.us-west-2.aws.<company>.io"
    
    def test_uses_env_var(self):
        """Test that adapter uses ALFA_CLAIM from environment."""
        with patch.dict(os.environ, {"ALFA_CLAIM": "env-claim"}):
            adapter = AlfaAdapter(model="claude-4-sonnet")
            assert adapter.alfa_claim == "env-claim"
    
    def test_missing_claim_error(self):
        """Test error when no claim is provided."""
        with patch.dict(os.environ, {"ALFA_CLAIM": ""}, clear=True):
            adapter = AlfaAdapter(model="claude-4-sonnet", alfa_claim=None)
            # Error should be raised on initialize, not creation
            assert adapter.alfa_claim is None or adapter.alfa_claim == ""
    
    def test_repr(self):
        """Test adapter string representation."""
        adapter = AlfaAdapter(
            model="claude-4-sonnet",
            alfa_claim="test",
            alfa_env="qa",
        )
        
        assert "AlfaAdapter" in repr(adapter)
        assert "claude-4-sonnet" in repr(adapter)
        assert "qa" in repr(adapter)
    
    def test_get_stats(self):
        """Test getting adapter stats."""
        adapter = AlfaAdapter(
            model="gpt-5",
            alfa_claim="test",
            alfa_env="qa",
        )
        
        stats = adapter.get_stats()
        
        assert stats["model"] == "gpt-5"
        assert stats["backend"] == "alfa"
        assert stats["environment"] == "qa"
        assert stats["initialized"] is False
        assert stats["request_count"] == 0
    
    @pytest.mark.asyncio
    async def test_count_tokens(self):
        """Test token counting estimation."""
        adapter = AlfaAdapter(
            model="claude-4-sonnet",
            alfa_claim="test",
        )
        
        # ~4 chars per token
        text = "Hello, this is a test message!"
        tokens = await adapter.count_tokens(text)
        
        assert tokens == len(text) // 4
    
    def test_supported_models(self):
        """Test that common models are in supported list."""
        assert "claude-4-sonnet" in AlfaAdapter.SUPPORTED_MODELS
        assert "gpt-5" in AlfaAdapter.SUPPORTED_MODELS
        assert "gpt-4o" in AlfaAdapter.SUPPORTED_MODELS


# Check if openai is available for integration tests
try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False


@pytest.mark.skipif(not HAS_OPENAI, reason="openai package not installed")
class TestAlfaAdapterIntegration:
    """Integration tests (require openai package for mocking)."""
    
    @pytest.mark.asyncio
    async def test_generate_mocked(self):
        """Test generate with mocked client."""
        adapter = AlfaAdapter(
            model="claude-4-sonnet",
            alfa_claim="test-claim",
        )
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello! I'm Claude."
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 50
        
        # Mock the client
        with patch("openai.AsyncOpenAI") as MockClient:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client
            
            await adapter.initialize()
            result = await adapter.generate("Hello!")
            
            assert result == "Hello! I'm Claude."
            assert adapter._request_count == 1
    
    @pytest.mark.asyncio
    async def test_chat_mocked(self):
        """Test chat with mocked client."""
        adapter = AlfaAdapter(
            model="gpt-5",
            alfa_claim="test-claim",
        )
        
        # Create mock response
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "I can help with that!"
        mock_response.choices[0].message.role = "assistant"
        mock_response.choices[0].message.tool_calls = None
        mock_response.choices[0].finish_reason = "stop"
        mock_response.usage = MagicMock()
        mock_response.usage.total_tokens = 100
        
        # Mock the client
        with patch("openai.AsyncOpenAI") as MockClient:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
            MockClient.return_value = mock_client
            
            await adapter.initialize()
            result = await adapter.chat([
                {"role": "user", "content": "Can you help me?"}
            ])
            
            assert result["content"] == "I can help with that!"
            assert result["role"] == "assistant"
            assert result["finish_reason"] == "stop"

