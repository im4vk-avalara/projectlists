# AIOS Design Review

This document discusses the 10 most critical design decisions in the AIOS implementation and how they were validated against the paper.

---

## 1. LLM Core as CPU Core Analogy

### Decision
Model LLM inference capacity as "LLM Cores" similar to how CPUs have cores.

### Paper Reference
- Section 3.1: "Similar to how OS kernel abstracts CPU cores..."
- Figure 2: Shows "LLM Core(s)" as a kernel module

### Implementation
```python
class LLMCore:
    """
    Represents a single LLM inference unit.
    Multiple cores can run different models or backends.
    """
    def __init__(self, name: str, backend: LLMBackend):
        self.name = name
        self.backend = backend
        self.is_busy = False
        self.current_agent = None
```

### Validation
- ✅ Supports multiple concurrent "cores"
- ✅ Each core can have different backend (heterogeneous)
- ✅ Scheduler assigns requests to available cores

### Trade-offs
- **Pro**: Clean abstraction, matches paper terminology
- **Con**: Unlike real CPU cores, LLM cores can't truly parallelize on single GPU

---

## 2. Centralized vs Distributed Scheduler

### Decision
Implement a single centralized scheduler managing all queues.

### Paper Reference
- Section 3.3: "The Agent Scheduler is in charge of..."
- Figure 3: Shows single "Scheduler" block managing all queues

### Implementation
```python
class Scheduler:
    def __init__(self):
        self.llm_queue = Queue()
        self.tool_queue = Queue()
        self.memory_queue = Queue()
        self.storage_queue = Queue()
    
    async def run(self):
        # Single scheduling loop
        while True:
            syscall = await self.select_next()
            await self.execute(syscall)
```

### Validation
- ✅ Matches Figure 3 architecture
- ✅ Enables global scheduling decisions
- ✅ Supports both FIFO and Round Robin

### Trade-offs
- **Pro**: Simpler implementation, easier to enforce fairness
- **Con**: Single point of bottleneck; may need sharding for scale

---

## 3. Context Snapshot Strategy Selection

### Decision
Implement text-based snapshots as primary, logits-based as optional.

### Paper Reference
- Section 3.4: Describes both approaches
- Figure 4: Shows snapshot/restore with probability trees

### Implementation
```python
class ContextManager:
    def __init__(self, snapshot_type: SnapshotType = SnapshotType.TEXT):
        self.snapshot_type = snapshot_type
    
    def create_snapshot(self, agent_id: str, state: GenerationState):
        if self.snapshot_type == SnapshotType.TEXT:
            return TextSnapshot(tokens=state.generated_tokens)
        else:
            return LogitsSnapshot(
                tokens=state.generated_tokens,
                logits=state.top_k_logits
            )
```

### Validation
- ✅ Text-based works for most use cases
- ✅ Logits-based preserves probability distribution
- ✅ Choice is configurable

### Trade-offs
| Approach | Memory Usage | Restoration Accuracy | Complexity |
|----------|--------------|---------------------|------------|
| Text-based | Low | Good | Low |
| Logits-based | High | Exact | High |

---

## 4. LRU-K Eviction with K=2

### Decision
Use LRU-2 for memory eviction policy.

### Paper Reference
- Section 3.5: "LRU-K eviction policy"
- Figure 5: Shows LRU-K Eviction label

### Implementation
```python
class LRUK:
    def __init__(self, k: int = 2):
        self.k = k
        self.access_history: Dict[str, List[float]] = {}
    
    def record_access(self, key: str):
        if key not in self.access_history:
            self.access_history[key] = []
        self.access_history[key].append(time.time())
        # Keep only last K accesses
        self.access_history[key] = self.access_history[key][-self.k:]
    
    def get_eviction_candidate(self) -> str:
        # Return key with oldest K-th access
        return min(
            self.access_history.keys(),
            key=lambda k: self.access_history[k][0] if len(self.access_history[k]) >= self.k else 0
        )
```

### Validation
- ✅ K=2 is a well-established choice in literature
- ✅ Handles scan-resistant patterns
- ✅ Simple to implement and understand

### Trade-offs
- **Pro**: Better than LRU-1 for bursty access patterns
- **Con**: Slightly more memory overhead to track K accesses

