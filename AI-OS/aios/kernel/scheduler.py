"""
AIOS Agent Scheduler

Centralized scheduler managing syscall queues and execution.
Supports FIFO and Round Robin scheduling strategies.

Paper Reference: Section 3.3, Figure 3
Spec Reference: Architecture.md, ExecutionFlow.md
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
import time

from aios.kernel.syscall import Syscall, SyscallType, SyscallStatus
from aios.sdk.models import Response, ResponseStatus


logger = logging.getLogger(__name__)


class SchedulingStrategy(str, Enum):
    """
    Scheduling strategies.
    
    Paper Reference: Section 3.3
    - FIFO: First-in-first-out, simple but can cause starvation
    - ROUND_ROBIN: Fair time-sliced, requires context interruption
    """
    FIFO = "fifo"
    ROUND_ROBIN = "round_robin"


@dataclass
class SchedulerConfig:
    """
    Scheduler configuration.
    
    Paper Reference: Section 3.3
    Design Decision: Assumptions A3, A4 in Assumptions.md
    """
    strategy: SchedulingStrategy = SchedulingStrategy.FIFO
    
    # Round Robin settings
    tokens_per_slice: int = 50
    max_time_slice_ms: int = 500
    
    # Concurrency limits per queue type
    max_concurrent_llm: int = 1
    max_concurrent_tool: int = 4
    max_concurrent_memory: int = 8
    max_concurrent_storage: int = 4


class SyscallQueue:
    """
    Thread-safe queue for syscalls.
    
    Paper Reference: Figure 3 shows LLM Queue, Tool Queue, Memory Queue, Storage Queue
    """
    
    def __init__(self, name: str, max_concurrent: int = 1):
        """
        Initialize queue.
        
        Args:
            name: Queue name for logging
            max_concurrent: Maximum concurrent executions
        """
        self.name = name
        self.max_concurrent = max_concurrent
        self._queue: deque[Syscall] = deque()
        self._in_progress: Set[str] = set()  # syscall_ids currently executing
        self._lock = asyncio.Lock()
    
    async def put(self, syscall: Syscall) -> None:
        """Add a syscall to the queue."""
        async with self._lock:
            self._queue.append(syscall)
            logger.debug(f"[{self.name}] Enqueued {syscall.syscall_id}")
    
    async def get(self) -> Optional[Syscall]:
        """Get the next syscall if available and under concurrency limit."""
        async with self._lock:
            if not self._queue:
                return None
            if len(self._in_progress) >= self.max_concurrent:
                return None
            
            syscall = self._queue.popleft()
            self._in_progress.add(syscall.syscall_id)
            return syscall
    
    async def peek(self) -> Optional[Syscall]:
        """Peek at the next syscall without removing it."""
        async with self._lock:
            if self._queue:
                return self._queue[0]
            return None
    
    async def complete(self, syscall_id: str) -> None:
        """Mark a syscall as complete, freeing a slot."""
        async with self._lock:
            self._in_progress.discard(syscall_id)
    
    async def find_by_agent(self, agent_id: str) -> Optional[Syscall]:
        """Find a syscall for a specific agent."""
        async with self._lock:
            for syscall in self._queue:
                if syscall.agent_id == agent_id:
                    return syscall
            return None
    
    @property
    def size(self) -> int:
        """Number of syscalls in queue."""
        return len(self._queue)
    
    @property
    def in_progress_count(self) -> int:
        """Number of syscalls currently executing."""
        return len(self._in_progress)
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        return len(self._queue) == 0
    
    def has_capacity(self) -> bool:
        """Check if queue can accept more concurrent executions."""
        return len(self._in_progress) < self.max_concurrent


# Type for syscall handlers
SyscallHandler = Callable[[Syscall], Coroutine[Any, Any, Response]]


class Scheduler:
    """
    Centralized agent scheduler.
    
    Manages four queues (LLM, Tool, Memory, Storage) and dispatches
    syscalls to the appropriate kernel modules.
    
    Paper Reference: Section 3.3, Figure 3
    
    Example:
        scheduler = Scheduler(config=SchedulerConfig(strategy=SchedulingStrategy.FIFO))
        scheduler.register_handler(SyscallType.LLM, llm_handler)
        await scheduler.start()
        
        result = await scheduler.submit(syscall)
    """
    
    def __init__(self, config: Optional[SchedulerConfig] = None):
        """
        Initialize the scheduler.
        
        Args:
            config: Scheduler configuration
        """
        self.config = config or SchedulerConfig()
        
        # Create queues (Figure 3)
        self.queues: Dict[SyscallType, SyscallQueue] = {
            SyscallType.LLM: SyscallQueue("LLM Queue", self.config.max_concurrent_llm),
            SyscallType.TOOL: SyscallQueue("Tool Queue", self.config.max_concurrent_tool),
            SyscallType.MEMORY: SyscallQueue("Memory Queue", self.config.max_concurrent_memory),
            SyscallType.STORAGE: SyscallQueue("Storage Queue", self.config.max_concurrent_storage),
        }
        
        # Handlers for each syscall type
        self._handlers: Dict[SyscallType, SyscallHandler] = {}
        
        # Tracking
        self._pending_results: Dict[str, asyncio.Future] = {}
        self._running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        
        # Round Robin state
        self._rr_agent_queue: deque[str] = deque()
        self._rr_current_agent: Optional[str] = None
        
        # Metrics
        self._total_syscalls = 0
        self._completed_syscalls = 0
        self._total_waiting_time = 0.0
        
        logger.info(f"Scheduler initialized with strategy: {self.config.strategy}")
    
    def register_handler(self, syscall_type: SyscallType, handler: SyscallHandler) -> None:
        """
        Register a handler for a syscall type.
        
        Args:
            syscall_type: Type of syscalls to handle
            handler: Async function that processes the syscall
        """
        self._handlers[syscall_type] = handler
        logger.info(f"Registered handler for {syscall_type.value}")
    
    async def submit(self, syscall: Syscall) -> Response:
        """
        Submit a syscall for execution.
        
        The syscall is placed in the appropriate queue and processed
        according to the scheduling strategy.
        
        Args:
            syscall: The syscall to execute
            
        Returns:
            Response from the syscall handler
        """
        # Track new agent for Round Robin
        if syscall.agent_id not in self._rr_agent_queue:
            self._rr_agent_queue.append(syscall.agent_id)
        
        # Create future for result
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_results[syscall.syscall_id] = future
        
        # Enqueue
        queue = self.queues.get(syscall.syscall_type)
        if not queue:
            # Default to LLM queue for unknown types
            queue = self.queues[SyscallType.LLM]
        
        await queue.put(syscall)
        self._total_syscalls += 1
        
        logger.debug(f"Submitted syscall {syscall.syscall_id} to {syscall.syscall_type.value} queue")
        
        # Wait for result
        try:
            result = await future
            return result
        finally:
            self._pending_results.pop(syscall.syscall_id, None)
    
    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            return
        
        self._running = True
        self._scheduler_task = asyncio.create_task(self._run_loop())
        logger.info("Scheduler started")
    
    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")
    
    async def _run_loop(self) -> None:
        """Main scheduling loop."""
        while self._running:
            try:
                # Select next syscall based on strategy
                syscall = await self._select_next()
                
                if syscall:
                    # Execute in background
                    asyncio.create_task(self._execute(syscall))
                else:
                    # No work available, brief sleep
                    await asyncio.sleep(0.001)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Error in scheduler loop: {e}")
                await asyncio.sleep(0.01)
    
    async def _select_next(self) -> Optional[Syscall]:
        """Select the next syscall to execute based on strategy."""
        if self.config.strategy == SchedulingStrategy.FIFO:
            return await self._select_fifo()
        else:
            return await self._select_round_robin()
    
    async def _select_fifo(self) -> Optional[Syscall]:
        """
        FIFO selection: oldest syscall from any non-empty queue with capacity.
        
        Paper Reference: Section 3.3 - FIFO strategy
        """
        candidates: List[tuple] = []
        
        for syscall_type, queue in self.queues.items():
            if queue.is_empty() or not queue.has_capacity():
                continue
            
            syscall = await queue.peek()
            if syscall:
                candidates.append((syscall.enqueued_at, syscall_type, syscall))
        
        if not candidates:
            return None
        
        # Sort by enqueue time (oldest first)
        candidates.sort(key=lambda x: x[0])
        _, syscall_type, _ = candidates[0]
        
        # Actually dequeue
        return await self.queues[syscall_type].get()
    
    async def _select_round_robin(self) -> Optional[Syscall]:
        """
        Round Robin selection: cycle through agents fairly.
        
        Paper Reference: Section 3.3 - RR requires context interruption
        """
        if not self._rr_agent_queue:
            return None
        
        # Try each agent in turn
        tried = 0
        while tried < len(self._rr_agent_queue):
            # Get current agent
            if not self._rr_current_agent:
                self._rr_current_agent = self._rr_agent_queue[0]
            
            # Find syscall for this agent
            for queue in self.queues.values():
                if not queue.has_capacity():
                    continue
                syscall = await queue.find_by_agent(self._rr_current_agent)
                if syscall:
                    # Actually dequeue
                    dequeued = await queue.get()
                    if dequeued and dequeued.syscall_id == syscall.syscall_id:
                        return dequeued
            
            # Move to next agent
            self._rr_agent_queue.rotate(-1)
            self._rr_current_agent = self._rr_agent_queue[0]
            tried += 1
        
        # No syscalls for any agent, fall back to FIFO
        return await self._select_fifo()
    
    async def _execute(self, syscall: Syscall) -> None:
        """Execute a syscall using the registered handler."""
        syscall.start()
        waiting_time = syscall.waiting_time
        self._total_waiting_time += waiting_time
        
        logger.debug(
            f"Executing syscall {syscall.syscall_id} "
            f"(waited {waiting_time:.3f}s)"
        )
        
        try:
            # Get handler
            handler = self._handlers.get(syscall.syscall_type)
            if not handler:
                raise RuntimeError(f"No handler for syscall type: {syscall.syscall_type}")
            
            # Execute
            response = await handler(syscall)
            syscall.complete(response)
            
        except Exception as e:
            logger.exception(f"Syscall {syscall.syscall_id} failed: {e}")
            syscall.fail(str(e))
            response = Response(
                query_id=syscall.query_id,
                status=ResponseStatus.ERROR,
                error=str(e),
            )
        
        finally:
            # Mark complete in queue
            queue = self.queues.get(syscall.syscall_type)
            if queue:
                await queue.complete(syscall.syscall_id)
            
            self._completed_syscalls += 1
            
            # Resolve waiting future
            future = self._pending_results.get(syscall.syscall_id)
            if future and not future.done():
                future.set_result(syscall.response or response)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        return {
            "strategy": self.config.strategy.value,
            "total_syscalls": self._total_syscalls,
            "completed_syscalls": self._completed_syscalls,
            "pending_syscalls": self._total_syscalls - self._completed_syscalls,
            "average_waiting_time": (
                self._total_waiting_time / self._completed_syscalls
                if self._completed_syscalls > 0 else 0
            ),
            "queues": {
                syscall_type.value: {
                    "size": queue.size,
                    "in_progress": queue.in_progress_count,
                    "max_concurrent": queue.max_concurrent,
                }
                for syscall_type, queue in self.queues.items()
            },
        }
    
    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running

