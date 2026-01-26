# AIOS Figure Digest

This document provides a comprehensive analysis of all figures and tables from the AIOS paper (arXiv:2403.16971v5).

---

## Figure 1: Travel Agent Workflow Example
**Paper Location**: Section 1 (Introduction), Page 1

### What it Depicts
Illustrates a real-world travel agent scenario demonstrating how an LLM agent must coordinate between LLM-managed operations and OS-managed resources to complete a user request.

### Components/Modules Shown
- User request interface
- Travel Agent response interface
- 7 sequential workflow steps
- Resource management labels (LLM vs OS managed)

### Data Flow / Control Flow
1. **Step 1: Preference Retrieval** → LLM Storage (managed by LLM)
2. **Step 2: Flight and hotel Recommendation** → Tool API (managed by LLM)
3. **Step 3: Photo ID Upload** → Disk Storage (managed by OS)
4. **Step 4: Seat Selection** → Tool API (managed by LLM)
5. **Step 5: Payment Processing** → Software (managed by OS)
6. **Step 6: Add Ticket to Calendar** → Software (managed by OS)
7. **Step 7: Reviews and tips** → Text Generation (managed by LLM)

### Implied APIs / Syscalls
- `llm_storage_read()` - Retrieve stored preferences
- `tool_call()` - Invoke external tools/APIs
- `storage_write()` - Upload files to disk
- `software_invoke()` - Execute OS software
- `llm_generate()` - Generate text responses

### Implied Algorithms
- Sequential task decomposition
- Resource type classification (LLM vs OS)
- Task orchestration

