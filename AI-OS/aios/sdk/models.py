"""
AIOS SDK Data Models

Defines Query and Response classes for SDK-to-kernel communication.
These models are serialized to JSON for HTTP transport.

Paper Reference: Section 3.2, Figure 3 (query types), Figure 9 (SDK)
Spec Reference: DataModels.md
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid
import time


# =============================================================================
# Enums
# =============================================================================

class QueryType(str, Enum):
    """
    Types of queries as shown in Figure 3.
    Each type maps to a syscall category.
    """
    LLM = "llm"
    MEMORY = "memory"
    STORAGE = "storage"
    TOOL = "tool"
    CONTEXT = "context"
    ACCESS = "access"


class ResponseStatus(str, Enum):
    """Response status codes."""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"


class MemoryOperation(str, Enum):
    """Memory operation types (Section 3.5)."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SEARCH = "search"
    LIST = "list"


class StorageOperation(str, Enum):
    """Storage operation types (Section 3.6)."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    LIST = "list"
    SEARCH = "search"
    ROLLBACK = "rollback"
    SHARE = "share"
    LOCK = "lock"
    UNLOCK = "unlock"
    VERSIONS = "versions"


class ToolOperation(str, Enum):
    """Tool operation types (Section 3.7)."""
    CALL = "call"
    LIST = "list"
    REGISTER = "register"
    UNREGISTER = "unregister"


class ContextOperation(str, Enum):
    """Context operation types (Section 3.4)."""
    SNAPSHOT = "snapshot"
    RESTORE = "restore"
    SUSPEND = "suspend"
    RESUME = "resume"
    LIST = "list"
    DELETE = "delete"


class AccessOperation(str, Enum):
    """Access operation types (Section 3.8)."""
    CHECK = "check"
    REQUEST = "request"
    CONFIRM = "confirm"
    GRANT = "grant"
    REVOKE = "revoke"


class SnapshotType(str, Enum):
    """Snapshot types for context manager (Figure 4)."""
    TEXT = "text"
    LOGITS = "logits"


class Permission(str, Enum):
    """Permission types for access control (Section 3.8)."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    SHARE = "share"
    ADMIN = "admin"


# =============================================================================
# Base Classes
# =============================================================================

@dataclass
class Query:
    """
    Base Query class for all AIOS SDK requests.
    
    All queries include agent identification, unique ID, and timestamp.
    Subclasses add operation-specific fields.
    
    Paper Reference: Section 3.2, Figure 3
    """
    agent_id: str
    query_type: QueryType = field(default=QueryType.LLM)
    query_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize query for HTTP transport."""
        return {
            "query_id": self.query_id,
            "agent_id": self.agent_id,
            "query_type": self.query_type.value if isinstance(self.query_type, Enum) else self.query_type,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Query":
        """Deserialize from dictionary."""
        return cls(
            agent_id=data["agent_id"],
            query_type=QueryType(data.get("query_type", "llm")),
            query_id=data.get("query_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Response:
    """
    Base Response class for all AIOS kernel responses.
    
    Paper Reference: Section 3.2, Figure 9
    """
    query_id: str
    status: ResponseStatus
    data: Any = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    execution_time_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize response for HTTP transport."""
        return {
            "query_id": self.query_id,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Response":
        """Deserialize from dictionary."""
        return cls(
            query_id=data["query_id"],
            status=ResponseStatus(data.get("status", "success")),
            data=data.get("data"),
            error=data.get("error"),
            timestamp=data.get("timestamp", time.time()),
            execution_time_ms=data.get("execution_time_ms", 0.0),
            metadata=data.get("metadata", {}),
        )
    
    @property
    def is_success(self) -> bool:
        """Check if response indicates success."""
        return self.status == ResponseStatus.SUCCESS


# =============================================================================
# Message Types
# =============================================================================

@dataclass
class Message:
    """A single chat message for LLM operations."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {"role": self.role, "content": self.content}
        if self.name:
            result["name"] = self.name
        if self.tool_calls:
            result["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create from dictionary."""
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            name=data.get("name"),
            tool_calls=data.get("tool_calls"),
            tool_call_id=data.get("tool_call_id"),
        )


