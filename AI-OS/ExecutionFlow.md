# AIOS Execution Flow

This document describes the end-to-end lifecycle of an agent query from submission to response, based on Sections 3.1-3.8 and Figures 2, 3, 4, and 9.

---

## High-Level Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AGENT APPLICATION                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  User Request: "Plan a trip from SF to NYC next month"               │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │ (1) Agent logic
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                               AIOS SDK (Cerebrum)                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  sdk.llm_chat(messages=[...], tools=[...])                            │   │
│  │     → LLMQuery(agent_id, messages, tools)                             │   │
│  │     → send_request(query) via HTTP                                    │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │ (2) HTTP POST
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                                AIOS KERNEL                                   │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  (3) Query Reception → (4) Access Check → (5) Query Decomposition     │   │
│  │      → (6) Syscall Enqueueing → (7) Scheduling → (8) Execution        │   │
│  │      → (9) Context Management → (10) Response Assembly                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │ (11) HTTP Response
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                               AIOS SDK (Cerebrum)                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  (12) Response Deserialization → LLMResponse                          │   │
│  │  (13) Return to Agent                                                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              AGENT APPLICATION                               │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  (14) Process response, possibly trigger more queries                 │   │
│  │  (15) Invoke tools, store memories, continue workflow                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Detailed Phase Breakdown

### Phase 1: Agent Query Initiation
**Location**: Agent Application
**Paper Reference**: Section 1, Figure 1

```python
# Example: Travel Agent initiating a query
agent = TravelAgent(agent_id="travel-001")

# User request arrives
user_message = "I'm flying from SF to NYC next month for business"

# Agent prepares to call LLM for planning
response = agent.sdk.llm_chat(
    messages=[
        {"role": "system", "content": "You are a travel planning assistant..."},
        {"role": "user", "content": user_message}
    ],
    tools=[search_flights_tool, book_hotel_tool]
)
```

---

### Phase 2: SDK Query Construction
**Location**: `aios/sdk/client.py`
**Paper Reference**: Section 3.2, Figure 9

```python
def llm_chat(self, messages, model="default", tools=None, **kwargs):
    """
    High-level LLM chat API.
    
    Flow:
    1. Validate inputs
    2. Construct LLMQuery object
    3. Call send_request()
    4. Deserialize and return LLMResponse
    """
    # 2.1 Construct query
    query = LLMQuery(
        agent_id=self.agent_id,
        messages=[Message(**m) for m in messages],
        model=model,
        tools=tools or [],
        **kwargs
    )
    
    # 2.2 Send via HTTP
    response = self.send_request(query)
    
    # 2.3 Return typed response
    return response

def send_request(self, query: Query) -> Response:
    """
    Transport layer for SDK-to-kernel communication.
    
    Paper Reference: Figure 9 - "HTTP (localhost/remote url)"
    """
    # 2.4 Serialize query
    payload = query.to_dict()
    
    # 2.5 HTTP POST to kernel
    http_response = requests.post(
        f"{self.kernel_url}/syscall",
        json=payload,
        headers={"Authorization": f"Bearer {self.api_key}"}
    )
    
    # 2.6 Deserialize response
    return self._parse_response(http_response.json(), type(query))
```

---

### Phase 3: Kernel Query Reception
**Location**: `aios/kernel/server.py`
**Paper Reference**: Section 2, Figure 2

```python
@app.post("/syscall")
async def handle_syscall(request: Request):
    """
    Entry point for all syscalls from SDK.
    
    Flow:
    1. Parse incoming request
    2. Validate agent authentication
    3. Route to query handler
    """
    # 3.1 Parse request body
    payload = await request.json()
    
    # 3.2 Reconstruct Query object
    query = parse_query(payload)
    
    # 3.3 Log for debugging/metrics
    logger.info(f"Received query {query.query_id} from agent {query.agent_id}")
    
    # 3.4 Hand off to kernel core
    response = await kernel.process_query(query)
    
    return JSONResponse(response.to_dict())
```

