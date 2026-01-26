# AIOS Implementation Assumptions

This document records all underspecified aspects of the AIOS paper and the design decisions made to resolve them. Each assumption includes the paper location, the ambiguity, considered alternatives, the chosen approach, and rationale.

---

## 1. LLM Core Abstraction

### Assumption A1: Number of LLM Cores
**Paper Location**: Section 3.1, Figure 2

**Ambiguity**: The paper mentions "LLM Core(s)" but doesn't specify:
- How many cores are supported
- How to configure core count
- Whether cores can be heterogeneous (different models)

**Alternatives Considered**:
1. Single core only (simplest)
2. Fixed number of cores configured at startup
3. Dynamic core pool that scales with demand

**Chosen Approach**: Option 2 - Fixed number of configurable cores at startup, with support for heterogeneous models.

**Rationale**: Matches traditional OS design where CPU count is fixed at boot. Heterogeneous support allows mixing OpenAI API with local models.

**Implementation**:
```python
# config.yaml
llm_cores:
  - name: "core-0"
    backend: "openai"
    model: "gpt-4"
  - name: "core-1"
    backend: "huggingface"
    model: "meta-llama/Llama-2-7b"
```

---

### Assumption A2: LLM Backend Abstraction
**Paper Location**: Section 3.1

**Ambiguity**: The paper doesn't specify the exact interface between LLM Core and actual LLM backends.

**Alternatives Considered**:
1. Direct integration with specific LLM libraries
2. OpenAI-compatible API as universal interface
3. Abstract base class with backend-specific implementations

**Chosen Approach**: Option 3 - Abstract base class (`LLMBackend`) with concrete implementations for OpenAI, HuggingFace, vLLM, and Ollama.

**Rationale**: Provides flexibility while maintaining consistent interface. Users can add new backends easily.

**Implementation**:
```python
class LLMBackend(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str: ...
    
    @abstractmethod
    async def chat(self, messages: List[Message], **kwargs) -> Message: ...
```

---

## 2. Scheduler Design

### Assumption A3: Time Slice Duration for Round Robin
**Paper Location**: Section 3.3

**Ambiguity**: The paper mentions Round Robin scheduling but doesn't specify:
- Time slice duration
- Granularity of interruption (token-level, sentence-level, etc.)

**Alternatives Considered**:
1. Fixed 100ms time slice
2. Token-count-based slicing (e.g., every 50 tokens)
3. Adaptive slicing based on queue depth

**Chosen Approach**: Hybrid - Token-count-based with configurable default of 50 tokens, but also respecting a maximum time limit of 500ms.

**Rationale**: Token-based is more natural for LLM generation and provides consistent granularity. Time limit prevents very slow tokens from blocking.

**Implementation**:
```python
scheduler_config:
  round_robin:
    tokens_per_slice: 50
    max_time_ms: 500
```

---

### Assumption A4: Queue Priority Between Syscall Types
**Paper Location**: Section 3.3, Figure 3

**Ambiguity**: The paper shows 4 queue types but doesn't specify relative priorities or how to choose between queues when multiple have pending syscalls.

**Alternatives Considered**:
1. Equal priority, round-robin between queues
2. Fixed priority order (Memory > Storage > Tool > LLM)
3. Weighted fair queuing

**Chosen Approach**: Option 1 with modification - Equal priority round-robin, but Memory/Storage syscalls are faster so naturally drain quicker. LLM queue has dedicated core(s).

**Rationale**: Prevents starvation while acknowledging that LLM is the bottleneck resource.

---

### Assumption A5: Syscall Ordering Within a Query
**Paper Location**: Section 3.3, Figure 3

**Ambiguity**: When a query decomposes into multiple syscalls (e.g., B1.1, B1.2, B1.3), must they execute in order?

**Alternatives Considered**:
1. Strict sequential execution
2. Parallel execution where possible
3. Dependency-aware execution

**Chosen Approach**: Option 3 - Dependency-aware execution. Syscalls specify dependencies, independent ones can run in parallel.

**Rationale**: Maximizes throughput while respecting logical dependencies.

**Implementation**:
```python
@dataclass
class Syscall:
    depends_on: List[str] = field(default_factory=list)  # List of syscall_ids
```

---

## 3. Context Manager

### Assumption A6: Snapshot Storage Location
**Paper Location**: Section 3.4, Figure 4

