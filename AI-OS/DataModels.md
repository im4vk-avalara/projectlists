# AIOS Data Models

This document defines the Query/Response schemas and data types used in the AIOS SDK and kernel, based on Section 3.2 and Figure 9.

---

## Base Classes

### Query (Base)

```python
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, List
from enum import Enum
import uuid
import time

class QueryType(Enum):
    """Types of queries as shown in Figure 3."""
    CHAT = "chat"
    FILE_OPERATION = "file_operation"
    TOOL_USE = "tool_use"
    MEMORY = "memory"
    CONTEXT = "context"
    ACCESS = "access"

@dataclass
class Query:
    """
    Base Query class for all AIOS SDK requests.
    
    Paper Reference: Section 3.2, Figure 3, Figure 9
    """
    agent_id: str
    query_type: QueryType
    query_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize query for HTTP transport."""
        return {
            "query_id": self.query_id,
            "agent_id": self.agent_id,
            "query_type": self.query_type.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }
```

### Response (Base)

```python
from enum import Enum

class ResponseStatus(Enum):
    """Response status codes."""
    SUCCESS = "success"
    ERROR = "error"
    PENDING = "pending"
    TIMEOUT = "timeout"
    PERMISSION_DENIED = "permission_denied"
    NOT_FOUND = "not_found"

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
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "timestamp": self.timestamp,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }
    
    @property
    def is_success(self) -> bool:
        return self.status == ResponseStatus.SUCCESS
```

---

## LLM Query/Response Models

### LLMQuery

```python
@dataclass
class Message:
    """A single chat message."""
    role: str  # "system", "user", "assistant", "tool"
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None

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
    tools: List[Dict] = field(default_factory=list)  # Tool schemas
    
    def __post_init__(self):
        self.query_type = QueryType.CHAT
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "messages": [
                {"role": m.role, "content": m.content, "name": m.name}
                for m in self.messages
            ],
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stop_sequences": self.stop_sequences,
            "stream": self.stream,
            "tools": self.tools,
        })
        return base
```

### LLMResponse

```python
@dataclass
class LLMResponse(Response):
    """
    Response from LLM operations.
    
    Paper Reference: Section 3.1
    """
    content: str = ""
    finish_reason: str = "stop"  # "stop", "length", "tool_calls"
    usage: Dict[str, int] = field(default_factory=dict)
    tool_calls: List[Dict] = field(default_factory=list)
    model: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "content": self.content,
            "finish_reason": self.finish_reason,
            "usage": self.usage,
            "tool_calls": self.tool_calls,
            "model": self.model,
        })
        return base
```

---

## Memory Query/Response Models

### MemoryQuery

```python
class MemoryOperation(Enum):
    """Memory operation types."""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    SEARCH = "search"
    LIST = "list"

@dataclass
class MemoryQuery(Query):
    """
    Query for memory operations.
    
    Paper Reference: Section 3.5, Figure 5
    """
    operation: MemoryOperation = MemoryOperation.READ
    key: Optional[str] = None
    value: Any = None
    ttl: Optional[int] = None  # Time-to-live in seconds
    search_query: Optional[str] = None
    search_limit: int = 10
    search_threshold: float = 0.5
    prefix: Optional[str] = None
    
    def __post_init__(self):
        self.query_type = QueryType.MEMORY
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "operation": self.operation.value,
            "key": self.key,
            "value": self.value,
            "ttl": self.ttl,
            "search_query": self.search_query,
            "search_limit": self.search_limit,
            "search_threshold": self.search_threshold,
            "prefix": self.prefix,
        })
        return base
```

### MemoryResponse

```python
@dataclass
class MemoryEntry:
    """A single memory entry."""
    key: str
    value: Any
    created_at: float
    updated_at: float
    ttl: Optional[int] = None
    access_count: int = 0
    last_accessed: float = 0.0

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
            "entry": self.entry.__dict__ if self.entry else None,
            "entries": [e.__dict__ for e in self.entries],
            "keys": self.keys,
        })
        return base
```

---

## Storage Query/Response Models

### StorageQuery

```python
class StorageOperation(Enum):
    """Storage operation types."""
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
    lock_mode: str = "exclusive"  # "exclusive" or "shared"
    lock_timeout: int = 30
    lock_handle: Optional[str] = None
    
    def __post_init__(self):
        self.query_type = QueryType.FILE_OPERATION
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "operation": self.operation.value,
            "path": self.path,
            "data": self.data.hex() if self.data else None,
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
```

### StorageResponse

```python
@dataclass
class FileInfo:
    """File metadata."""
    path: str
    size: int
    created_at: float
    updated_at: float
    version: int
    is_directory: bool = False
    owner_agent_id: str = ""
    shared_with: List[str] = field(default_factory=list)

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
            "file_info": self.file_info.__dict__ if self.file_info else None,
            "files": [f.__dict__ for f in self.files],
            "versions": self.versions,
            "lock_handle": self.lock_handle,
        })
        return base
```

---

## Tool Query/Response Models

### ToolQuery

```python
class ToolOperation(Enum):
    """Tool operation types."""
    CALL = "call"
    LIST = "list"
    REGISTER = "register"
    UNREGISTER = "unregister"

@dataclass
class ToolSchema:
    """Tool definition schema."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema for parameters
    category: Optional[str] = None
    requires_confirmation: bool = False

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
        self.query_type = QueryType.TOOL_USE
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "operation": self.operation.value,
            "tool_name": self.tool_name,
            "parameters": self.parameters,
            "tool_schema": self.tool_schema.__dict__ if self.tool_schema else None,
            "category_filter": self.category_filter,
        })
        return base
```