---

### Phase 4: Access Control Check
**Location**: `aios/kernel/access_manager.py`
**Paper Reference**: Section 3.8

```python
async def check_access(self, query: Query) -> bool:
    """
    Verify agent has permission for the requested operation.
    
    Flow:
    1. Get agent's privilege group
    2. Determine required permissions for query type
    3. Check against access control list
    4. Request user confirmation if needed
    """
    agent = self.get_agent(query.agent_id)
    
    # 4.1 Check basic permission
    required_perm = self.get_required_permission(query)
    if not self.has_permission(agent, required_perm):
        raise PermissionDenied(f"Agent lacks {required_perm}")
    
    # 4.2 Check for irreversible operations
    if self.is_irreversible(query):
        # Request user confirmation (Section 3.8)
        confirmed = await self.request_user_confirmation(
            agent_id=query.agent_id,
            operation=query.query_type,
            description=self.describe_operation(query)
        )
        if not confirmed:
            raise OperationCancelled("User denied operation")
    
    return True
```

---

### Phase 5: Query Decomposition
**Location**: `aios/kernel/query.py`
**Paper Reference**: Section 3.3, Figure 3

```python
def decompose_query(query: Query) -> List[Syscall]:
    """
    Break down a high-level query into atomic syscalls.
    
    Paper Reference: Figure 3 shows queries decomposing into multiple syscalls.
    Example: Query B1 (File Operation) → B1.1 LLM + B1.2 Storage + B1.3 Memory
    """
    syscalls = []
    
    if isinstance(query, LLMQuery):
        # LLM queries may need memory syscall first (load history)
        if query.needs_history:
            syscalls.append(Syscall(
                syscall_type=SyscallType.MEMORY,
                operation="memory_read",
                params={"key": "conversation_history"}
            ))
        
        # Main LLM syscall
        syscalls.append(Syscall(
            syscall_type=SyscallType.LLM,
            operation="llm_chat",
            params=query.to_llm_params()
        ))
        
        # Memory syscall to save response
        syscalls.append(Syscall(
            syscall_type=SyscallType.MEMORY,
            operation="memory_write",
            params={"key": "conversation_history"}
        ))
    
    elif isinstance(query, ToolQuery):
        # Tool queries: LLM → Tool → Memory pattern (Figure 3, Query C2)
        syscalls.append(Syscall(
            syscall_type=SyscallType.LLM,
            operation="llm_parse_tool_call",
            params={"tool_name": query.tool_name}
        ))
        syscalls.append(Syscall(
            syscall_type=SyscallType.TOOL,
            operation="tool_call",
            params=query.parameters
        ))
        syscalls.append(Syscall(
            syscall_type=SyscallType.MEMORY,
            operation="memory_write",
            params={"key": "tool_results"}
        ))
    
    # Assign sequential IDs for ordering
    for i, syscall in enumerate(syscalls):
        syscall.sequence_number = i
        syscall.query_id = query.query_id
        syscall.agent_id = query.agent_id
    
    return syscalls
```

---

### Phase 6: Syscall Enqueueing
**Location**: `aios/kernel/scheduler.py`
**Paper Reference**: Section 3.3, Figure 3

```python
def enqueue_syscalls(self, syscalls: List[Syscall]):
    """
    Add syscalls to appropriate queues.
    
    Paper Reference: Figure 3 shows 4 queue types:
    - LLM Queue
    - Tool Queue
    - Memory Queue
    - Storage Queue
    """
    for syscall in syscalls:
        syscall.status = SyscallStatus.QUEUED
        syscall.enqueued_at = time.time()
        
        # Route to appropriate queue
        if syscall.syscall_type == SyscallType.LLM:
            self.llm_queue.put(syscall)
        elif syscall.syscall_type == SyscallType.TOOL:
            self.tool_queue.put(syscall)
        elif syscall.syscall_type == SyscallType.MEMORY:
            self.memory_queue.put(syscall)
        elif syscall.syscall_type == SyscallType.STORAGE:
            self.storage_queue.put(syscall)
        
        logger.debug(f"Enqueued {syscall.syscall_id} to {syscall.syscall_type} queue")
```

