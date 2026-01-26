"""
Tests for LLM Core Module

Tests the LLM Core abstraction and adapters.
Paper Reference: Section 3.1
"""

import pytest
import asyncio

from aios.core.llm import LLMCore, LLMCoreManager, CoreStatus
from aios.core.adapters.base import LLMMessage, LLMGenerationConfig, MessageRole
from aios.core.adapters.mock_adapter import MockAdapter


class TestLLMMessage:
    """Tests for LLMMessage class."""
    
    def test_create_message(self):
        """Test creating a message."""
        msg = LLMMessage(role=MessageRole.USER, content="Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"
    
    def test_to_dict(self):
        """Test converting message to dict."""
        msg = LLMMessage(role=MessageRole.ASSISTANT, content="Hi there")
        d = msg.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Hi there"
    
    def test_from_dict(self):
        """Test creating message from dict."""
        msg = LLMMessage.from_dict({"role": "user", "content": "Test"})
        assert msg.role == MessageRole.USER
        assert msg.content == "Test"


class TestMockAdapter:
    """Tests for Mock LLM Adapter."""
    
    @pytest.fixture
    async def adapter(self) -> MockAdapter:
        """Create and initialize mock adapter."""
        adapter = MockAdapter(
            model="test-model",
            default_response="Test response",
            latency_ms=1,
        )
        await adapter.initialize()
        yield adapter
        await adapter.shutdown()
    
    @pytest.mark.asyncio
    async def test_initialize(self, adapter: MockAdapter):
        """Test adapter initialization."""
        assert adapter.is_initialized
    
    @pytest.mark.asyncio
    async def test_generate(self, adapter: MockAdapter):
        """Test text generation."""
        result = await adapter.generate("Generate something")
        assert result.content is not None
        assert len(result.content) > 0
        assert result.finish_reason == "stop"
    
    @pytest.mark.asyncio
    async def test_chat(self, adapter: MockAdapter):
        """Test chat completion."""
        messages = [
            LLMMessage(role=MessageRole.USER, content="Generate something"),
        ]
        result = await adapter.chat(messages)
        assert result.content is not None
        assert len(result.content) > 0
    
    @pytest.mark.asyncio
    async def test_keyword_response(self, adapter: MockAdapter):
        """Test keyword-based responses."""
        messages = [
            LLMMessage(role=MessageRole.USER, content="Can you help me?"),
        ]
        result = await adapter.chat(messages)
        # The mock adapter returns different responses based on keywords
        assert len(result.content) > 0
    
    @pytest.mark.asyncio
    async def test_count_tokens(self, adapter: MockAdapter):
        """Test token counting."""
        count = await adapter.count_tokens("Hello world test")
        assert count == 3  # Word-based counting
    
    @pytest.mark.asyncio
    async def test_tracking(self, adapter: MockAdapter):
        """Test call tracking."""
        adapter.reset_tracking()
        assert adapter.call_count == 0
        
        await adapter.generate("Test")
        assert adapter.call_count == 1
        
        await adapter.chat([LLMMessage(role=MessageRole.USER, content="Test")])
        assert adapter.call_count == 2


class TestLLMCore:
    """Tests for LLMCore class."""
    
    @pytest.mark.asyncio
    async def test_create_core(self):
        """Test creating an LLM core."""
        adapter = MockAdapter(model="test")
        core = LLMCore(name="test-core", backend=adapter)
        
        assert core.name == "test-core"
        assert core.status == CoreStatus.IDLE
        # Core is available when status is IDLE (even before explicit initialization)
        assert core.is_available
    
    @pytest.mark.asyncio
    async def test_initialize_core(self):
        """Test initializing a core."""
        adapter = MockAdapter(model="test")
        core = LLMCore(name="test-core", backend=adapter)
        
        await core.initialize()
        
        assert core.status == CoreStatus.IDLE
        assert core.is_available
        
        await core.shutdown()
    
    @pytest.mark.asyncio
    async def test_execute_request(self):
        """Test executing a request on a core."""
        adapter = MockAdapter(model="test", latency_ms=1)
        core = LLMCore(name="test-core", backend=adapter)
        await core.initialize()
        
        messages = [LLMMessage(role=MessageRole.USER, content="Hello")]
        result = await core.execute("agent-1", messages)
        
        assert result.content is not None
        assert core.request_count == 1
        
        await core.shutdown()


class TestLLMCoreManager:
    """Tests for LLMCoreManager class."""
    
    @pytest.fixture
    async def manager(self) -> LLMCoreManager:
        """Create a core manager."""
        mgr = LLMCoreManager()
        yield mgr
        await mgr.shutdown()
    
    @pytest.mark.asyncio
    async def test_add_core(self, manager: LLMCoreManager):
        """Test adding a core."""
        core = await manager.add_core(
            name="core-0",
            backend_type="mock",
            model="test-model",
        )
        
        assert core.name == "core-0"
        assert manager.core_count == 1
        assert manager.available_core_count == 1
    
    @pytest.mark.asyncio
    async def test_add_duplicate_core_fails(self, manager: LLMCoreManager):
        """Test that adding duplicate core fails."""
        await manager.add_core("core-0", "mock", "test")
        
        with pytest.raises(ValueError, match="already exists"):
            await manager.add_core("core-0", "mock", "test")
    
    @pytest.mark.asyncio
    async def test_remove_core(self, manager: LLMCoreManager):
        """Test removing a core."""
        await manager.add_core("core-0", "mock", "test")
        assert manager.core_count == 1
        
        await manager.remove_core("core-0")
        assert manager.core_count == 0
    
    @pytest.mark.asyncio
    async def test_execute_on_manager(self, manager: LLMCoreManager):
        """Test executing through manager."""
        await manager.add_core("core-0", "mock", "test")
        
        messages = [LLMMessage(role=MessageRole.USER, content="Hello")]
        result = await manager.execute("agent-1", messages)
        
        assert result.content is not None
    
    @pytest.mark.asyncio
    async def test_get_stats(self, manager: LLMCoreManager):
        """Test getting manager statistics."""
        await manager.add_core("core-0", "mock", "test")
        
        stats = manager.get_stats()
        
        assert stats["total_cores"] == 1
        assert stats["available_cores"] == 1
        assert "core-0" in stats["cores"]

