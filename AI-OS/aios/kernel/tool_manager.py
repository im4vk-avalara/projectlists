"""
AIOS Tool Manager

Manages tool registration, validation, and execution with conflict resolution.

Paper Reference: Section 3.7
Spec Reference: Architecture.md, Syscalls.md
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
import json
import inspect

logger = logging.getLogger(__name__)


# Type alias for tool functions
ToolFunction = Callable[..., Coroutine[Any, Any, Any]]


@dataclass
class ToolParameter:
    """A tool parameter definition."""
    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    description: str = ""
    required: bool = True
    default: Any = None
    enum: Optional[List[Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        result = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "required": self.required,
        }
        if self.default is not None:
            result["default"] = self.default
        if self.enum:
            result["enum"] = self.enum
        return result


@dataclass
class Tool:
    """
    A registered tool.
    
    Paper Reference: Section 3.7
    
    Attributes:
        name: Unique tool name
        description: Tool description
        function: The async function to execute
        parameters: Parameter definitions
        category: Tool category
        requires_confirmation: Needs user approval
        max_instances: Maximum concurrent executions
        current_instances: Active execution count
    """
    name: str
    description: str
    function: ToolFunction
    parameters: List[ToolParameter] = field(default_factory=list)
    category: str = "general"
    requires_confirmation: bool = False
    max_instances: int = 4
    current_instances: int = 0
    execution_count: int = 0
    total_execution_time: float = 0.0
    
    def get_schema(self) -> Dict[str, Any]:
        """Get OpenAI-compatible tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        p.name: {
                            "type": p.type,
                            "description": p.description,
                            **({"enum": p.enum} if p.enum else {}),
                        }
                        for p in self.parameters
                    },
                    "required": [p.name for p in self.parameters if p.required],
                },
            },
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": [p.to_dict() for p in self.parameters],
            "requires_confirmation": self.requires_confirmation,
            "max_instances": self.max_instances,
            "current_instances": self.current_instances,
            "execution_count": self.execution_count,
            "avg_execution_time": (
                self.total_execution_time / self.execution_count
                if self.execution_count > 0 else 0
            ),
        }


@dataclass
class ToolExecution:
    """Record of a tool execution."""
    execution_id: str
    tool_name: str
    agent_id: str
    parameters: Dict[str, Any]
    started_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    result: Any = None
    error: Optional[str] = None
    
    @property
    def duration(self) -> float:
        if self.completed_at:
            return self.completed_at - self.started_at
        return time.time() - self.started_at


