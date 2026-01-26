# AIOS Implementation Plan

This document outlines the implementation milestones for AIOS, organized as vertical slices that build upon each other.

---

## Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          IMPLEMENTATION TIMELINE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  M1: Minimal Kernel    M2: Full Kernel    M3: SDK      M4: Adapters   M5: Eval│
│  ──────────────────►  ──────────────────► ─────────► ─────────────► ─────────►│
│                                                                              │
│  Week 1-2             Week 3-4            Week 5-6    Week 7-8       Week 9-10│
│                                                                              │
│  ┌───────────┐        ┌───────────┐       ┌───────┐   ┌──────────┐   ┌──────┐│
│  │ LLM Core  │        │ Context   │       │ SDK   │   │ ReAct    │   │Bench-││
│  │ Scheduler │        │ Memory    │       │ Client│   │ AutoGen  │   │marks ││
│  │ Basic     │        │ Storage   │       │ APIs  │   │ MetaGPT  │   │Plots ││
│  │ Queues    │        │ Tool      │       │ Agents│   │ Reflexion│   │      ││
│  │           │        │ Access    │       │       │   │          │   │      ││
│  └───────────┘        └───────────┘       └───────┘   └──────────┘   └──────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Milestone 1: Minimal Working Kernel
**Duration**: 2 weeks
**Paper Coverage**: Sections 3.1, 3.3 (partial)

### Goals
- Basic AIOS kernel that can process LLM queries
- Single LLM core with FIFO scheduling
- Proof that the architecture works end-to-end

### Deliverables

#### 1.1 Project Structure
```
aios/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── llm.py                 # LLM Core abstraction
│   └── adapters/
│       ├── __init__.py
│       ├── base.py            # Abstract LLM backend
│       ├── openai_adapter.py  # OpenAI implementation
│       └── mock_adapter.py    # Mock for testing
├── kernel/
│   ├── __init__.py
│   ├── server.py              # HTTP server entry point
│   ├── scheduler.py           # Basic FIFO scheduler
│   ├── syscall.py             # Syscall definitions
│   └── query.py               # Query decomposition
├── sdk/
│   ├── __init__.py
│   ├── client.py              # Basic SDK client
│   └── models.py              # Query/Response models
└── config/
    └── default.yaml           # Default configuration
```

#### 1.2 Core Components

| Component | File | Description |
|-----------|------|-------------|
| LLMBackend | `core/adapters/base.py` | Abstract interface for LLM backends |
| OpenAIAdapter | `core/adapters/openai_adapter.py` | OpenAI API integration |
| LLMCore | `core/llm.py` | Manages LLM backends, routes requests |
| Scheduler | `kernel/scheduler.py` | FIFO queue management |
| Syscall | `kernel/syscall.py` | Syscall data structures |
| Server | `kernel/server.py` | FastAPI HTTP server |
| Client | `sdk/client.py` | SDK HTTP client |

#### 1.3 Acceptance Tests

```python
# test_m1_basic_flow.py
def test_llm_query_end_to_end():
    """Query flows from SDK through kernel to LLM and back."""
    client = AIOSClient("http://localhost:8000")
    response = client.llm_chat(
        agent_id="test-agent",
        messages=[{"role": "user", "content": "Hello"}]
    )
    assert response.status == "success"
    assert response.content is not None

def test_fifo_ordering():
    """Earlier queries are processed before later ones."""
    # Submit 3 queries rapidly
    # Verify response order matches submission order

def test_multiple_agents():
    """Multiple agents can submit queries concurrently."""
    # Create 5 agents, each submits a query
    # All should complete successfully
```

---

## Milestone 2: Full Kernel Modules
**Duration**: 2 weeks
**Paper Coverage**: Sections 3.4, 3.5, 3.6, 3.7, 3.8

### Goals
- Complete all 6 kernel modules
- Round Robin scheduling with context interruption
- Functional memory and storage managers

### Deliverables