# =============================================================================
# LLM Query/Response (Section 3.1)
# =============================================================================

@dataclass
class LLMQuery(Query):
    """
    Query for LLM operations (generate/chat).
    
    Paper Reference: Section 3.1, Figure 9
    """
    messages: List[Message] = field(default_factory=list)
    model: str = "default"
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 1.0
    stop_sequences: List[str] = field(default_factory=list)
    stream: bool = False
    tools: List[Dict[str, Any]] = field(default_factory=list)
    tool_choice: Optional[str] = None
    
    def __post_init__(self):
        self.query_type = QueryType.LLM
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "messages": [m.to_dict() if isinstance(m, Message) else m for m in self.messages],
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stop_sequences": self.stop_sequences,
            "stream": self.stream,
            "tools": self.tools,
            "tool_choice": self.tool_choice,
        })
        return base
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMQuery":
        messages = [
            Message.from_dict(m) if isinstance(m, dict) else m 
            for m in data.get("messages", [])
        ]
        return cls(
            agent_id=data["agent_id"],
            query_id=data.get("query_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
            messages=messages,
            model=data.get("model", "default"),
            max_tokens=data.get("max_tokens", 256),
            temperature=data.get("temperature", 0.7),
            top_p=data.get("top_p", 1.0),
            stop_sequences=data.get("stop_sequences", []),
            stream=data.get("stream", False),
            tools=data.get("tools", []),
            tool_choice=data.get("tool_choice"),
        )


@dataclass
class LLMResponse(Response):
    """
    Response from LLM operations.
    
    Paper Reference: Section 3.1
    """
    content: str = ""
    finish_reason: str = "stop"
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    model: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "content": self.content,
            "finish_reason": self.finish_reason,
            "tool_calls": self.tool_calls,
            "usage": self.usage,
            "model": self.model,
        })
        return base
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LLMResponse":
        return cls(
            query_id=data["query_id"],
            status=ResponseStatus(data.get("status", "success")),
            data=data.get("data"),
            error=data.get("error"),
            timestamp=data.get("timestamp", time.time()),
            execution_time_ms=data.get("execution_time_ms", 0.0),
            metadata=data.get("metadata", {}),
            content=data.get("content", ""),
            finish_reason=data.get("finish_reason", "stop"),
            tool_calls=data.get("tool_calls", []),
            usage=data.get("usage", {}),
            model=data.get("model", ""),
        )


# =============================================================================
# Memory Query/Response (Section 3.5)
# =============================================================================

@dataclass
class MemoryQuery(Query):
    """
    Query for memory operations.
    
    Paper Reference: Section 3.5, Figure 5
    """
    operation: MemoryOperation = MemoryOperation.READ
    key: Optional[str] = None
    value: Any = None
    ttl: Optional[int] = None
    search_query: Optional[str] = None
    search_limit: int = 10
    search_threshold: float = 0.5
    prefix: Optional[str] = None
    
    def __post_init__(self):
        self.query_type = QueryType.MEMORY
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "operation": self.operation.value if isinstance(self.operation, Enum) else self.operation,
            "key": self.key,
            "value": self.value,
            "ttl": self.ttl,
            "search_query": self.search_query,
            "search_limit": self.search_limit,
            "search_threshold": self.search_threshold,
            "prefix": self.prefix,
        })
        return base
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryQuery":
        return cls(
            agent_id=data["agent_id"],
            query_id=data.get("query_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", time.time()),
            metadata=data.get("metadata", {}),
            operation=MemoryOperation(data.get("operation", "read")),
            key=data.get("key"),
            value=data.get("value"),
            ttl=data.get("ttl"),
            search_query=data.get("search_query"),
            search_limit=data.get("search_limit", 10),
            search_threshold=data.get("search_threshold", 0.5),
            prefix=data.get("prefix"),
        )


@dataclass
class MemoryEntry:
    """A single memory entry."""
    key: str
    value: Any
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ttl: Optional[int] = None
    access_count: int = 0
    last_accessed: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "ttl": self.ttl,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
        }


