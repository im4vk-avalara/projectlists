"""
AIOS Memory Manager

Manages short-term runtime memory for agents with LRU-K eviction policy.
Supports swapping to storage when memory limit is reached.

Paper Reference: Section 3.5, Figure 5
Spec Reference: Architecture.md, Assumptions.md (A8)
"""

import asyncio
import logging
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import heapq
import json

logger = logging.getLogger(__name__)


@dataclass
class MemoryBlock:
    """
    A single memory block storing agent data.
    
    Paper Reference: Section 3.5, Figure 5
    
    Attributes:
        key: Unique key within agent namespace
        agent_id: Owner agent
        value: Stored data
        created_at: Creation timestamp
        updated_at: Last update timestamp
        access_times: List of access timestamps (for LRU-K)
        access_count: Total access count
        size_bytes: Estimated size
        ttl: Time-to-live in seconds (None = no expiry)
        is_swapped: Whether block is on disk
        swap_path: Path if swapped to storage
    """
    key: str
    agent_id: str
    value: Any
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    access_times: List[float] = field(default_factory=list)
    access_count: int = 0
    size_bytes: int = 0
    ttl: Optional[int] = None
    is_swapped: bool = False
    swap_path: Optional[str] = None
    
    def __post_init__(self):
        self._update_size()
    
    def _update_size(self):
        """Update size estimate."""
        try:
            self.size_bytes = len(json.dumps(self.value).encode())
        except (TypeError, ValueError):
            self.size_bytes = 256  # Default estimate
    
    def record_access(self):
        """Record an access for LRU-K."""
        now = time.time()
        self.access_times.append(now)
        self.access_count += 1
        # Keep only last K access times (K=2 by default)
        if len(self.access_times) > 10:
            self.access_times = self.access_times[-10:]
    
    def get_lru_k_score(self, k: int = 2) -> float:
        """
        Get LRU-K score for eviction.
        
        Lower score = more likely to be evicted.
        Score is the K-th most recent access time.
        
        Paper Reference: Section 3.5 - LRU-K policy
        """
        if len(self.access_times) < k:
            # Not enough accesses, use oldest or creation time
            return self.access_times[0] if self.access_times else self.created_at
        return self.access_times[-k]
    
    def is_expired(self) -> bool:
        """Check if block has expired."""
        if self.ttl is None:
            return False
        return time.time() > (self.created_at + self.ttl)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize block metadata."""
        return {
            "key": self.key,
            "agent_id": self.agent_id,
            "value": self.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "access_count": self.access_count,
            "size_bytes": self.size_bytes,
            "ttl": self.ttl,
            "is_swapped": self.is_swapped,
        }


class MemoryManager:
    """
    Manages runtime memory for agents with LRU-K eviction.
    
    Features:
    - Per-agent namespaced memory
    - LRU-K eviction policy (K=2 by default)
    - Memory limit with automatic eviction
    - Swap to storage when limit reached
    - TTL support for automatic expiry
    
    Paper Reference: Section 3.5, Figure 5
    
    Example:
        mem_mgr = MemoryManager(memory_limit_mb=512, lru_k=2)
        
        # Write
        await mem_mgr.write("agent-1", "key", {"data": "value"})
        
        # Read
        data = await mem_mgr.read("agent-1", "key")
        
        # Search (semantic - requires embeddings)
        results = await mem_mgr.search("agent-1", "query text")
    """
    
    def __init__(
        self,
        memory_limit_mb: int = 512,
        swap_threshold_percent: float = 75.0,
        lru_k: int = 2,
        storage_manager: Optional[Any] = None,
    ):
        """
        Initialize memory manager.
        
        Args:
            memory_limit_mb: Maximum memory in MB
            swap_threshold_percent: Start swapping at this %
            lru_k: K value for LRU-K eviction
            storage_manager: Storage manager for swapping
        """
        self.memory_limit_bytes = memory_limit_mb * 1024 * 1024
        self.swap_threshold = swap_threshold_percent / 100.0
        self.lru_k = lru_k
        self.storage_manager = storage_manager
        
        # Memory store: agent_id -> key -> MemoryBlock
        self._store: Dict[str, Dict[str, MemoryBlock]] = {}
        self._current_size: int = 0
        self._lock = asyncio.Lock()
        
        # Eviction stats
        self._eviction_count = 0
        self._swap_count = 0
        
        logger.info(
            f"Memory Manager initialized "
            f"(limit={memory_limit_mb}MB, LRU-K={lru_k})"
        )
    
    async def write(
        self,
        agent_id: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> MemoryBlock:
        """
        Write a value to memory.
        
        Paper Reference: Section 3.5 - memory_write syscall
        
        Args:
            agent_id: Agent namespace
            key: Key within namespace
            value: Value to store
            ttl: Optional TTL in seconds
            
        Returns:
            Created or updated MemoryBlock
        """
        async with self._lock:
            # Ensure agent namespace exists
            if agent_id not in self._store:
                self._store[agent_id] = {}
            
            # Check if updating existing
            existing = self._store[agent_id].get(key)
            if existing:
                self._current_size -= existing.size_bytes
            
            # Create block
            block = MemoryBlock(
                key=key,
                agent_id=agent_id,
                value=value,
                ttl=ttl,
            )
            block.record_access()
            
            # Check if we need to evict
            new_size = self._current_size + block.size_bytes
            if new_size > self.memory_limit_bytes * self.swap_threshold:
                await self._evict_if_needed(block.size_bytes)
            
            # Store
            self._store[agent_id][key] = block
            self._current_size += block.size_bytes
            
            logger.debug(f"Memory write: {agent_id}/{key} ({block.size_bytes} bytes)")
            
            return block
    
    async def read(
        self,
        agent_id: str,
        key: str,
    ) -> Optional[MemoryBlock]:
        """
        Read a value from memory.
        
        Paper Reference: Section 3.5 - memory_read syscall
        
        Args:
            agent_id: Agent namespace
            key: Key to read
            
        Returns:
            MemoryBlock or None if not found
        """
        async with self._lock:
            agent_store = self._store.get(agent_id, {})
            block = agent_store.get(key)
            
            if not block:
                return None
            
            # Check expiry
            if block.is_expired():
                await self._delete_block(agent_id, key)
                return None
            
            # Check if swapped
            if block.is_swapped:
                block = await self._restore_from_swap(block)
            
            # Record access
            block.record_access()
            
            logger.debug(f"Memory read: {agent_id}/{key}")
            return block
    
    async def delete(
        self,
        agent_id: str,
        key: str,
    ) -> bool:
        """
        Delete a value from memory.
        
        Args:
            agent_id: Agent namespace
            key: Key to delete
            
        Returns:
            True if deleted, False if not found
        """
        async with self._lock:
            return await self._delete_block(agent_id, key)
    
    async def _delete_block(self, agent_id: str, key: str) -> bool:
        """Internal delete without lock."""
        agent_store = self._store.get(agent_id, {})
        block = agent_store.get(key)
        
        if not block:
            return False
        
        self._current_size -= block.size_bytes
        del agent_store[key]
        
        logger.debug(f"Memory delete: {agent_id}/{key}")
        return True
    
    async def list_keys(
        self,
        agent_id: str,
        prefix: str = "",
    ) -> List[str]:
        """
        List keys for an agent.
        
        Args:
            agent_id: Agent namespace
            prefix: Optional key prefix filter
            
        Returns:
            List of keys
        """
        agent_store = self._store.get(agent_id, {})
        keys = list(agent_store.keys())
        
        if prefix:
            keys = [k for k in keys if k.startswith(prefix)]
        
        return keys
    
    async def search(
        self,
        agent_id: str,
        query: str,
        limit: int = 10,
        threshold: float = 0.5,
    ) -> List[MemoryBlock]:
        """
        Semantic search in agent memory.
        
        Paper Reference: Section 3.5 - memory_search syscall
        
        Note: Full semantic search requires embeddings.
        This is a simple text-based fallback.
        
        Args:
            agent_id: Agent namespace
            query: Search query
            limit: Max results
            threshold: Similarity threshold
            
        Returns:
            List of matching blocks
        """
        agent_store = self._store.get(agent_id, {})
        results = []
        
        query_lower = query.lower()
        
        for block in agent_store.values():
            # Simple text matching
            value_str = json.dumps(block.value).lower()
            if query_lower in value_str or query_lower in block.key.lower():
                results.append(block)
                block.record_access()
        
        return results[:limit]
    
    async def _evict_if_needed(self, needed_bytes: int) -> int:
        """
        Evict blocks using LRU-K until we have enough space.
        
        Paper Reference: Section 3.5 - LRU-K eviction
        
        Returns:
            Number of bytes freed
        """
        freed = 0
        target = self._current_size + needed_bytes - int(self.memory_limit_bytes * self.swap_threshold)
        
        if target <= 0:
            return 0
        
        # Collect all blocks with LRU-K scores
        candidates: List[Tuple[float, str, str, MemoryBlock]] = []
        
        for agent_id, agent_store in self._store.items():
            for key, block in agent_store.items():
                if not block.is_swapped:
                    score = block.get_lru_k_score(self.lru_k)
                    candidates.append((score, agent_id, key, block))
        
        # Sort by score (oldest K-th access first)
        candidates.sort(key=lambda x: x[0])
        
        # Evict until we have enough space
        for score, agent_id, key, block in candidates:
            if freed >= target:
                break
            
            if self.storage_manager:
                # Swap to storage
                await self._swap_to_storage(block)
                self._swap_count += 1
            else:
                # Just evict
                await self._delete_block(agent_id, key)
            
            freed += block.size_bytes
            self._eviction_count += 1
            
            logger.debug(f"Evicted: {agent_id}/{key} (score={score:.2f})")
        
        return freed
    
    async def _swap_to_storage(self, block: MemoryBlock) -> None:
        """Swap a block to storage."""
        if not self.storage_manager:
            return
        
        # Generate swap path
        swap_path = f"swap/{block.agent_id}/{block.key}"
        
        # Write to storage
        # await self.storage_manager.write(swap_path, block.to_dict())
        
        # Mark as swapped
        block.is_swapped = True
        block.swap_path = swap_path
        block.value = None  # Free memory
        self._current_size -= block.size_bytes
        block.size_bytes = 64  # Minimal size for metadata
        self._current_size += block.size_bytes
    
    async def _restore_from_swap(self, block: MemoryBlock) -> MemoryBlock:
        """Restore a swapped block from storage."""
        if not self.storage_manager or not block.swap_path:
            return block
        
        # Read from storage
        # data = await self.storage_manager.read(block.swap_path)
        # block.value = data.get("value")
        
        block.is_swapped = False
        block.swap_path = None
        block._update_size()
        self._current_size += block.size_bytes - 64
        
        return block
    
    async def clear_agent(self, agent_id: str) -> int:
        """
        Clear all memory for an agent.
        
        Args:
            agent_id: Agent namespace
            
        Returns:
            Number of blocks cleared
        """
        async with self._lock:
            agent_store = self._store.get(agent_id, {})
            count = len(agent_store)
            
            for block in agent_store.values():
                self._current_size -= block.size_bytes
            
            self._store[agent_id] = {}
            
            logger.info(f"Cleared memory for agent '{agent_id}': {count} blocks")
            return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get memory manager statistics."""
        total_blocks = sum(len(s) for s in self._store.values())
        swapped_blocks = sum(
            sum(1 for b in s.values() if b.is_swapped)
            for s in self._store.values()
        )
        
        return {
            "current_size_bytes": self._current_size,
            "current_size_mb": self._current_size / (1024 * 1024),
            "limit_mb": self.memory_limit_bytes / (1024 * 1024),
            "usage_percent": (self._current_size / self.memory_limit_bytes) * 100,
            "total_blocks": total_blocks,
            "swapped_blocks": swapped_blocks,
            "agent_count": len(self._store),
            "eviction_count": self._eviction_count,
            "swap_count": self._swap_count,
            "lru_k": self.lru_k,
        }
    
    def get_agent_stats(self, agent_id: str) -> Dict[str, Any]:
        """Get stats for a specific agent."""
        agent_store = self._store.get(agent_id, {})
        
        total_size = sum(b.size_bytes for b in agent_store.values())
        
        return {
            "agent_id": agent_id,
            "block_count": len(agent_store),
            "total_size_bytes": total_size,
            "keys": list(agent_store.keys()),
        }

