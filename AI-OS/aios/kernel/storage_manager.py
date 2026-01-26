"""
AIOS Storage Manager

Manages persistent storage for agents with versioning, rollback, and sharing.

Paper Reference: Section 3.6
Spec Reference: Architecture.md, Syscalls.md
"""

import asyncio
import logging
import os
import time
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import uuid

logger = logging.getLogger(__name__)


@dataclass
class FileVersion:
    """A version of a file."""
    version: int
    created_at: float
    size_bytes: int
    checksum: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
            "checksum": self.checksum,
        }


@dataclass
class FileMetadata:
    """
    Metadata for a stored file.
    
    Attributes:
        path: Relative path within agent namespace
        agent_id: Owner agent
        current_version: Current version number
        versions: List of versions
        created_at: Creation time
        updated_at: Last update time
        size_bytes: Current size
        shared_with: Agent IDs this is shared with
        locked_by: Agent holding lock (if any)
        lock_expires: Lock expiration time
    """
    path: str
    agent_id: str
    current_version: int = 1
    versions: List[FileVersion] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    size_bytes: int = 0
    shared_with: Set[str] = field(default_factory=set)
    locked_by: Optional[str] = None
    lock_expires: Optional[float] = None
    is_directory: bool = False
    
    def is_locked(self) -> bool:
        """Check if file is currently locked."""
        if not self.locked_by:
            return False
        if self.lock_expires and time.time() > self.lock_expires:
            self.locked_by = None
            self.lock_expires = None
            return False
        return True
    
    def can_access(self, agent_id: str) -> bool:
        """Check if agent can access this file."""
        return agent_id == self.agent_id or agent_id in self.shared_with
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "agent_id": self.agent_id,
            "current_version": self.current_version,
            "versions": [v.to_dict() for v in self.versions],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "size_bytes": self.size_bytes,
            "shared_with": list(self.shared_with),
            "locked_by": self.locked_by,
            "is_directory": self.is_directory,
        }


@dataclass
class FileLock:
    """A file lock."""
    lock_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str = ""
    path: str = ""
    mode: str = "exclusive"  # exclusive or shared
    acquired_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None


