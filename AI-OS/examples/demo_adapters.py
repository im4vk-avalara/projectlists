"""
AIOS Agent Framework Adapters Demo

Demonstrates the various agent framework adapters:
- ReAct (Reasoning + Acting)
- Reflexion (Self-reflection)
- AutoGen (Multi-agent conversation)
- Interpreter (Code execution)

Paper Reference: Section 3.2, Figure 9
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

def print_step(step):
    print(f"{Colors.YELLOW}    Step {step.step_number}:{Colors.END}")
    if step.thought:
        print(f"      Thought: {step.thought[:60]}...")
    if step.action:
        print(f"      Action: {step.action}")
    if step.observation:
        obs = step.observation[:80] + "..." if len(step.observation) > 80 else step.observation
        print(f"      Observation: {obs}")


async def demo_react():
    """Demo ReAct adapter."""
    from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
    from aios.adapters.react import ReActAdapter
    from aios.adapters.base import AdapterConfig
    
    print_section("ReAct Adapter (Reasoning + Acting)")
    
    print(f"  {Colors.BLUE}ReAct alternates between thinking and acting.")
    print(f"  The agent reasons about what to do, takes an action,")
    print(f"  observes the result, and repeats.{Colors.END}\n")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = KernelConfig(storage_root=tmpdir)
        kernel = AIOSKernel(config=config)
        await kernel.start()
        
        try:
            adapter_config = AdapterConfig(max_iterations=5, verbose=False)
            adapter = ReActAdapter(kernel, agent_id="react-agent", config=adapter_config)
            
            task = "Use the calculator to compute 15 * 7 + 23"
            print(f"  Task: {task}\n")
            
            result = await adapter.run(task)
            
            print_result(f"Completed in {result.iterations} steps")
            print_result(f"Success: {result.success}")
            
            if result.steps:
                print(f"\n  {Colors.CYAN}Execution trace:{Colors.END}")
                for step in result.steps[:3]:  # Show first 3 steps
                    print_step(step)
            
            if result.output:
                print(f"\n  {Colors.GREEN}Final output: {result.output[:100]}{Colors.END}")
            
        finally:
            await kernel.stop()


async def demo_reflexion():
    """Demo Reflexion adapter."""
    from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
    from aios.adapters.reflexion import ReflexionAdapter
    from aios.adapters.base import AdapterConfig
    
    print_section("Reflexion Adapter (Self-Reflection)")
    
    print(f"  {Colors.BLUE}Reflexion adds self-evaluation to the reasoning process.")
    print(f"  The agent attempts a task, reflects on what went well")
    print(f"  and what could be improved, then retries.{Colors.END}\n")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = KernelConfig(storage_root=tmpdir)
        kernel = AIOSKernel(config=config)
        await kernel.start()
        
        try:
            adapter_config = AdapterConfig(max_iterations=3)
            adapter = ReflexionAdapter(
                kernel,
                agent_id="reflexion-agent",
                config=adapter_config,
                max_retries=2,
                reflection_enabled=True,
            )
            
            task = "What time is it right now?"
            print(f"  Task: {task}\n")
            
            result = await adapter.run(task)
            
            print_result(f"Completed with {len(adapter._attempts)} attempt(s)")
            print_result(f"Success: {result.success}")
            
            if adapter._reflections:
                print(f"\n  {Colors.CYAN}Reflections:{Colors.END}")
                for i, reflection in enumerate(adapter._reflections):
                    print(f"    Reflection {i+1}: {reflection[:80]}...")
            
            if result.output:
                print(f"\n  {Colors.GREEN}Final output: {result.output[:100]}{Colors.END}")
            
        finally:
            await kernel.stop()


async def demo_autogen():
    """Demo AutoGen adapter."""
    from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
    from aios.adapters.autogen import AutoGenAdapter
    from aios.adapters.base import AdapterConfig
    
    print_section("AutoGen Adapter (Multi-Agent Conversation)")
    
    print(f"  {Colors.BLUE}AutoGen enables multi-agent conversations.")
    print(f"  Multiple agents take turns speaking, each with")
    print(f"  their own role and capabilities.{Colors.END}\n")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = KernelConfig(storage_root=tmpdir)
        kernel = AIOSKernel(config=config)
        await kernel.start()
        
        try:
            adapter_config = AdapterConfig(max_iterations=4)
            adapter = AutoGenAdapter(kernel, config=adapter_config)
            
            # Create agents
            planner = adapter.create_agent(
                name="planner",
                system_message="You are a project planner. Help organize tasks.",
            )
            
            executor = adapter.create_agent(
                name="executor",
                system_message="You are an executor. Confirm understanding and say TERMINATE when done.",
                is_termination_msg=lambda x: "terminate" in x.lower(),
            )
            
            print(f"  Created agents: planner, executor\n")
            
            result = await adapter.initiate_chat(
                sender=planner,
                receiver=executor,
                message="Let's plan a simple web app. First, we need to decide on the tech stack.",
                max_turns=3,
            )
            
            print_result(f"Conversation completed in {result.iterations} turns")
            
            if adapter._conversation:
                print(f"\n  {Colors.CYAN}Conversation:{Colors.END}")
                for msg in adapter._conversation[:4]:
                    content = msg.content[:60] + "..." if len(msg.content) > 60 else msg.content
                    print(f"    [{msg.sender}]: {content}")
            
        finally:
            await kernel.stop()


async def demo_interpreter():
    """Demo Interpreter adapter."""
    from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
    from aios.adapters.interpreter import InterpreterAdapter
    from aios.adapters.base import AdapterConfig
    
    print_section("Interpreter Adapter (Code Execution)")
    
    print(f"  {Colors.BLUE}Interpreter allows agents to write and execute code.")
    print(f"  The agent can run Python or bash commands to")
    print(f"  accomplish tasks.{Colors.END}\n")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config = KernelConfig(storage_root=tmpdir)
        kernel = AIOSKernel(config=config)
        await kernel.start()
        
        try:
            adapter_config = AdapterConfig(max_iterations=3)
            adapter = InterpreterAdapter(
                kernel,
                agent_id="interpreter-agent",
                config=adapter_config,
                safe_mode=True,
            )
            
            # Test direct code execution
            print("  Direct code execution test:")
            output, error = await adapter._execute_python("print(sum(range(1, 11)))")
            print_result(f"Python: sum(1..10) = {output.strip()}")
            
            output, error = await adapter._execute_bash("echo 'Hello from bash!'")
            print_result(f"Bash: {output.strip()}")
            
            # Test through agent
            print(f"\n  Agent execution:")
            task = "Calculate the factorial of 5"
            print(f"  Task: {task}\n")
            
            result = await adapter.run(task)
            
            print_result(f"Completed in {result.iterations} steps")
            print_result(f"Code executions: {adapter._execution_count}")
            
            if result.output:
                output_preview = result.output[:100] + "..." if len(result.output) > 100 else result.output
                print(f"\n  {Colors.GREEN}Output: {output_preview}{Colors.END}")
            
        finally:
            await kernel.stop()


async def main():
    logging.getLogger().setLevel(logging.WARNING)
    
    print_header("AIOS Agent Framework Adapters Demo")
    
    print(f"""  {Colors.BLUE}This demo showcases the agent framework adapters that allow
  popular agent patterns to run on top of AIOS.
  
  All adapters route LLM calls, tool execution, and memory
  operations through the AIOS kernel, enabling:
  
  • Centralized scheduling (FIFO/Round Robin)
  • Unified memory management (LRU-K eviction)
  • Access control and permissions
  • Context management for interruptible generation{Colors.END}
""")
    
    await demo_react()
    await demo_reflexion()
    await demo_autogen()
    await demo_interpreter()
    
    print_header("Demo Complete!")
    
    print(f"""
  {Colors.CYAN}Implemented Adapters:
  
  ┌─────────────────────────────────────────────────────────────────┐
  │  ReAct              Reflexion           AutoGen                 │
  │  ┌─────────┐        ┌─────────┐        ┌─────────┐             │
  │  │ Think   │        │ Attempt │        │ Agent A │◄────┐       │
  │  │   ↓     │        │    ↓    │        │    ↓    │     │       │
  │  │ Act     │        │ Reflect │        │ Agent B │─────┘       │
  │  │   ↓     │        │    ↓    │        └─────────┘             │
  │  │ Observe │        │ Retry   │                                 │
  │  └────┬────┘        └─────────┘        Interpreter              │
  │       │                                ┌─────────┐             │
  │       └─────────────────────────────── │ Python  │             │
  │              All through AIOS          │ Bash    │             │
  │                                        └─────────┘             │
  └─────────────────────────────────────────────────────────────────┘
  
  Paper Reference: Section 3.2, Figure 9{Colors.END}
""")


if __name__ == "__main__":
    asyncio.run(main())