**Ambiguity**: Where are context snapshots stored? In memory? On disk?

**Alternatives Considered**:
1. In-memory only (fast but limited)
2. Disk-based (persistent but slow)
3. Tiered: hot snapshots in memory, cold on disk

**Chosen Approach**: Option 3 - Tiered storage. Recent snapshots (last 5 per agent) in memory, older ones swapped to disk.

**Rationale**: Balances performance with memory constraints. Most restorations are recent.

---

### Assumption A7: Logits Snapshot Granularity
**Paper Location**: Section 3.4, Figure 4

**Ambiguity**: For logits-based snapshots, how much of the probability distribution is stored?

**Alternatives Considered**:
1. Full vocabulary logits at each position
2. Top-K logits only (e.g., top 100)
3. Only the selected token path

**Chosen Approach**: Option 2 - Store top-K logits (K=100 default) at each generation step.

**Rationale**: Full vocabulary is prohibitively large (32K+ floats per position). Top-K captures the meaningful probability mass while being practical.

**Implementation**:
```python
@dataclass
class LogitsSnapshot:
    top_k: int = 100
    logits_per_step: List[Dict[int, float]]  # token_id -> probability
```

---

### Assumption A8: KV-Cache Handling
**Paper Location**: Section 3.4, Figure 4

**Ambiguity**: The paper doesn't explicitly discuss KV-cache (key-value cache used by transformers for efficient generation).

**Alternatives Considered**:
1. Discard KV-cache on interruption, regenerate on resume
2. Serialize and store KV-cache with snapshot
3. Use prompt-caching features of LLM backends

**Chosen Approach**: Backend-dependent. For local models, serialize KV-cache. For API-based (OpenAI), use their prompt caching if available, otherwise regenerate.

**Rationale**: KV-cache serialization is backend-specific. API backends don't expose this.

---

## 4. Memory Manager

### Assumption A9: LRU-K Parameter Value
**Paper Location**: Section 3.5, Figure 5

**Ambiguity**: The paper mentions "LRU-K" but doesn't specify the value of K.

**Alternatives Considered**:
1. K=1 (standard LRU)
2. K=2 (LRU-2, common choice)
3. Configurable K

**Chosen Approach**: K=2 as default, configurable.

**Rationale**: LRU-2 is a well-studied choice that handles scan-resistant patterns better than LRU-1 while being simpler than higher K values.

**Implementation**:
```python
memory_manager:
  eviction_policy: "lru-k"
  lru_k_value: 2
  memory_limit_mb: 512
```

---

### Assumption A10: Memory Block Size
**Paper Location**: Section 3.5, Figure 5

**Ambiguity**: Figure 5 shows memory blocks but doesn't specify their size or whether they're fixed or variable.

**Alternatives Considered**:
1. Fixed 4KB blocks (like OS pages)
2. Variable-size blocks per entry
3. Fixed 64KB blocks for LLM contexts

**Chosen Approach**: Variable-size blocks with 64KB maximum.

**Rationale**: LLM conversation histories vary greatly in size. Fixed blocks waste space for small entries.

---

### Assumption A11: Memory-Storage Swap Trigger
**Paper Location**: Section 3.5, Figure 5

**Ambiguity**: When exactly does memory swap to storage trigger?

**Alternatives Considered**:
1. Fixed threshold (e.g., 80% full)
2. On each eviction
3. Background swapping when idle

**Chosen Approach**: Threshold-based (75% default) with background swapping.

**Rationale**: Proactive swapping prevents blocking on write operations.

**Implementation**:
```python
memory_manager:
  swap_threshold_percent: 75
  background_swap_enabled: true
```

---

## 5. Storage Manager

### Assumption A12: Vector Database Choice
**Paper Location**: Section 3.6

**Ambiguity**: The paper mentions "semantic retrieval" but doesn't specify the vector database.

**Alternatives Considered**:
1. Embedded: SQLite with vector extension
2. Lightweight: Chroma, LanceDB
3. Production: Milvus, Qdrant, Pinecone

**Chosen Approach**: ChromaDB as default (embedded, no external service required), with adapter interface for other backends.

**Rationale**: Easy to install, no external dependencies, suitable for development. Can swap for production use.

---

### Assumption A13: Versioning Implementation
**Paper Location**: Section 3.6

