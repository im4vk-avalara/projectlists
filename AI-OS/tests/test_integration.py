"""
Integration Tests

End-to-end tests for the AIOS system.
Paper Reference: Various sections
"""

import pytest
import asyncio

from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
from aios.sdk.client import AIOSClient
from aios.sdk.models import LLMQuery, Message, ResponseStatus


class TestKernelIntegration:
    """Integration tests for AIOS kernel."""
    
    @pytest.mark.asyncio
    async def test_kernel_lifecycle(self):
        """Test kernel start/stop lifecycle."""
        config = KernelConfig(scheduling_strategy="fifo", llm_cores=[])
        kernel = AIOSKernel(config=config)
        
        await kernel.start()
        assert kernel.is_running
        
        stats = kernel.get_stats()
        assert stats["is_running"]
        assert stats["llm_manager"]["total_cores"] >= 1
        
        await kernel.stop()
        assert not kernel.is_running
    
    @pytest.mark.asyncio
    async def test_llm_query_flow(self):
        """Test full LLM query flow through kernel."""
        kernel = AIOSKernel()
        await kernel.start()
        
        try:
            query = LLMQuery(
                agent_id="test-agent",
                messages=[Message(role="user", content="Hello")],
                max_tokens=50,
            )
            
            response = await kernel.process_query(query)
            
            assert response.status == ResponseStatus.SUCCESS
            assert response.content is not None
        finally:
            await kernel.stop()


class TestMultiAgentIntegration:
    """Tests for multi-agent scenarios."""
    
    @pytest.mark.asyncio
    async def test_agent_memory_isolation(self):
        """Test that agent memories are isolated."""
        kernel = AIOSKernel()
        await kernel.start()
        
        try:
            client1 = AIOSClient(kernel=kernel, agent_id="agent-1")
            client2 = AIOSClient(kernel=kernel, agent_id="agent-2")
            
            # Agent 1 writes
            await client1.memory_write("shared-key", "agent-1-value")
            
            # Agent 2 writes same key
            await client2.memory_write("shared-key", "agent-2-value")
            
            # Each should read their own value
            resp1 = await client1.memory_read("shared-key")
            resp2 = await client2.memory_read("shared-key")
            
            assert resp1.data["value"] == "agent-1-value"
            assert resp2.data["value"] == "agent-2-value"
            
            await client1.close()
            await client2.close()
        finally:
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_two_agents_sequential(self):
        """Test two agents making sequential requests."""
        kernel = AIOSKernel()
        await kernel.start()
        
        try:
            client1 = AIOSClient(kernel=kernel, agent_id="agent-1")
            client2 = AIOSClient(kernel=kernel, agent_id="agent-2")
            
            # Sequential requests
            r1 = await client1.chat([{"role": "user", "content": "Hello from 1"}])
            r2 = await client2.chat([{"role": "user", "content": "Hello from 2"}])
            
            assert r1.status == ResponseStatus.SUCCESS
            assert r2.status == ResponseStatus.SUCCESS
            
            await client1.close()
            await client2.close()
        finally:
            await kernel.stop()


class TestQueryDecomposition:
    """Tests for query decomposition flow."""
    
    @pytest.mark.asyncio
    async def test_llm_query_becomes_syscall(self):
        """Test that LLM query is processed as syscall."""
        kernel = AIOSKernel()
        await kernel.start()
        
        try:
            # Check scheduler stats before
            stats_before = kernel.scheduler.get_stats()
            completed_before = stats_before["completed_syscalls"]
            
            # Send query
            query = LLMQuery(
                agent_id="test-agent",
                messages=[Message(role="user", content="Hello")],
            )
            await kernel.process_query(query)
            
            # Check scheduler stats after
            stats_after = kernel.scheduler.get_stats()
            completed_after = stats_after["completed_syscalls"]
            
            # Should have processed at least one more syscall
            assert completed_after > completed_before
        finally:
            await kernel.stop()


class TestSchedulerStrategies:
    """Tests for scheduler strategies."""
    
    @pytest.mark.asyncio
    async def test_fifo_strategy(self):
        """Test FIFO scheduling works."""
        config = KernelConfig(scheduling_strategy="fifo")
        kernel = AIOSKernel(config=config)
        await kernel.start()
        
        try:
            client = AIOSClient(kernel=kernel, agent_id="test")
            response = await client.chat([{"role": "user", "content": "test"}])
            assert response.status == ResponseStatus.SUCCESS
            await client.close()
        finally:
            await kernel.stop()
    
    @pytest.mark.asyncio
    async def test_round_robin_strategy(self):
        """Test Round Robin scheduling works."""
        config = KernelConfig(scheduling_strategy="round_robin")
        kernel = AIOSKernel(config=config)
        await kernel.start()
        
        try:
            client = AIOSClient(kernel=kernel, agent_id="test")
            response = await client.chat([{"role": "user", "content": "test"}])
            assert response.status == ResponseStatus.SUCCESS
            await client.close()
        finally:
            await kernel.stop()