### ToolResponse

```python
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
            "tools": [t.__dict__ for t in self.tools],
            "output": self.output,
        })
        return base
```

---

## Context Query/Response Models

### ContextQuery

```python
class ContextOperation(Enum):
    """Context operation types."""
    SNAPSHOT = "snapshot"
    RESTORE = "restore"
    SUSPEND = "suspend"
    RESUME = "resume"
    LIST = "list"
    DELETE = "delete"

class SnapshotType(Enum):
    """Snapshot approach types from Figure 4."""
    TEXT = "text"      # Text-based: store generated tokens
    LOGITS = "logits"  # Logits-based: store probability distributions

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
            "operation": self.operation.value,
            "snapshot_type": self.snapshot_type.value,
            "snapshot_id": self.snapshot_id,
        })
        return base
```

### ContextResponse

```python
@dataclass
class SnapshotInfo:
    """Snapshot metadata."""
    snapshot_id: str
    snapshot_type: str
    created_at: float
    size_bytes: int
    tokens_generated: int = 0

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
            "snapshot_info": self.snapshot_info.__dict__ if self.snapshot_info else None,
            "snapshots": [s.__dict__ for s in self.snapshots],
            "is_suspended": self.is_suspended,
        })
        return base
```

---

## Access Query/Response Models

### AccessQuery

```python
class AccessOperation(Enum):
    """Access operation types."""
    CHECK = "check"
    REQUEST = "request"
    CONFIRM = "confirm"
    GRANT = "grant"
    REVOKE = "revoke"

class Permission(Enum):
    """Permission types."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    DELETE = "delete"
    SHARE = "share"
    ADMIN = "admin"

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
            "operation": self.operation.value,
            "resource": self.resource,
            "permission": self.permission.value,
            "target_agent_id": self.target_agent_id,
            "justification": self.justification,
            "description": self.description,
            "timeout": self.timeout,
            "permissions_to_grant": [p.value for p in self.permissions_to_grant],
        })
        return base
```

### AccessResponse

```python
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
            "granted_permissions": [p.value for p in self.granted_permissions],
            "denial_reason": self.denial_reason,
        })
        return base
```

---

## Syscall Internal Models

### Syscall

```python
class SyscallType(Enum):
    """Syscall types matching queue types in Figure 3."""
    LLM = "llm"
    MEMORY = "memory"
    STORAGE = "storage"
    TOOL = "tool"
    CONTEXT = "context"
    ACCESS = "access"

class SyscallStatus(Enum):
    """Syscall execution status."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SUSPENDED = "suspended"

@dataclass
class Syscall:
    """
    Internal syscall representation used by scheduler.
    
    Paper Reference: Section 3.3, Figure 3
    """
    syscall_id: str
    syscall_type: SyscallType
    agent_id: str
    query_id: str
    query: Query
    status: SyscallStatus = SyscallStatus.QUEUED
    thread_id: Optional[str] = None
    enqueued_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    response: Optional[Response] = None
    priority: int = 0  # Lower = higher priority
    
    @property
    def waiting_time(self) -> float:
        """Time spent waiting in queue."""
        if self.started_at:
            return self.started_at - self.enqueued_at
        return time.time() - self.enqueued_at
    
    @property
    def execution_time(self) -> float:
        """Time spent executing."""
        if self.completed_at and self.started_at:
            return self.completed_at - self.started_at
        return 0.0
```

---

## Scheduler Models

### SchedulerConfig

```python
class SchedulingStrategy(Enum):
    """Scheduling strategies from Section 3.3."""
    FIFO = "fifo"
    ROUND_ROBIN = "round_robin"

@dataclass
class SchedulerConfig:
    """
    Scheduler configuration.
    
    Paper Reference: Section 3.3
    """
    strategy: SchedulingStrategy = SchedulingStrategy.FIFO
    time_slice_ms: int = 100  # For Round Robin
    max_concurrent_llm: int = 1
    max_concurrent_tool: int = 4
    max_concurrent_memory: int = 8
    max_concurrent_storage: int = 4
```

---

## Type Aliases and Helpers

```python
from typing import Union, TypeVar

# Query type union
AnyQuery = Union[LLMQuery, MemoryQuery, StorageQuery, ToolQuery, ContextQuery, AccessQuery]

# Response type union
AnyResponse = Union[LLMResponse, MemoryResponse, StorageResponse, ToolResponse, ContextResponse, AccessResponse]

# Generic type variable for query-response pairing
Q = TypeVar('Q', bound=Query)
R = TypeVar('R', bound=Response)

def query_to_response_type(query: Query) -> type:
    """Map query type to expected response type."""
    mapping = {
        LLMQuery: LLMResponse,
        MemoryQuery: MemoryResponse,
        StorageQuery: StorageResponse,
        ToolQuery: ToolResponse,
        ContextQuery: ContextResponse,
        AccessQuery: AccessResponse,
    }
    return mapping.get(type(query), Response)
```

---

## References

- Paper Section 3.2: AIOS SDK
- Figure 3: Query decomposition showing query types
- Figure 9: SDK architecture with code snippets

