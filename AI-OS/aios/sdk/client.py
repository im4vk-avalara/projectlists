"""
AIOS SDK Client (Cerebrum)

Provides the client interface for agents to communicate with the AIOS kernel.
Supports both local (in-process) and remote (HTTP) connections.

Paper Reference: Section 3.2, Figure 9
Spec Reference: DataModels.md
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Union
import json

from aios.sdk.models import (
    Query,
    Response,
    ResponseStatus,
    LLMQuery,
    LLMResponse,
    MemoryQuery,
    MemoryResponse,
    MemoryOperation,
    StorageQuery,
    StorageResponse,
    StorageOperation,
    ToolQuery,
    ToolResponse,
    ToolOperation,
    Message,
)


logger = logging.getLogger(__name__)


@dataclass
class ClientConfig:
    """
    AIOS Client configuration.
    
    Attributes:
        base_url: URL for remote kernel (None for local)
        agent_id: Default agent ID for requests
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
    """
    base_url: Optional[str] = None
    agent_id: str = "default-agent"
    timeout: float = 60.0
    max_retries: int = 3


class AIOSClient:
    """
    AIOS SDK Client.
    
    Provides APIs for agents to interact with the AIOS kernel.
    Supports chat (LLM), memory, storage, and tool operations.
    
    Paper Reference: Section 3.2, Figure 9
    
    Example (remote mode):
        client = AIOSClient(base_url="http://localhost:8000", agent_id="my-agent")
        
        # Chat with LLM
        response = await client.chat([
            {"role": "user", "content": "Hello!"}
        ])
        print(response.content)
        
        # Memory operations
        await client.memory_write("my-key", {"data": "value"})
        data = await client.memory_read("my-key")
    
    Example (local mode):
        from aios.kernel.aios_kernel import AIOSKernel
        
        kernel = AIOSKernel()
        await kernel.start()
        
        client = AIOSClient(kernel=kernel, agent_id="my-agent")
        response = await client.chat([{"role": "user", "content": "Hello!"}])
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        agent_id: str = "default-agent",
        kernel: Optional[Any] = None,
        config: Optional[ClientConfig] = None,
    ):
        """
        Initialize the client.
        
        Args:
            base_url: URL for remote kernel (e.g., "http://localhost:8000")
            agent_id: Agent ID for all requests
            kernel: Local kernel instance (for in-process mode)
            config: Full client configuration
        """
        if config:
            self.config = config
        else:
            self.config = ClientConfig(base_url=base_url, agent_id=agent_id)
        
        self.kernel = kernel
        self._http_client = None
        self._is_remote = base_url is not None
        
        logger.info(
            f"AIOS Client initialized for agent '{self.config.agent_id}' "
            f"(mode: {'remote' if self._is_remote else 'local'})"
        )
    
    async def _ensure_http_client(self):
        """Ensure HTTP client is initialized."""
        if self._http_client is None and self._is_remote:
            try:
                import httpx
                self._http_client = httpx.AsyncClient(
                    base_url=self.config.base_url,
                    timeout=self.config.timeout,
                )
            except ImportError:
                raise ImportError(
                    "httpx is required for remote mode. Install with: pip install httpx"
                )
    
    async def close(self):
        """Close the client and release resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
    
    async def _send_request(self, query: Query) -> Response:
        """
        Send a request to the kernel.
        
        Routes to local kernel or remote HTTP endpoint.
        
        Paper Reference: Section 3.2 - send_request() transport
        """
        if self.kernel is not None:
            # Local mode - direct kernel call
            return await self.kernel.process_query(query)
        
        elif self._is_remote:
            # Remote mode - HTTP call
            await self._ensure_http_client()
            return await self._send_http_request(query)
        
        else:
            raise RuntimeError(
                "No kernel or base_url provided. "
                "Initialize with kernel=... or base_url=..."
            )
    
    async def _send_http_request(self, query: Query) -> Response:
        """Send HTTP request to remote kernel."""
        endpoint = self._get_endpoint(query)
        data = query.to_dict()
        
        try:
            response = await self._http_client.post(endpoint, json=data)
            response.raise_for_status()
            result = response.json()
            
            return self._parse_response(query, result)
            
        except Exception as e:
            logger.error(f"HTTP request failed: {e}")
            return Response(
                query_id=query.query_id,
                status=ResponseStatus.ERROR,
                error=str(e),
            )
    
    def _get_endpoint(self, query: Query) -> str:
        """Get HTTP endpoint for query type."""
        if isinstance(query, LLMQuery):
            return "/llm/chat"
        elif isinstance(query, MemoryQuery):
            op = query.operation.value
            return f"/memory/{op}"
        elif isinstance(query, StorageQuery):
            op = query.operation.value
            return f"/storage/{op}"
        elif isinstance(query, ToolQuery):
            op = query.operation.value
            return f"/tool/{op}"
        else:
            return "/query"
    
    def _parse_response(self, query: Query, data: Dict[str, Any]) -> Response:
        """Parse HTTP response into appropriate Response type."""
        status = ResponseStatus(data.get("status", "success"))
        
        if isinstance(query, LLMQuery):
            return LLMResponse(
                query_id=data.get("query_id", query.query_id),
                status=status,
                content=data.get("content", ""),
                finish_reason=data.get("finish_reason", "stop"),
                tool_calls=data.get("tool_calls", []),
                usage=data.get("usage", {}),
                model=data.get("model", ""),
                execution_time_ms=data.get("execution_time_ms", 0),
                error=data.get("error"),
            )
        else:
            return Response(
                query_id=data.get("query_id", query.query_id),
                status=status,
                data=data.get("data"),
                error=data.get("error"),
            )
    
    # =========================================================================
    # LLM APIs (Section 3.1)
    # =========================================================================
    
    async def chat(
        self,
        messages: List[Union[Dict[str, Any], Message]],
        model: str = "default",
        max_tokens: int = 256,
        temperature: float = 0.7,
        top_p: float = 1.0,
        stop_sequences: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
    ) -> LLMResponse:
        """
        Send a chat completion request.
        
        Paper Reference: Section 3.1 - llm_chat syscall
        
        Args:
            messages: List of chat messages
            model: Model to use
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling parameter
            stop_sequences: Stop sequences
            tools: Tool definitions for function calling
            tool_choice: Tool choice mode
            
        Returns:
            LLMResponse with generated content
        """
        # Convert dict messages to Message objects
        processed_messages = []
        for msg in messages:
            if isinstance(msg, dict):
                processed_messages.append(Message(
                    role=msg.get("role", "user"),
                    content=msg.get("content", ""),
                    name=msg.get("name"),
                    tool_calls=msg.get("tool_calls"),
                    tool_call_id=msg.get("tool_call_id"),
                ))
            else:
                processed_messages.append(msg)
        
        query = LLMQuery(
            agent_id=self.config.agent_id,
            messages=processed_messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop_sequences=stop_sequences or [],
            tools=tools or [],
            tool_choice=tool_choice,
        )
        
        response = await self._send_request(query)
        
        if isinstance(response, LLMResponse):
            return response
        else:
            return LLMResponse(
                query_id=response.query_id,
                status=response.status,
                content=response.data.get("content", "") if response.data else "",
                error=response.error,
            )
    
    async def generate(
        self,
        prompt: str,
        **kwargs,
    ) -> LLMResponse:
        """
        Generate text from a prompt (convenience method).
        
        Args:
            prompt: The input prompt
            **kwargs: Additional arguments passed to chat()
            
        Returns:
            LLMResponse with generated content
        """
        return await self.chat(
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
    
    # =========================================================================
    # Memory APIs (Section 3.5)
    # =========================================================================
    
    async def memory_read(self, key: str) -> MemoryResponse:
        """
        Read a value from agent memory.
        
        Paper Reference: Section 3.5 - memory_read syscall
        
        Args:
            key: The key to read
            
        Returns:
            MemoryResponse with the value
        """
        query = MemoryQuery(
            agent_id=self.config.agent_id,
            operation=MemoryOperation.READ,
            key=key,
        )
        response = await self._send_request(query)
        return response if isinstance(response, MemoryResponse) else MemoryResponse(
            query_id=response.query_id,
            status=response.status,
            data=response.data,
            error=response.error,
        )
    
    async def memory_write(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> MemoryResponse:
        """
        Write a value to agent memory.
        
        Paper Reference: Section 3.5 - memory_write syscall
        
        Args:
            key: The key to write
            value: The value to store
            ttl: Optional time-to-live in seconds
            
        Returns:
            MemoryResponse with status
        """
        query = MemoryQuery(
            agent_id=self.config.agent_id,
            operation=MemoryOperation.WRITE,
            key=key,
            value=value,
            ttl=ttl,
        )
        response = await self._send_request(query)
        return response if isinstance(response, MemoryResponse) else MemoryResponse(
            query_id=response.query_id,
            status=response.status,
            data=response.data,
            error=response.error,
        )
    
    async def memory_delete(self, key: str) -> MemoryResponse:
        """
        Delete a key from agent memory.
        
        Paper Reference: Section 3.5 - memory_delete syscall
        
        Args:
            key: The key to delete
            
        Returns:
            MemoryResponse with status
        """
        query = MemoryQuery(
            agent_id=self.config.agent_id,
            operation=MemoryOperation.DELETE,
            key=key,
        )
        response = await self._send_request(query)
        return response if isinstance(response, MemoryResponse) else MemoryResponse(
            query_id=response.query_id,
            status=response.status,
            error=response.error,
        )
    
    async def memory_list(self, prefix: str = "") -> MemoryResponse:
        """
        List keys in agent memory.
        
        Paper Reference: Section 3.5
        
        Args:
            prefix: Key prefix to filter by
            
        Returns:
            MemoryResponse with keys list
        """
        query = MemoryQuery(
            agent_id=self.config.agent_id,
            operation=MemoryOperation.LIST,
            prefix=prefix,
        )
        response = await self._send_request(query)
        return response if isinstance(response, MemoryResponse) else MemoryResponse(
            query_id=response.query_id,
            status=response.status,
            keys=response.data.get("keys", []) if response.data else [],
            error=response.error,
        )
    
    async def memory_search(
        self,
        query_text: str,
        limit: int = 10,
        threshold: float = 0.5,
    ) -> MemoryResponse:
        """
        Semantic search in agent memory.
        
        Paper Reference: Section 3.5 - memory_search syscall
        
        Args:
            query_text: Search query
            limit: Maximum results
            threshold: Similarity threshold
            
        Returns:
            MemoryResponse with search results
        """
        query = MemoryQuery(
            agent_id=self.config.agent_id,
            operation=MemoryOperation.SEARCH,
            search_query=query_text,
            search_limit=limit,
            search_threshold=threshold,
        )
        response = await self._send_request(query)
        return response if isinstance(response, MemoryResponse) else MemoryResponse(
            query_id=response.query_id,
            status=response.status,
            data=response.data,
            error=response.error,
        )
    
    # =========================================================================
    # Tool APIs (Section 3.7)
    # =========================================================================
    
    async def tool_call(
        self,
        tool_name: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> ToolResponse:
        """
        Call a registered tool.
        
        Paper Reference: Section 3.7 - tool_call syscall
        
        Args:
            tool_name: Name of the tool
            parameters: Tool parameters
            
        Returns:
            ToolResponse with result
        """
        query = ToolQuery(
            agent_id=self.config.agent_id,
            operation=ToolOperation.CALL,
            tool_name=tool_name,
            parameters=parameters or {},
        )
        response = await self._send_request(query)
        return response if isinstance(response, ToolResponse) else ToolResponse(
            query_id=response.query_id,
            status=response.status,
            result=response.data,
            error=response.error,
        )
    
    async def tool_list(
        self,
        category: Optional[str] = None,
    ) -> ToolResponse:
        """
        List available tools.
        
        Paper Reference: Section 3.7
        
        Args:
            category: Optional category filter
            
        Returns:
            ToolResponse with tools list
        """
        query = ToolQuery(
            agent_id=self.config.agent_id,
            operation=ToolOperation.LIST,
            category_filter=category,
        )
        response = await self._send_request(query)
        return response if isinstance(response, ToolResponse) else ToolResponse(
            query_id=response.query_id,
            status=response.status,
            data=response.data,
            error=response.error,
        )
    
    # =========================================================================
    # Context Manager
    # =========================================================================
    
    async def __aenter__(self) -> "AIOSClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