@dataclass
class MemoryResponse(Response):
    """
    Response from memory operations.
    
    Paper Reference: Section 3.5
    """
    entry: Optional[MemoryEntry] = None
    entries: List[MemoryEntry] = field(default_factory=list)
    keys: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "entry": self.entry.to_dict() if self.entry else None,
            "entries": [e.to_dict() for e in self.entries],
            "keys": self.keys,
        })
        return base


# =============================================================================
# Storage Query/Response (Section 3.6)
# =============================================================================

@dataclass
class StorageQuery(Query):
    """
    Query for storage operations.
    
    Paper Reference: Section 3.6, Figure 5
    """
    operation: StorageOperation = StorageOperation.READ
    path: str = "/"
    data: Optional[bytes] = None
    version: Optional[int] = None
    create_version: bool = True
    recursive: bool = False
    search_query: Optional[str] = None
    search_limit: int = 10
    target_agent_id: Optional[str] = None
    permissions: List[str] = field(default_factory=list)
    lock_mode: str = "exclusive"
    lock_timeout: int = 30
    lock_handle: Optional[str] = None
    
    def __post_init__(self):
        self.query_type = QueryType.STORAGE
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        # Handle data serialization - can be bytes or string
        if self.data:
            if isinstance(self.data, bytes):
                data_value = self.data.hex()
            else:
                data_value = self.data  # Keep string as is
        else:
            data_value = None
        base.update({
            "operation": self.operation.value if isinstance(self.operation, Enum) else self.operation,
            "path": self.path,
            "data": data_value,
            "version": self.version,
            "create_version": self.create_version,
            "recursive": self.recursive,
            "search_query": self.search_query,
            "search_limit": self.search_limit,
            "target_agent_id": self.target_agent_id,
            "permissions": self.permissions,
            "lock_mode": self.lock_mode,
            "lock_timeout": self.lock_timeout,
            "lock_handle": self.lock_handle,
        })
        return base


@dataclass
class FileInfo:
    """File metadata."""
    path: str
    size: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: int = 1
    is_directory: bool = False
    owner_agent_id: str = ""
    shared_with: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "size": self.size,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
            "is_directory": self.is_directory,
            "owner_agent_id": self.owner_agent_id,
            "shared_with": self.shared_with,
        }


@dataclass
class StorageResponse(Response):
    """
    Response from storage operations.
    
    Paper Reference: Section 3.6
    """
    file_data: Optional[bytes] = None
    file_info: Optional[FileInfo] = None
    files: List[FileInfo] = field(default_factory=list)
    versions: List[int] = field(default_factory=list)
    lock_handle: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "file_data": self.file_data.hex() if self.file_data else None,
            "file_info": self.file_info.to_dict() if self.file_info else None,
            "files": [f.to_dict() for f in self.files],
            "versions": self.versions,
            "lock_handle": self.lock_handle,
        })
        return base


# =============================================================================
# Tool Query/Response (Section 3.7)
# =============================================================================

@dataclass
class ToolSchema:
    """Tool definition schema."""
    name: str
    description: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    category: Optional[str] = None
    requires_confirmation: bool = False
    max_instances: int = 4
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
            "category": self.category,
            "requires_confirmation": self.requires_confirmation,
            "max_instances": self.max_instances,
        }


@dataclass
class ToolQuery(Query):
    """
    Query for tool operations.
    
    Paper Reference: Section 3.7, Figure 1
    """
    operation: ToolOperation = ToolOperation.CALL
    tool_name: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    tool_schema: Optional[ToolSchema] = None
    category_filter: Optional[str] = None
    
    def __post_init__(self):
        self.query_type = QueryType.TOOL
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "operation": self.operation.value if isinstance(self.operation, Enum) else self.operation,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "tool_schema": self.tool_schema.to_dict() if self.tool_schema else None,
            "category_filter": self.category_filter,
        })
        return base


@dataclass
class ToolResponse(Response):
    """
    Response from tool operations.
    
    Paper Reference: Section 3.7
    """
    result: Any = None
    tools: List[ToolSchema] = field(default_factory=list)
    output: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "result": self.result,
            "tools": [t.to_dict() for t in self.tools],
            "output": self.output,
        })
        return base