#### 2.1 Extended Structure
```
aios/kernel/
├── context_manager.py         # Context snapshot/restore
├── context/
│   ├── __init__.py
│   ├── text_snapshot.py       # Text-based snapshots
│   └── logits_snapshot.py     # Logits-based snapshots
├── memory_manager.py          # Short-term memory
├── memory/
│   ├── __init__.py
│   ├── block.py               # Memory block
│   └── lru_k.py               # LRU-K eviction
├── storage_manager.py         # Persistent storage
├── storage/
│   ├── __init__.py
│   ├── filesystem.py          # File operations
│   ├── vector_db.py           # ChromaDB integration
│   └── versioning.py          # Version control
├── tool_manager.py            # Tool registry and execution
├── access_manager.py          # Access control
└── syscalls/
    ├── __init__.py
    ├── llm.py
    ├── memory.py
    ├── storage.py
    ├── tool.py
    ├── context.py
    └── access.py
```

#### 2.2 Component Details

| Component | Requirements | Paper Section |
|-----------|--------------|---------------|
| Context Manager | Snapshot/restore, suspend/resume | 3.4, Fig 4 |
| Memory Manager | CRUD, LRU-K eviction, swap to storage | 3.5, Fig 5 |
| Storage Manager | File ops, versioning, sharing, locks | 3.6 |
| Tool Manager | Registry, validation, conflict resolution | 3.7 |
| Access Manager | Privilege groups, cross-agent checks | 3.8 |

#### 2.3 Scheduler Enhancement

```python
# scheduler.py additions
class Scheduler:
    def __init__(self, strategy: SchedulingStrategy):
        self.strategy = strategy
        # Add Round Robin support
        self.rr_agent_queue = deque()
        self.rr_time_slice_tokens = 50
```

#### 2.4 Acceptance Tests

```python
# test_m2_context_manager.py
def test_snapshot_restore_text_based():
    """Text-based snapshot correctly restores generation state."""
    
def test_snapshot_restore_logits_based():
    """Logits-based snapshot correctly restores probabilities."""

def test_round_robin_fairness():
    """Round Robin gives fair time to each agent."""

# test_m2_memory_manager.py
def test_memory_crud():
    """Basic create/read/update/delete operations."""

def test_lru_k_eviction():
    """LRU-K correctly evicts least recently used blocks."""

def test_memory_swap_to_storage():
    """Evicted blocks are correctly swapped to storage."""

# test_m2_storage_manager.py
def test_file_versioning():
    """File versions are tracked correctly."""

def test_rollback():
    """Rollback restores previous version."""

def test_file_locking():
    """Concurrent access is properly serialized."""

# test_m2_tool_manager.py
def test_tool_registration():
    """Tools can be registered and invoked."""

def test_conflict_resolution():
    """Naming conflicts are resolved with namespacing."""

# test_m2_access_manager.py
def test_cross_agent_access_denied():
    """Agent cannot access another's resources without permission."""

def test_user_confirmation():
    """Irreversible operations require confirmation."""
```

---

## Milestone 3: SDK and Example Agents
**Duration**: 2 weeks
**Paper Coverage**: Section 3.2, Figure 9, Agent types from Figure 2

### Goals
- Complete SDK with all APIs
- Runnable example agents
- Documentation and examples

### Deliverables

#### 3.1 SDK Structure
```
aios/sdk/
├── __init__.py
├── cerebrum.py                # Main SDK class (named after Fig 9)
├── client.py                  # HTTP transport
├── models.py                  # All Query/Response models
├── llm.py                     # LLM APIs
├── memory.py                  # Memory APIs
├── storage.py                 # Storage APIs
├── tool.py                    # Tool APIs
└── context.py                 # Context APIs
```

#### 3.2 Example Agents
```
aios/agents/
├── __init__.py
├── base.py                    # Base agent class
├── travel_agent.py            # Travel planning (Fig 1)
├── rec_agent.py               # Recommendation agent
├── math_agent.py              # Mathematical reasoning
├── coding_agent.py            # Code generation
└── narrative_agent.py         # Story generation
```

#### 3.3 SDK API Surface

