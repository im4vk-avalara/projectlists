"""
AIOS Architecture Demo

This demo shows the complete flow through the AIOS system:
1. Agent Query → 2. SDK → 3. Scheduler → 4. LLM Core → 5. Response

Paper Reference: Figure 2 (Architecture), Figure 3 (Scheduler)
"""

import asyncio
import logging

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
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.END}\n")

def print_step(step, text):
    print(f"{Colors.CYAN}[Step {step}]{Colors.END} {text}")

def print_result(text):
    print(f"{Colors.GREEN}  → {text}{Colors.END}")

def print_data(label, data):
    print(f"{Colors.YELLOW}  {label}:{Colors.END} {data}")


async def demo():
    from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
    from aios.sdk.client import AIOSClient
    from aios.sdk.models import LLMQuery, Message
    
    # Suppress logs for cleaner output
    logging.getLogger().setLevel(logging.WARNING)
    
    print_header("AIOS: LLM Agent Operating System Demo")
    
    # =========================================================================
    # STEP 1: Initialize Kernel
    # =========================================================================
    print_step(1, "Initialize AIOS Kernel (Paper Section 2)")
    
    config = KernelConfig(
        scheduling_strategy="fifo",
        max_concurrent_llm=1,
    )
    kernel = AIOSKernel(config=config)
    await kernel.start()
    
    print_result("Kernel started successfully")
    print_data("LLM Cores", kernel.llm_manager.core_count)
    print_data("Scheduler Strategy", kernel.scheduler.config.strategy.value)
    print_data("Queue Types", "LLM, Tool, Memory, Storage (Figure 3)")
    
    # =========================================================================
    # STEP 2: Create Agent Client (SDK)
    # =========================================================================
    print_step(2, "Create Agent via AIOS SDK (Paper Section 3.2)")
    
    travel_agent = AIOSClient(kernel=kernel, agent_id="travel-agent")
    math_agent = AIOSClient(kernel=kernel, agent_id="math-agent")
    
    print_result("Created 2 agents")
    print_data("Agent IDs", "travel-agent, math-agent")
    print_data("Connection Mode", "local (in-process)")
    
    # =========================================================================
    # STEP 3: Agent sends LLM Query
    # =========================================================================
    print_step(3, "Agent sends LLM Query → SDK → Kernel")
    
    print(f"\n  {Colors.BOLD}Travel Agent:{Colors.END} 'Plan a trip to Paris'")
    
    response = await travel_agent.chat([
        {"role": "system", "content": "You are a travel planning assistant."},
        {"role": "user", "content": "Plan a trip to Paris for 3 days."}
    ], max_tokens=100)
    
    print_result(f"Response received!")
    print_data("Status", response.status.value)
    print_data("Content", response.content[:80] + "..." if len(response.content) > 80 else response.content)
    
    # =========================================================================
    # STEP 4: Memory Operations
    # =========================================================================
    print_step(4, "Agent uses Memory Manager (Paper Section 3.5)")
    
    # Write
    await travel_agent.memory_write("destination", "Paris")
    await travel_agent.memory_write("days", 3)
    await travel_agent.memory_write("preferences", {"budget": "medium", "interests": ["art", "food"]})
    
    print_result("Wrote 3 items to agent memory")
    
    # Read
    dest = await travel_agent.memory_read("destination")
    print_data("Retrieved destination", dest.data["value"])
    
    # List
    keys = await travel_agent.memory_list()
    print_data("Memory keys", keys.keys)
    
    # =========================================================================
    # STEP 5: Multi-Agent Scheduling
    # =========================================================================
    print_step(5, "Multi-Agent via Scheduler (Paper Section 3.3)")
    
    print(f"\n  {Colors.BOLD}Sending parallel requests from 2 agents...{Colors.END}")
    
    # Get stats before
    stats_before = kernel.scheduler.get_stats()
    
    # Parallel requests
    results = await asyncio.gather(
        travel_agent.chat([{"role": "user", "content": "Best restaurants in Paris?"}]),
        math_agent.chat([{"role": "user", "content": "What is 42 * 17?"}]),
    )
    
    # Get stats after
    stats_after = kernel.scheduler.get_stats()
    
    print_result(f"Both requests completed via FIFO scheduler")
    print_data("Travel Agent got", results[0].content[:50] + "...")
    print_data("Math Agent got", results[1].content[:50] + "...")
    print_data("Syscalls processed", f"{stats_after['completed_syscalls']} (was {stats_before['completed_syscalls']})")
    
    # =========================================================================
    # STEP 6: Memory Isolation
    # =========================================================================
    print_step(6, "Memory Isolation Between Agents")
    
    # Each agent writes to same key
    await travel_agent.memory_write("shared-key", "travel-value")
    await math_agent.memory_write("shared-key", "math-value")
    
    # Each reads back their own value
    travel_read = await travel_agent.memory_read("shared-key")
    math_read = await math_agent.memory_read("shared-key")
    
    print_result("Agents have isolated memory namespaces")
    print_data("Travel agent reads", travel_read.data["value"])
    print_data("Math agent reads", math_read.data["value"])
    
    # =========================================================================
    # STEP 7: Kernel Stats
    # =========================================================================
    print_step(7, "Final Kernel Statistics")
    
    stats = kernel.get_stats()
    
    print_result("System metrics")
    print_data("Total Syscalls", stats["scheduler"]["total_syscalls"])
    print_data("Completed", stats["scheduler"]["completed_syscalls"])
    print_data("Avg Wait Time", f"{stats['scheduler']['average_waiting_time']*1000:.2f}ms")
    print_data("LLM Queue Status", f"size={stats['scheduler']['queues']['llm']['size']}")
    print_data("Memory Queue Status", f"size={stats['scheduler']['queues']['memory']['size']}")
    
    # =========================================================================
    # Cleanup
    # =========================================================================
    await travel_agent.close()
    await math_agent.close()
    await kernel.stop()
    
    print_header("Demo Complete!")
    print(f"""
  This demo showed the AIOS architecture from the paper:
  
  {Colors.CYAN}┌─────────────────────────────────────────────┐
  │         Agent Applications Layer            │
  │     (travel-agent, math-agent)              │
  ├─────────────────────────────────────────────┤
  │              AIOS SDK (Cerebrum)            │
  │    (Query/Response, memory ops, chat API)   │
  ├─────────────────────────────────────────────┤
  │              AIOS Kernel                    │
  │  ┌─────────┐ ┌──────────┐ ┌─────────────┐   │
  │  │LLM Core │ │Scheduler │ │Memory Mgr   │   │
  │  │Manager  │ │(FIFO/RR) │ │(per-agent)  │   │
  │  └─────────┘ └──────────┘ └─────────────┘   │
  └─────────────────────────────────────────────┘{Colors.END}
  
  Paper Reference: arXiv:2403.16971v5
""")


if __name__ == "__main__":
    asyncio.run(demo())

