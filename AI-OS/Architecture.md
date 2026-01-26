# AIOS Architecture

This document describes the layered architecture of AIOS as specified in the paper (Section 2, Figure 2).

---

## Layer Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           APPLICATION LAYER                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐        │
│  │ Travel Agent │ │  Rec Agent   │ │ Coding Agent │ │  Math Agent  │ ...    │
│  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘        │
│         │                │                │                │                 │
│         └────────────────┴────────────────┴────────────────┘                 │
│                                   │                                          │
│                          ┌────────▼────────┐                                 │
│                          │  AIOS-Agent SDK │                                 │
│                          │   (Cerebrum)    │                                 │
│                          └────────┬────────┘                                 │
│                                   │                                          │
│         ┌─────────────────────────┴─────────────────────────┐                │
│         │                                                   │                │
│   Non-LLM Queries                                    LLM Queries             │
│   (File/Network/IO)                            (Reasoning/Planning)          │
└─────────┼───────────────────────────────────────────────────┼────────────────┘
          │                                                   │
          ▼                                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             KERNEL LAYER                                     │
├─────────────────────────┬───────────────────────────────────────────────────┤
│                         │                                                   │
│     ┌─────────────────┐ │  ┌─────────────────────────────────────────────┐  │
│     │   OS KERNEL     │ │  │              AIOS KERNEL                    │  │
│     ├─────────────────┤ │  ├─────────────────────────────────────────────┤  │
│     │                 │ │  │            AIOS System Call                 │  │
│     │ Process         │ │  │  ┌─────────────────────────────────────────┐│  │
│     │ Scheduler       │ │  │  │                                         ││  │
│     │                 │ │  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐   ││  │
│     │ Memory          │◄├──┤  │  │   LLM   │ │  Agent  │ │ Context │   ││  │
│     │ Manager         │ │  │  │  │ Core(s) │ │Scheduler│ │ Manager │   ││  │
│     │                 │ │  │  │  └─────────┘ └─────────┘ └─────────┘   ││  │
│     │ Filesystem      │ │  │  │                                         ││  │
│     │                 │ │  │  │  ┌─────────┐ ┌─────────┐ ┌─────────┐   ││  │
│     │ Hardware        │ │  │  │  │ Memory  │ │ Storage │ │  Tool   │   ││  │
│     │ Driver          │ │  │  │  │ Manager │ │ Manager │ │ Manager │   ││  │
│     │                 │ │  │  │  └─────────┘ └─────────┘ └─────────┘   ││  │
│     └────────┬────────┘ │  │  │                                         ││  │
│              │          │  │  │              ┌─────────┐                ││  │
│              │          │  │  │              │ Access  │                ││  │
│              │          │  │  │              │ Manager │                ││  │
│              │          │  │  │              └─────────┘                ││  │
│              │          │  │  └─────────────────────────────────────────┘│  │
│              │          │  └───────────────────────┬─────────────────────┘  │
│              │          │                          │                        │
│              └──────────┴──────────────────────────┘                        │
│                                   │                                          │
│                          OS System Call                                      │
└───────────────────────────────────┼─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            HARDWARE LAYER                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐  │
│   │   CPU   │    │   GPU   │    │  Memory │    │   Disk  │    │Peripherals│ │
│   └─────────┘    └─────────┘    └─────────┘    └─────────┘    └─────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Module Responsibilities

### Application Layer

#### Agent Applications
**Location**: `aios/agents/`

- **Travel Agent**: Handles travel planning, booking, and recommendations
- **Rec Agent**: Provides personalized recommendations
- **Coding Agent**: Assists with code generation and debugging
- **Math Agent**: Solves mathematical problems
- **Narrative Agent**: Generates creative content and stories

**Responsibilities**:
- Define agent-specific logic and workflows
- Decompose user requests into sub-tasks
- Coordinate tool usage and LLM calls
- Manage agent-specific state

#### AIOS-Agent SDK (Cerebrum)
**Location**: `aios/sdk/`

**Responsibilities**:
- Provide unified API for agents to interact with AIOS kernel
- Handle query serialization and transport (HTTP)
- Route queries to appropriate kernel (AIOS vs OS)
- Manage client-side state and caching
- Abstract away kernel implementation details

**Key Components**:
- `client.py`: HTTP client for kernel communication
- `models.py`: Query/Response data classes
- `llm.py`: LLM-specific APIs
- `memory.py`: Memory CRUD operations
- `storage.py`: File storage operations
- `tool.py`: Tool invocation APIs

---

### Kernel Layer

#### AIOS Kernel
**Location**: `aios/kernel/`

##### LLM Core(s)
**Location**: `aios/core/llm.py`