---

## 5. Storage Versioning via Copy-on-Write

### Decision
Implement file versioning using full copies with monotonic version numbers.

### Paper Reference
- Section 3.6: "versioning" and "rollback" capabilities

### Implementation
```python
class StorageManager:
    def write(self, agent_id: str, path: str, data: bytes) -> FileInfo:
        # Get current version
        current_version = self.get_latest_version(agent_id, path)
        new_version = current_version + 1
        
        # Write new version
        version_path = f"versions/{path}/v{new_version}"
        self._write_file(version_path, data)
        
        # Update current symlink
        self._update_symlink(path, version_path)
        
        return FileInfo(path=path, version=new_version)
```

### Validation
- ✅ Simple and reliable
- ✅ Rollback is just changing symlink
- ✅ No complex diff algorithms needed

### Trade-offs
- **Pro**: Easy to implement, fast rollback
- **Con**: Storage space grows with each version

---

## 6. Tool Conflict Resolution via Namespacing

### Decision
Use agent-prefixed namespacing for tool names to avoid conflicts.

### Paper Reference
- Section 3.7: "conflict resolution" using hashmap

### Implementation
```python
class ToolManager:
    def register(self, agent_id: str, tool_schema: ToolSchema) -> str:
        # Namespace with agent ID
        namespaced_name = f"{agent_id}/{tool_schema.name}"
        
        if namespaced_name in self.registry:
            raise ToolConflict(f"Tool {namespaced_name} already exists")
        
        self.registry[namespaced_name] = tool_schema
        return namespaced_name
    
    def call(self, agent_id: str, tool_name: str, params: Dict) -> Any:
        # Try agent-specific first, then global
        candidates = [
            f"{agent_id}/{tool_name}",  # Agent-specific
            tool_name                     # Global
        ]
        
        for candidate in candidates:
            if candidate in self.registry:
                return self._execute(candidate, params)
        
        raise ToolNotFound(tool_name)
```

### Validation
- ✅ Prevents name collisions
- ✅ Allows agent-specific tool overrides
- ✅ Global tools still accessible

### Trade-offs
- **Pro**: Clean isolation between agents
- **Con**: Slightly more complex lookup

---

## 7. User Confirmation as Pluggable Handler

### Decision
Make user confirmation mechanism pluggable with CLI as default.

### Paper Reference
- Section 3.8: "user intervention" for irreversible operations

### Implementation
```python
class ConfirmationHandler(ABC):
    @abstractmethod
    async def request_confirmation(self, request: ConfirmationRequest) -> bool:
        pass

class CLIConfirmationHandler(ConfirmationHandler):
    async def request_confirmation(self, request: ConfirmationRequest) -> bool:
        print(f"\n⚠️ Operation requires confirmation:")
        print(f"   {request.description}")
        response = input("Approve? [y/N]: ")
        return response.lower() == 'y'

class WebhookConfirmationHandler(ConfirmationHandler):
    async def request_confirmation(self, request: ConfirmationRequest) -> bool:
        response = await httpx.post(
            self.webhook_url,
            json=request.to_dict(),
            timeout=request.timeout
        )
        return response.json()["approved"]
```

### Validation
- ✅ CLI works for development/testing
- ✅ Webhook enables production integrations
- ✅ Easy to add new handlers (Slack, email, etc.)

### Trade-offs
- **Pro**: Flexible deployment options
- **Con**: Adds latency for confirmation

---

## 8. REST+JSON for SDK Transport

### Decision
Use REST with JSON over HTTP for SDK-to-kernel communication.

### Paper Reference
- Section 3.2, Figure 9: Shows "HTTP (localhost/remote url)"

### Implementation
```python
class AIOSClient:
    def __init__(self, kernel_url: str = "http://localhost:8000"):
        self.kernel_url = kernel_url
        self.client = httpx.AsyncClient()
    
    async def send_request(self, query: Query) -> Response:
        response = await self.client.post(
            f"{self.kernel_url}/syscall",
            json=query.to_dict(),
            headers={"Content-Type": "application/json"}
        )
        return self._parse_response(response.json())
```

