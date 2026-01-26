# AIOS System Calls Catalog

This document provides a complete catalog of all system calls supported by the AIOS kernel, derived from Sections 3.1-3.8 and the Appendix of the paper.

---

## Overview

AIOS syscalls are organized into 6 categories:
1. **LLM Syscalls** - LLM inference operations
2. **Memory Syscalls** - Short-term memory management
3. **Storage Syscalls** - Persistent file operations
4. **Tool Syscalls** - External tool invocation
5. **Context Syscalls** - LLM generation state management
6. **Access Syscalls** - Permission and access control

---

## 1. LLM Syscalls

### `llm_generate`
Generate text completion from a prompt.

```python
def llm_generate(
    agent_id: str,
    prompt: str,
    model: str = "default",
    max_tokens: int = 256,
    temperature: float = 0.7,
    stop_sequences: List[str] = None,
    stream: bool = False
) -> LLMResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `prompt`: Input text prompt
- `model`: LLM model identifier
- `max_tokens`: Maximum tokens to generate
- `temperature`: Sampling temperature
- `stop_sequences`: Sequences that stop generation
- `stream`: Whether to stream tokens

**Returns**: `LLMResponse` with generated text

**Paper Reference**: Section 3.1 (LLM Core)

---

### `llm_chat`
Conduct a multi-turn chat conversation.

```python
def llm_chat(
    agent_id: str,
    messages: List[Message],
    model: str = "default",
    max_tokens: int = 256,
    temperature: float = 0.7,
    tools: List[ToolSchema] = None,
    stream: bool = False
) -> LLMResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `messages`: List of chat messages (role + content)
- `model`: LLM model identifier
- `max_tokens`: Maximum tokens to generate
- `temperature`: Sampling temperature
- `tools`: Available tools for function calling
- `stream`: Whether to stream tokens

**Returns**: `LLMResponse` with assistant message

**Paper Reference**: Section 3.1, Figure 9 (SDK)

---

### `llm_embed`
Generate embeddings for text.

```python
def llm_embed(
    agent_id: str,
    text: Union[str, List[str]],
    model: str = "default"
) -> EmbeddingResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `text`: Text or list of texts to embed
- `model`: Embedding model identifier

**Returns**: `EmbeddingResponse` with vector embeddings

**Paper Reference**: Section 3.6 (Storage Manager - semantic retrieval)

---

## 2. Memory Syscalls

### `memory_read`
Read data from agent's short-term memory.

```python
def memory_read(
    agent_id: str,
    key: str
) -> MemoryResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `key`: Memory key to read

**Returns**: `MemoryResponse` with stored data or None

**Paper Reference**: Section 3.5, Figure 5

---

### `memory_write`
Write data to agent's short-term memory.

```python
def memory_write(
    agent_id: str,
    key: str,
    value: Any,
    ttl: int = None
) -> MemoryResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `key`: Memory key to write
- `value`: Data to store
- `ttl`: Time-to-live in seconds (optional)

**Returns**: `MemoryResponse` with write confirmation

**Paper Reference**: Section 3.5, Figure 5

---

### `memory_delete`
Delete data from agent's short-term memory.

```python
def memory_delete(
    agent_id: str,
    key: str
) -> MemoryResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `key`: Memory key to delete

**Returns**: `MemoryResponse` with deletion confirmation

**Paper Reference**: Section 3.5

---

### `memory_search`
Search agent's memory by semantic similarity.

```python
def memory_search(
    agent_id: str,
    query: str,
    limit: int = 10,
    threshold: float = 0.5
) -> MemorySearchResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `query`: Search query text
- `limit`: Maximum results to return
- `threshold`: Minimum similarity score

**Returns**: `MemorySearchResponse` with matching entries

**Paper Reference**: Section 3.5

---

### `memory_list`
List all memory keys for an agent.

```python
def memory_list(
    agent_id: str,
    prefix: str = None
) -> MemoryListResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `prefix`: Optional key prefix filter

**Returns**: `MemoryListResponse` with key list

**Paper Reference**: Section 3.5

---

## 3. Storage Syscalls

### `storage_read`
Read a file from persistent storage.

```python
def storage_read(
    agent_id: str,
    path: str,
    version: int = None
) -> StorageResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `path`: File path relative to agent's storage root
- `version`: Specific version to read (None = latest)

**Returns**: `StorageResponse` with file contents

**Paper Reference**: Section 3.6

---

### `storage_write`
Write a file to persistent storage.

```python
def storage_write(
    agent_id: str,
    path: str,
    data: bytes,
    create_version: bool = True
) -> StorageResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `path`: File path relative to agent's storage root
- `data`: File contents to write
- `create_version`: Whether to create a new version

**Returns**: `StorageResponse` with write confirmation and version

**Paper Reference**: Section 3.6

---

### `storage_delete`
Delete a file from persistent storage.