```python
# cerebrum.py
class Cerebrum:
    """
    AIOS-Agent SDK (Cerebrum) - Main entry point for agents.
    
    Paper Reference: Figure 9
    """
    
    # LLM APIs
    def llm_chat(self, messages, model="default", **kwargs) -> LLMResponse
    def llm_generate(self, prompt, **kwargs) -> LLMResponse
    
    # Memory APIs
    def memory_read(self, key) -> Any
    def memory_write(self, key, value, ttl=None) -> bool
    def memory_delete(self, key) -> bool
    def memory_search(self, query, limit=10) -> List[MemoryEntry]
    
    # Storage APIs
    def storage_read(self, path, version=None) -> bytes
    def storage_write(self, path, data) -> FileInfo
    def storage_delete(self, path) -> bool
    def storage_list(self, path="/") -> List[FileInfo]
    def storage_search(self, query) -> List[FileInfo]
    
    # Tool APIs
    def tool_call(self, tool_name, parameters) -> Any
    def tool_list(self, category=None) -> List[ToolSchema]
```

#### 3.4 Acceptance Tests

```python
# test_m3_sdk.py
def test_sdk_llm_chat():
    """SDK llm_chat works correctly."""

def test_sdk_memory_workflow():
    """Complete memory read/write/search workflow."""

def test_sdk_storage_versioning():
    """Storage versioning through SDK."""

# test_m3_agents.py
def test_travel_agent_workflow():
    """Travel agent completes the 7-step workflow from Figure 1."""

def test_rec_agent_basic():
    """Rec agent provides recommendations."""
```

---

## Milestone 4: Framework Adapters
**Duration**: 2 weeks
**Paper Coverage**: Figure 9 (Autogen, Open-Interpreter, MetaGPT), evaluation frameworks

### Goals
- Adapters for major agent frameworks
- Compatibility layer for existing agents

### Deliverables

#### 4.1 Adapter Structure
```
aios/adapters/
├── __init__.py
├── base.py                    # Base adapter class
├── react.py                   # ReAct framework
├── reflexion.py               # Reflexion framework
├── autogen.py                 # Microsoft AutoGen
├── open_interpreter.py        # Open Interpreter
└── metagpt.py                 # MetaGPT framework
```

#### 4.2 Adapter Interface

```python
# base.py
class FrameworkAdapter(ABC):
    """
    Base class for agent framework adapters.
    
    Adapters intercept LLM/tool calls and route through AIOS.
    """
    
    @abstractmethod
    def intercept_llm_call(self, original_call, *args, **kwargs):
        """Intercept and redirect LLM call to AIOS."""
        pass
    
    @abstractmethod
    def intercept_tool_call(self, original_call, *args, **kwargs):
        """Intercept and redirect tool call to AIOS."""
        pass
    
    @abstractmethod
    def wrap_agent(self, agent):
        """Wrap an existing agent to use AIOS."""
        pass
```

#### 4.3 ReAct Adapter Example

```python
# react.py
class ReActAdapter(FrameworkAdapter):
    """
    Adapter for ReAct-style agents.
    
    Intercepts thought-action-observation loops.
    """
    
    def intercept_llm_call(self, messages, **kwargs):
        # Route through AIOS SDK
        return self.sdk.llm_chat(messages, **kwargs)
    
    def intercept_tool_call(self, action, action_input):
        # Route through AIOS tool manager
        return self.sdk.tool_call(action, action_input)
```

#### 4.4 Acceptance Tests

```python
# test_m4_adapters.py
def test_react_adapter():
    """ReAct agent works through AIOS."""

def test_autogen_adapter():
    """AutoGen multi-agent conversation works through AIOS."""

def test_adapter_interception():
    """All LLM calls are routed through AIOS kernel."""
```

---

## Milestone 5: Evaluation Harness
**Duration**: 2 weeks
**Paper Coverage**: Section 4, Figures 6-15

### Goals
- Reproduce evaluation metrics from paper
- Generate comparison plots
- Benchmark FIFO vs Round Robin

### Deliverables

#### 5.1 Evaluation Structure
```
aios/evaluation/
├── __init__.py
├── harness.py                 # Main evaluation runner
├── metrics.py                 # Throughput, latency measurement
├── scaling.py                 # Scaling experiments
├── compare.py                 # FIFO vs RR comparison
├── benchmarks/
│   ├── __init__.py
│   ├── humaneval.py           # HumanEval benchmark
│   ├── mint.py                # MINT benchmark
│   ├── gaia.py                # GAIA benchmark
│   └── swebench.py            # SWE-Bench-Lite
└── plotting/
    ├── __init__.py
    ├── throughput_latency.py  # Fig 6-7, 10-15 style
    └── scaling.py             # Fig 8 style
```