### Validation
- ✅ Matches paper's HTTP mention
- ✅ Universal support (any language can call)
- ✅ Easy debugging (curl, Postman)

### Trade-offs
- **Pro**: Simple, widely supported
- **Con**: Higher overhead than gRPC; no built-in streaming

---

## 9. Agent-Indexed Memory Blocks

### Decision
Organize memory by agent ID with hierarchical key structure.

### Paper Reference
- Section 3.5, Figure 5: Shows "Memory Note" with "Agent ID: 1, 2, ..., n"

### Implementation
```python
class MemoryManager:
    def __init__(self):
        self.memory: Dict[str, Dict[str, MemoryBlock]] = {}  # agent_id -> {key -> block}
    
    def write(self, agent_id: str, key: str, value: Any) -> MemoryBlock:
        if agent_id not in self.memory:
            self.memory[agent_id] = {}
        
        block = MemoryBlock(
            agent_id=agent_id,
            key=key,
            value=value,
            created_at=time.time()
        )
        
        self.memory[agent_id][key] = block
        return block
    
    def read(self, agent_id: str, key: str) -> Optional[Any]:
        return self.memory.get(agent_id, {}).get(key)
```

### Validation
- ✅ Matches Figure 5 structure
- ✅ Natural isolation between agents
- ✅ Efficient per-agent eviction

### Trade-offs
- **Pro**: Clean agent isolation
- **Con**: Cross-agent access requires explicit sharing

---

## 10. Evaluation Metrics Aligned with Paper

### Decision
Measure throughput as syscalls/second and latency as average wait time.

### Paper Reference
- Section 4: "throughput" and "latency" metrics
- Figures 6-7: Normalized throughput/latency charts

### Implementation
```python
class MetricsCollector:
    def __init__(self):
        self.syscalls_completed = 0
        self.waiting_times: List[float] = []
        self.start_time = time.time()
    
    def record_syscall_complete(self, syscall: Syscall):
        self.syscalls_completed += 1
        wait_time = syscall.started_at - syscall.enqueued_at
        self.waiting_times.append(wait_time)
    
    @property
    def throughput(self) -> float:
        elapsed = time.time() - self.start_time
        return self.syscalls_completed / elapsed
    
    @property
    def average_latency(self) -> float:
        return statistics.mean(self.waiting_times)
    
    def normalize(self, baseline_throughput: float, baseline_latency: float):
        return {
            "normalized_throughput": self.throughput / baseline_throughput,
            "normalized_latency": self.average_latency / baseline_latency
        }
```

### Validation
- ✅ Matches paper's methodology
- ✅ Normalization allows fair comparison
- ✅ Results should match paper's trends (AIOS improves both)

### Trade-offs
- **Pro**: Directly comparable to paper results
- **Con**: May miss other important metrics (e.g., tail latency)

---

## Summary Validation Matrix

| Design Decision | Paper Section | Validated By | Status |
|-----------------|---------------|--------------|--------|
| LLM Core abstraction | 3.1, Fig 2 | Unit tests | ✅ |
| Centralized scheduler | 3.3, Fig 3 | Integration tests | ✅ |
| Context snapshot | 3.4, Fig 4 | Regression tests | ✅ |
| LRU-K eviction | 3.5, Fig 5 | Unit tests | ✅ |
| Copy-on-write versioning | 3.6 | Unit tests | ✅ |
| Tool namespacing | 3.7 | Unit tests | ✅ |
| Pluggable confirmation | 3.8 | Integration tests | ✅ |
| REST+JSON transport | 3.2, Fig 9 | Integration tests | ✅ |
| Agent-indexed memory | 3.5, Fig 5 | Unit tests | ✅ |
| Paper-aligned metrics | 4, Fig 6-7 | Benchmark tests | ✅ |

---

## Open Questions for Future Work

1. **Distributed Scheduling**: How to scale scheduler across multiple nodes?
2. **GPU Memory Management**: How to handle GPU memory for local LLM cores?
3. **Persistent Context**: Should context snapshots survive kernel restart?
4. **Federated Agents**: How to support agents across multiple AIOS instances?
5. **Security Hardening**: Sandboxing for tool execution?

These are documented but not addressed in the paper, marking opportunities for future research.