---

### Phase 7: Scheduling
**Location**: `aios/kernel/scheduler.py`
**Paper Reference**: Section 3.3

```python
class Scheduler:
    """
    Centralized scheduler managing all syscall queues.
    
    Supports two strategies:
    - FIFO: First-in-first-out (simple, unfair with long tasks)
    - Round Robin: Time-sliced (fair, requires context interruption)
    """
    
    async def run(self):
        """Main scheduling loop."""
        while self.running:
            # 7.1 Select next syscall based on strategy
            if self.strategy == SchedulingStrategy.FIFO:
                syscall = await self.select_fifo()
            else:
                syscall = await self.select_round_robin()
            
            if syscall:
                # 7.2 Bind to execution thread
                thread = await self.bind_thread(syscall)
                
                # 7.3 Execute syscall
                await self.execute_syscall(syscall, thread)
    
    async def select_fifo(self) -> Optional[Syscall]:
        """FIFO selection: oldest syscall from any non-empty queue."""
        candidates = []
        for queue in [self.llm_queue, self.tool_queue, 
                      self.memory_queue, self.storage_queue]:
            if not queue.empty():
                syscall = queue.peek()
                candidates.append((syscall.enqueued_at, syscall, queue))
        
        if candidates:
            candidates.sort(key=lambda x: x[0])
            _, syscall, queue = candidates[0]
            queue.get()  # Remove from queue
            return syscall
        return None
    
    async def select_round_robin(self) -> Optional[Syscall]:
        """
        Round Robin selection: cycle through agents with time slices.
        
        Paper Reference: Section 3.3 - RR requires context interruption
        """
        # Get current agent's turn
        current_agent = self.rr_current_agent
        
        # Find syscall for current agent
        for queue in self.all_queues:
            syscall = queue.find(agent_id=current_agent)
            if syscall:
                return syscall
        
        # Move to next agent
        self.rr_current_agent = self.get_next_agent()
        return None
```

---

### Phase 8: Syscall Execution
**Location**: `aios/kernel/` (various managers)
**Paper Reference**: Sections 3.4-3.7

```python
async def execute_syscall(self, syscall: Syscall, thread) -> Response:
    """
    Execute a syscall on the appropriate manager.
    
    Flow depends on syscall type:
    - LLM: LLM Core + Context Manager
    - Tool: Tool Manager
    - Memory: Memory Manager
    - Storage: Storage Manager
    """
    syscall.status = SyscallStatus.IN_PROGRESS
    syscall.started_at = time.time()
    syscall.thread_id = thread.id
    
    try:
        if syscall.syscall_type == SyscallType.LLM:
            response = await self.llm_core.execute(syscall)
        elif syscall.syscall_type == SyscallType.TOOL:
            response = await self.tool_manager.execute(syscall)
        elif syscall.syscall_type == SyscallType.MEMORY:
            response = await self.memory_manager.execute(syscall)
        elif syscall.syscall_type == SyscallType.STORAGE:
            response = await self.storage_manager.execute(syscall)
        
        syscall.status = SyscallStatus.COMPLETED
        syscall.response = response
        
    except Exception as e:
        syscall.status = SyscallStatus.FAILED
        syscall.response = ErrorResponse(error=str(e))
    
    syscall.completed_at = time.time()
    return syscall.response
```

---

### Phase 9: Context Management (LLM Syscalls)
**Location**: `aios/kernel/context_manager.py`
**Paper Reference**: Section 3.4, Figure 4