class ToolManager:
    """
    Manages tool registration and execution.
    
    Features:
    - Standardized tool loading
    - Parameter validation
    - Conflict resolution (hashmap with instance counts)
    - Concurrent execution limiting
    
    Paper Reference: Section 3.7
    
    Example:
        tool_mgr = ToolManager()
        
        # Register a tool
        @tool_mgr.register(
            name="calculator",
            description="Performs basic math",
            parameters=[
                ToolParameter("expression", "string", "Math expression"),
            ]
        )
        async def calculator(expression: str) -> str:
            return str(eval(expression))
        
        # Call tool
        result = await tool_mgr.call("agent-1", "calculator", {"expression": "2+2"})
    """
    
    def __init__(
        self,
        default_max_instances: int = 4,
        validation_enabled: bool = True,
        timeout_seconds: int = 30,
    ):
        """
        Initialize tool manager.
        
        Args:
            default_max_instances: Default max concurrent executions
            validation_enabled: Enable parameter validation
            timeout_seconds: Default execution timeout
        """
        self.default_max_instances = default_max_instances
        self.validation_enabled = validation_enabled
        self.timeout_seconds = timeout_seconds
        
        # Tool registry: name -> Tool
        self._tools: Dict[str, Tool] = {}
        self._lock = asyncio.Lock()
        
        # Execution tracking
        self._active_executions: Dict[str, ToolExecution] = {}
        self._execution_history: List[ToolExecution] = []
        
        logger.info("Tool Manager initialized")
    
    def register(
        self,
        name: str,
        description: str,
        parameters: Optional[List[ToolParameter]] = None,
        category: str = "general",
        requires_confirmation: bool = False,
        max_instances: Optional[int] = None,
    ) -> Callable[[ToolFunction], ToolFunction]:
        """
        Decorator to register a tool.
        
        Paper Reference: Section 3.7 - standardized tool loading
        
        Example:
            @tool_mgr.register("my_tool", "Does something")
            async def my_tool(param: str) -> str:
                return f"Result: {param}"
        """
        def decorator(func: ToolFunction) -> ToolFunction:
            tool = Tool(
                name=name,
                description=description,
                function=func,
                parameters=parameters or [],
                category=category,
                requires_confirmation=requires_confirmation,
                max_instances=max_instances or self.default_max_instances,
            )
            self._tools[name] = tool
            logger.info(f"Registered tool: {name}")
            return func
        return decorator
    
    async def register_tool(
        self,
        name: str,
        description: str,
        function: ToolFunction,
        parameters: Optional[List[ToolParameter]] = None,
        category: str = "general",
        requires_confirmation: bool = False,
        max_instances: Optional[int] = None,
    ) -> Tool:
        """
        Programmatically register a tool.
        
        Args:
            name: Tool name
            description: Tool description
            function: Async function to execute
            parameters: Parameter definitions
            category: Tool category
            requires_confirmation: Needs user approval
            max_instances: Max concurrent executions
            
        Returns:
            Registered Tool
        """
        async with self._lock:
            # Check for conflict
            if name in self._tools:
                existing = self._tools[name]
                logger.warning(
                    f"Tool '{name}' already exists, replacing "
                    f"(instances: {existing.current_instances})"
                )
            
            tool = Tool(
                name=name,
                description=description,
                function=function,
                parameters=parameters or [],
                category=category,
                requires_confirmation=requires_confirmation,
                max_instances=max_instances or self.default_max_instances,
            )
            self._tools[name] = tool
            
            logger.info(f"Registered tool: {name}")
            return tool
    
    async def unregister_tool(self, name: str) -> bool:
        """Unregister a tool."""
        async with self._lock:
            if name not in self._tools:
                return False
            
            tool = self._tools[name]
            if tool.current_instances > 0:
                raise RuntimeError(
                    f"Cannot unregister '{name}': {tool.current_instances} active instances"
                )
            
            del self._tools[name]
            logger.info(f"Unregistered tool: {name}")
            return True
    
    def _validate_parameters(
        self,
        tool: Tool,
        params: Dict[str, Any],
    ) -> List[str]:
        """
        Validate parameters against tool schema.
        
        Paper Reference: Section 3.7 - parameter validation
        
        Returns:
            List of validation errors (empty if valid)
        """
        errors = []
        
        # Check required parameters
        for param_def in tool.parameters:
            if param_def.required and param_def.name not in params:
                errors.append(f"Missing required parameter: {param_def.name}")
        
        # Check parameter types
        for param_name, value in params.items():
            param_def = next(
                (p for p in tool.parameters if p.name == param_name),
                None
            )
            
            if not param_def:
                errors.append(f"Unknown parameter: {param_name}")
                continue
            
            # Type checking
            expected_type = param_def.type
            if expected_type == "string" and not isinstance(value, str):
                errors.append(f"Parameter '{param_name}' should be string")
            elif expected_type == "number" and not isinstance(value, (int, float)):
                errors.append(f"Parameter '{param_name}' should be number")
            elif expected_type == "boolean" and not isinstance(value, bool):
                errors.append(f"Parameter '{param_name}' should be boolean")
            elif expected_type == "object" and not isinstance(value, dict):
                errors.append(f"Parameter '{param_name}' should be object")
            elif expected_type == "array" and not isinstance(value, list):
                errors.append(f"Parameter '{param_name}' should be array")
            
            # Enum validation
            if param_def.enum and value not in param_def.enum:
                errors.append(
                    f"Parameter '{param_name}' must be one of: {param_def.enum}"
                )
        
        return errors
    
    async def call(
        self,
        agent_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        timeout: Optional[int] = None,
    ) -> Any:
        """
        Call a tool.
        
        Paper Reference: Section 3.7 - tool_call syscall
        
        Args:
            agent_id: Calling agent
            tool_name: Tool to call
            parameters: Tool parameters
            timeout: Execution timeout
            
        Returns:
            Tool result
            
        Raises:
            ValueError: Tool not found or validation failed
            TimeoutError: Execution timeout
            RuntimeError: Max instances reached
        """
        import uuid
        
        # Get tool
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {tool_name}")
        
        # Validate parameters
        if self.validation_enabled:
            errors = self._validate_parameters(tool, parameters)
            if errors:
                raise ValueError(f"Parameter validation failed: {errors}")
        
        # Check instance limit (conflict resolution)
        async with self._lock:
            if tool.current_instances >= tool.max_instances:
                raise RuntimeError(
                    f"Tool '{tool_name}' at max instances ({tool.max_instances})"
                )
            tool.current_instances += 1
        
        # Create execution record
        execution = ToolExecution(
            execution_id=str(uuid.uuid4()),
            tool_name=tool_name,
            agent_id=agent_id,
            parameters=parameters,
        )
        self._active_executions[execution.execution_id] = execution
        
        try:
            # Execute with timeout
            result = await asyncio.wait_for(
                tool.function(**parameters),
                timeout=timeout or self.timeout_seconds,
            )
            
            execution.result = result
            execution.completed_at = time.time()
            
            # Update stats
            tool.execution_count += 1
            tool.total_execution_time += execution.duration
            
            logger.debug(
                f"Tool '{tool_name}' executed for agent '{agent_id}' "
                f"in {execution.duration:.3f}s"
            )
            
            return result
            
        except asyncio.TimeoutError:
            execution.error = "Execution timeout"
            execution.completed_at = time.time()
            raise TimeoutError(f"Tool '{tool_name}' execution timeout")
            
        except Exception as e:
            execution.error = str(e)
            execution.completed_at = time.time()
            raise
            
        finally:
            async with self._lock:
                tool.current_instances -= 1
            
            del self._active_executions[execution.execution_id]
            self._execution_history.append(execution)
            
            # Keep limited history
            if len(self._execution_history) > 1000:
                self._execution_history = self._execution_history[-1000:]
    
    def list_tools(
        self,
        category: Optional[str] = None,
    ) -> List[Tool]:
        """
        List available tools.
        
        Args:
            category: Filter by category
            
        Returns:
            List of tools
        """
        tools = list(self._tools.values())
        
        if category:
            tools = [t for t in tools if t.category == category]
        
        return tools
    
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def get_tool_schemas(
        self,
        category: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool schemas."""
        tools = self.list_tools(category)
        return [t.get_schema() for t in tools]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get tool manager statistics."""
        return {
            "registered_tools": len(self._tools),
            "active_executions": len(self._active_executions),
            "total_executions": len(self._execution_history),
            "tools": {name: t.to_dict() for name, t in self._tools.items()},
        }


# Built-in tools

async def _calculator(expression: str) -> str:
    """Simple calculator tool."""
    # Safe eval - only basic math
    allowed = set("0123456789+-*/.(). ")
    if not all(c in allowed for c in expression):
        return "Error: Invalid characters in expression"
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error: {e}"


async def _current_time() -> str:
    """Get current time."""
    from datetime import datetime
    return datetime.now().isoformat()


def register_builtin_tools(manager: ToolManager) -> None:
    """Register built-in tools."""
    import asyncio
    
    asyncio.get_event_loop().run_until_complete(
        manager.register_tool(
            name="calculator",
            description="Evaluate a mathematical expression",
            function=_calculator,
            parameters=[
                ToolParameter("expression", "string", "The math expression to evaluate"),
            ],
            category="utilities",
        )
    )
    
    asyncio.get_event_loop().run_until_complete(
        manager.register_tool(
            name="current_time",
            description="Get the current date and time",
            function=_current_time,
            parameters=[],
            category="utilities",
        )
    )

