"""
Tests for Context Manager

Paper Reference: Section 3.4, Figure 4
"""

import pytest
import asyncio

from aios.kernel.context_manager import (
    ContextManager,
    ContextSnapshot,
    AgentState,
    SnapshotType,
)


class TestContextSnapshot:
    """Tests for ContextSnapshot class."""
    
    def test_create_snapshot(self):
        """Test creating a snapshot."""
        snapshot = ContextSnapshot(
            agent_id="agent-1",
            messages=[{"role": "user", "content": "Hello"}],
            generated_tokens="Hello! I am",
            tokens_count=4,
        )
        
        assert snapshot.agent_id == "agent-1"
        assert snapshot.tokens_count == 4
        assert snapshot.generated_tokens == "Hello! I am"
        assert snapshot.snapshot_type == SnapshotType.TEXT
    
    def test_snapshot_size(self):
        """Test size calculation."""
        snapshot = ContextSnapshot(
            agent_id="agent-1",
            messages=[{"role": "user", "content": "Hello"}],
            generated_tokens="This is some generated text",
        )
        
        assert snapshot.size_bytes > 0
    
    def test_snapshot_serialization(self):
        """Test to_dict/from_dict."""
        snapshot = ContextSnapshot(
            agent_id="agent-1",
            generated_tokens="Test tokens",
            tokens_count=2,
        )
        
        data = snapshot.to_dict()
        restored = ContextSnapshot.from_dict(data)
        
        assert restored.agent_id == snapshot.agent_id
        assert restored.generated_tokens == snapshot.generated_tokens


class TestContextManager:
    """Tests for ContextManager class."""
    
    @pytest.fixture
    def ctx_mgr(self) -> ContextManager:
        """Create context manager."""
        return ContextManager(max_snapshots_per_agent=3)
    
    @pytest.mark.asyncio
    async def test_create_snapshot(self, ctx_mgr: ContextManager):
        """Test creating a snapshot."""
        snapshot = await ctx_mgr.create_snapshot(
            agent_id="agent-1",
            messages=[{"role": "user", "content": "Hello"}],
            generated_tokens="Hi there",
            tokens_count=2,
        )
        
        assert snapshot.agent_id == "agent-1"
        assert snapshot.tokens_count == 2
    
    @pytest.mark.asyncio
    async def test_get_latest_snapshot(self, ctx_mgr: ContextManager):
        """Test retrieving latest snapshot."""
        # Create multiple snapshots
        await ctx_mgr.create_snapshot("agent-1", [], "First", 1)
        await ctx_mgr.create_snapshot("agent-1", [], "Second", 2)
        await ctx_mgr.create_snapshot("agent-1", [], "Third", 3)
        
        latest = await ctx_mgr.get_latest_snapshot("agent-1")
        
        assert latest is not None
        assert latest.generated_tokens == "Third"
    
    @pytest.mark.asyncio
    async def test_restore_snapshot(self, ctx_mgr: ContextManager):
        """Test restoring a snapshot."""
        snapshot = await ctx_mgr.create_snapshot(
            "agent-1", [], "Tokens", 5
        )
        
        restored = await ctx_mgr.restore_snapshot("agent-1")
        
        assert restored is not None
        assert restored.snapshot_id == snapshot.snapshot_id
        
        state = await ctx_mgr.get_agent_state("agent-1")
        assert state == AgentState.RUNNING
    
    @pytest.mark.asyncio
    async def test_agent_state_transitions(self, ctx_mgr: ContextManager):
        """Test agent state transitions."""
        # Initially idle
        state = await ctx_mgr.get_agent_state("agent-1")
        assert state == AgentState.IDLE
        
        # Create snapshot -> suspended
        await ctx_mgr.create_snapshot("agent-1", [], "Test", 1)
        state = await ctx_mgr.get_agent_state("agent-1")
        assert state == AgentState.SUSPENDED
        
        # Restore -> running
        await ctx_mgr.restore_snapshot("agent-1")
        state = await ctx_mgr.get_agent_state("agent-1")
        assert state == AgentState.RUNNING
        
        # Clear -> idle
        await ctx_mgr.clear_snapshot("agent-1")
        state = await ctx_mgr.get_agent_state("agent-1")
        assert state == AgentState.IDLE
    
    @pytest.mark.asyncio
    async def test_max_snapshots_limit(self, ctx_mgr: ContextManager):
        """Test that old snapshots are pruned."""
        # Create more than max
        for i in range(5):
            await ctx_mgr.create_snapshot("agent-1", [], f"Snapshot {i}", i)
        
        snapshots = await ctx_mgr.list_snapshots("agent-1")
        
        # Should only keep max (3)
        assert len(snapshots) == 3
    
    @pytest.mark.asyncio
    async def test_delete_snapshot(self, ctx_mgr: ContextManager):
        """Test deleting a snapshot."""
        snapshot = await ctx_mgr.create_snapshot("agent-1", [], "Test", 1)
        
        result = await ctx_mgr.delete_snapshot("agent-1", snapshot.snapshot_id)
        assert result is True
        
        snapshots = await ctx_mgr.list_snapshots("agent-1")
        assert len(snapshots) == 0
    
    @pytest.mark.asyncio
    async def test_stats(self, ctx_mgr: ContextManager):
        """Test getting stats."""
        await ctx_mgr.create_snapshot("agent-1", [], "Test 1", 1)
        await ctx_mgr.create_snapshot("agent-2", [], "Test 2", 2)
        
        stats = ctx_mgr.get_stats()
        
        assert stats["total_agents"] == 2
        assert stats["total_snapshots"] == 2

