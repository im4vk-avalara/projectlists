"""
LLM Core Manager

Manages LLM cores as abstracted resources, similar to how an OS manages CPU cores.
Each LLM core can use different backends (OpenAI, HuggingFace, local models).

Paper Reference: Section 3.1 - "LLM cores abstract LLM as CPU cores"
Figure 2 shows "LLM Core(s)" as a kernel module
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type
from enum import Enum

from aios.core.adapters.base import (
    LLMBackend,
    LLMGenerationConfig,
    LLMGenerationResult,
    LLMMessage,
)
from aios.core.adapters.openai_adapter import OpenAIAdapter
from aios.core.adapters.mock_adapter import MockAdapter
from aios.core.adapters.alfa_adapter import AlfaAdapter


logger = logging.getLogger(__name__)


class CoreStatus(str, Enum):
    """Status of an LLM core."""
    IDLE = "idle"
    BUSY = "busy"
    INITIALIZING = "initializing"
    ERROR = "error"
    SHUTDOWN = "shutdown"


@dataclass
class LLMCore:
    """
    Represents a single LLM inference core.
    
    Similar to how CPU cores handle compute tasks, LLM cores handle
    text generation tasks. Multiple cores can run concurrently.
    
    Paper Reference: Section 3.1, Figure 2
    
    Attributes:
        name: Unique identifier for this core
        backend: The LLM backend adapter
        status: Current status of the core
        current_agent_id: ID of agent currently using this core
        request_count: Number of requests processed
    """
    name: str
    backend: LLMBackend
    status: CoreStatus = CoreStatus.IDLE
    current_agent_id: Optional[str] = None
    request_count: int = 0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    
    async def initialize(self) -> None:
        """Initialize the core and its backend."""
        self.status = CoreStatus.INITIALIZING
        try:
            await self.backend.initialize()
            self.status = CoreStatus.IDLE
            logger.info(f"LLM Core '{self.name}' initialized with {self.backend}")
        except Exception as e:
            self.status = CoreStatus.ERROR
            logger.error(f"Failed to initialize LLM Core '{self.name}': {e}")
            raise
    
    async def shutdown(self) -> None:
        """Shutdown the core and its backend."""
        try:
            await self.backend.shutdown()
        finally:
            self.status = CoreStatus.SHUTDOWN
            logger.info(f"LLM Core '{self.name}' shut down")
    
    async def execute(
        self,
        agent_id: str,
        messages: List[LLMMessage],
        config: Optional[LLMGenerationConfig] = None,
    ) -> LLMGenerationResult:
        """
        Execute an LLM request on this core.
        
        Args:
            agent_id: ID of the requesting agent
            messages: Chat messages to process
            config: Generation configuration
            
        Returns:
            LLMGenerationResult with the response
        """
        async with self._lock:
            if self.status != CoreStatus.IDLE:
                raise RuntimeError(f"Core '{self.name}' is not available (status: {self.status})")
            
            self.status = CoreStatus.BUSY
            self.current_agent_id = agent_id
        
        try:
            result = await self.backend.chat(messages, config)
            self.request_count += 1
            return result
        finally:
            async with self._lock:
                self.status = CoreStatus.IDLE
                self.current_agent_id = None
    
    @property
    def is_available(self) -> bool:
        """Check if this core is available for new requests."""
        return self.status == CoreStatus.IDLE


# Backend registry for dynamic instantiation
BACKEND_REGISTRY: Dict[str, Type[LLMBackend]] = {
    "openai": OpenAIAdapter,
    "mock": MockAdapter,
    "alfa": AlfaAdapter,
}


def register_backend(name: str, backend_class: Type[LLMBackend]) -> None:
    """Register a new backend type."""
    BACKEND_REGISTRY[name] = backend_class


class LLMCoreManager:
    """
    Manages multiple LLM cores for the AIOS kernel.
    
    Provides core allocation, request routing, and lifecycle management.
    
    Paper Reference: Section 3.1 - LLM cores are treated as resources
    
    Example:
        manager = LLMCoreManager()
        await manager.add_core("core-0", "openai", "gpt-4o-mini")
        await manager.add_core("core-1", "mock", "mock-model")
        
        result = await manager.execute(
            agent_id="agent-001",
            messages=[LLMMessage(role="user", content="Hello!")],
        )
    """
    
    def __init__(self):
        """Initialize the core manager."""
        self.cores: Dict[str, LLMCore] = {}
        self._core_lock = asyncio.Lock()
        self._request_queue: asyncio.Queue = asyncio.Queue()
        logger.info("LLM Core Manager initialized")
    
    async def add_core(
        self,
        name: str,
        backend_type: str,
        model: str,
        **backend_kwargs
    ) -> LLMCore:
        """
        Add a new LLM core.
        
        Args:
            name: Unique name for the core
            backend_type: Backend type (openai, mock, huggingface, etc.)
            model: Model identifier
            **backend_kwargs: Backend-specific configuration
            
        Returns:
            The created LLMCore
        """
        if name in self.cores:
            raise ValueError(f"Core '{name}' already exists")
        
        if backend_type not in BACKEND_REGISTRY:
            raise ValueError(
                f"Unknown backend type '{backend_type}'. "
                f"Available: {list(BACKEND_REGISTRY.keys())}"
            )
        
        # Create backend
        backend_class = BACKEND_REGISTRY[backend_type]
        backend = backend_class(model=model, **backend_kwargs)
        
        # Create core
        core = LLMCore(name=name, backend=backend)
        await core.initialize()
        
        self.cores[name] = core
        logger.info(f"Added LLM Core '{name}' with backend '{backend_type}' model '{model}'")
        
        return core
    
    async def remove_core(self, name: str) -> None:
        """Remove and shutdown a core."""
        if name not in self.cores:
            raise ValueError(f"Core '{name}' not found")
        
        core = self.cores.pop(name)
        await core.shutdown()
        logger.info(f"Removed LLM Core '{name}'")
    
    async def shutdown(self) -> None:
        """Shutdown all cores."""
        for name, core in list(self.cores.items()):
            try:
                await core.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down core '{name}': {e}")
        self.cores.clear()
        logger.info("LLM Core Manager shut down")
    
    def get_available_core(self) -> Optional[LLMCore]:
        """Get an available core for processing."""
        for core in self.cores.values():
            if core.is_available:
                return core
        return None
    
    async def wait_for_core(self, timeout: Optional[float] = None) -> LLMCore:
        """
        Wait for an available core.
        
        Args:
            timeout: Maximum seconds to wait
            
        Returns:
            An available LLMCore
            
        Raises:
            TimeoutError: If no core becomes available within timeout
        """
        start_time = asyncio.get_event_loop().time()
        
        while True:
            core = self.get_available_core()
            if core:
                return core
            
            if timeout:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    raise TimeoutError("No LLM core available within timeout")
            
            await asyncio.sleep(0.01)  # Brief sleep before retry
    
    async def execute(
        self,
        agent_id: str,
        messages: List[LLMMessage],
        config: Optional[LLMGenerationConfig] = None,
        core_name: Optional[str] = None,
        timeout: Optional[float] = 60.0,
    ) -> LLMGenerationResult:
        """
        Execute an LLM request.
        
        Routes the request to an available core or specified core.
        
        Args:
            agent_id: ID of the requesting agent
            messages: Chat messages to process
            config: Generation configuration
            core_name: Specific core to use (optional)
            timeout: Maximum seconds to wait for a core
            
        Returns:
            LLMGenerationResult with the response
        """
        # Use specific core if requested
        if core_name:
            if core_name not in self.cores:
                raise ValueError(f"Core '{core_name}' not found")
            core = self.cores[core_name]
            if not core.is_available:
                raise RuntimeError(f"Core '{core_name}' is busy")
        else:
            # Wait for any available core
            core = await self.wait_for_core(timeout=timeout)
        
        return await core.execute(agent_id, messages, config)
    
    @property
    def core_count(self) -> int:
        """Number of cores."""
        return len(self.cores)
    
    @property
    def available_core_count(self) -> int:
        """Number of available cores."""
        return sum(1 for c in self.cores.values() if c.is_available)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get manager statistics."""
        return {
            "total_cores": self.core_count,
            "available_cores": self.available_core_count,
            "cores": {
                name: {
                    "status": core.status.value,
                    "model": core.backend.model,
                    "request_count": core.request_count,
                    "current_agent": core.current_agent_id,
                }
                for name, core in self.cores.items()
            }
        }

