"""
AIOS Kernel Main Module

The central kernel that orchestrates all managers and the scheduler.
This is the entry point for the AIOS system.

Paper Reference: Section 2 (Architecture), Figure 2
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import yaml
import os

from aios.core.llm import LLMCoreManager
from aios.core.adapters.base import LLMMessage, LLMGenerationConfig
from aios.kernel.scheduler import Scheduler, SchedulerConfig, SchedulingStrategy
from aios.kernel.syscall import Syscall, SyscallType
from aios.kernel.context_manager import ContextManager, SnapshotType
from aios.kernel.memory_manager import MemoryManager
from aios.kernel.storage_manager import StorageManager
from aios.kernel.tool_manager import ToolManager, ToolParameter
from aios.kernel.access_manager import AccessManager, Permission
from aios.sdk.models import (
    Query,
    Response,
    ResponseStatus,
    LLMQuery,
    LLMResponse,
    MemoryQuery,
    MemoryResponse,
    StorageQuery,
    StorageResponse,
    ToolQuery,
    ToolResponse,
)


logger = logging.getLogger(__name__)


@dataclass
class KernelConfig:
    """
    AIOS Kernel configuration.
    
    Loaded from config file or passed directly.
    """
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    
    # Scheduling
    scheduling_strategy: str = "fifo"
    
    # LLM Cores
    llm_cores: List[Dict[str, Any]] = field(default_factory=list)
    
    # Manager configs
    max_concurrent_llm: int = 1
    max_concurrent_tool: int = 4
    max_concurrent_memory: int = 8
    max_concurrent_storage: int = 4
    
    # Context Manager
    max_snapshots_per_agent: int = 5
    snapshot_type: str = "text"
    
    # Memory Manager
    memory_limit_mb: int = 512
    memory_swap_threshold: float = 75.0
    lru_k: int = 2
    
    # Storage Manager
    storage_root: str = "./data/storage"
    max_versions: int = 10
    
    # Tool Manager
    tool_timeout: int = 30
    default_max_tool_instances: int = 4
    
    # Access Manager
    default_privilege_group: str = "user"
    auto_approve_confirmations: bool = False
    
    @classmethod
    def from_yaml(cls, path: str) -> "KernelConfig":
        """Load configuration from YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)
        
        kernel_data = data.get("kernel", {})
        scheduler_data = kernel_data.get("scheduler", {})
        memory_data = kernel_data.get("memory_manager", {})
        storage_data = kernel_data.get("storage_manager", {})
        tool_data = kernel_data.get("tool_manager", {})
        access_data = kernel_data.get("access_manager", {})
        
        return cls(
            host=kernel_data.get("host", "0.0.0.0"),
            port=kernel_data.get("port", 8000),
            log_level=kernel_data.get("log_level", "INFO"),
            scheduling_strategy=kernel_data.get("scheduling_strategy", "fifo"),
            llm_cores=kernel_data.get("llm_cores", []),
            max_concurrent_llm=scheduler_data.get("max_concurrent_llm", 1),
            max_concurrent_tool=scheduler_data.get("max_concurrent_tool", 4),
            max_concurrent_memory=scheduler_data.get("max_concurrent_memory", 8),
            max_concurrent_storage=scheduler_data.get("max_concurrent_storage", 4),
            memory_limit_mb=memory_data.get("max_memory_blocks", 512),
            lru_k=memory_data.get("lru_k_value", 2),
            storage_root=storage_data.get("base_dir", "./data/storage"),
            max_versions=storage_data.get("max_versions", 10),
            tool_timeout=tool_data.get("timeout", 30),
            default_privilege_group=access_data.get("default_privilege_group", "user"),
        )


