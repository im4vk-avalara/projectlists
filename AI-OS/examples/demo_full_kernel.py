"""
AIOS Full Kernel Demo

Demonstrates the complete AIOS kernel with all integrated managers:
- LLM Core (Section 3.1)
- Scheduler (Section 3.3)
- Context Manager (Section 3.4)
- Memory Manager (Section 3.5)
- Storage Manager (Section 3.6)
- Tool Manager (Section 3.7)
- Access Manager (Section 3.8)

Paper Reference: Section 2 (Architecture), Figure 2
"""

import asyncio
import logging
import tempfile

# Colorful output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.END}\n")

def print_section(text):
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- {text} ---{Colors.END}\n")

def print_result(text):
    print(f"{Colors.GREEN}  ✓ {text}{Colors.END}")

def print_data(label, data):
    print(f"{Colors.YELLOW}    {label}:{Colors.END} {data}")

def print_error(text):
    print(f"{Colors.RED}  ✗ {text}{Colors.END}")


async def main():
    logging.getLogger().setLevel(logging.WARNING)
    
    from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
    from aios.sdk.models import (
        LLMQuery, MemoryQuery, StorageQuery, ToolQuery,
        Message, MemoryOperation, StorageOperation,
        ResponseStatus,
    )
    from aios.kernel.tool_manager import ToolParameter
    
    print_header("AIOS Full Kernel Demo")
    
    print(f"  {Colors.BLUE}This demo shows the complete AIOS kernel with all managers")
    print(f"  integrated and working together, as described in the paper.{Colors.END}\n")
    
    # Create kernel with temp storage
    with tempfile.TemporaryDirectory() as tmpdir:
        config = KernelConfig(
            scheduling_strategy="round_robin",
            llm_cores=[{"name": "mock-0", "backend": "mock", "model": "mock"}],
            storage_root=tmpdir,
            auto_approve_confirmations=True,
        )
        
        kernel = AIOSKernel(config=config)
        await kernel.start()
        
        try:
            # ===== 1. LLM Interaction =====
            print_section("1. LLM Core Interaction (Section 3.1)")
            
            llm_query = LLMQuery(
                agent_id="demo-agent",
                messages=[
                    Message(role="user", content="What is the capital of France?"),
                ],
                max_tokens=100,
            )
            response = await kernel.process_query(llm_query)
            
            print_result("LLM query processed successfully")
            print_data("Response", response.content[:80] + "..." if len(response.content) > 80 else response.content)
            print_data("Model", response.model)
            
            # ===== 2. Memory Operations =====
            print_section("2. Memory Manager (Section 3.5)")
            
            # Write to memory
            await kernel.process_query(MemoryQuery(
                agent_id="demo-agent",
                operation=MemoryOperation.WRITE,
                key="conversation_context",
                value={"topic": "geography", "question_count": 1},
            ))
            print_result("Wrote conversation context to memory")
            
            # Read from memory
            read_response = await kernel.process_query(MemoryQuery(
                agent_id="demo-agent",
                operation=MemoryOperation.READ,
                key="conversation_context",
            ))
            print_result(f"Read from memory: {read_response.data['value']}")
            
            # List keys
            list_response = await kernel.process_query(MemoryQuery(
                agent_id="demo-agent",
                operation=MemoryOperation.LIST,
            ))
            print_data("Memory keys", list_response.data["keys"])
            
            # ===== 3. Storage Operations =====
            print_section("3. Storage Manager with Versioning (Section 3.6)")
            
            # Write file v1
            await kernel.process_query(StorageQuery(
                agent_id="demo-agent",
                operation=StorageOperation.WRITE,
                path="notes/research.txt",
                data="Research notes v1: Capital cities",
            ))
            print_result("Created notes/research.txt (v1)")
            
            # Write file v2
            await kernel.process_query(StorageQuery(
                agent_id="demo-agent",
                operation=StorageOperation.WRITE,
                path="notes/research.txt",
                data="Research notes v2: Capital cities\n- Paris is capital of France",
            ))
            print_result("Updated notes/research.txt (v2)")
            
            # Read current version
            read_storage = await kernel.process_query(StorageQuery(
                agent_id="demo-agent",
                operation=StorageOperation.READ,
                path="notes/research.txt",
            ))
            print_data("Current content", read_storage.data["content"][:60] + "...")
            
            # ===== 4. Tool Execution =====
            print_section("4. Tool Manager (Section 3.7)")
            
            # Register a custom tool
            async def web_search(query: str, limit: int = 5) -> dict:
                """Simulated web search."""
                return {
                    "query": query,
                    "results": [
                        {"title": f"Result {i+1} for '{query}'", "url": f"https://example.com/{i}"}
                        for i in range(limit)
                    ]
                }
            
            await kernel.tool_manager.register_tool(
                name="web_search",
                description="Search the web",
                function=web_search,
                parameters=[
                    ToolParameter("query", "string", "Search query"),
                    ToolParameter("limit", "number", "Max results", required=False, default=5),
                ],
            )
            print_result("Registered custom 'web_search' tool")
            
            # Use built-in calculator
            calc_response = await kernel.process_query(ToolQuery(
                agent_id="demo-agent",
                tool_name="calculator",
                parameters={"expression": "2 ** 10"},
            ))
            print_result(f"calculator('2 ** 10') = {calc_response.result}")
            
            # Use custom tool
            search_response = await kernel.process_query(ToolQuery(
                agent_id="demo-agent",
                tool_name="web_search",
                parameters={"query": "Paris capital", "limit": 3},
            ))
            print_result(f"web_search returned {len(search_response.result['results'])} results")
            
            # ===== 5. Access Control =====
            print_section("5. Access Manager (Section 3.8)")
            
            # Check default permissions
            has_read = await kernel.access_manager.check_permission("demo-agent", kernel.access_manager.DEFAULT_GROUPS["user"].permissions.pop())
            print_result(f"Agent 'demo-agent' registered with 'user' privileges")
            
            # Register a guest agent
            await kernel.access_manager.register_agent("guest-agent", "guest")
            print_result("Registered 'guest-agent' with 'guest' privileges")
            
            # Guest cannot write
            guest_write = await kernel.process_query(MemoryQuery(
                agent_id="guest-agent",
                operation=MemoryOperation.WRITE,
                key="test",
                value="data",
            ))
            if guest_write.status == ResponseStatus.FORBIDDEN:
                print_result("Guest agent correctly denied write access")
            
            # ===== 6. Context Management =====
            print_section("6. Context Manager for RR Scheduling (Section 3.4)")
            
            # Simulate suspending an agent mid-generation
            await kernel.suspend_agent(
                agent_id="demo-agent",
                messages=[{"role": "user", "content": "Tell me a story"}],
                generated_tokens="Once upon a time, in a magical kingdom,",
                tokens_count=9,
            )
            print_result("Suspended agent with partial generation")
            print_data("Saved tokens", "Once upon a time, in a magical kingdom,")
            
            # Resume agent
            resume_data = await kernel.resume_agent("demo-agent")
            print_result(f"Resumed agent - can continue from: '{resume_data['generated_tokens']}'")
            
            # ===== 7. Multi-Agent Scenario =====
            print_section("7. Multi-Agent Concurrent Execution")
            
            async def agent_task(agent_id: str) -> dict:
                """Simulate an agent doing work."""
                # LLM call
                await kernel.process_query(LLMQuery(
                    agent_id=agent_id,
                    messages=[Message(role="user", content=f"Task from {agent_id}")],
                ))
                
                # Memory write
                await kernel.process_query(MemoryQuery(
                    agent_id=agent_id,
                    operation=MemoryOperation.WRITE,
                    key="task_result",
                    value={"agent": agent_id, "completed": True},
                ))
                
                return {"agent_id": agent_id, "status": "complete"}
            
            # Run 5 agents concurrently
            agents = [f"agent-{i}" for i in range(5)]
            results = await asyncio.gather(*[agent_task(a) for a in agents])
            
            print_result(f"Ran {len(results)} agents concurrently")
            for r in results:
                print_data(r["agent_id"], r["status"])
            
            # ===== 8. Kernel Stats =====
            print_section("8. Kernel Statistics")
            
            stats = kernel.get_stats()
            
            print_data("LLM Cores", stats["llm_manager"]["total_cores"])
            print_data("Scheduler strategy", stats["scheduler"]["strategy"])
            print_data("Completed syscalls", stats["scheduler"]["completed_syscalls"])
            print_data("Memory blocks", stats["memory_manager"]["total_blocks"])
            print_data("Context snapshots", stats["context_manager"]["total_snapshots"])
            print_data("Registered tools", stats["tool_manager"]["registered_tools"])
            print_data("Registered agents", stats["access_manager"]["registered_agents"])
            
        finally:
            await kernel.stop()
    
    print_header("Demo Complete!")
    
    print(f"""
  {Colors.CYAN}The AIOS Kernel now integrates all paper components:
  
  ┌────────────────────────────────────────────────────────────────┐
  │                    APPLICATION LAYER                          │
  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
  │  │ Agent 1  │ │ Agent 2  │ │ Agent 3  │ │ Agent N  │          │
  │  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘          │
  │       │            │            │            │                 │
  │       └────────────┴────────────┴────────────┘                 │
  │                        │ SDK                                   │
  ├────────────────────────┼───────────────────────────────────────┤
  │                        ▼                                       │
  │  ┌─────────────────────────────────────────────────────────┐  │
  │  │                    AIOS KERNEL                          │  │
  │  │  ┌───────────┐ ┌─────────────┐ ┌─────────────────────┐ │  │
  │  │  │ Scheduler │ │ LLM Manager │ │  Context Manager    │ │  │
  │  │  │ FIFO / RR │ │ Multi-core  │ │  Snapshot/Resume    │ │  │
  │  │  └───────────┘ └─────────────┘ └─────────────────────┘ │  │
  │  │  ┌───────────┐ ┌─────────────┐ ┌─────────────────────┐ │  │
  │  │  │  Memory   │ │   Storage   │ │   Tool Manager      │ │  │
  │  │  │  LRU-K    │ │  Versioning │ │   Validation        │ │  │
  │  │  └───────────┘ └─────────────┘ └─────────────────────┘ │  │
  │  │  ┌─────────────────────────────────────────────────────┐│  │
  │  │  │             Access Manager                          ││  │
  │  │  │    Privileges • Permissions • User Confirmation     ││  │
  │  │  └─────────────────────────────────────────────────────┘│  │
  │  └─────────────────────────────────────────────────────────┘  │
  ├────────────────────────────────────────────────────────────────┤
  │                    HARDWARE LAYER                              │
  │              LLM(s) • GPU • Disk • Network                     │
  └────────────────────────────────────────────────────────────────┘
  
  Paper Reference: Figure 2, Section 2{Colors.END}
""")


if __name__ == "__main__":
    asyncio.run(main())