```python
class ContextManager:
    """
    Manages LLM generation state for interruption/resumption.
    
    Two approaches (Figure 4):
    1. Text-based: Store generated tokens
    2. Logits-based: Store probability distributions
    """
    
    async def execute_with_context(self, syscall: Syscall, llm_core) -> LLMResponse:
        """
        Execute LLM syscall with context management.
        
        For Round Robin scheduling, allows interruption mid-generation.
        """
        agent_id = syscall.agent_id
        
        # 9.1 Check for existing snapshot to restore
        if self.has_snapshot(agent_id):
            state = self.restore(agent_id)
            logger.info(f"Restored context for agent {agent_id}")
        else:
            state = None
        
        # 9.2 Begin generation with optional state
        generator = llm_core.generate_stream(
            syscall.query,
            initial_state=state
        )
        
        tokens = []
        async for token, logits in generator:
            tokens.append(token)
            
            # 9.3 Check for interruption (Round Robin time slice exceeded)
            if self.should_interrupt(agent_id):
                # 9.4 Snapshot current state
                snapshot = self.create_snapshot(
                    agent_id=agent_id,
                    tokens=tokens,
                    logits=logits,
                    snapshot_type=self.snapshot_type
                )
                self.save_snapshot(agent_id, snapshot)
                
                # 9.5 Mark as suspended, return partial response
                syscall.status = SyscallStatus.SUSPENDED
                return PartialLLMResponse(
                    tokens_so_far=tokens,
                    is_complete=False
                )
        
        # 9.6 Generation completed
        return LLMResponse(
            content="".join(tokens),
            finish_reason="stop"
        )
    
    def create_snapshot(self, agent_id, tokens, logits, snapshot_type):
        """
        Create a snapshot based on the configured approach.
        
        Text-based (Figure 4, left side):
        - Store: generated tokens so far
        - Pros: Lower memory usage
        - Cons: May not perfectly restore probability state
        
        Logits-based (Figure 4, right side):
        - Store: full probability distribution at each step
        - Pros: Exact state restoration
        - Cons: Higher memory usage
        """
        if snapshot_type == SnapshotType.TEXT:
            return TextSnapshot(
                agent_id=agent_id,
                tokens=tokens,
                position=len(tokens)
            )
        else:
            return LogitsSnapshot(
                agent_id=agent_id,
                tokens=tokens,
                logits_history=logits,  # Full probability trees
                position=len(tokens)
            )
```

---

### Phase 10: Response Assembly
**Location**: `aios/kernel/query.py`
**Paper Reference**: Section 3.2

```python
async def assemble_response(query: Query, syscall_results: List[Response]) -> Response:
    """
    Combine syscall results into a unified query response.
    
    Flow:
    1. Check all syscalls completed successfully
    2. Extract relevant data from each syscall response
    3. Construct typed response matching query type
    """
    # 10.1 Verify all syscalls completed
    failed = [r for r in syscall_results if not r.is_success]
    if failed:
        return ErrorResponse(
            query_id=query.query_id,
            error=f"Syscall failures: {[f.error for f in failed]}"
        )
    
    # 10.2 Assemble based on query type
    if isinstance(query, LLMQuery):
        # Find the main LLM response
        llm_response = next(r for r in syscall_results if isinstance(r, LLMResponse))
        return llm_response
    
    elif isinstance(query, ToolQuery):
        # Combine LLM parsing + tool result
        tool_response = next(r for r in syscall_results if isinstance(r, ToolResponse))
        return tool_response
    
    # ... handle other query types
```

---

### Phase 11-13: Response Transport
**Location**: `aios/kernel/server.py`, `aios/sdk/client.py`

```python
# Kernel side (Phase 11)
async def handle_syscall(request):
    # ... processing ...
    response = await kernel.process_query(query)
    
    # 11.1 Serialize response
    return JSONResponse(response.to_dict())

# SDK side (Phase 12-13)
def send_request(self, query):
    http_response = requests.post(...)
    
    # 12.1 Parse JSON response
    data = http_response.json()
    
    # 12.2 Deserialize to typed Response
    response = self._parse_response(data, type(query))
    
    # 13.1 Return to caller
    return response
```

---

