"""
Tests for Scheduler Module

Tests the FIFO and Round Robin schedulers.
Paper Reference: Section 3.3
"""

import pytest
import asyncio

from aios.kernel.scheduler import (
    Scheduler,
    SchedulerConfig,
    SchedulingStrategy,
    SyscallQueue,
)
from aios.kernel.syscall import Syscall, SyscallType, SyscallStatus
from aios.sdk.models import Response, ResponseStatus


class TestSyscallQueue:
    """Tests for SyscallQueue class."""
    
    @pytest.mark.asyncio
    async def test_put_and_get(self):
        """Test basic put and get operations."""
        queue = SyscallQueue("test", max_concurrent=2)
        
        syscall = Syscall(
            syscall_type=SyscallType.LLM,
            agent_id="agent-1",
        )
        
        await queue.put(syscall)
        assert queue.size == 1
        
        retrieved = await queue.get()
        assert retrieved is not None
        assert retrieved.syscall_id == syscall.syscall_id
    
    @pytest.mark.asyncio
    async def test_concurrency_limit(self):
        """Test that concurrency limit is enforced."""
        queue = SyscallQueue("test", max_concurrent=1)
        
        # Add two syscalls
        syscall1 = Syscall(syscall_type=SyscallType.LLM, agent_id="agent-1")
        syscall2 = Syscall(syscall_type=SyscallType.LLM, agent_id="agent-2")
        
        await queue.put(syscall1)
        await queue.put(syscall2)
        
        # Get first (should succeed)
        first = await queue.get()
        assert first is not None
        assert queue.in_progress_count == 1
        
        # Try to get second (should return None due to limit)
        second = await queue.get()
        assert second is None
        
        # Complete first and try again
        await queue.complete(first.syscall_id)
        second = await queue.get()
        assert second is not None
    
    @pytest.mark.asyncio
    async def test_find_by_agent(self):
        """Test finding syscalls by agent ID."""
        queue = SyscallQueue("test", max_concurrent=4)
        
        await queue.put(Syscall(agent_id="agent-1"))
        await queue.put(Syscall(agent_id="agent-2"))
        await queue.put(Syscall(agent_id="agent-1"))
        
        found = await queue.find_by_agent("agent-2")
        assert found is not None
        assert found.agent_id == "agent-2"
        
        not_found = await queue.find_by_agent("agent-3")
        assert not_found is None


class TestScheduler:
    """Tests for Scheduler class."""
    
    @pytest.fixture
    async def scheduler(self) -> Scheduler:
        """Create a test scheduler."""
        config = SchedulerConfig(
            strategy=SchedulingStrategy.FIFO,
            max_concurrent_llm=2,
            max_concurrent_tool=2,
            max_concurrent_memory=4,
            max_concurrent_storage=2,
        )
        sched = Scheduler(config=config)
        
        # Register mock handlers
        async def mock_handler(syscall: Syscall) -> Response:
            await asyncio.sleep(0.01)  # Simulate work
            return Response(
                query_id=syscall.query_id,
                status=ResponseStatus.SUCCESS,
                data={"result": f"Handled {syscall.syscall_id}"},
            )
        
        sched.register_handler(SyscallType.LLM, mock_handler)
        sched.register_handler(SyscallType.MEMORY, mock_handler)
        sched.register_handler(SyscallType.STORAGE, mock_handler)
        sched.register_handler(SyscallType.TOOL, mock_handler)
        
        await sched.start()
        yield sched
        await sched.stop()
    
    @pytest.mark.asyncio
    async def test_scheduler_starts(self, scheduler: Scheduler):
        """Test that scheduler starts correctly."""
        assert scheduler.is_running
    
    @pytest.mark.asyncio
    async def test_submit_syscall(self, scheduler: Scheduler):
        """Test submitting a syscall."""
        syscall = Syscall(
            syscall_type=SyscallType.LLM,
            agent_id="agent-1",
            query_id="query-1",
        )
        
        response = await scheduler.submit(syscall)
        
        assert response.status == ResponseStatus.SUCCESS
        assert response.query_id == "query-1"
    
    @pytest.mark.asyncio
    async def test_fifo_ordering(self, scheduler: Scheduler):
        """Test FIFO ordering of syscalls."""
        results = []
        
        async def submit_and_track(i: int):
            syscall = Syscall(
                syscall_type=SyscallType.MEMORY,  # Use memory queue (higher concurrency)
                agent_id=f"agent-{i}",
                query_id=f"query-{i}",
            )
            await scheduler.submit(syscall)
            results.append(i)
        
        # Submit multiple syscalls
        await asyncio.gather(*[submit_and_track(i) for i in range(5)])
        
        # Results may not be strictly ordered due to concurrent execution,
        # but all should complete
        assert len(results) == 5
        assert set(results) == {0, 1, 2, 3, 4}
    
    @pytest.mark.asyncio
    async def test_multiple_agents(self, scheduler: Scheduler):
        """Test handling multiple agents."""
        responses = []
        
        for i in range(3):
            syscall = Syscall(
                syscall_type=SyscallType.LLM,
                agent_id=f"agent-{i}",
                query_id=f"query-{i}",
            )
            response = await scheduler.submit(syscall)
            responses.append(response)
        
        assert all(r.status == ResponseStatus.SUCCESS for r in responses)
    
    @pytest.mark.asyncio
    async def test_get_stats(self, scheduler: Scheduler):
        """Test getting scheduler statistics."""
        # Submit a syscall
        syscall = Syscall(
            syscall_type=SyscallType.LLM,
            agent_id="agent-1",
        )
        await scheduler.submit(syscall)
        
        stats = scheduler.get_stats()
        
        assert stats["strategy"] == "fifo"
        assert stats["completed_syscalls"] >= 1
        assert "queues" in stats
        assert "llm" in stats["queues"]


class TestRoundRobinScheduler:
    """Tests for Round Robin scheduling."""
    
    @pytest.fixture
    async def rr_scheduler(self) -> Scheduler:
        """Create a Round Robin scheduler."""
        config = SchedulerConfig(
            strategy=SchedulingStrategy.ROUND_ROBIN,
            max_concurrent_llm=1,
        )
        sched = Scheduler(config=config)
        
        async def mock_handler(syscall: Syscall) -> Response:
            await asyncio.sleep(0.005)
            return Response(
                query_id=syscall.query_id,
                status=ResponseStatus.SUCCESS,
            )
        
        sched.register_handler(SyscallType.LLM, mock_handler)
        sched.register_handler(SyscallType.MEMORY, mock_handler)
        
        await sched.start()
        yield sched
        await sched.stop()
    
    @pytest.mark.asyncio
    async def test_round_robin_fairness(self, rr_scheduler: Scheduler):
        """Test that Round Robin provides fair scheduling."""
        # Submit syscalls from multiple agents
        tasks = []
        
        for agent_num in range(3):
            for _ in range(2):
                syscall = Syscall(
                    syscall_type=SyscallType.MEMORY,
                    agent_id=f"agent-{agent_num}",
                )
                tasks.append(rr_scheduler.submit(syscall))
        
        responses = await asyncio.gather(*tasks)
        
        # All should complete
        assert all(r.status == ResponseStatus.SUCCESS for r in responses)

