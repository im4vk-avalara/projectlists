"""
AIOS Syscall Definitions

Defines the internal syscall representation used by the scheduler.
Syscalls are atomic operations that the kernel executes.

Paper Reference: Section 3.3, Figure 3
Spec Reference: Syscalls.md
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional
import time
import uuid

from aios.sdk.models import Query, Response


class SyscallType(str, Enum):
    """
    Syscall types matching queue types in Figure 3.
    
    Each type corresponds to a kernel module:
    - LLM: LLM Core
    - MEMORY: Memory Manager
    - STORAGE: Storage Manager
    - TOOL: Tool Manager
    - CONTEXT: Context Manager
    - ACCESS: Access Manager
    """
    LLM = "llm"
    MEMORY = "memory"
    STORAGE = "storage"
    TOOL = "tool"
    CONTEXT = "context"
    ACCESS = "access"


class SyscallStatus(str, Enum):
    """
    Syscall execution status.
    
    Lifecycle: QUEUED -> IN_PROGRESS -> COMPLETED/FAILED/SUSPENDED
    """
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SUSPENDED = "suspended"


@dataclass
class Syscall:
    """
    Internal syscall representation used by the scheduler.
    
    When a Query arrives from the SDK, it is decomposed into one or more
    Syscalls. Each Syscall is placed in the appropriate queue and processed
    by the corresponding kernel module.
    
    Paper Reference: Section 3.3, Figure 3
    
    Example from Figure 3:
        Query B1 (File Operation) decomposes into:
        - B1.1 LLM Syscall
        - B1.2 Storage Syscall
        - B1.3 Memory Syscall
    
    Attributes:
        syscall_id: Unique identifier (e.g., "B1.1")
        syscall_type: Type determining which queue/manager handles it
        agent_id: ID of the agent that originated this syscall
        query_id: ID of the parent query
        query: The original Query object
        operation: Specific operation (e.g., "llm_chat", "memory_read")
        params: Operation parameters
        status: Current execution status
        thread_id: ID of the thread executing this syscall
        enqueued_at: Timestamp when added to queue
        started_at: Timestamp when execution started
        completed_at: Timestamp when execution completed
        response: The Response after completion
        priority: Lower = higher priority (0 is highest)
        depends_on: List of syscall_ids this depends on
        sequence_number: Order within the parent query
    """
    syscall_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    syscall_type: SyscallType = SyscallType.LLM
    agent_id: str = ""
    query_id: str = ""
    query: Optional[Query] = None
    operation: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    status: SyscallStatus = SyscallStatus.QUEUED
    thread_id: Optional[str] = None
    enqueued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    response: Optional[Response] = None
    priority: int = 0
    depends_on: list = field(default_factory=list)
    sequence_number: int = 0
    
    @property
    def waiting_time(self) -> float:
        """Time spent waiting in queue (seconds)."""
        if self.started_at:
            return self.started_at - self.enqueued_at
        return time.time() - self.enqueued_at
    
    @property
    def execution_time(self) -> float:
        """Time spent executing (seconds)."""
        if self.completed_at and self.started_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return time.time() - self.started_at
        return 0.0
    
    @property
    def total_time(self) -> float:
        """Total time from enqueue to completion (seconds)."""
        if self.completed_at:
            return self.completed_at - self.enqueued_at
        return time.time() - self.enqueued_at
    
    @property
    def is_complete(self) -> bool:
        """Check if syscall has finished (success or failure)."""
        return self.status in (SyscallStatus.COMPLETED, SyscallStatus.FAILED)
    
    def start(self, thread_id: Optional[str] = None) -> None:
        """Mark syscall as started."""
        self.status = SyscallStatus.IN_PROGRESS
        self.started_at = time.time()
        self.thread_id = thread_id
    
    def complete(self, response: Response) -> None:
        """Mark syscall as completed with response."""
        self.status = SyscallStatus.COMPLETED
        self.completed_at = time.time()
        self.response = response
    
    def fail(self, error: str) -> None:
        """Mark syscall as failed with error."""
        self.status = SyscallStatus.FAILED
        self.completed_at = time.time()
        from aios.sdk.models import Response, ResponseStatus
        self.response = Response(
            query_id=self.query_id,
            status=ResponseStatus.ERROR,
            error=error,
        )
    
    def suspend(self) -> None:
        """Mark syscall as suspended (for context switching)."""
        self.status = SyscallStatus.SUSPENDED
    
    def resume(self) -> None:
        """Resume a suspended syscall."""
        self.status = SyscallStatus.IN_PROGRESS
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/debugging."""
        return {
            "syscall_id": self.syscall_id,
            "syscall_type": self.syscall_type.value,
            "agent_id": self.agent_id,
            "query_id": self.query_id,
            "operation": self.operation,
            "status": self.status.value,
            "priority": self.priority,
            "sequence_number": self.sequence_number,
            "waiting_time": self.waiting_time,
            "execution_time": self.execution_time,
        }
    
    def __repr__(self) -> str:
        return (
            f"Syscall(id={self.syscall_id}, type={self.syscall_type.value}, "
            f"agent={self.agent_id}, status={self.status.value})"
        )


def create_llm_syscall(
    agent_id: str,
    query_id: str,
    query: Query,
    sequence_number: int = 0,
) -> Syscall:
    """Create an LLM syscall from a query."""
    return Syscall(
        syscall_type=SyscallType.LLM,
        agent_id=agent_id,
        query_id=query_id,
        query=query,
        operation="llm_chat",
        params=query.to_dict() if query else {},
        sequence_number=sequence_number,
    )


def create_memory_syscall(
    agent_id: str,
    query_id: str,
    operation: str,
    params: Dict[str, Any],
    sequence_number: int = 0,
) -> Syscall:
    """Create a memory syscall."""
    return Syscall(
        syscall_type=SyscallType.MEMORY,
        agent_id=agent_id,
        query_id=query_id,
        operation=operation,
        params=params,
        sequence_number=sequence_number,
    )


def create_storage_syscall(
    agent_id: str,
    query_id: str,
    operation: str,
    params: Dict[str, Any],
    sequence_number: int = 0,
) -> Syscall:
    """Create a storage syscall."""
    return Syscall(
        syscall_type=SyscallType.STORAGE,
        agent_id=agent_id,
        query_id=query_id,
        operation=operation,
        params=params,
        sequence_number=sequence_number,
    )


def create_tool_syscall(
    agent_id: str,
    query_id: str,
    tool_name: str,
    params: Dict[str, Any],
    sequence_number: int = 0,
) -> Syscall:
    """Create a tool syscall."""
    return Syscall(
        syscall_type=SyscallType.TOOL,
        agent_id=agent_id,
        query_id=query_id,
        operation="tool_call",
        params={"tool_name": tool_name, **params},
        sequence_number=sequence_number,
    )