### Phase 14-15: Agent Post-Processing
**Location**: Agent Application
**Paper Reference**: Figure 1

```python
# Agent receives response and continues workflow
response = agent.sdk.llm_chat(...)

if response.tool_calls:
    # 14.1 LLM requested tool calls
    for tool_call in response.tool_calls:
        # 15.1 Execute tool via SDK
        tool_result = agent.sdk.tool_call(
            tool_name=tool_call["name"],
            parameters=tool_call["arguments"]
        )
        
        # 15.2 Store result in memory
        agent.sdk.memory_write(
            key=f"tool_result_{tool_call['id']}",
            value=tool_result.result
        )
        
        # 15.3 Continue conversation with tool result
        messages.append({
            "role": "tool",
            "content": str(tool_result.result),
            "tool_call_id": tool_call["id"]
        })

# 14.2 Continue to next step in workflow
# (e.g., Step 2: Flight recommendation after Step 1: Preference retrieval)
```

---

## Timing Diagram

```
Time ──────────────────────────────────────────────────────────────────────►

Agent    ┌─────┐                                                    ┌─────┐
         │Send │                                                    │Recv │
         │Query│                                                    │Resp │
         └──┬──┘                                                    └──▲──┘
            │                                                          │
SDK         │    ┌───────────────────────────────────────────────┐    │
            └───►│ Serialize → HTTP POST → Deserialize Response  ├────┘
                 └───────────────────┬───────────────────────────┘
                                     │
Kernel                               │
            ┌────────────────────────▼────────────────────────────┐
            │                                                      │
            │  ┌──────┐  ┌───────┐  ┌────────┐  ┌────────┐        │
            │  │Access│  │Decomp │  │Enqueue │  │Schedule│        │
            │  │Check │→ │ose    │→ │        │→ │        │        │
            │  └──────┘  └───────┘  └────────┘  └───┬────┘        │
            │                                       │              │
            │                           ┌───────────▼───────────┐  │
            │                           │    Execute Syscalls   │  │
            │                           │  ┌─────┐ ┌─────────┐  │  │
            │                           │  │ LLM │ │ Context │  │  │
            │                           │  │Core │←│ Manager │  │  │
            │                           │  └─────┘ └─────────┘  │  │
            │                           └───────────┬───────────┘  │
            │                                       │              │
            │  ┌──────────────────────────────────┐│              │
            │  │         Assemble Response        ◄┘              │
            │  └──────────────────────────────────┘               │
            └──────────────────────────────────────────────────────┘
```

---

## Error Handling Flow

```python
async def process_query_with_errors(query: Query) -> Response:
    """
    Complete query processing with error handling at each phase.
    """
    try:
        # Phase 4: Access check
        await access_manager.check_access(query)
    except PermissionDenied as e:
        return AccessResponse(
            status=ResponseStatus.PERMISSION_DENIED,
            error=str(e)
        )
    
    try:
        # Phase 5: Decomposition
        syscalls = decompose_query(query)
    except DecompositionError as e:
        return ErrorResponse(status=ResponseStatus.ERROR, error=str(e))
    
    try:
        # Phases 6-9: Execution
        results = []
        for syscall in syscalls:
            result = await execute_syscall(syscall)
            if not result.is_success:
                # Rollback any completed syscalls if needed
                await rollback_syscalls(results)
                return result
            results.append(result)
        
        # Phase 10: Assembly
        return await assemble_response(query, results)
        
    except TimeoutError:
        return ErrorResponse(status=ResponseStatus.TIMEOUT)
    except Exception as e:
        logger.exception("Unexpected error processing query")
        return ErrorResponse(status=ResponseStatus.ERROR, error=str(e))
```

---

## References

- Section 3.1: LLM Core
- Section 3.2: AIOS SDK (Figure 9)
- Section 3.3: Agent Scheduler (Figure 3)
- Section 3.4: Context Manager (Figure 4)
- Sections 3.5-3.8: Memory/Storage/Tool/Access Managers