class AIOSKernel:
    """
    The AIOS Kernel.
    
    Central component that:
    - Manages LLM cores (Section 3.1)
    - Schedules agent syscalls (Section 3.3)
    - Manages context for RR scheduling (Section 3.4)
    - Manages memory with LRU-K (Section 3.5)
    - Manages persistent storage (Section 3.6)
    - Manages tools (Section 3.7)
    - Enforces access control (Section 3.8)
    
    Paper Reference: Section 2, Figure 2
    
    Example:
        kernel = AIOSKernel()
        await kernel.start()
        
        # Process a query
        response = await kernel.process_query(query)
        
        await kernel.stop()
    """
    
    def __init__(self, config: Optional[KernelConfig] = None):
        """
        Initialize the kernel.
        
        Args:
            config: Kernel configuration (uses defaults if None)
        """
        self.config = config or KernelConfig()
        
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        
        # Initialize LLM Core Manager (Section 3.1)
        self.llm_manager = LLMCoreManager()
        
        # Initialize Scheduler (Section 3.3)
        strategy = SchedulingStrategy(self.config.scheduling_strategy)
        scheduler_config = SchedulerConfig(
            strategy=strategy,
            max_concurrent_llm=self.config.max_concurrent_llm,
            max_concurrent_tool=self.config.max_concurrent_tool,
            max_concurrent_memory=self.config.max_concurrent_memory,
            max_concurrent_storage=self.config.max_concurrent_storage,
        )
        self.scheduler = Scheduler(config=scheduler_config)
        
        # Initialize Context Manager (Section 3.4)
        snapshot_type = SnapshotType(self.config.snapshot_type)
        self.context_manager = ContextManager(
            max_snapshots_per_agent=self.config.max_snapshots_per_agent,
            snapshot_type=snapshot_type,
        )
        
        # Initialize Memory Manager (Section 3.5)
        self.memory_manager = MemoryManager(
            memory_limit_mb=self.config.memory_limit_mb,
            swap_threshold_percent=self.config.memory_swap_threshold,
            lru_k=self.config.lru_k,
        )
        
        # Initialize Storage Manager (Section 3.6)
        self.storage_manager = StorageManager(
            root_path=self.config.storage_root,
            max_versions=self.config.max_versions,
        )
        
        # Initialize Tool Manager (Section 3.7)
        self.tool_manager = ToolManager(
            default_max_instances=self.config.default_max_tool_instances,
            timeout_seconds=self.config.tool_timeout,
        )
        
        # Initialize Access Manager (Section 3.8)
        self.access_manager = AccessManager(
            default_group=self.config.default_privilege_group,
            auto_approve=self.config.auto_approve_confirmations,
        )
        
        # Wire storage manager to memory manager for swapping
        self.memory_manager.storage_manager = self.storage_manager
        
        self._is_running = False
        
        logger.info("AIOS Kernel initialized with all managers")
    
    async def start(self) -> None:
        """
        Start the kernel.
        
        Initializes all managers and starts the scheduler.
        """
        if self._is_running:
            return
        
        logger.info("Starting AIOS Kernel...")
        
        # Initialize LLM cores from config
        if self.config.llm_cores:
            for core_config in self.config.llm_cores:
                await self._add_llm_core(core_config)
        else:
            # Add default mock core for testing
            await self.llm_manager.add_core(
                name="core-0",
                backend_type="mock",
                model="mock-model",
            )
        
        # Register built-in tools
        await self._register_builtin_tools()
        
        # Register syscall handlers
        self.scheduler.register_handler(SyscallType.LLM, self._handle_llm_syscall)
        self.scheduler.register_handler(SyscallType.MEMORY, self._handle_memory_syscall)
        self.scheduler.register_handler(SyscallType.STORAGE, self._handle_storage_syscall)
        self.scheduler.register_handler(SyscallType.TOOL, self._handle_tool_syscall)
        
        # Start scheduler
        await self.scheduler.start()
        
        self._is_running = True
        logger.info("AIOS Kernel started")
    
    async def stop(self) -> None:
        """Stop the kernel."""
        if not self._is_running:
            return
        
        logger.info("Stopping AIOS Kernel...")
        
        # Stop scheduler
        await self.scheduler.stop()
        
        # Shutdown LLM cores
        await self.llm_manager.shutdown()
        
        self._is_running = False
        logger.info("AIOS Kernel stopped")
    
    async def _add_llm_core(self, core_config: Dict[str, Any]) -> None:
        """Add an LLM core from configuration."""
        name = core_config.get("name", f"core-{len(self.llm_manager.cores)}")
        backend = core_config.get("backend", "mock")
        model = core_config.get("model", "mock-model")
        
        # Extract additional kwargs
        kwargs = {k: v for k, v in core_config.items() if k not in ("name", "backend", "model")}
        
        try:
            await self.llm_manager.add_core(
                name=name,
                backend_type=backend,
                model=model,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Failed to add LLM core '{name}': {e}")
    
    async def _register_builtin_tools(self) -> None:
        """Register built-in tools."""
        
        # Calculator tool
        async def calculator(expression: str) -> str:
            """Evaluate a mathematical expression."""
            allowed = set("0123456789+-*/.(). ")
            if not all(c in allowed for c in expression):
                return "Error: Invalid characters"
            try:
                return str(eval(expression))
            except Exception as e:
                return f"Error: {e}"
        
        await self.tool_manager.register_tool(
            name="calculator",
            description="Evaluate mathematical expressions",
            function=calculator,
            parameters=[ToolParameter("expression", "string", "Math expression")],
            category="utilities",
        )
        
        # Current time tool
        async def current_time() -> str:
            """Get current date and time."""
            from datetime import datetime
            return datetime.now().isoformat()
        
        await self.tool_manager.register_tool(
            name="current_time",
            description="Get the current date and time",
            function=current_time,
            parameters=[],
            category="utilities",
        )
        
        logger.debug("Registered built-in tools")
    
    async def process_query(self, query: Query) -> Response:
        """
        Process a query from the SDK.
        
        Decomposes the query into syscalls and routes them through
        the scheduler.
        
        Paper Reference: Figure 9 (SDK -> Kernel flow)
        """
        from aios.kernel.syscall import (
            create_llm_syscall,
            create_memory_syscall,
            create_storage_syscall,
            create_tool_syscall,
        )
        
        # Access control check
        agent_id = query.agent_id
        if not await self._check_agent_access(agent_id, query):
            return Response(
                query_id=query.query_id,
                status=ResponseStatus.FORBIDDEN,
                error="Access denied",
            )
        
        # Decompose query into syscall(s)
        if isinstance(query, LLMQuery):
            syscall = create_llm_syscall(
                agent_id=query.agent_id,
                query_id=query.query_id,
                query=query,
            )
        elif isinstance(query, MemoryQuery):
            syscall = create_memory_syscall(
                agent_id=query.agent_id,
                query_id=query.query_id,
                operation=query.operation.value,
                params=query.to_dict(),
            )
        elif isinstance(query, StorageQuery):
            syscall = create_storage_syscall(
                agent_id=query.agent_id,
                query_id=query.query_id,
                operation=query.operation.value,
                params=query.to_dict(),
            )
        elif isinstance(query, ToolQuery):
            from aios.sdk.models import ToolOperation
            if query.operation == ToolOperation.LIST:
                # List tools - no tool name needed
                syscall = Syscall(
                    agent_id=query.agent_id,
                    query_id=query.query_id,
                    syscall_type=SyscallType.TOOL,
                    operation="list",
                    params={
                        "operation": "list",
                        "category_filter": query.category_filter,
                    },
                )
            else:
                # Call tool
                syscall = create_tool_syscall(
                    agent_id=query.agent_id,
                    query_id=query.query_id,
                    tool_name=query.tool_name,
                    params={"parameters": query.parameters},
                )
        else:
            # Generic handling
            syscall = Syscall(
                agent_id=query.agent_id,
                query_id=query.query_id,
                syscall_type=SyscallType.LLM,
                operation="unknown",
                params=query.to_dict() if hasattr(query, "to_dict") else {},
            )
        
        # Submit to scheduler
        response = await self.scheduler.submit(syscall)
        return response
    
    async def _check_agent_access(self, agent_id: str, query: Query) -> bool:
        """Check if agent has access to perform the query."""
        # Register agent if not already registered
        await self.access_manager.get_agent_access(agent_id)
        
        # Check permission based on query type
        if isinstance(query, LLMQuery):
            return await self.access_manager.check_permission(agent_id, Permission.EXECUTE)
        elif isinstance(query, MemoryQuery):
            if query.operation.value == "read":
                return await self.access_manager.check_permission(agent_id, Permission.READ)
            else:
                return await self.access_manager.check_permission(agent_id, Permission.WRITE)
        elif isinstance(query, StorageQuery):
            if query.operation.value in ("read", "list"):
                return await self.access_manager.check_permission(agent_id, Permission.READ)
            elif query.operation.value == "delete":
                return await self.access_manager.check_permission(agent_id, Permission.DELETE)
            else:
                return await self.access_manager.check_permission(agent_id, Permission.WRITE)
        elif isinstance(query, ToolQuery):
            return await self.access_manager.check_tool_access(agent_id, query.tool_name)
        
        return True
    
    async def _handle_llm_syscall(self, syscall: Syscall) -> Response:
        """
        Handle LLM syscall with context management.
        
        Paper Reference: Section 3.1, 3.4
        """
        query = syscall.query
        if not isinstance(query, LLMQuery):
            return Response(
                query_id=syscall.query_id,
                status=ResponseStatus.ERROR,
                error="Invalid query type for LLM syscall",
            )
        
        agent_id = query.agent_id
        
        try:
            # Check for existing context snapshot (for RR scheduling resume)
            snapshot = await self.context_manager.get_latest_snapshot(agent_id)
            
            # Convert SDK messages to adapter messages
            messages = [
                LLMMessage(
                    role=msg.role,
                    content=msg.content,
                    name=msg.name,
                    tool_calls=msg.tool_calls,
                    tool_call_id=msg.tool_call_id,
                )
                for msg in query.messages
            ]
            
            # If resuming from snapshot, prepend generated content
            if snapshot and snapshot.generated_tokens:
                # Find the assistant message being generated and update it
                if messages and messages[-1].role == "assistant":
                    messages[-1].content = snapshot.generated_tokens + (messages[-1].content or "")
                else:
                    # Add the partial generation as context
                    messages.append(LLMMessage(
                        role="assistant",
                        content=snapshot.generated_tokens,
                    ))
                
                # Clear the snapshot after using it
                await self.context_manager.clear_snapshot(agent_id)
            
            # Mark agent as running
            await self.context_manager.resume_agent(agent_id)
            
            # Build config
            config = LLMGenerationConfig(
                max_tokens=query.max_tokens,
                temperature=query.temperature,
                top_p=query.top_p,
                stop_sequences=query.stop_sequences,
                stream=query.stream,
                tools=query.tools,
                tool_choice=query.tool_choice,
            )
            
            # Execute on LLM core
            result = await self.llm_manager.execute(
                agent_id=query.agent_id,
                messages=messages,
                config=config,
            )
            
            # Mark agent as idle after completion
            await self.context_manager.clear_snapshot(agent_id)
            
            return LLMResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.SUCCESS,
                content=result.content,
                finish_reason=result.finish_reason,
                tool_calls=result.tool_calls,
                usage=result.usage,
                model=result.model,
                execution_time_ms=result.generation_time_ms,
            )
            
        except Exception as e:
            logger.exception(f"LLM syscall failed: {e}")
            return LLMResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.ERROR,
                error=str(e),
            )
    
    async def _handle_memory_syscall(self, syscall: Syscall) -> Response:
        """
        Handle memory syscall using MemoryManager.
        
        Paper Reference: Section 3.5
        """
        params = syscall.params
        operation = params.get("operation", "read")
        agent_id = syscall.agent_id
        key = params.get("key", "")
        
        try:
            if operation == "write":
                value = params.get("value")
                ttl = params.get("ttl")
                block = await self.memory_manager.write(agent_id, key, value, ttl)
                return MemoryResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.SUCCESS,
                    data={"key": key, "size_bytes": block.size_bytes},
                )
            
            elif operation == "read":
                block = await self.memory_manager.read(agent_id, key)
                if block:
                    return MemoryResponse(
                        query_id=syscall.query_id,
                        status=ResponseStatus.SUCCESS,
                        data={"key": key, "value": block.value},
                    )
                else:
                    return MemoryResponse(
                        query_id=syscall.query_id,
                        status=ResponseStatus.NOT_FOUND,
                        error=f"Key not found: {key}",
                    )
            
            elif operation == "delete":
                deleted = await self.memory_manager.delete(agent_id, key)
                return MemoryResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.SUCCESS if deleted else ResponseStatus.NOT_FOUND,
                )
            
            elif operation == "list":
                prefix = params.get("prefix", "")
                keys = await self.memory_manager.list_keys(agent_id, prefix)
                return MemoryResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.SUCCESS,
                    data={"keys": keys},
                )
            
            elif operation == "search":
                query_text = params.get("query", "")
                limit = params.get("limit", 10)
                results = await self.memory_manager.search(agent_id, query_text, limit)
                return MemoryResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.SUCCESS,
                    data={"results": [{"key": b.key, "value": b.value} for b in results]},
                )
            
            else:
                return MemoryResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.ERROR,
                    error=f"Unknown operation: {operation}",
                )
                
        except Exception as e:
            logger.exception(f"Memory syscall failed: {e}")
            return MemoryResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.ERROR,
                error=str(e),
            )
    
    async def _handle_storage_syscall(self, syscall: Syscall) -> Response:
        """
        Handle storage syscall using StorageManager.
        
        Paper Reference: Section 3.6
        """
        params = syscall.params
        operation = params.get("operation", "read")
        agent_id = syscall.agent_id
        path = params.get("path", "")
        
        try:
            if operation == "write":
                data = params.get("data", b"")
                if isinstance(data, str):
                    data = data.encode()
                metadata = await self.storage_manager.write(agent_id, path, data)
                return StorageResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.SUCCESS,
                    data={"path": path, "version": metadata.current_version},
                )
            
            elif operation == "read":
                version = params.get("version")
                data = await self.storage_manager.read(agent_id, path, version)
                if data:
                    return StorageResponse(
                        query_id=syscall.query_id,
                        status=ResponseStatus.SUCCESS,
                        data={"path": path, "content": data.decode() if data else None},
                    )
                else:
                    return StorageResponse(
                        query_id=syscall.query_id,
                        status=ResponseStatus.NOT_FOUND,
                        error=f"File not found: {path}",
                    )
            
            elif operation == "delete":
                deleted = await self.storage_manager.delete(agent_id, path)
                return StorageResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.SUCCESS if deleted else ResponseStatus.NOT_FOUND,
                )
            
            elif operation == "list":
                recursive = params.get("recursive", False)
                files = await self.storage_manager.list_files(agent_id, path, recursive)
                return StorageResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.SUCCESS,
                    data={"files": [f.to_dict() for f in files]},
                )
            
            elif operation == "rollback":
                version = params.get("version", 1)
                success = await self.storage_manager.rollback(agent_id, path, version)
                return StorageResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.SUCCESS if success else ResponseStatus.ERROR,
                    error=None if success else f"Failed to rollback to version {version}",
                )
            
            elif operation == "share":
                target_agent = params.get("target_agent_id")
                success = await self.storage_manager.share(agent_id, path, target_agent)
                return StorageResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.SUCCESS if success else ResponseStatus.ERROR,
                )
            
            elif operation == "lock":
                lock = await self.storage_manager.acquire_lock(agent_id, path)
                if lock:
                    return StorageResponse(
                        query_id=syscall.query_id,
                        status=ResponseStatus.SUCCESS,
                        data={"lock_id": lock.lock_id},
                    )
                else:
                    return StorageResponse(
                        query_id=syscall.query_id,
                        status=ResponseStatus.ERROR,
                        error="Failed to acquire lock",
                    )
            
            elif operation == "unlock":
                lock_id = params.get("lock_id")
                success = await self.storage_manager.release_lock(lock_id)
                return StorageResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.SUCCESS if success else ResponseStatus.ERROR,
                )
            
            else:
                return StorageResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.ERROR,
                    error=f"Unknown operation: {operation}",
                )
                
        except PermissionError as e:
            return StorageResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.FORBIDDEN,
                error=str(e),
            )
        except Exception as e:
            logger.exception(f"Storage syscall failed: {e}")
            return StorageResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.ERROR,
                error=str(e),
            )
    
    async def _handle_tool_syscall(self, syscall: Syscall) -> Response:
        """
        Handle tool syscall using ToolManager.
        
        Paper Reference: Section 3.7
        """
        agent_id = syscall.agent_id
        operation = syscall.params.get("operation", "call")
        tool_name = syscall.params.get("tool_name", "")
        parameters = syscall.params.get("parameters", {})
        
        # Handle list operation
        if operation == "list":
            category = syscall.params.get("category_filter")
            tools = self.tool_manager.list_tools(category)
            return ToolResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.SUCCESS,
                tools=[t.get_schema() for t in tools],
            )
        
        try:
            # Check tool access
            if not await self.access_manager.check_tool_access(agent_id, tool_name):
                return ToolResponse(
                    query_id=syscall.query_id,
                    status=ResponseStatus.FORBIDDEN,
                    error=f"Access denied for tool: {tool_name}",
                )
            
            # Check if tool requires confirmation
            tool = self.tool_manager.get_tool(tool_name)
            if tool and tool.requires_confirmation:
                approved = await self.access_manager.request_confirmation(
                    agent_id=agent_id,
                    resource=f"tool:{tool_name}",
                    permission=Permission.EXECUTE,
                    description=f"Execute tool: {tool_name}",
                    justification=f"Parameters: {parameters}",
                )
                if not approved:
                    return ToolResponse(
                        query_id=syscall.query_id,
                        status=ResponseStatus.FORBIDDEN,
                        error="User denied tool execution",
                    )
            
            # Execute tool
            result = await self.tool_manager.call(agent_id, tool_name, parameters)
            
            return ToolResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.SUCCESS,
                result=result,
            )
            
        except ValueError as e:
            return ToolResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.ERROR,
                error=str(e),
            )
        except RuntimeError as e:
            return ToolResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.ERROR,
                error=str(e),
            )
        except TimeoutError as e:
            return ToolResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.TIMEOUT,
                error=str(e),
            )
        except Exception as e:
            logger.exception(f"Tool syscall failed: {e}")
            return ToolResponse(
                query_id=syscall.query_id,
                status=ResponseStatus.ERROR,
                error=str(e),
            )
    
    # Context management helpers for Round Robin scheduling
    
    async def suspend_agent(
        self,
        agent_id: str,
        messages: List[Dict[str, Any]],
        generated_tokens: str,
        tokens_count: int,
    ) -> None:
        """
        Suspend an agent's generation and create a snapshot.
        
        Called by the scheduler during Round Robin time slice expiry.
        
        Paper Reference: Section 3.4
        """
        await self.context_manager.create_snapshot(
            agent_id=agent_id,
            messages=messages,
            generated_tokens=generated_tokens,
            tokens_count=tokens_count,
        )
    
    async def resume_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """
        Resume an agent from its last snapshot.
        
        Returns the snapshot data for continuing generation.
        
        Paper Reference: Section 3.4
        """
        snapshot = await self.context_manager.restore_snapshot(agent_id)
        if snapshot:
            return {
                "messages": snapshot.messages,
                "generated_tokens": snapshot.generated_tokens,
                "tokens_count": snapshot.tokens_count,
            }
        return None
    
    def get_stats(self) -> Dict[str, Any]:
        """Get kernel statistics."""
        return {
            "is_running": self._is_running,
            "llm_manager": self.llm_manager.get_stats(),
            "scheduler": self.scheduler.get_stats(),
            "context_manager": self.context_manager.get_stats(),
            "memory_manager": self.memory_manager.get_stats(),
            "storage_manager": self.storage_manager.get_stats(),
            "tool_manager": self.tool_manager.get_stats(),
            "access_manager": self.access_manager.get_stats(),
        }
    
    @property
    def is_running(self) -> bool:
        """Check if kernel is running."""
        return self._is_running
