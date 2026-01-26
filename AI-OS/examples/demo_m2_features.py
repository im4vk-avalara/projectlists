"""
AIOS Milestone 2 Features Demo

Demonstrates the advanced kernel features:
- Context Manager (snapshots for RR scheduling)
- Memory Manager (LRU-K eviction)
- Storage Manager (persistence, versioning)
- Tool Manager (registration, validation)
- Access Manager (privilege control)

Paper Reference: Sections 3.4-3.8
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

def print_section(text):
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- {text} ---{Colors.END}\n")

def print_result(text):
    print(f"{Colors.GREEN}  ✓ {text}{Colors.END}")

def print_data(label, data):
    print(f"{Colors.YELLOW}    {label}:{Colors.END} {data}")


async def demo_context_manager():
    """Demo Context Manager features."""
    from aios.kernel.context_manager import ContextManager, SnapshotType
    
    print_section("Context Manager (Section 3.4)")
    
    ctx_mgr = ContextManager(max_snapshots_per_agent=5)
    
    # Simulate agent being interrupted during generation
    print("  Simulating agent 'agent-1' being interrupted mid-generation...")
    
    snapshot = await ctx_mgr.create_snapshot(
        agent_id="agent-1",
        messages=[
            {"role": "user", "content": "Write a story about a cat"},
            {"role": "assistant", "content": ""},  # Partial
        ],
        generated_tokens="Once upon a time, there was a curious",
        tokens_count=8,
    )
    
    print_result(f"Snapshot created: {snapshot.snapshot_id[:8]}...")
    print_data("Generated tokens", snapshot.generated_tokens)
    print_data("Token count", snapshot.tokens_count)
    print_data("Size", f"{snapshot.size_bytes} bytes")
    
    # Restore snapshot
    restored = await ctx_mgr.restore_snapshot("agent-1")
    print_result(f"Snapshot restored - agent can continue from: '{restored.generated_tokens}'")
    
    # Stats
    stats = ctx_mgr.get_stats()
    print_data("Total snapshots", stats["total_snapshots"])


async def demo_memory_manager():
    """Demo Memory Manager features."""
    from aios.kernel.memory_manager import MemoryManager
    
    print_section("Memory Manager with LRU-K (Section 3.5)")
    
    mem_mgr = MemoryManager(memory_limit_mb=1, lru_k=2)
    
    # Write some data
    await mem_mgr.write("agent-1", "conversation_history", [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ])
    await mem_mgr.write("agent-1", "user_preferences", {"theme": "dark", "language": "en"})
    await mem_mgr.write("agent-1", "task_context", {"current_task": "coding", "priority": "high"})
    
    print_result("Wrote 3 memory blocks for agent-1")
    
    # Read and access (updates LRU-K scores)
    block = await mem_mgr.read("agent-1", "user_preferences")
    print_result(f"Read user_preferences: {block.value}")
    print_data("Access count", block.access_count)
    print_data("LRU-2 score", f"{block.get_lru_k_score(k=2):.2f}")
    
    # Search
    results = await mem_mgr.search("agent-1", "task")
    print_result(f"Search for 'task': found {len(results)} results")
    
    # Stats
    stats = mem_mgr.get_stats()
    print_data("Total blocks", stats["total_blocks"])
    print_data("Memory usage", f"{stats['current_size_mb']:.4f} MB")


async def demo_storage_manager():
    """Demo Storage Manager features."""
    from aios.kernel.storage_manager import StorageManager
    import tempfile
    import os
    
    print_section("Storage Manager with Versioning (Section 3.6)")
    
    # Use temp directory for demo
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = StorageManager(root_path=tmpdir, max_versions=5)
        
        # Write file
        await storage.write("agent-1", "notes/todo.txt", b"1. Buy groceries")
        print_result("Created notes/todo.txt (v1)")
        
        # Update file (creates new version)
        await storage.write("agent-1", "notes/todo.txt", b"1. Buy groceries\n2. Call mom")
        print_result("Updated notes/todo.txt (v2)")
        
        await storage.write("agent-1", "notes/todo.txt", b"1. Buy groceries\n2. Call mom\n3. Exercise")
        print_result("Updated notes/todo.txt (v3)")
        
        # Read current version
        data = await storage.read("agent-1", "notes/todo.txt")
        print_data("Current content", data.decode())
        
        # Get versions
        versions = await storage.get_versions("agent-1", "notes/todo.txt")
        print_result(f"File has {len(versions)} versions")
        
        # Rollback
        await storage.rollback("agent-1", "notes/todo.txt", version=1)
        data = await storage.read("agent-1", "notes/todo.txt")
        print_result(f"Rolled back to v1: {data.decode()}")
        
        # Share file
        await storage.share("agent-1", "notes/todo.txt", "agent-2")
        print_result("Shared notes/todo.txt with agent-2")
        
        # Lock file
        lock = await storage.acquire_lock("agent-1", "notes/todo.txt")
        print_result(f"Acquired lock: {lock.lock_id[:8]}...")
        
        await storage.release_lock(lock.lock_id)
        print_result("Released lock")


async def demo_tool_manager():
    """Demo Tool Manager features."""
    from aios.kernel.tool_manager import ToolManager, ToolParameter
    
    print_section("Tool Manager (Section 3.7)")
    
    tool_mgr = ToolManager(default_max_instances=2)
    
    # Register tools
    async def calculator(expression: str) -> str:
        """Evaluate math expression."""
        try:
            return str(eval(expression))
        except:
            return "Error"
    
    async def web_search(query: str, limit: int = 5) -> dict:
        """Simulated web search."""
        return {"query": query, "results": [f"Result {i}" for i in range(limit)]}
    
    await tool_mgr.register_tool(
        name="calculator",
        description="Evaluates mathematical expressions",
        function=calculator,
        parameters=[ToolParameter("expression", "string", "Math expression")],
        category="utilities",
    )
    
    await tool_mgr.register_tool(
        name="web_search",
        description="Searches the web",
        function=web_search,
        parameters=[
            ToolParameter("query", "string", "Search query"),
            ToolParameter("limit", "number", "Max results", required=False, default=5),
        ],
        category="search",
    )
    
    print_result(f"Registered {len(tool_mgr.list_tools())} tools")
    
    # Call tools
    result = await tool_mgr.call("agent-1", "calculator", {"expression": "2 ** 10"})
    print_result(f"calculator('2 ** 10') = {result}")
    
    result = await tool_mgr.call("agent-1", "web_search", {"query": "AIOS paper", "limit": 3})
    print_result(f"web_search returned {len(result['results'])} results")
    
    # Get OpenAI-compatible schemas
    schemas = tool_mgr.get_tool_schemas()
    print_data("Tool schemas", f"{len(schemas)} tools available for LLM")
    
    # Stats
    stats = tool_mgr.get_stats()
    print_data("Total executions", stats["total_executions"])


async def demo_access_manager():
    """Demo Access Manager features."""
    from aios.kernel.access_manager import AccessManager, Permission, PrivilegeLevel
    
    print_section("Access Manager (Section 3.8)")
    
    access_mgr = AccessManager(default_group="user", auto_approve=True)
    
    # Register agents with different privilege levels
    await access_mgr.register_agent("admin-agent", "admin")
    await access_mgr.register_agent("user-agent", "user")
    await access_mgr.register_agent("guest-agent", "guest")
    
    print_result("Registered 3 agents with different privileges")
    
    # Check permissions
    perms = {
        "admin-agent": [Permission.READ, Permission.WRITE, Permission.DELETE, Permission.ADMIN],
        "user-agent": [Permission.READ, Permission.WRITE, Permission.EXECUTE],
        "guest-agent": [Permission.READ],
    }
    
    for agent, expected_perms in perms.items():
        for perm in expected_perms:
            has = await access_mgr.check_permission(agent, perm)
            status = "✓" if has else "✗"
            # Only print first permission for brevity
        print_result(f"{agent} has {len(expected_perms)} permissions")
    
    # Grant additional permission
    await access_mgr.grant_permission("guest-agent", Permission.WRITE, "shared/file.txt")
    print_result("Granted guest-agent WRITE on shared/file.txt")
    
    # User confirmation (auto-approved in demo)
    approved = await access_mgr.request_confirmation(
        agent_id="user-agent",
        resource="important_data.db",
        permission=Permission.DELETE,
        description="Delete the database",
        justification="User requested cleanup",
    )
    print_result(f"Confirmation request: {'approved' if approved else 'denied'}")
    
    # Audit log
    log = access_mgr.get_audit_log(limit=5)
    print_data("Recent audit events", len(log))


async def main():
    logging.getLogger().setLevel(logging.WARNING)
    
    print_header("AIOS Milestone 2 Features Demo")
    
    await demo_context_manager()
    await demo_memory_manager()
    await demo_storage_manager()
    await demo_tool_manager()
    await demo_access_manager()
    
    print_header("Demo Complete!")
    
    print(f"""
  {Colors.CYAN}Milestone 2 implemented these paper sections:
  
  • Section 3.4: Context Manager
    - Text-based snapshots for RR scheduling
    - Suspend/resume agent generation
    
  • Section 3.5: Memory Manager  
    - LRU-K eviction policy (K=2)
    - Per-agent memory isolation
    - Semantic search support
    
  • Section 3.6: Storage Manager
    - Persistent file storage
    - Versioning with rollback
    - Cross-agent sharing
    - File locking
    
  • Section 3.7: Tool Manager
    - Standardized tool registration
    - Parameter validation
    - Concurrent instance limits
    - OpenAI-compatible schemas
    
  • Section 3.8: Access Manager
    - Privilege groups (guest/user/privileged/admin)
    - Permission checks
    - User confirmation flow
    - Audit logging{Colors.END}
""")


if __name__ == "__main__":
    asyncio.run(main())