#### 5.2 Metrics Implementation

```python
# metrics.py
class MetricsCollector:
    """
    Collect evaluation metrics matching paper.
    
    Paper Reference: Section 4
    """
    
    def measure_throughput(self, duration_seconds: float) -> float:
        """Syscalls completed per second."""
        return self.completed_syscalls / duration_seconds
    
    def measure_latency(self) -> float:
        """Average waiting time per syscall."""
        return statistics.mean(self.waiting_times)
    
    def normalize(self, value: float, baseline: float) -> float:
        """Normalize against baseline (without AIOS)."""
        return value / baseline
```

#### 5.3 Experiment Configurations

```yaml
# evaluation/configs/scaling.yaml
experiment: scaling
description: "Figure 8 reproduction"
agent_counts: [250, 500, 750, 1000, 2000]
models:
  - mistral-7b
  - llama-3.1-8b
configurations:
  - with_aios: true
  - with_aios: false
metrics:
  - overall_execution_time
  - average_agent_waiting_time
```

#### 5.4 Acceptance Tests

```python
# test_m5_evaluation.py
def test_throughput_measurement():
    """Throughput is correctly measured."""

def test_latency_measurement():
    """Latency is correctly measured."""

def test_scaling_experiment():
    """Scaling experiment runs with increasing agent counts."""

def test_fifo_vs_rr_comparison():
    """FIFO and RR produce different results."""

def test_plot_generation():
    """Plots are generated matching paper style."""
```

---

## Repository Files

### Documentation
```
docs/
├── README.md                  # Project overview
├── Repro.md                   # Reproduction commands
├── DesignReview.md           # Key design decisions
└── API.md                     # API documentation
```

### Testing
```
tests/
├── unit/
│   ├── test_llm_core.py
│   ├── test_scheduler.py
│   ├── test_context_manager.py
│   ├── test_memory_manager.py
│   ├── test_storage_manager.py
│   ├── test_tool_manager.py
│   └── test_access_manager.py
├── integration/
│   ├── test_query_flow.py
│   ├── test_multi_agent.py
│   └── test_context_interruption.py
└── regression/
    └── test_context_similarity.py
```

### Configuration
```
config/
├── default.yaml               # Default settings
├── development.yaml           # Dev environment
├── production.yaml            # Production settings
└── evaluation.yaml            # Evaluation settings
```

---

## Acceptance Criteria Summary

| Milestone | Key Criterion | Verification |
|-----------|--------------|--------------|
| M1 | LLM query works end-to-end | Integration test passes |
| M2 | All 6 kernel modules functional | Unit tests for each module |
| M3 | Example agents run successfully | Agent workflow tests pass |
| M4 | Adapters intercept all LLM calls | Adapter tests verify routing |
| M5 | Metrics match paper methodology | Metric validation tests |

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM API rate limits | Mock adapter for testing; configurable retry |
| Complex context snapshot | Start with text-based; logits optional |
| Framework adapter complexity | Minimal compatibility layer first |
| Benchmark data access | Use public benchmark subsets |

---

## Dependencies

```
# requirements.txt
fastapi>=0.100.0
uvicorn>=0.23.0
pydantic>=2.0.0
httpx>=0.24.0
openai>=1.0.0
chromadb>=0.4.0
numpy>=1.24.0
matplotlib>=3.7.0
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

---

## Timeline Summary

| Week | Milestone | Focus |
|------|-----------|-------|
| 1-2 | M1 | Minimal kernel, FIFO, basic flow |
| 3-4 | M2 | All managers, Round Robin, context |
| 5-6 | M3 | SDK, example agents |
| 7-8 | M4 | Framework adapters |
| 9-10 | M5 | Evaluation harness, plots |

---

## Next Steps

After creating this plan, the implementation will proceed as follows:

1. **Setup**: Create repository structure, install dependencies
2. **M1 Implementation**: Build minimal kernel
3. **M1 Testing**: Verify basic flow works
4. **Iterate**: Continue through milestones with continuous testing

Each milestone will update `paper_coverage.csv` to track progress.