class StorageManager:
    """
    Manages persistent storage for agents.
    
    Features:
    - Per-agent namespaced storage
    - File versioning with rollback
    - Cross-agent file sharing
    - File locking for concurrent access
    - Semantic search (with vector DB integration)
    
    Paper Reference: Section 3.6
    
    Example:
        storage = StorageManager(root_path="./data/storage")
        
        # Write file
        await storage.write("agent-1", "notes/todo.txt", b"Buy groceries")
        
        # Read file
        data = await storage.read("agent-1", "notes/todo.txt")
        
        # Rollback to previous version
        await storage.rollback("agent-1", "notes/todo.txt", version=1)
        
        # Share with another agent
        await storage.share("agent-1", "notes/todo.txt", "agent-2")
    """
    
    def __init__(
        self,
        root_path: str = "./data/storage",
        max_versions: int = 10,
        default_lock_timeout: int = 30,
    ):
        """
        Initialize storage manager.
        
        Args:
            root_path: Root directory for storage
            max_versions: Maximum versions to keep per file
            default_lock_timeout: Default lock timeout in seconds
        """
        self.root_path = Path(root_path)
        self.max_versions = max_versions
        self.default_lock_timeout = default_lock_timeout
        
        # File metadata cache
        self._metadata: Dict[str, Dict[str, FileMetadata]] = {}  # agent_id -> path -> metadata
        self._locks: Dict[str, FileLock] = {}  # lock_id -> FileLock
        self._lock = asyncio.Lock()
        
        # Ensure root exists
        self.root_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Storage Manager initialized (root={root_path})")
    
    def _get_agent_path(self, agent_id: str) -> Path:
        """Get the storage path for an agent."""
        return self.root_path / agent_id
    
    def _get_file_path(self, agent_id: str, path: str, version: Optional[int] = None) -> Path:
        """Get full path to a file."""
        agent_path = self._get_agent_path(agent_id)
        if version:
            return agent_path / ".versions" / path / f"v{version}"
        return agent_path / path
    
    async def write(
        self,
        agent_id: str,
        path: str,
        data: bytes,
        create_version: bool = True,
    ) -> FileMetadata:
        """
        Write data to storage.
        
        Paper Reference: Section 3.6 - storage_write syscall
        
        Args:
            agent_id: Agent namespace
            path: File path within namespace
            data: Data to write
            create_version: Whether to create a new version
            
        Returns:
            File metadata
        """
        async with self._lock:
            # Get or create metadata
            if agent_id not in self._metadata:
                self._metadata[agent_id] = {}
            
            metadata = self._metadata[agent_id].get(path)
            
            if metadata:
                # Check lock
                if metadata.is_locked() and metadata.locked_by != agent_id:
                    raise PermissionError(f"File is locked by {metadata.locked_by}")
                
                # Create version of current file
                if create_version:
                    await self._create_version(agent_id, path, metadata)
            else:
                metadata = FileMetadata(path=path, agent_id=agent_id)
                self._metadata[agent_id][path] = metadata
            
            # Write file
            file_path = self._get_file_path(agent_id, path)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(data)
            
            # Update metadata
            metadata.size_bytes = len(data)
            metadata.updated_at = time.time()
            if create_version:
                metadata.current_version += 1
            
            logger.debug(f"Storage write: {agent_id}/{path} ({len(data)} bytes)")
            
            return metadata
    
    async def read(
        self,
        agent_id: str,
        path: str,
        version: Optional[int] = None,
        requesting_agent: Optional[str] = None,
    ) -> Optional[bytes]:
        """
        Read data from storage.
        
        Paper Reference: Section 3.6 - storage_read syscall
        
        Args:
            agent_id: Owner agent namespace
            path: File path
            version: Specific version (or current if None)
            requesting_agent: Agent making request (for access check)
            
        Returns:
            File data or None if not found
        """
        # Access check
        metadata = self._metadata.get(agent_id, {}).get(path)
        if metadata and requesting_agent:
            if not metadata.can_access(requesting_agent):
                raise PermissionError(f"Access denied for {requesting_agent}")
        
        file_path = self._get_file_path(agent_id, path, version)
        
        if not file_path.exists():
            return None
        
        logger.debug(f"Storage read: {agent_id}/{path}")
        return file_path.read_bytes()
    
    async def delete(
        self,
        agent_id: str,
        path: str,
        recursive: bool = False,
    ) -> bool:
        """
        Delete a file or directory.
        
        Args:
            agent_id: Agent namespace
            path: Path to delete
            recursive: Delete directory contents
            
        Returns:
            True if deleted
        """
        async with self._lock:
            metadata = self._metadata.get(agent_id, {}).get(path)
            
            if metadata and metadata.is_locked():
                raise PermissionError(f"File is locked by {metadata.locked_by}")
            
            file_path = self._get_file_path(agent_id, path)
            
            if not file_path.exists():
                return False
            
            if file_path.is_dir():
                if recursive:
                    shutil.rmtree(file_path)
                else:
                    file_path.rmdir()
            else:
                file_path.unlink()
            
            # Remove metadata
            if agent_id in self._metadata and path in self._metadata[agent_id]:
                del self._metadata[agent_id][path]
            
            logger.debug(f"Storage delete: {agent_id}/{path}")
            return True
    
    async def list_files(
        self,
        agent_id: str,
        path: str = "",
        recursive: bool = False,
    ) -> List[FileMetadata]:
        """
        List files in a directory.
        
        Args:
            agent_id: Agent namespace
            path: Directory path (empty for root)
            recursive: Include subdirectories
            
        Returns:
            List of file metadata
        """
        base_path = self._get_agent_path(agent_id)
        if path:
            base_path = base_path / path
        
        if not base_path.exists():
            return []
        
        results = []
        
        if recursive:
            paths = base_path.rglob("*")
        else:
            paths = base_path.iterdir()
        
        for file_path in paths:
            if file_path.name.startswith("."):
                continue
            
            rel_path = str(file_path.relative_to(self._get_agent_path(agent_id)))
            
            # Get or create metadata
            metadata = self._metadata.get(agent_id, {}).get(rel_path)
            if not metadata:
                metadata = FileMetadata(
                    path=rel_path,
                    agent_id=agent_id,
                    is_directory=file_path.is_dir(),
                    size_bytes=file_path.stat().st_size if file_path.is_file() else 0,
                )
            
            results.append(metadata)
        
        return results
    
    async def _create_version(
        self,
        agent_id: str,
        path: str,
        metadata: FileMetadata,
    ) -> None:
        """Create a version of the current file."""
        current_path = self._get_file_path(agent_id, path)
        if not current_path.exists():
            return
        
        # Copy to versions directory
        version_path = self._get_file_path(agent_id, path, metadata.current_version)
        version_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(current_path, version_path)
        
        # Add to versions list
        version = FileVersion(
            version=metadata.current_version,
            created_at=time.time(),
            size_bytes=current_path.stat().st_size,
        )
        metadata.versions.append(version)
        
        # Prune old versions
        if len(metadata.versions) > self.max_versions:
            old_version = metadata.versions.pop(0)
            old_path = self._get_file_path(agent_id, path, old_version.version)
            if old_path.exists():
                old_path.unlink()
    
    async def rollback(
        self,
        agent_id: str,
        path: str,
        version: int,
    ) -> bool:
        """
        Rollback a file to a previous version.
        
        Paper Reference: Section 3.6 - rollback support
        
        Args:
            agent_id: Agent namespace
            path: File path
            version: Version to rollback to
            
        Returns:
            True if successful
        """
        async with self._lock:
            version_path = self._get_file_path(agent_id, path, version)
            
            if not version_path.exists():
                return False
            
            # Read version data
            data = version_path.read_bytes()
            
            # Write as current (this creates a new version)
            await self.write(agent_id, path, data, create_version=True)
            
            logger.info(f"Rolled back {agent_id}/{path} to version {version}")
            return True
    
    async def get_versions(
        self,
        agent_id: str,
        path: str,
    ) -> List[FileVersion]:
        """Get all versions of a file."""
        metadata = self._metadata.get(agent_id, {}).get(path)
        if not metadata:
            return []
        return metadata.versions.copy()
    
    async def share(
        self,
        agent_id: str,
        path: str,
        target_agent_id: str,
    ) -> bool:
        """
        Share a file with another agent.
        
        Paper Reference: Section 3.6 - cross-agent sharing
        
        Args:
            agent_id: Owner agent
            path: File path
            target_agent_id: Agent to share with
            
        Returns:
            True if successful
        """
        async with self._lock:
            metadata = self._metadata.get(agent_id, {}).get(path)
            if not metadata:
                return False
            
            metadata.shared_with.add(target_agent_id)
            logger.info(f"Shared {agent_id}/{path} with {target_agent_id}")
            return True
    
    async def unshare(
        self,
        agent_id: str,
        path: str,
        target_agent_id: str,
    ) -> bool:
        """Remove sharing for a file."""
        async with self._lock:
            metadata = self._metadata.get(agent_id, {}).get(path)
            if not metadata:
                return False
            
            metadata.shared_with.discard(target_agent_id)
            return True
    
    async def acquire_lock(
        self,
        agent_id: str,
        path: str,
        mode: str = "exclusive",
        timeout: Optional[int] = None,
    ) -> Optional[FileLock]:
        """
        Acquire a lock on a file.
        
        Paper Reference: Section 3.6 - file locking
        
        Args:
            agent_id: Agent requesting lock
            path: File path
            mode: "exclusive" or "shared"
            timeout: Lock timeout in seconds
            
        Returns:
            FileLock if acquired, None if failed
        """
        async with self._lock:
            metadata = self._metadata.get(agent_id, {}).get(path)
            
            if metadata and metadata.is_locked() and metadata.locked_by != agent_id:
                return None
            
            # Create metadata if needed
            if not metadata:
                if agent_id not in self._metadata:
                    self._metadata[agent_id] = {}
                metadata = FileMetadata(path=path, agent_id=agent_id)
                self._metadata[agent_id][path] = metadata
            
            # Create lock
            lock = FileLock(
                agent_id=agent_id,
                path=path,
                mode=mode,
                expires_at=time.time() + (timeout or self.default_lock_timeout),
            )
            
            metadata.locked_by = agent_id
            metadata.lock_expires = lock.expires_at
            self._locks[lock.lock_id] = lock
            
            logger.debug(f"Lock acquired: {agent_id}/{path}")
            return lock
    
    async def release_lock(
        self,
        lock_id: str,
    ) -> bool:
        """Release a file lock."""
        async with self._lock:
            lock = self._locks.get(lock_id)
            if not lock:
                return False
            
            metadata = self._metadata.get(lock.agent_id, {}).get(lock.path)
            if metadata:
                metadata.locked_by = None
                metadata.lock_expires = None
            
            del self._locks[lock_id]
            logger.debug(f"Lock released: {lock.agent_id}/{lock.path}")
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get storage manager statistics."""
        total_files = sum(len(m) for m in self._metadata.values())
        
        return {
            "root_path": str(self.root_path),
            "agent_count": len(self._metadata),
            "total_files": total_files,
            "active_locks": len(self._locks),
            "max_versions": self.max_versions,
        }

