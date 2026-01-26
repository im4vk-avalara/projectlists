"""
Tests for Memory Manager

Paper Reference: Section 3.5, Figure 5
"""

import pytest
import asyncio

from aios.kernel.memory_manager import MemoryManager, MemoryBlock


class TestMemoryBlock:
    """Tests for MemoryBlock class."""
    
    def test_create_block(self):
        """Test creating a memory block."""
        block = MemoryBlock(
            key="test-key",
            agent_id="agent-1",
            value={"data": "value"},
        )
        
        assert block.key == "test-key"
        assert block.agent_id == "agent-1"
        assert block.value == {"data": "value"}
        assert block.size_bytes > 0
    
    def test_record_access(self):
        """Test recording accesses."""
        block = MemoryBlock(key="test", agent_id="agent-1", value="data")
        
        block.record_access()
        block.record_access()
        block.record_access()
        
        assert block.access_count == 3
        assert len(block.access_times) == 3
    
    def test_lru_k_score(self):
        """Test LRU-K scoring."""
        block = MemoryBlock(key="test", agent_id="agent-1", value="data")
        
        # Initially, score is creation time
        score1 = block.get_lru_k_score(k=2)
        
        block.record_access()
        block.record_access()
        block.record_access()
        
        # After accesses, score is 2nd most recent
        score2 = block.get_lru_k_score(k=2)
        
        assert score2 >= score1
    
    def test_ttl_expiry(self):
        """Test TTL expiry."""
        block = MemoryBlock(key="test", agent_id="agent-1", value="data", ttl=0)
        
        # Should be expired immediately
        assert block.is_expired()
        
        block2 = MemoryBlock(key="test", agent_id="agent-1", value="data", ttl=3600)
        assert not block2.is_expired()


class TestMemoryManager:
    """Tests for MemoryManager class."""
    
    @pytest.fixture
    def mem_mgr(self) -> MemoryManager:
        """Create memory manager."""
        return MemoryManager(memory_limit_mb=10, lru_k=2)
    
    @pytest.mark.asyncio
    async def test_write_and_read(self, mem_mgr: MemoryManager):
        """Test basic write and read."""
        block = await mem_mgr.write("agent-1", "key1", {"value": 42})
        
        assert block.key == "key1"
        assert block.value == {"value": 42}
        
        read_block = await mem_mgr.read("agent-1", "key1")
        
        assert read_block is not None
        assert read_block.value == {"value": 42}
    
    @pytest.mark.asyncio
    async def test_read_nonexistent(self, mem_mgr: MemoryManager):
        """Test reading non-existent key."""
        block = await mem_mgr.read("agent-1", "nonexistent")
        assert block is None
    
    @pytest.mark.asyncio
    async def test_delete(self, mem_mgr: MemoryManager):
        """Test deleting a key."""
        await mem_mgr.write("agent-1", "key1", "value")
        
        result = await mem_mgr.delete("agent-1", "key1")
        assert result is True
        
        block = await mem_mgr.read("agent-1", "key1")
        assert block is None
    
    @pytest.mark.asyncio
    async def test_list_keys(self, mem_mgr: MemoryManager):
        """Test listing keys."""
        await mem_mgr.write("agent-1", "prefix:key1", "v1")
        await mem_mgr.write("agent-1", "prefix:key2", "v2")
        await mem_mgr.write("agent-1", "other:key3", "v3")
        
        all_keys = await mem_mgr.list_keys("agent-1")
        assert len(all_keys) == 3
        
        prefix_keys = await mem_mgr.list_keys("agent-1", prefix="prefix:")
        assert len(prefix_keys) == 2
    
    @pytest.mark.asyncio
    async def test_agent_isolation(self, mem_mgr: MemoryManager):
        """Test that agents have isolated memory."""
        await mem_mgr.write("agent-1", "key", "value-1")
        await mem_mgr.write("agent-2", "key", "value-2")
        
        block1 = await mem_mgr.read("agent-1", "key")
        block2 = await mem_mgr.read("agent-2", "key")
        
        assert block1.value == "value-1"
        assert block2.value == "value-2"
    
    @pytest.mark.asyncio
    async def test_update_existing(self, mem_mgr: MemoryManager):
        """Test updating existing key."""
        await mem_mgr.write("agent-1", "key", "value1")
        await mem_mgr.write("agent-1", "key", "value2")
        
        block = await mem_mgr.read("agent-1", "key")
        assert block.value == "value2"
    
    @pytest.mark.asyncio
    async def test_search(self, mem_mgr: MemoryManager):
        """Test searching memory."""
        await mem_mgr.write("agent-1", "note1", {"text": "Hello world"})
        await mem_mgr.write("agent-1", "note2", {"text": "Goodbye world"})
        await mem_mgr.write("agent-1", "other", {"data": 123})
        
        results = await mem_mgr.search("agent-1", "world")
        
        assert len(results) == 2
    
    @pytest.mark.asyncio
    async def test_clear_agent(self, mem_mgr: MemoryManager):
        """Test clearing agent memory."""
        await mem_mgr.write("agent-1", "key1", "v1")
        await mem_mgr.write("agent-1", "key2", "v2")
        
        count = await mem_mgr.clear_agent("agent-1")
        
        assert count == 2
        
        keys = await mem_mgr.list_keys("agent-1")
        assert len(keys) == 0
    
    @pytest.mark.asyncio
    async def test_stats(self, mem_mgr: MemoryManager):
        """Test getting stats."""
        await mem_mgr.write("agent-1", "key1", "value1")
        await mem_mgr.write("agent-2", "key2", "value2")
        
        stats = mem_mgr.get_stats()
        
        assert stats["total_blocks"] == 2
        assert stats["agent_count"] == 2
        assert stats["lru_k"] == 2