```python
def storage_delete(
    agent_id: str,
    path: str
) -> StorageResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `path`: File path to delete

**Returns**: `StorageResponse` with deletion confirmation

**Paper Reference**: Section 3.6

---

### `storage_list`
List files in a storage directory.

```python
def storage_list(
    agent_id: str,
    path: str = "/",
    recursive: bool = False
) -> StorageListResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `path`: Directory path to list
- `recursive`: Whether to list recursively

**Returns**: `StorageListResponse` with file list

**Paper Reference**: Section 3.6

---

### `storage_search`
Semantic search across stored files.

```python
def storage_search(
    agent_id: str,
    query: str,
    path: str = "/",
    limit: int = 10
) -> StorageSearchResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `query`: Search query text
- `path`: Directory scope for search
- `limit`: Maximum results

**Returns**: `StorageSearchResponse` with matching files

**Paper Reference**: Section 3.6 (semantic retrieval)

---

### `storage_rollback`
Rollback a file to a previous version.

```python
def storage_rollback(
    agent_id: str,
    path: str,
    version: int
) -> StorageResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `path`: File path to rollback
- `version`: Version to restore

**Returns**: `StorageResponse` with rollback confirmation

**Paper Reference**: Section 3.6 (versioning/rollback)

---

### `storage_share`
Share a file with another agent.

```python
def storage_share(
    agent_id: str,
    path: str,
    target_agent_id: str,
    permissions: List[str] = ["read"]
) -> StorageResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `path`: File path to share
- `target_agent_id`: Agent to share with
- `permissions`: Granted permissions (read/write)

**Returns**: `StorageResponse` with share confirmation

**Paper Reference**: Section 3.6 (sharing)

---

### `storage_lock`
Acquire a lock on a file.

```python
def storage_lock(
    agent_id: str,
    path: str,
    mode: str = "exclusive",
    timeout: int = 30
) -> StorageLockResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `path`: File path to lock
- `mode`: Lock mode (exclusive/shared)
- `timeout`: Lock timeout in seconds

**Returns**: `StorageLockResponse` with lock handle

**Paper Reference**: Section 3.6 (locking)

---

### `storage_unlock`
Release a lock on a file.

```python
def storage_unlock(
    agent_id: str,
    lock_handle: str
) -> StorageResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `lock_handle`: Lock handle from storage_lock

**Returns**: `StorageResponse` with unlock confirmation

**Paper Reference**: Section 3.6 (locking)

---

## 4. Tool Syscalls

### `tool_call`
Execute a registered tool.

```python
def tool_call(
    agent_id: str,
    tool_name: str,
    parameters: Dict[str, Any]
) -> ToolResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `tool_name`: Name of the tool to execute
- `parameters`: Tool parameters as key-value dict

**Returns**: `ToolResponse` with execution result

**Paper Reference**: Section 3.7, Figure 1

---

### `tool_list`
List available tools.

```python
def tool_list(
    agent_id: str,
    category: str = None
) -> ToolListResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `category`: Optional category filter

**Returns**: `ToolListResponse` with tool schemas

**Paper Reference**: Section 3.7

---

### `tool_register`
Register a new tool dynamically.

```python
def tool_register(
    agent_id: str,
    tool_schema: ToolSchema,
    handler: Callable
) -> ToolResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `tool_schema`: Tool definition (name, description, parameters)
- `handler`: Function to execute

**Returns**: `ToolResponse` with registration confirmation

**Paper Reference**: Section 3.7 (standardized loading)

---

### `tool_unregister`
Unregister a tool.

```python
def tool_unregister(
    agent_id: str,
    tool_name: str
) -> ToolResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `tool_name`: Name of the tool to unregister

**Returns**: `ToolResponse` with unregistration confirmation

**Paper Reference**: Section 3.7

---

## 5. Context Syscalls

### `context_snapshot`
Snapshot current LLM generation state.

```python
def context_snapshot(
    agent_id: str,
    snapshot_type: str = "text"
) -> ContextResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `snapshot_type`: "text" or "logits"

**Returns**: `ContextResponse` with snapshot ID

**Paper Reference**: Section 3.4, Figure 4

---

### `context_restore`
Restore LLM state from a snapshot.

```python
def context_restore(
    agent_id: str,
    snapshot_id: str
) -> ContextResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `snapshot_id`: ID of snapshot to restore

**Returns**: `ContextResponse` with restoration confirmation

**Paper Reference**: Section 3.4, Figure 4

---

### `context_suspend`
Suspend an agent's LLM generation.

```python
def context_suspend(
    agent_id: str
) -> ContextResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent

**Returns**: `ContextResponse` with suspension confirmation

**Paper Reference**: Section 3.4, Figure 4

---

### `context_resume`
Resume a suspended agent's LLM generation.

