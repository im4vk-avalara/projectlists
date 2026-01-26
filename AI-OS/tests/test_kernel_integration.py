"""
Integration tests for the full AIOS Kernel with all managers.

Paper Reference: Section 2-3 (Full Architecture)
"""

import pytest
import asyncio
import tempfile

from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
from aios.kernel.access_manager import Permission
from aios.sdk.models import (
    LLMQuery,
    MemoryQuery,
    StorageQuery,
    ToolQuery,
    Message,
    ResponseStatus,
    MemoryOperation,
    StorageOperation,
)


class TestKernelWithAllManagers:
    """Test the kernel with all managers integrated."""
    
    @pytest.fixture
    async def kernel(self):
        """Create a kernel with all managers."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KernelConfig(
                scheduling_strategy="fifo",
                llm_cores=[{"name": "mock-0", "backend": "mock", "model": "mock"}],
                storage_root=tmpdir,
                auto_approve_confirmations=True,
            )
            kernel = AIOSKernel(config=config)
            await kernel.start()
            yield kernel
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_llm_query(self, kernel: AIOSKernel):
        """Test LLM query processing."""
        query = LLMQuery(
            agent_id="agent-1",
            messages=[Message(role="user", content="Hello!")],
        )
        
        response = await kernel.process_query(query)
        
        assert response.status == ResponseStatus.SUCCESS
        assert response.content is not None
    
    @pytest.mark.asyncio
    async def test_memory_write_read(self, kernel: AIOSKernel):
        """Test memory write and read."""
        # Write
        write_query = MemoryQuery(
            agent_id="agent-1",
            operation=MemoryOperation.WRITE,
            key="test-key",
            value={"data": "test-value"},
        )
        write_response = await kernel.process_query(write_query)
        assert write_response.status == ResponseStatus.SUCCESS
        
        # Read
        read_query = MemoryQuery(
            agent_id="agent-1",
            operation=MemoryOperation.READ,
            key="test-key",
        )
        read_response = await kernel.process_query(read_query)
        assert read_response.status == ResponseStatus.SUCCESS
        assert read_response.data["value"]["data"] == "test-value"
    
    @pytest.mark.asyncio
    async def test_memory_list(self, kernel: AIOSKernel):
        """Test memory list operation."""
        # Write some keys
        for i in range(3):
            query = MemoryQuery(
                agent_id="agent-1",
                operation=MemoryOperation.WRITE,
                key=f"key-{i}",
                value=f"value-{i}",
            )
            await kernel.process_query(query)
        
        # List
        list_query = MemoryQuery(
            agent_id="agent-1",
            operation=MemoryOperation.LIST,
        )
        response = await kernel.process_query(list_query)
        
        assert response.status == ResponseStatus.SUCCESS
        assert len(response.data["keys"]) == 3
    
    @pytest.mark.asyncio
    async def test_storage_write_read(self, kernel: AIOSKernel):
        """Test storage write and read."""
        # Write
        write_query = StorageQuery(
            agent_id="agent-1",
            operation=StorageOperation.WRITE,
            path="test.txt",
            data="Hello, storage!",
        )
        write_response = await kernel.process_query(write_query)
        assert write_response.status == ResponseStatus.SUCCESS
        
        # Read
        read_query = StorageQuery(
            agent_id="agent-1",
            operation=StorageOperation.READ,
            path="test.txt",
        )
        read_response = await kernel.process_query(read_query)
        assert read_response.status == ResponseStatus.SUCCESS
        assert read_response.data["content"] == "Hello, storage!"
    
    @pytest.mark.asyncio
    async def test_storage_versioning(self, kernel: AIOSKernel):
        """Test storage versioning and rollback."""
        # Write v1
        await kernel.process_query(StorageQuery(
            agent_id="agent-1",
            operation=StorageOperation.WRITE,
            path="versioned.txt",
            data="Version 1",
        ))
        
        # Write v2
        await kernel.process_query(StorageQuery(
            agent_id="agent-1",
            operation=StorageOperation.WRITE,
            path="versioned.txt",
            data="Version 2",
        ))
        
        # Read current (should be v2)
        response = await kernel.process_query(StorageQuery(
            agent_id="agent-1",
            operation=StorageOperation.READ,
            path="versioned.txt",
        ))
        assert response.data["content"] == "Version 2"
    
    @pytest.mark.asyncio
    async def test_tool_call(self, kernel: AIOSKernel):
        """Test tool call through kernel."""
        query = ToolQuery(
            agent_id="agent-1",
            tool_name="calculator",
            parameters={"expression": "2 + 2"},
        )
        
        response = await kernel.process_query(query)
        
        assert response.status == ResponseStatus.SUCCESS
        assert response.result == "4"
    
    @pytest.mark.asyncio
    async def test_tool_current_time(self, kernel: AIOSKernel):
        """Test built-in current_time tool."""
        query = ToolQuery(
            agent_id="agent-1",
            tool_name="current_time",
            parameters={},
        )
        
        response = await kernel.process_query(query)
        
        assert response.status == ResponseStatus.SUCCESS
        # Should be ISO format datetime
        assert "T" in response.result
    
    @pytest.mark.asyncio
    async def test_agent_isolation(self, kernel: AIOSKernel):
        """Test that agents have isolated memory."""
        # Write to agent-1
        await kernel.process_query(MemoryQuery(
            agent_id="agent-1",
            operation=MemoryOperation.WRITE,
            key="secret",
            value="agent-1-data",
        ))
        
        # Write to agent-2
        await kernel.process_query(MemoryQuery(
            agent_id="agent-2",
            operation=MemoryOperation.WRITE,
            key="secret",
            value="agent-2-data",
        ))
        
        # Read agent-1's data
        response1 = await kernel.process_query(MemoryQuery(
            agent_id="agent-1",
            operation=MemoryOperation.READ,
            key="secret",
        ))
        assert response1.data["value"] == "agent-1-data"
        
        # Read agent-2's data
        response2 = await kernel.process_query(MemoryQuery(
            agent_id="agent-2",
            operation=MemoryOperation.READ,
            key="secret",
        ))
        assert response2.data["value"] == "agent-2-data"
    
    @pytest.mark.asyncio
    async def test_kernel_stats(self, kernel: AIOSKernel):
        """Test getting kernel stats."""
        # Do some operations
        await kernel.process_query(LLMQuery(
            agent_id="agent-1",
            messages=[Message(role="user", content="Test")],
        ))
        await kernel.process_query(MemoryQuery(
            agent_id="agent-1",
            operation=MemoryOperation.WRITE,
            key="k",
            value="v",
        ))
        
        stats = kernel.get_stats()
        
        assert stats["is_running"] is True
        assert "llm_manager" in stats
        assert "scheduler" in stats
        assert "context_manager" in stats
        assert "memory_manager" in stats
        assert "storage_manager" in stats
        assert "tool_manager" in stats
        assert "access_manager" in stats


class TestAccessControl:
    """Test access control integration."""
    
    @pytest.fixture
    async def kernel(self):
        """Create a kernel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KernelConfig(
                storage_root=tmpdir,
                auto_approve_confirmations=True,
            )
            kernel = AIOSKernel(config=config)
            await kernel.start()
            yield kernel
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_guest_read_only(self, kernel: AIOSKernel):
        """Test that guest agents have read-only access."""
        # Register agent as guest
        await kernel.access_manager.register_agent("guest-agent", "guest")
        
        # Guests can read memory
        read_query = MemoryQuery(
            agent_id="guest-agent",
            operation=MemoryOperation.READ,
            key="any-key",
        )
        response = await kernel.process_query(read_query)
        # NOT_FOUND is fine, just checking access
        assert response.status in [ResponseStatus.SUCCESS, ResponseStatus.NOT_FOUND]
        
        # Guests cannot write
        write_query = MemoryQuery(
            agent_id="guest-agent",
            operation=MemoryOperation.WRITE,
            key="key",
            value="value",
        )
        response = await kernel.process_query(write_query)
        assert response.status == ResponseStatus.FORBIDDEN
    
    @pytest.mark.asyncio
    async def test_tool_access_control(self, kernel: AIOSKernel):
        """Test tool access is checked."""
        query = ToolQuery(
            agent_id="agent-1",
            tool_name="calculator",
            parameters={"expression": "1+1"},
        )
        
        response = await kernel.process_query(query)
        
        # Default user can access tools
        assert response.status == ResponseStatus.SUCCESS