### Edge Cases / Constraints
- Mixed resource dependencies require coordination
- Some steps require LLM, others require OS
- Order of operations matters (can't pay before selecting seat)

### Implementation Mapping
- `aios/sdk/agents/travel_agent.py`
- `aios/kernel/tool_manager.py`
- `aios/kernel/storage_manager.py`

---

## Figure 2: AIOS Architecture Overview
**Paper Location**: Section 2, Page 3

### What it Depicts
Complete three-layer architecture of AIOS showing the relationship between Application Layer, Kernel Layer, and Hardware Layer.

### Components/Modules Shown

**Application Layer:**
- Agent Applications: Travel Agent, Rec Agent, Coding Agent, Math Agent, Narrative Agent
- AIOS-Agent SDK
- Non-LLM Related Queries (File Operation, Network Request, Keyboard/Mouse)
- LLM Related Queries (Reasoning & Planning, Tool Parsing, Code Generation)

**Kernel Layer:**
- OS Kernel: Process Scheduler, Memory Manager, Filesystem, Hardware Driver
- AIOS Kernel with AIOS System Call interface containing:
  - LLM Core(s)
  - Agent Scheduler
  - Context Manager
  - Memory Manager
  - Storage Manager
  - Tool Manager
  - Access Manager
- OS System Call interface

**Hardware Layer:**
- CPU, GPU, Memory, Disk, Peripheral Devices

### Data Flow / Control Flow
1. Agent Applications → AIOS-Agent SDK
2. SDK splits queries: Non-LLM → OS Kernel, LLM-related → AIOS Kernel
3. AIOS System Call routes to appropriate kernel modules
4. Kernel modules use OS System Call for hardware access
5. Hardware resources provide compute/storage

### Implied APIs / Syscalls
- SDK API: `send_request(query)`
- AIOS Syscalls: LLM syscalls, Memory syscalls, Storage syscalls, Tool syscalls
- OS Syscalls: File I/O, Network I/O, Device I/O

### Implied Algorithms
- Query routing (LLM vs non-LLM classification)
- Module dispatch based on syscall type
- Resource multiplexing across agents

### Edge Cases / Constraints
- AIOS Kernel sits alongside OS Kernel, not replacing it
- All hardware access goes through OS System Call
- SDK must handle both LLM and non-LLM paths

### Implementation Mapping
- `aios/kernel/` - All kernel modules
- `aios/sdk/` - SDK implementation
- `aios/agents/` - Example agent applications
- `aios/core/llm.py` - LLM Core abstraction

---

## Figure 3: Query Decomposition and Scheduler Architecture
**Paper Location**: Section 3.3, Page 4-5

### What it Depicts
Detailed view of how agent queries are decomposed into system calls and scheduled across kernel modules.

### Components/Modules Shown

**Agent Queries Layer:**
- Query A1 (Type: Chat)
- Query B1 (Type: File Operation)
- Query C2 (Type: Tool Use)
- Query D2 (Type: Chat)
- Query E3 (Type: File Operation)
- Query F3 (Type: Tool Use)

**AIOS System Call Layer:**
- A1.1 LLM Syscall, A1.2 Memory Syscall
- B1.1 LLM Syscall, B1.2 Storage Syscall, B1.3 Memory Syscall
- C2.1 LLM Syscall, C2.2 Tool Syscall, C2.3 Memory Syscall
- D2.1 LLM Syscall, D2.2 Memory Syscall
- E3.1 LLM Syscall, E3.2 Storage Syscall, E3.3 Memory Syscall
- F3.1 LLM Syscall, F3.2 Tool Syscall, F3.3 Memory Syscall

**AIOS Kernel:**
- Scheduler with Thread Binding
- LLM Queue (showing E3.1 in-processing)
- Tool Queue (showing C2.2, F3.2)
- Memory Queue (showing A1.2, D2.2)
- Storage Queue (showing B1.2)
- Connected managers: Context Manager, LLM Core(s), Tool Manager, Memory Manager, Storage Manager

### Data Flow / Control Flow
1. Agent queries arrive with Content and Type
2. Query Decomposition breaks queries into typed syscalls
3. Thread Binding assigns syscalls to threads
4. Scheduler places syscalls into appropriate queues
5. Managers process syscalls from their queues
6. In-processing syscalls shown with yellow highlighting

### Implied APIs / Syscalls
- `query_decompose(query) -> List[Syscall]`
- `scheduler.enqueue(syscall, queue_type)`
- `scheduler.bind_thread(syscall)`
- Queue types: LLM_QUEUE, TOOL_QUEUE, MEMORY_QUEUE, STORAGE_QUEUE

### Implied Algorithms
- Query decomposition algorithm
- FIFO queue management
- Round-robin scheduling (implied by multiple queues)
- Thread binding strategy

### Edge Cases / Constraints
- Single query can generate multiple syscalls
- Syscalls from same query may go to different queues
- Order within query must be preserved where dependencies exist

### Implementation Mapping
- `aios/kernel/scheduler.py` - Scheduler with queues
- `aios/kernel/syscall.py` - Syscall definitions
- `aios/kernel/query.py` - Query decomposition

---

## Figure 4: Context Manager - Snapshot/Restore Mechanism
**Paper Location**: Section 3.4, Page 5-6

### What it Depicts
Demonstrates how the Context Manager enables LLM generation interruption and resumption through snapshot/restore of decoding state.

### Components/Modules Shown
- Agent request input
- LLM processing block
- Token generation steps (1-4) with probability trees
- Context Manager component
- Snapshot capture point
- Suspended state indicator
- Restore mechanism
- Final output generation

### Data Flow / Control Flow

**Left Side (Interruption):**
1. Agent request: "Determine whether there will be rain in the destination of flight UA057"
2. LLM starts generation
3. Step 1: Token "/s" with branches to "Search" (0.6) and "Retrieve" (0.4)
4. Step 2: "Search" selected, branches to "weather" (0.7) and "time" (0.3)
5. **Snapshot captured** at step 2
6. Step 3: Continues to "in" (0.8) and "of" (0.2) - then **Suspended**

**Right Side (Restoration):**
1. **Restore** triggered
2. LLM resumes from snapshot
3. Step 3: Restores probability state
4. Step 4: Continues with "Paris" (0.7) and "London" (0.3)
5. Final output: "Search weather in Paris"

### Implied APIs / Syscalls
- `context_manager.snapshot(agent_id, generation_state)`
- `context_manager.restore(agent_id) -> generation_state`
- `context_manager.suspend(agent_id)`
- `context_manager.resume(agent_id)`

### Implied Algorithms
- **Text-based snapshot**: Store generated tokens and logits
- **Logits-based snapshot**: Store full probability distribution at each step
- State serialization for suspension
- State deserialization for resumption

### Edge Cases / Constraints
- Must capture complete probability tree state
- Restore must exactly match snapshot state
- Suspension can happen mid-generation
- Memory overhead for storing snapshots

### Implementation Mapping
- `aios/kernel/context_manager.py` - Main context manager
- `aios/kernel/context/snapshot.py` - Snapshot logic
- `aios/kernel/context/restore.py` - Restore logic
- `aios/core/llm_state.py` - LLM state representation

---

## Figure 5: Memory Manager Architecture
**Paper Location**: Section 3.5, Page 6

### What it Depicts
Shows the hierarchical memory management with short-term memory (Memory Manager) and long-term storage (Storage Manager), including eviction policies.

### Components/Modules Shown
- Interaction History example (Agent B, Agent ID=2)
- User message and Agent response
- Memory Manager (Short-term) containing:
  - Original Interaction History
  - Memory Note with blocks per Agent ID (1, 2, ..., n)
  - Memory Limit threshold
  - LRU-K Eviction mechanism
- Storage Manager (Long-term) containing:
  - Agent folders (Agent A, B, C, ..., X)

### Data Flow / Control Flow
1. Interaction history flows into Memory Manager
2. Memory Note stores blocks per agent (indexed by Agent ID)
3. When Memory Limit is exceeded:
   - LRU-K Eviction identifies least-recently-used blocks
   - Selected blocks are swapped to Storage Manager
4. Storage Manager maintains persistent folders per agent

### Implied APIs / Syscalls
- `memory_manager.store(agent_id, data) -> block_id`
- `memory_manager.read(agent_id, block_id) -> data`
- `memory_manager.evict(strategy="LRU-K")`
- `storage_manager.swap_in(agent_id, block_id)`
- `storage_manager.swap_out(agent_id, block_id, data)`

### Implied Algorithms
- **LRU-K Eviction**: Track K most recent accesses per block
  - Evict blocks with oldest K-th access time
- **Memory Limit Check**: Trigger eviction when threshold exceeded
- **Block Management**: Fixed-size memory blocks per agent

### Edge Cases / Constraints
- Memory limit is a hard threshold
- Eviction must not lose data (swap to storage first)
- Multiple agents share memory space
- Hot blocks should remain in memory

### Implementation Mapping
- `aios/kernel/memory_manager.py` - Memory manager
- `aios/kernel/memory/lru_k.py` - LRU-K eviction policy
- `aios/kernel/memory/block.py` - Memory block abstraction
- `aios/kernel/storage_manager.py` - Storage manager integration

---

## Figure 6: Efficiency Analysis - Llama-3.1-8b on HumanEval
**Paper Location**: Section 4 (Evaluation), Page 8

### What it Depicts
Bar charts comparing normalized throughput and latency for different agent frameworks with and without AIOS on Llama-3.1-8b model using HumanEval benchmark.

### Components/Modules Shown
- (a) Normalized throughput (higher is better)
- (b) Normalized latency (lower is better)
- Agent frameworks: ReAct, Reflexion, Autogen, Open-Interpreter, MetaGPT
- Comparison: With AIOS (pink) vs Without AIOS (blue)

### Data Flow / Control Flow
N/A (evaluation results)

### Implied APIs / Syscalls
N/A (metrics collection)

### Implied Algorithms
- Throughput measurement: syscalls executed per second
- Latency measurement: average waiting time per syscall

### Evaluation Metrics
- Throughput normalized to 1.0 for "Without AIOS"
- With AIOS shows ~0.5 throughput (2x improvement)
- Latency normalized to 1.0 for "Without AIOS"
- With AIOS shows 0.15-0.5 latency (2-6x improvement)

### Implementation Mapping
- `aios/evaluation/throughput.py`
- `aios/evaluation/latency.py`
- `aios/evaluation/benchmarks/humaneval.py`

---

## Figure 7: Efficiency Analysis - Mistral-7b on HumanEval
**Paper Location**: Section 4 (Evaluation), Page 8

### What it Depicts
Same analysis as Figure 6 but using Mistral-7b model.

### Evaluation Metrics
- Similar patterns to Llama-3.1-8b
- With AIOS shows ~0.5-0.7 throughput improvement
- With AIOS shows 0.25-0.45 latency improvement

### Implementation Mapping
- Same as Figure 6, different model config

---

## Figure 8: Scaling Analysis - Execution Time and Waiting Time vs. Agent Count
**Paper Location**: Section 4 (Evaluation), Page 8

### What it Depicts
Line graphs showing how overall execution time and average agent waiting time scale with number of agents (250-2000).

### Components/Modules Shown
- (a) Overall Execution Time vs. # Agents
- (b) Average Agent Waiting Time vs. # Agents
- Configurations:
  - Mistral-7b with AIOS (blue circle)
  - Mistral-7b without AIOS (red square)
  - Llama-3.1-8b with AIOS (green diamond)
  - Llama-3.1-8b without AIOS (yellow triangle)

### Evaluation Metrics
- Agent counts: 250, 500, 750, 1000, 2000
- Execution time range: ~100-1050 seconds
- Waiting time range: ~2-17.5 seconds
- With AIOS consistently lower than without

### Implied Algorithms
- Concurrent agent scheduling
- Queue wait time tracking
- Execution time aggregation

### Implementation Mapping
- `aios/evaluation/scaling.py`
- `aios/evaluation/metrics.py`

---

## Figure 9: AIOS-Agent SDK (Cerebrum) Architecture
**Paper Location**: Section 3.2 (SDK), Page 4

### What it Depicts
Detailed architecture of the AIOS-Agent SDK (codenamed Cerebrum) showing how agents integrate with the AIOS kernel.

### Components/Modules Shown

**Agents Layer:**
- Autogen with Agent A, Agent B
- Open-Interpreter with Agent C, Agent D
- MetaGPT with Agent E, Agent F

**AIOS-Agent SDK (Cerebrum):**
- LLM Code Snippet:
  - `setup_planning()`
  - `# preprocess steps`
  - `# call LLM apis` (highlighted)
  - `# postprocess steps`
  - `return planning results`
- Tool Code Snippet (same pattern)
- Memory Code Snippet (same pattern)
- Storage Code Snippet (same pattern)
- `send_request(Query)` central function
- HTTP (localhost/remote url) transport

**AIOS Kernel:**
- Receives requests from SDK

### Data Flow / Control Flow
1. Agent frameworks (Autogen, Open-Interpreter, MetaGPT) host multiple agents
2. Agents use SDK code snippets for LLM/Tool/Memory/Storage operations
3. All code snippets call `send_request(Query)`
4. HTTP transport sends Query to AIOS Kernel
5. Kernel processes and returns Response

### Implied APIs / Syscalls
```python
def send_request(query: Query) -> Response
def llm_chat(messages, model, **kwargs) -> LLMResponse
def tool_call(tool_name, params) -> ToolResponse
def memory_read(agent_id, key) -> MemoryResponse
def memory_write(agent_id, key, value) -> MemoryResponse
def storage_read(path) -> StorageResponse
def storage_write(path, data) -> StorageResponse
```

### Implied Algorithms
- Query serialization for HTTP transport
- Response deserialization
- API pattern: preprocess → call → postprocess

### Implementation Mapping
- `aios/sdk/cerebrum.py` - Main SDK
- `aios/sdk/client.py` - HTTP client
- `aios/sdk/llm.py` - LLM APIs
- `aios/sdk/tool.py` - Tool APIs
- `aios/sdk/memory.py` - Memory APIs
- `aios/sdk/storage.py` - Storage APIs

---

## Figure 10: Efficiency Analysis - Llama-3.1-8b on MINT Benchmark
**Paper Location**: Appendix D, Page 9+

### What it Depicts
Throughput and latency comparison on MINT benchmark with Llama-3.1-8b.

### Implementation Mapping
- `aios/evaluation/benchmarks/mint.py`

---

## Figure 11: Efficiency Analysis - Mistral-7b on MINT Benchmark
**Paper Location**: Appendix D

### What it Depicts
Throughput and latency comparison on MINT benchmark with Mistral-7b.

---

## Figure 12: Efficiency Analysis - Llama-3.1-8b on GAIA Benchmark
**Paper Location**: Appendix D

### What it Depicts
Throughput and latency comparison on GAIA benchmark with Llama-3.1-8b.

### Implementation Mapping
- `aios/evaluation/benchmarks/gaia.py`

---

## Figure 13: Efficiency Analysis - Mistral-7b on GAIA Benchmark
**Paper Location**: Appendix D

### What it Depicts
Throughput and latency comparison on GAIA benchmark with Mistral-7b.

---

## Figure 14: Efficiency Analysis - Llama-3.1-8b on SWE-Bench-Lite
**Paper Location**: Appendix D

### What it Depicts
Throughput and latency comparison on SWE-Bench-Lite benchmark with Llama-3.1-8b.

### Implementation Mapping
- `aios/evaluation/benchmarks/swebench.py`

---

## Figure 15: Efficiency Analysis - Mistral-7b on SWE-Bench-Lite
**Paper Location**: Appendix D

### What it Depicts
Throughput and latency comparison on SWE-Bench-Lite benchmark with Mistral-7b.

---

## Cross-Reference Matrix

| Figure | Paper Section | Key Concepts | Primary Modules |
|--------|---------------|--------------|-----------------|
| Fig 1 | 1 (Intro) | Motivation, Mixed Resources | agents/, sdk/ |
| Fig 2 | 2 (Architecture) | Three-layer design | kernel/, sdk/, agents/ |
| Fig 3 | 3.3 (Scheduler) | Query decomposition, Queues | scheduler.py, syscall.py |
| Fig 4 | 3.4 (Context Mgr) | Snapshot/Restore | context_manager.py |
| Fig 5 | 3.5 (Memory Mgr) | LRU-K, Swapping | memory_manager.py |
| Fig 6-7 | 4 (Eval) | Throughput/Latency | evaluation/ |
| Fig 8 | 4 (Eval) | Scaling | evaluation/scaling.py |
| Fig 9 | 3.2 (SDK) | Cerebrum, HTTP | sdk/cerebrum.py |
| Fig 10-15 | Appendix D | Additional benchmarks | evaluation/benchmarks/ |

---

## Requirements Extracted from Figures

### From Figure 1:
- REQ-F1-01: Support mixed LLM and OS-managed operations in single workflow
- REQ-F1-02: Agents must coordinate resource access through unified interface

### From Figure 2:
- REQ-F2-01: Implement three-layer architecture (Application, Kernel, Hardware)
- REQ-F2-02: AIOS Kernel must contain 6 core modules
- REQ-F2-03: SDK must route queries to appropriate kernel
- REQ-F2-04: Support 5+ agent application types

### From Figure 3:
- REQ-F3-01: Implement query decomposition into typed syscalls
- REQ-F3-02: Implement 4 queue types (LLM, Tool, Memory, Storage)
- REQ-F3-03: Implement thread binding for syscalls
- REQ-F3-04: Scheduler must process queues according to strategy

### From Figure 4:
- REQ-F4-01: Context manager must snapshot LLM generation state
- REQ-F4-02: Context manager must restore from snapshot
- REQ-F4-03: Support suspension mid-generation
- REQ-F4-04: Preserve probability tree state across suspend/resume

### From Figure 5:
- REQ-F5-01: Implement short-term memory with agent-indexed blocks
- REQ-F5-02: Implement LRU-K eviction policy
- REQ-F5-03: Memory limit threshold must trigger eviction
- REQ-F5-04: Swapping to storage manager for evicted blocks

### From Figure 6-8:
- REQ-F6-01: Measure and report normalized throughput
- REQ-F6-02: Measure and report normalized latency
- REQ-F8-01: Support scaling evaluation up to 2000 agents
- REQ-F8-02: Track overall execution time and average waiting time

### From Figure 9:
- REQ-F9-01: SDK must provide LLM, Tool, Memory, Storage code patterns
- REQ-F9-02: Implement send_request(Query) function
- REQ-F9-03: Support HTTP transport (localhost/remote)
- REQ-F9-04: Support framework adapters (Autogen, Open-Interpreter, MetaGPT)