**Responsibilities**:
- Abstract LLM inference as CPU cores abstract compute
- Manage multiple LLM backends (OpenAI, HuggingFace, local)
- Handle concurrent LLM requests
- Provide unified interface for text generation

**Key Features**:
- Multi-backend support
- Request batching
- Token counting
- Response streaming

##### Agent Scheduler
**Location**: `aios/kernel/scheduler.py`

**Responsibilities**:
- Centralized scheduling of all agent syscalls
- Maintain separate queues for different syscall types
- Implement FIFO and Round Robin strategies
- Bind syscalls to execution threads
- Ensure fair resource allocation

**Key Features**:
- 4 queue types: LLM, Tool, Memory, Storage
- Configurable scheduling strategy
- Priority support (optional)
- Starvation prevention

##### Context Manager
**Location**: `aios/kernel/context_manager.py`

**Responsibilities**:
- Enable LLM generation interruption and resumption
- Snapshot LLM state (tokens, logits, KV-cache)
- Restore state for resumed generation
- Support Round Robin scheduling fairness

**Key Features**:
- Text-based snapshot (generated tokens)
- Logits-based snapshot (probability distributions)
- KV-cache preservation
- State serialization

##### Memory Manager
**Location**: `aios/kernel/memory_manager.py`

**Responsibilities**:
- Manage short-term memory for agent interactions
- Store interaction history and agent state
- Implement LRU-K eviction policy
- Coordinate with Storage Manager for swapping

**Key Features**:
- Agent-indexed memory blocks
- Configurable memory limits
- LRU-K eviction (K=2 default)
- Automatic swap to storage

##### Storage Manager
**Location**: `aios/kernel/storage_manager.py`

**Responsibilities**:
- Provide persistent file storage
- Enable semantic retrieval via vector database
- Manage file versions and rollback
- Handle cross-agent file sharing
- Implement file locking

**Key Features**:
- Hierarchical file system (per-agent folders)
- Vector DB integration for semantic search
- Version control with rollback
- Configurable sharing permissions
- Lock management for concurrent access

##### Tool Manager
**Location**: `aios/kernel/tool_manager.py`

**Responsibilities**:
- Load and register available tools
- Validate tool parameters before execution
- Resolve naming conflicts
- Track tool instance counts
- Execute tools safely

**Key Features**:
- Standardized tool interface
- JSON schema validation
- Conflict resolution via hashmap
- Instance limiting
- Error handling and retry

##### Access Manager
**Location**: `aios/kernel/access_manager.py`

**Responsibilities**:
- Define and enforce privilege groups
- Validate cross-agent access requests
- Require user confirmation for irreversible operations
- Log access attempts for auditing

**Key Features**:
- Role-based access control
- Permission inheritance
- User intervention hooks
- Audit logging

---

### Hardware Layer

The hardware layer is accessed through the OS System Call interface:

- **CPU**: General computation
- **GPU**: LLM inference acceleration
- **Memory**: RAM for runtime data
- **Disk**: Persistent storage
- **Peripheral Devices**: Network, input devices, etc.

---

## Data Flow

### LLM Query Flow
```
Agent → SDK.llm_chat() → send_request(LLMQuery)
     → HTTP → AIOS Kernel → Scheduler → LLM Queue
     → LLM Core → Context Manager (if interrupted)
     → Response → SDK → Agent
```

### Memory Query Flow
```
Agent → SDK.memory_write() → send_request(MemoryQuery)
     → HTTP → AIOS Kernel → Scheduler → Memory Queue
     → Memory Manager → (eviction if needed) → Storage Manager
     → Response → SDK → Agent
```

### Tool Query Flow
```
Agent → SDK.tool_call() → send_request(ToolQuery)
     → HTTP → AIOS Kernel → Scheduler → Tool Queue
     → Access Manager (permission check)
     → Tool Manager → Tool Execution
     → Response → SDK → Agent
```

---

## Module Initialization

The kernel uses a hook mechanism for clean initialization:

```python
def initialize_kernel():
    # Initialize in dependency order
    hooks.init_access_manager()
    hooks.init_storage_manager()
    hooks.init_memory_manager()
    hooks.init_tool_manager()
    hooks.init_context_manager()
    hooks.init_llm_cores()
    hooks.init_scheduler()
    hooks.start_kernel()
```

---

## Design Principles

1. **Separation of Concerns**: Each module has a single, well-defined responsibility
2. **Layered Architecture**: Clear boundaries between layers
3. **Extensibility**: Easy to add new agents, tools, LLM backends
4. **Fault Isolation**: Module failures don't crash the kernel
5. **Observable**: Comprehensive logging and metrics
6. **Testable**: Each module is independently testable

---

## References

- Paper Section 2: The Architecture of AIOS
- Figure 2: AIOS Architecture Overview
- Figure 3: Query Decomposition and Scheduling