# =============================================================================
# Context Query/Response (Section 3.4)
# =============================================================================

@dataclass
class ContextQuery(Query):
    """
    Query for context management operations.
    
    Paper Reference: Section 3.4, Figure 4
    """
    operation: ContextOperation = ContextOperation.SNAPSHOT
    snapshot_type: SnapshotType = SnapshotType.TEXT
    snapshot_id: Optional[str] = None
    
    def __post_init__(self):
        self.query_type = QueryType.CONTEXT
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "operation": self.operation.value if isinstance(self.operation, Enum) else self.operation,
            "snapshot_type": self.snapshot_type.value if isinstance(self.snapshot_type, Enum) else self.snapshot_type,
            "snapshot_id": self.snapshot_id,
        })
        return base


@dataclass
class SnapshotInfo:
    """Snapshot metadata."""
    snapshot_id: str
    snapshot_type: str = "text"
    created_at: float = field(default_factory=time.time)
    size_bytes: int = 0
    tokens_generated: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_type": self.snapshot_type,
            "created_at": self.created_at,
            "size_bytes": self.size_bytes,
            "tokens_generated": self.tokens_generated,
        }


@dataclass
class ContextResponse(Response):
    """
    Response from context operations.
    
    Paper Reference: Section 3.4
    """
    snapshot_id: Optional[str] = None
    snapshot_info: Optional[SnapshotInfo] = None
    snapshots: List[SnapshotInfo] = field(default_factory=list)
    is_suspended: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "snapshot_id": self.snapshot_id,
            "snapshot_info": self.snapshot_info.to_dict() if self.snapshot_info else None,
            "snapshots": [s.to_dict() for s in self.snapshots],
            "is_suspended": self.is_suspended,
        })
        return base


# =============================================================================
# Access Query/Response (Section 3.8)
# =============================================================================

@dataclass
class AccessQuery(Query):
    """
    Query for access control operations.
    
    Paper Reference: Section 3.8
    """
    operation: AccessOperation = AccessOperation.CHECK
    resource: str = ""
    permission: Permission = Permission.READ
    target_agent_id: Optional[str] = None
    justification: Optional[str] = None
    description: Optional[str] = None
    timeout: int = 60
    permissions_to_grant: List[Permission] = field(default_factory=list)
    
    def __post_init__(self):
        self.query_type = QueryType.ACCESS
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "operation": self.operation.value if isinstance(self.operation, Enum) else self.operation,
            "resource": self.resource,
            "permission": self.permission.value if isinstance(self.permission, Enum) else self.permission,
            "target_agent_id": self.target_agent_id,
            "justification": self.justification,
            "description": self.description,
            "timeout": self.timeout,
            "permissions_to_grant": [
                p.value if isinstance(p, Enum) else p for p in self.permissions_to_grant
            ],
        })
        return base


@dataclass
class AccessResponse(Response):
    """
    Response from access operations.
    
    Paper Reference: Section 3.8
    """
    is_permitted: bool = False
    user_confirmed: Optional[bool] = None
    granted_permissions: List[Permission] = field(default_factory=list)
    denial_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "is_permitted": self.is_permitted,
            "user_confirmed": self.user_confirmed,
            "granted_permissions": [
                p.value if isinstance(p, Enum) else p for p in self.granted_permissions
            ],
            "denial_reason": self.denial_reason,
        })
        return base


# =============================================================================
# Query Parsing Helper
# =============================================================================

def parse_query(data: Dict[str, Any]) -> Query:
    """
    Parse a dictionary into the appropriate Query subclass.
    
    Args:
        data: Dictionary from HTTP request
        
    Returns:
        Appropriate Query subclass instance
    """
    query_type = data.get("query_type", "llm")
    
    parsers = {
        "llm": LLMQuery.from_dict,
        "memory": MemoryQuery.from_dict,
        # Add more as implemented
    }
    
    parser = parsers.get(query_type, Query.from_dict)
    return parser(data)