**Ambiguity**: The paper mentions "versioning" and "rollback" but doesn't specify implementation.

**Alternatives Considered**:
1. Git-based versioning
2. Copy-on-write with version numbers
3. Differential patches

**Chosen Approach**: Option 2 - Copy-on-write with monotonic version numbers. Full file copies for each version.

**Rationale**: Simple, reliable, easy to implement. Space can be optimized later with differential storage.

**Implementation**:
```
storage/
  agent-001/
    files/
      data.json          # Current version
    versions/
      data.json/
        v1/              # Version 1
        v2/              # Version 2 (latest)
```

---

### Assumption A14: Lock Implementation
**Paper Location**: Section 3.6

**Ambiguity**: Lock mechanism details not specified.

**Alternatives Considered**:
1. In-memory locks (fast but not distributed)
2. File-based locks (portable)
3. Redis-based distributed locks

**Chosen Approach**: In-memory locks for single-node deployment, with interface for distributed locks.

**Rationale**: Start simple, design for extensibility.

---

## 6. Tool Manager

### Assumption A15: Tool Conflict Resolution Strategy
**Paper Location**: Section 3.7

**Ambiguity**: The paper mentions "conflict resolution" using hashmap/instance counts but doesn't detail the strategy.

**Alternatives Considered**:
1. First-registered wins
2. Last-registered wins
3. Namespace prefixing
4. User prompt to resolve

**Chosen Approach**: Namespace prefixing by agent ID for agent-registered tools; global tools must have unique names.

**Rationale**: Allows multiple agents to register same-named tools without conflict.

**Implementation**:
```python
# Global tool: "search_web"
# Agent-specific: "agent-001/custom_search"
```

---

### Assumption A16: Tool Instance Limits
**Paper Location**: Section 3.7

**Ambiguity**: How are concurrent tool instances limited?

**Alternatives Considered**:
1. Per-tool limits defined in schema
2. Global limit on total concurrent tools
3. Resource-based limits (CPU/memory)

**Chosen Approach**: Per-tool limits defined in tool schema, with global default.

**Implementation**:
```python
@dataclass
class ToolSchema:
    name: str
    max_concurrent_instances: int = 4
```

---

## 7. Access Manager

### Assumption A17: Privilege Group Definition
**Paper Location**: Section 3.8

**Ambiguity**: The paper mentions "privilege groups" but doesn't define specific groups.

**Alternatives Considered**:
1. Simple two-level (user/admin)
2. Unix-like (owner/group/others)
3. Role-based with custom roles

**Chosen Approach**: Four-level hierarchy (GUEST, USER, ELEVATED, ADMIN) with role-based extension capability.

**Rationale**: Provides sensible defaults while allowing customization.

---

### Assumption A18: User Confirmation Mechanism
**Paper Location**: Section 3.8

**Ambiguity**: How does user confirmation work at runtime?

**Alternatives Considered**:
1. CLI prompt
2. Web UI dialog
3. Callback/webhook
4. Auto-approve with logging

**Chosen Approach**: Pluggable confirmation handler with CLI default, webhook support for integration.

**Implementation**:
```python
class ConfirmationHandler(ABC):
    @abstractmethod
    async def request_confirmation(self, request: ConfirmationRequest) -> bool: ...

class CLIConfirmationHandler(ConfirmationHandler):
    async def request_confirmation(self, request):
        response = input(f"Approve '{request.description}'? [y/N]: ")
        return response.lower() == 'y'
```

---

## 8. SDK Design

### Assumption A19: Transport Protocol
**Paper Location**: Section 3.2, Figure 9

**Ambiguity**: Figure 9 shows "HTTP" but doesn't specify:
- REST vs GraphQL vs gRPC
- Sync vs async
- Streaming support

**Alternatives Considered**:
1. REST with JSON
2. gRPC with protobuf
3. WebSocket for bidirectional

**Chosen Approach**: REST with JSON for simplicity, WebSocket optional for streaming.

**Rationale**: HTTP/JSON is universally supported, easy to debug, and sufficient for most use cases.

---

### Assumption A20: SDK Language Support
**Paper Location**: Section 3.2

**Ambiguity**: Paper doesn't specify SDK languages beyond the reference implementation.

**Alternatives Considered**:
1. Python only
2. Python + JavaScript
3. Multi-language via OpenAPI

**Chosen Approach**: Python primary, with OpenAPI spec generation for other language clients.