class TestContextManagement:
    """Test context management for scheduling."""
    
    @pytest.fixture
    async def kernel(self):
        """Create a kernel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KernelConfig(storage_root=tmpdir)
            kernel = AIOSKernel(config=config)
            await kernel.start()
            yield kernel
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_suspend_and_resume(self, kernel: AIOSKernel):
        """Test suspending and resuming an agent."""
        agent_id = "test-agent"
        
        # Suspend agent with partial generation
        await kernel.suspend_agent(
            agent_id=agent_id,
            messages=[{"role": "user", "content": "Hello"}],
            generated_tokens="Hi there! I am",
            tokens_count=4,
        )
        
        # Check snapshot was created
        snapshot = await kernel.context_manager.get_latest_snapshot(agent_id)
        assert snapshot is not None
        assert snapshot.generated_tokens == "Hi there! I am"
        
        # Resume agent
        data = await kernel.resume_agent(agent_id)
        assert data is not None
        assert data["generated_tokens"] == "Hi there! I am"


class TestMultiAgentScenario:
    """Test multi-agent scenarios."""
    
    @pytest.fixture
    async def kernel(self):
        """Create a kernel."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = KernelConfig(
                storage_root=tmpdir,
                scheduling_strategy="round_robin",
            )
            kernel = AIOSKernel(config=config)
            await kernel.start()
            yield kernel
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_concurrent_agents(self, kernel: AIOSKernel):
        """Test multiple agents making queries concurrently."""
        agents = [f"agent-{i}" for i in range(5)]
        
        async def agent_workflow(agent_id: str):
            # LLM query
            await kernel.process_query(LLMQuery(
                agent_id=agent_id,
                messages=[Message(role="user", content=f"Hello from {agent_id}")],
            ))
            
            # Memory write
            await kernel.process_query(MemoryQuery(
                agent_id=agent_id,
                operation=MemoryOperation.WRITE,
                key="my_data",
                value={"agent": agent_id},
            ))
            
            # Tool call
            await kernel.process_query(ToolQuery(
                agent_id=agent_id,
                tool_name="calculator",
                parameters={"expression": "1+1"},
            ))
            
            return agent_id
        
        # Run all agents concurrently
        results = await asyncio.gather(*[agent_workflow(a) for a in agents])
        
        assert len(results) == 5
        
        # Verify each agent's memory is separate
        for agent_id in agents:
            response = await kernel.process_query(MemoryQuery(
                agent_id=agent_id,
                operation=MemoryOperation.READ,
                key="my_data",
            ))
            assert response.data["value"]["agent"] == agent_id

