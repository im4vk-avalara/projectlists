"""
AIOS Context Manager

Manages agent context for interruption and resumption during scheduling.
Supports text-based snapshots (fully implemented) and logits-based (scaffolded).

Paper Reference: Section 3.4, Figure 4
Spec Reference: ExecutionFlow.md, Assumptions.md (A7)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid
import json

logger = logging.getLogger(__name__)


class SnapshotType(str, Enum):
    """Type of context snapshot."""
    TEXT = "text"      # Store generated tokens as text
    LOGITS = "logits"  # Store probability distributions (scaffold only)


class AgentState(str, Enum):
    """Agent execution state."""
    IDLE = "idle"
    RUNNING = "running"
    SUSPENDED = "suspended"
    COMPLETED = "completed"


@dataclass
class ContextSnapshot:
    """
    A snapshot of agent context at a point in time.
    
    Paper Reference: Section 3.4, Figure 4
    - Text-based: stores generated tokens
    - Logits-based: stores probability tree (scaffold)
    
    Attributes:
        snapshot_id: Unique identifier
        agent_id: Owner agent
        snapshot_type: TEXT or LOGITS
        created_at: Timestamp
        messages: Conversation history
        generated_tokens: Tokens generated so far
        tokens_count: Number of tokens
        generation_config: LLM config at snapshot time
        metadata: Additional context data
    """
    snapshot_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    snapshot_type: SnapshotType = SnapshotType.TEXT
    created_at: float = field(default_factory=time.time)
    
    # Text-based snapshot data
    messages: List[Dict[str, Any]] = field(default_factory=list)
    generated_tokens: str = ""
    tokens_count: int = 0
    
    # Generation config at snapshot time
    generation_config: Dict[str, Any] = field(default_factory=dict)
    
    # Logits-based snapshot data (scaffold)
    logits_data: Optional[bytes] = None
    kv_cache: Optional[bytes] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def size_bytes(self) -> int:
        """Estimate snapshot size in bytes."""
        size = len(self.generated_tokens.encode())
        size += sum(len(json.dumps(m).encode()) for m in self.messages)
        if self.logits_data:
            size += len(self.logits_data)
        if self.kv_cache:
            size += len(self.kv_cache)
        return size
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize snapshot."""
        return {
            "snapshot_id": self.snapshot_id,
            "agent_id": self.agent_id,
            "snapshot_type": self.snapshot_type.value,
            "created_at": self.created_at,
            "messages": self.messages,
            "generated_tokens": self.generated_tokens,
            "tokens_count": self.tokens_count,
            "generation_config": self.generation_config,
            "size_bytes": self.size_bytes,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ContextSnapshot":
        """Deserialize snapshot."""
        return cls(
            snapshot_id=data.get("snapshot_id", str(uuid.uuid4())),
            agent_id=data.get("agent_id", ""),
            snapshot_type=SnapshotType(data.get("snapshot_type", "text")),
            created_at=data.get("created_at", time.time()),
            messages=data.get("messages", []),
            generated_tokens=data.get("generated_tokens", ""),
            tokens_count=data.get("tokens_count", 0),
            generation_config=data.get("generation_config", {}),
            metadata=data.get("metadata", {}),
        )


@dataclass
class AgentContext:
    """
    Full context for an agent including state and snapshots.
    
    Attributes:
        agent_id: Agent identifier
        state: Current execution state
        current_snapshot: Active snapshot (if suspended)
        snapshots: History of snapshots
        suspension_count: Times this agent has been suspended
    """
    agent_id: str
    state: AgentState = AgentState.IDLE
    current_snapshot: Optional[ContextSnapshot] = None
    snapshots: List[ContextSnapshot] = field(default_factory=list)
    suspension_count: int = 0
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize context."""
        return {
            "agent_id": self.agent_id,
            "state": self.state.value,
            "current_snapshot_id": self.current_snapshot.snapshot_id if self.current_snapshot else None,
            "snapshot_count": len(self.snapshots),
            "suspension_count": self.suspension_count,
            "created_at": self.created_at,
            "last_active": self.last_active,
        }


class ContextManager:
    """
    Manages agent contexts for scheduling interruption/resumption.
    
    The Context Manager enables Round Robin scheduling by allowing
    LLM generation to be interrupted mid-stream and resumed later.
    
    Paper Reference: Section 3.4, Figure 4
    
    Text-based approach (implemented):
    - When interrupted, save generated tokens so far
    - When resumed, prepend saved tokens to continue generation
    
    Logits-based approach (scaffold):
    - Save probability distributions and KV cache
    - Restore exact generation state
    
    Example:
        ctx_mgr = ContextManager()
        
        # Create snapshot when suspending
        snapshot = await ctx_mgr.create_snapshot(
            agent_id="agent-1",
            messages=[{"role": "user", "content": "Hello"}],
            generated_tokens="Hello! I am",
            tokens_count=4,
        )
        
        # Later, restore and continue
        snapshot = await ctx_mgr.get_latest_snapshot("agent-1")
        # Continue generation from snapshot.generated_tokens
    """
    
    def __init__(
        self,
        max_snapshots_per_agent: int = 5,
        snapshot_type: SnapshotType = SnapshotType.TEXT,
    ):
        """
        Initialize context manager.
        
        Args:
            max_snapshots_per_agent: Maximum snapshots to keep per agent
            snapshot_type: Default snapshot type
        """
        self.max_snapshots_per_agent = max_snapshots_per_agent
        self.default_snapshot_type = snapshot_type
        
        # Agent contexts indexed by agent_id
        self._contexts: Dict[str, AgentContext] = {}
        self._lock = asyncio.Lock()
        
        logger.info(
            f"Context Manager initialized "
            f"(type={snapshot_type.value}, max_snapshots={max_snapshots_per_agent})"
        )
    
    async def get_or_create_context(self, agent_id: str) -> AgentContext:
        """Get or create context for an agent."""
        async with self._lock:
            if agent_id not in self._contexts:
                self._contexts[agent_id] = AgentContext(agent_id=agent_id)
                logger.debug(f"Created context for agent '{agent_id}'")
            return self._contexts[agent_id]
    
    async def create_snapshot(
        self,
        agent_id: str,
        messages: List[Dict[str, Any]],
        generated_tokens: str = "",
        tokens_count: int = 0,
        generation_config: Optional[Dict[str, Any]] = None,
        snapshot_type: Optional[SnapshotType] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ContextSnapshot:
        """
        Create a context snapshot for an agent.
        
        Called when suspending an agent during Round Robin scheduling.
        
        Paper Reference: Section 3.4 - snapshot mechanism
        
        Args:
            agent_id: Agent to snapshot
            messages: Current conversation messages
            generated_tokens: Tokens generated so far
            tokens_count: Number of tokens generated
            generation_config: LLM config
            snapshot_type: Override default type
            metadata: Additional data
            
        Returns:
            Created ContextSnapshot
        """
        context = await self.get_or_create_context(agent_id)
        
        snapshot = ContextSnapshot(
            agent_id=agent_id,
            snapshot_type=snapshot_type or self.default_snapshot_type,
            messages=messages.copy(),
            generated_tokens=generated_tokens,
            tokens_count=tokens_count,
            generation_config=generation_config or {},
            metadata=metadata or {},
        )
        
        async with self._lock:
            context.snapshots.append(snapshot)
            context.current_snapshot = snapshot
            context.state = AgentState.SUSPENDED
            context.suspension_count += 1
            
            # Prune old snapshots
            if len(context.snapshots) > self.max_snapshots_per_agent:
                context.snapshots = context.snapshots[-self.max_snapshots_per_agent:]
        
        logger.debug(
            f"Created snapshot for agent '{agent_id}': "
            f"{tokens_count} tokens, {snapshot.size_bytes} bytes"
        )
        
        return snapshot
    
    async def get_latest_snapshot(self, agent_id: str) -> Optional[ContextSnapshot]:
        """
        Get the latest snapshot for an agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Latest snapshot or None
        """
        context = self._contexts.get(agent_id)
        if context and context.snapshots:
            return context.snapshots[-1]
        return None
    
    async def get_snapshot(
        self,
        agent_id: str,
        snapshot_id: str,
    ) -> Optional[ContextSnapshot]:
        """Get a specific snapshot by ID."""
        context = self._contexts.get(agent_id)
        if not context:
            return None
        
        for snapshot in context.snapshots:
            if snapshot.snapshot_id == snapshot_id:
                return snapshot
        return None
    
    async def restore_snapshot(
        self,
        agent_id: str,
        snapshot_id: Optional[str] = None,
    ) -> Optional[ContextSnapshot]:
        """
        Restore agent from a snapshot.
        
        Called when resuming an agent after suspension.
        
        Paper Reference: Section 3.4 - restore mechanism
        
        Args:
            agent_id: Agent to restore
            snapshot_id: Specific snapshot (or latest if None)
            
        Returns:
            Restored snapshot or None
        """
        if snapshot_id:
            snapshot = await self.get_snapshot(agent_id, snapshot_id)
        else:
            snapshot = await self.get_latest_snapshot(agent_id)
        
        if not snapshot:
            logger.warning(f"No snapshot found for agent '{agent_id}'")
            return None
        
        async with self._lock:
            context = self._contexts.get(agent_id)
            if context:
                context.state = AgentState.RUNNING
                context.current_snapshot = snapshot
                context.last_active = time.time()
        
        logger.debug(
            f"Restored snapshot for agent '{agent_id}': "
            f"{snapshot.tokens_count} tokens"
        )
        
        return snapshot
    
    async def clear_snapshot(self, agent_id: str) -> None:
        """
        Clear current snapshot after generation completes.
        
        Args:
            agent_id: Agent ID
        """
        async with self._lock:
            context = self._contexts.get(agent_id)
            if context:
                context.current_snapshot = None
                context.state = AgentState.IDLE
                context.last_active = time.time()
        
        logger.debug(f"Cleared current snapshot for agent '{agent_id}'")
    
    async def suspend_agent(self, agent_id: str) -> None:
        """Mark agent as suspended."""
        async with self._lock:
            context = self._contexts.get(agent_id)
            if context:
                context.state = AgentState.SUSPENDED
    
    async def resume_agent(self, agent_id: str) -> None:
        """Mark agent as running."""
        async with self._lock:
            context = self._contexts.get(agent_id)
            if context:
                context.state = AgentState.RUNNING
                context.last_active = time.time()
    
    async def get_agent_state(self, agent_id: str) -> AgentState:
        """Get current state of an agent."""
        context = self._contexts.get(agent_id)
        if context:
            return context.state
        return AgentState.IDLE
    
    async def list_snapshots(
        self,
        agent_id: str,
    ) -> List[Dict[str, Any]]:
        """List all snapshots for an agent."""
        context = self._contexts.get(agent_id)
        if not context:
            return []
        
        return [
            {
                "snapshot_id": s.snapshot_id,
                "created_at": s.created_at,
                "tokens_count": s.tokens_count,
                "size_bytes": s.size_bytes,
            }
            for s in context.snapshots
        ]
    
    async def delete_snapshot(
        self,
        agent_id: str,
        snapshot_id: str,
    ) -> bool:
        """Delete a specific snapshot."""
        async with self._lock:
            context = self._contexts.get(agent_id)
            if not context:
                return False
            
            for i, snapshot in enumerate(context.snapshots):
                if snapshot.snapshot_id == snapshot_id:
                    del context.snapshots[i]
                    if context.current_snapshot and context.current_snapshot.snapshot_id == snapshot_id:
                        context.current_snapshot = None
                    return True
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get context manager statistics."""
        total_snapshots = sum(len(c.snapshots) for c in self._contexts.values())
        total_size = sum(
            sum(s.size_bytes for s in c.snapshots)
            for c in self._contexts.values()
        )
        
        return {
            "total_agents": len(self._contexts),
            "total_snapshots": total_snapshots,
            "total_size_bytes": total_size,
            "default_type": self.default_snapshot_type.value,
            "max_per_agent": self.max_snapshots_per_agent,
            "agents": {
                agent_id: ctx.to_dict()
                for agent_id, ctx in self._contexts.items()
            },
        }

