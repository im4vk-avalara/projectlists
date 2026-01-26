"""
Base Adapter for Agent Frameworks

Provides the common interface and utilities for all framework adapters.

Paper Reference: Section 3.2, Figure 9
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union
import uuid

from aios.kernel.aios_kernel import AIOSKernel
from aios.sdk.client import AIOSClient
from aios.sdk.models import (
    Message,
    LLMQuery,
    MemoryQuery,
    ToolQuery,
    ResponseStatus,
    MemoryOperation,
)

logger = logging.getLogger(__name__)


@dataclass
class AdapterConfig:
    """
    Configuration for agent adapters.
    
    Attributes:
        max_iterations: Maximum reasoning/action cycles
        temperature: LLM temperature
        max_tokens: Max tokens per LLM call
        verbose: Enable verbose logging
        tools: Available tools for the agent
        system_prompt: Custom system prompt
        memory_enabled: Use AIOS memory manager
        stop_on_error: Stop on first error
    """
    max_iterations: int = 10
    temperature: float = 0.7
    max_tokens: int = 1024
    verbose: bool = False
    tools: List[str] = field(default_factory=list)
    system_prompt: Optional[str] = None
    memory_enabled: bool = True
    stop_on_error: bool = False


@dataclass
class AgentStep:
    """A single step in the agent's execution."""
    step_number: int
    thought: str = ""
    action: str = ""
    action_input: Any = None
    observation: str = ""
    is_final: bool = False
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step": self.step_number,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "observation": self.observation,
            "is_final": self.is_final,
            "error": self.error,
        }


@dataclass
class AgentResult:
    """Result of an agent execution."""
    success: bool
    output: str
    steps: List[AgentStep] = field(default_factory=list)
    iterations: int = 0
    total_tokens: int = 0
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "steps": [s.to_dict() for s in self.steps],
            "iterations": self.iterations,
            "total_tokens": self.total_tokens,
            "error": self.error,
            "metadata": self.metadata,
        }


class BaseAdapter(ABC):
    """
    Base class for agent framework adapters.
    
    All adapters intercept LLM and tool calls and route them through
    the AIOS kernel, enabling centralized scheduling, memory management,
    and access control.
    
    Paper Reference: Section 3.2, Figure 9
    
    Example:
        class MyAdapter(BaseAdapter):
            async def run(self, task: str) -> AgentResult:
                # Implementation
                pass
    """
    
    def __init__(
        self,
        kernel: AIOSKernel,
        agent_id: Optional[str] = None,
        config: Optional[AdapterConfig] = None,
    ):
        """
        Initialize the adapter.
        
        Args:
            kernel: AIOS Kernel instance
            agent_id: Unique agent identifier
            config: Adapter configuration
        """
        self.kernel = kernel
        self.agent_id = agent_id or f"agent-{uuid.uuid4().hex[:8]}"
        self.config = config or AdapterConfig()
        
        # Create AIOS client for this agent
        self.client = AIOSClient(kernel=kernel, agent_id=self.agent_id)
        
        # Execution state
        self._steps: List[AgentStep] = []
        self._total_tokens = 0
        
        logger.debug(f"Adapter initialized for agent '{self.agent_id}'")
    
    @abstractmethod
    async def run(self, task: str, **kwargs) -> AgentResult:
        """
        Execute the agent on a task.
        
        Args:
            task: The task/query to execute
            **kwargs: Additional arguments
            
        Returns:
            AgentResult with output and execution trace
        """
        pass
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Send a chat request through AIOS.
        
        Args:
            messages: Conversation messages
            tools: Optional tool definitions
            **kwargs: Additional LLM parameters
            
        Returns:
            LLM response dict
        """
        # Convert to Message objects
        msg_objects = [
            Message(role=m["role"], content=m.get("content", ""))
            for m in messages
        ]
        
        response = await self.client.chat(
            messages=[m.to_dict() for m in msg_objects],
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
            tools=tools,
        )
        
        # Track tokens
        if hasattr(response, "usage") and response.usage:
            self._total_tokens += response.usage.get("total_tokens", 0)
        
        return {
            "content": response.content,
            "tool_calls": response.tool_calls,
            "finish_reason": response.finish_reason,
        }
    
    async def call_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> Any:
        """
        Call a tool through AIOS.
        
        Args:
            tool_name: Name of the tool
            parameters: Tool parameters
            
        Returns:
            Tool result
        """
        response = await self.client.tool_call(tool_name, parameters)
        
        if response.status == ResponseStatus.SUCCESS:
            return response.result
        else:
            raise RuntimeError(f"Tool call failed: {response.error}")
    
    async def save_memory(self, key: str, value: Any) -> None:
        """Save data to agent memory."""
        if self.config.memory_enabled:
            await self.client.memory_write(key, value)
    
    async def load_memory(self, key: str) -> Optional[Any]:
        """Load data from agent memory."""
        if not self.config.memory_enabled:
            return None
        
        response = await self.client.memory_read(key)
        if response.status == ResponseStatus.SUCCESS:
            return response.data.get("value")
        return None
    
    async def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools."""
        response = await self.client.tool_list()
        if response.status == ResponseStatus.SUCCESS:
            return response.tools
        return []
    
    def _add_step(self, step: AgentStep) -> None:
        """Add a step to the execution trace."""
        self._steps.append(step)
        
        if self.config.verbose:
            logger.info(f"Step {step.step_number}: {step.action}")
            if step.thought:
                logger.info(f"  Thought: {step.thought}")
            if step.observation:
                logger.info(f"  Observation: {step.observation[:100]}...")
    
    def _reset(self) -> None:
        """Reset execution state."""
        self._steps = []
        self._total_tokens = 0
    
    def _create_result(
        self,
        success: bool,
        output: str,
        error: Optional[str] = None,
    ) -> AgentResult:
        """Create an agent result."""
        return AgentResult(
            success=success,
            output=output,
            steps=self._steps.copy(),
            iterations=len(self._steps),
            total_tokens=self._total_tokens,
            error=error,
        )

