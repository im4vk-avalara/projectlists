"""
Tests for SDK Module

Tests the AIOS SDK client and models.
Paper Reference: Section 3.2, Figure 9
"""

import pytest

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
    Message,
)
from aios.sdk.client import AIOSClient
from aios.kernel.aios_kernel import AIOSKernel, KernelConfig


class TestQueryModels:
    """Tests for Query models."""
    
    def test_base_query(self):
        """Test base Query creation."""
        query = Query(agent_id="test-agent")
        
        assert query.agent_id == "test-agent"
        assert query.query_type == QueryType.LLM
        assert query.query_id is not None
    
    def test_query_to_dict(self):
        """Test Query serialization."""
        query = Query(agent_id="test-agent")
        d = query.to_dict()
        
        assert d["agent_id"] == "test-agent"
        assert d["query_type"] == "llm"
        assert "query_id" in d
        assert "timestamp" in d
    
    def test_llm_query(self):
        """Test LLMQuery creation."""
        query = LLMQuery(
            agent_id="test-agent",
            messages=[Message(role="user", content="Hello")],
            max_tokens=100,
        )
        
        assert query.query_type == QueryType.LLM
        assert len(query.messages) == 1
        assert query.max_tokens == 100
    
    def test_llm_query_to_dict(self):
        """Test LLMQuery serialization."""
        query = LLMQuery(
            agent_id="test-agent",
            messages=[Message(role="user", content="Hello")],
        )
        d = query.to_dict()
        
        assert d["messages"][0]["role"] == "user"
        assert d["messages"][0]["content"] == "Hello"
    
    def test_memory_query(self):
        """Test MemoryQuery creation."""
        query = MemoryQuery(
            agent_id="test-agent",
            operation=MemoryOperation.WRITE,
            key="test-key",
            value={"data": "value"},
        )
        
        assert query.query_type == QueryType.MEMORY
        assert query.operation == MemoryOperation.WRITE
        assert query.key == "test-key"


class TestResponseModels:
    """Tests for Response models."""
    
    def test_base_response(self):
        """Test base Response creation."""
        response = Response(
            query_id="query-1",
            status=ResponseStatus.SUCCESS,
            data={"result": "test"},
        )
        
        assert response.query_id == "query-1"
        assert response.status == ResponseStatus.SUCCESS
        assert response.is_success
    
    def test_error_response(self):
        """Test error Response."""
        response = Response(
            query_id="query-1",
            status=ResponseStatus.ERROR,
            error="Something went wrong",
        )
        
        assert not response.is_success
        assert response.error == "Something went wrong"
    
    def test_llm_response(self):
        """Test LLMResponse creation."""
        response = LLMResponse(
            query_id="query-1",
            status=ResponseStatus.SUCCESS,
            content="Hello there!",
            finish_reason="stop",
            usage={"total_tokens": 10},
        )
        
        assert response.content == "Hello there!"
        assert response.finish_reason == "stop"
    
    def test_response_to_dict(self):
        """Test Response serialization."""
        response = Response(
            query_id="query-1",
            status=ResponseStatus.SUCCESS,
        )
        d = response.to_dict()
        
        assert d["query_id"] == "query-1"
        assert d["status"] == "success"


class TestMessage:
    """Tests for Message class."""
    
    def test_create_message(self):
        """Test creating a message."""
        msg = Message(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
    
    def test_message_with_tool_calls(self):
        """Test message with tool calls."""
        tool_calls = [{"id": "1", "function": {"name": "test"}}]
        msg = Message(role="assistant", content="", tool_calls=tool_calls)
        assert msg.tool_calls == tool_calls
    
    def test_message_to_dict(self):
        """Test message serialization."""
        msg = Message(role="user", content="Test")
        d = msg.to_dict()
        assert d == {"role": "user", "content": "Test"}


class TestAIOSClient:
    """Tests for AIOSClient class."""
    
    @pytest.fixture
    async def local_kernel(self) -> AIOSKernel:
        """Create a local kernel for testing."""
        config = KernelConfig()
        kernel = AIOSKernel(config=config)
        await kernel.start()
        yield kernel
        await kernel.stop()
    
    @pytest.fixture
    async def client(self, local_kernel: AIOSKernel) -> AIOSClient:
        """Create a client connected to local kernel."""
        c = AIOSClient(kernel=local_kernel, agent_id="test-agent")
        yield c
        await c.close()
    
    @pytest.mark.asyncio
    async def test_chat(self, client: AIOSClient):
        """Test chat API."""
        response = await client.chat([
            {"role": "user", "content": "Hello"}
        ])
        
        assert response.status == ResponseStatus.SUCCESS
        assert response.content is not None
    
    @pytest.mark.asyncio
    async def test_generate(self, client: AIOSClient):
        """Test generate convenience method."""
        response = await client.generate("Hello world")
        
        assert response.status == ResponseStatus.SUCCESS
    
    @pytest.mark.asyncio
    async def test_memory_write_and_read(self, client: AIOSClient):
        """Test memory write and read."""
        # Write
        write_response = await client.memory_write("test-key", {"value": 42})
        assert write_response.status == ResponseStatus.SUCCESS
        
        # Read
        read_response = await client.memory_read("test-key")
        assert read_response.status == ResponseStatus.SUCCESS
        assert read_response.data is not None
    
    @pytest.mark.asyncio
    async def test_memory_delete(self, client: AIOSClient):
        """Test memory delete."""
        # Write first
        await client.memory_write("delete-me", "value")
        
        # Delete
        delete_response = await client.memory_delete("delete-me")
        assert delete_response.status == ResponseStatus.SUCCESS
        
        # Verify deleted
        read_response = await client.memory_read("delete-me")
        assert read_response.status == ResponseStatus.NOT_FOUND
    
    @pytest.mark.asyncio
    async def test_memory_list(self, client: AIOSClient):
        """Test memory list."""
        # Write some keys
        await client.memory_write("prefix:key1", "value1")
        await client.memory_write("prefix:key2", "value2")
        await client.memory_write("other:key3", "value3")
        
        # List with prefix
        response = await client.memory_list("prefix:")
        assert response.status == ResponseStatus.SUCCESS
    
    @pytest.mark.asyncio
    async def test_context_manager(self, local_kernel: AIOSKernel):
        """Test async context manager."""
        async with AIOSClient(kernel=local_kernel, agent_id="test") as client:
            response = await client.generate("Hello")
            assert response.status == ResponseStatus.SUCCESS