```python
def context_resume(
    agent_id: str
) -> ContextResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent

**Returns**: `ContextResponse` with resumption confirmation

**Paper Reference**: Section 3.4, Figure 4

---

### `context_list`
List all snapshots for an agent.

```python
def context_list(
    agent_id: str
) -> ContextListResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent

**Returns**: `ContextListResponse` with snapshot list

**Paper Reference**: Section 3.4

---

### `context_delete`
Delete a snapshot.

```python
def context_delete(
    agent_id: str,
    snapshot_id: str
) -> ContextResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `snapshot_id`: ID of snapshot to delete

**Returns**: `ContextResponse` with deletion confirmation

**Paper Reference**: Section 3.4

---

## 6. Access Syscalls

### `access_check`
Check if an operation is permitted.

```python
def access_check(
    agent_id: str,
    operation: str,
    resource: str,
    target_agent_id: str = None
) -> AccessResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `operation`: Operation type (read/write/execute/delete)
- `resource`: Resource identifier
- `target_agent_id`: Target agent for cross-agent ops

**Returns**: `AccessResponse` with permission status

**Paper Reference**: Section 3.8

---

### `access_request`
Request access to a protected resource.

```python
def access_request(
    agent_id: str,
    operation: str,
    resource: str,
    justification: str = None
) -> AccessResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `operation`: Operation type
- `resource`: Resource identifier
- `justification`: Reason for access request

**Returns**: `AccessResponse` with request status

**Paper Reference**: Section 3.8

---

### `access_confirm`
Request user confirmation for irreversible operation.

```python
def access_confirm(
    agent_id: str,
    operation: str,
    description: str,
    timeout: int = 60
) -> AccessResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the calling agent
- `operation`: Operation requiring confirmation
- `description`: Human-readable description
- `timeout`: Confirmation timeout in seconds

**Returns**: `AccessResponse` with user decision

**Paper Reference**: Section 3.8 (user intervention)

---

### `access_grant`
Grant access to another agent (admin only).

```python
def access_grant(
    agent_id: str,
    target_agent_id: str,
    resource: str,
    permissions: List[str]
) -> AccessResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the admin agent
- `target_agent_id`: Agent to grant access to
- `resource`: Resource identifier
- `permissions`: Permissions to grant

**Returns**: `AccessResponse` with grant confirmation

**Paper Reference**: Section 3.8

---

### `access_revoke`
Revoke access from another agent (admin only).

```python
def access_revoke(
    agent_id: str,
    target_agent_id: str,
    resource: str,
    permissions: List[str] = None
) -> AccessResponse
```

**Parameters**:
- `agent_id`: Unique identifier of the admin agent
- `target_agent_id`: Agent to revoke access from
- `resource`: Resource identifier
- `permissions`: Permissions to revoke (None = all)

**Returns**: `AccessResponse` with revoke confirmation

**Paper Reference**: Section 3.8

---

## Syscall Summary Table

| Category | Syscall | Description | Paper Section |
|----------|---------|-------------|---------------|
| LLM | llm_generate | Text completion | 3.1 |
| LLM | llm_chat | Multi-turn chat | 3.1 |
| LLM | llm_embed | Generate embeddings | 3.6 |
| Memory | memory_read | Read from memory | 3.5 |
| Memory | memory_write | Write to memory | 3.5 |
| Memory | memory_delete | Delete from memory | 3.5 |
| Memory | memory_search | Semantic search | 3.5 |
| Memory | memory_list | List memory keys | 3.5 |
| Storage | storage_read | Read file | 3.6 |
| Storage | storage_write | Write file | 3.6 |
| Storage | storage_delete | Delete file | 3.6 |
| Storage | storage_list | List files | 3.6 |
| Storage | storage_search | Semantic file search | 3.6 |
| Storage | storage_rollback | Restore file version | 3.6 |
| Storage | storage_share | Share file | 3.6 |
| Storage | storage_lock | Acquire file lock | 3.6 |
| Storage | storage_unlock | Release file lock | 3.6 |
| Tool | tool_call | Execute tool | 3.7 |
| Tool | tool_list | List tools | 3.7 |
| Tool | tool_register | Register tool | 3.7 |
| Tool | tool_unregister | Unregister tool | 3.7 |
| Context | context_snapshot | Save generation state | 3.4 |
| Context | context_restore | Restore state | 3.4 |
| Context | context_suspend | Pause generation | 3.4 |
| Context | context_resume | Resume generation | 3.4 |
| Context | context_list | List snapshots | 3.4 |
| Context | context_delete | Delete snapshot | 3.4 |
| Access | access_check | Check permission | 3.8 |
| Access | access_request | Request access | 3.8 |
| Access | access_confirm | User confirmation | 3.8 |
| Access | access_grant | Grant permission | 3.8 |
| Access | access_revoke | Revoke permission | 3.8 |