**Rationale**: Python is primary for AI/ML. OpenAPI enables automatic client generation.

---

## 9. Evaluation Harness

### Assumption A21: Throughput Measurement Method
**Paper Location**: Section 4, Figures 6-7

**Ambiguity**: Exact throughput measurement methodology not fully specified.

**Alternatives Considered**:
1. Requests per second
2. Syscalls per second
3. Tokens per second

**Chosen Approach**: Syscalls per second, normalized against baseline (without AIOS).

**Rationale**: Aligns with paper's architecture (syscall-centric). Normalization allows fair comparison.

**Implementation**:
```python
throughput = completed_syscalls / total_time_seconds
normalized_throughput = throughput / baseline_throughput
```

---

### Assumption A22: Latency Measurement Point
**Paper Location**: Section 4, Figures 6-7

**Ambiguity**: Where is latency measured? End-to-end or queue wait time?

**Alternatives Considered**:
1. End-to-end (query submit to response)
2. Queue wait time only
3. Execution time only

**Chosen Approach**: Both metrics tracked separately; primary metric is average waiting time per syscall (queue time).

**Rationale**: Figure 8 specifically mentions "Average Agent Waiting Time", suggesting queue-focused measurement.

---

## 10. Figure Interpretation Ambiguities

### Assumption A23: Figure 4 - Probability Values
**Paper Location**: Figure 4, Section 3.4

**Ambiguity**: The probability values shown (0.6, 0.4, 0.7, 0.3, etc.) - are these exact values to reproduce or illustrative?

**Chosen Approach**: Illustrative. The mechanism (branching probabilities, snapshot at branching points) is what matters, not specific values.

---

### Assumption A24: Figure 5 - Agent ID Numbering
**Paper Location**: Figure 5, Section 3.5

**Ambiguity**: Agent IDs shown as integers (1, 2, n) - are IDs integers or strings?

**Chosen Approach**: String UUIDs for actual implementation; integers are for illustration only.

**Rationale**: UUIDs prevent collision in distributed settings.

---

## Summary Table

| ID | Topic | Paper Location | Decision | Confidence |
|----|-------|----------------|----------|------------|
| A1 | LLM Core Count | 3.1, Fig 2 | Configurable, heterogeneous | Medium |
| A2 | LLM Backend Interface | 3.1 | Abstract base class | High |
| A3 | RR Time Slice | 3.3 | 50 tokens / 500ms max | Medium |
| A4 | Queue Priority | 3.3, Fig 3 | Equal priority round-robin | Medium |
| A5 | Syscall Ordering | 3.3, Fig 3 | Dependency-aware | High |
| A6 | Snapshot Storage | 3.4, Fig 4 | Tiered (memory + disk) | Medium |
| A7 | Logits Granularity | 3.4, Fig 4 | Top-100 | Medium |
| A8 | KV-Cache | 3.4 | Backend-dependent | Low |
| A9 | LRU-K Value | 3.5, Fig 5 | K=2 | High |
| A10 | Memory Block Size | 3.5, Fig 5 | Variable, 64KB max | Medium |
| A11 | Swap Trigger | 3.5, Fig 5 | 75% threshold | Medium |
| A12 | Vector DB | 3.6 | ChromaDB default | Medium |
| A13 | Versioning | 3.6 | Copy-on-write | High |
| A14 | Locking | 3.6 | In-memory | Medium |
| A15 | Tool Conflicts | 3.7 | Namespace prefixing | High |
| A16 | Tool Instances | 3.7 | Per-tool limits | Medium |
| A17 | Privilege Groups | 3.8 | 4-level hierarchy | Medium |
| A18 | User Confirmation | 3.8 | Pluggable handler | High |
| A19 | Transport | 3.2, Fig 9 | REST + WebSocket | High |
| A20 | SDK Languages | 3.2 | Python + OpenAPI | High |
| A21 | Throughput | 4, Fig 6-7 | Syscalls/sec, normalized | High |
| A22 | Latency | 4, Fig 6-7 | Queue wait time | High |
| A23 | Fig 4 Probs | Fig 4 | Illustrative | High |
| A24 | Agent IDs | Fig 5 | String UUIDs | High |

---

## Updates

This document will be updated as implementation progresses and new ambiguities are discovered.

Last updated: [Implementation Start Date]

