"""
AIOS FastAPI Application

HTTP server exposing the AIOS kernel APIs.

Paper Reference: Section 3.2 (SDK transport)
Spec Reference: Syscalls.md, DataModels.md
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
import os

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
from aios.sdk.models import (
    LLMQuery,
    LLMResponse,
    MemoryQuery,
    MemoryResponse,
    MemoryOperation,
    Message,
    ResponseStatus,
)


logger = logging.getLogger(__name__)


# =============================================================================
# Pydantic Models for API
# =============================================================================

class MessageModel(BaseModel):
    """Chat message for API."""
    role: str = "user"
    content: str
    name: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class LLMChatRequest(BaseModel):
    """Request for LLM chat endpoint."""
    agent_id: str
    messages: List[MessageModel]
    model: str = "default"
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 1.0
    stop_sequences: List[str] = Field(default_factory=list)
    stream: bool = False
    tools: List[Dict[str, Any]] = Field(default_factory=list)
    tool_choice: Optional[str] = None


class LLMChatResponse(BaseModel):
    """Response from LLM chat endpoint."""
    query_id: str
    status: str
    content: str = ""
    finish_reason: str = "stop"
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    usage: Dict[str, int] = Field(default_factory=dict)
    model: str = ""
    execution_time_ms: float = 0.0
    error: Optional[str] = None


class MemoryReadRequest(BaseModel):
    """Request for memory read."""
    agent_id: str
    key: str


class MemoryWriteRequest(BaseModel):
    """Request for memory write."""
    agent_id: str
    key: str
    value: Any
    ttl: Optional[int] = None


class MemoryDeleteRequest(BaseModel):
    """Request for memory delete."""
    agent_id: str
    key: str


class MemoryListRequest(BaseModel):
    """Request for memory list."""
    agent_id: str
    prefix: str = ""


class MemoryResponse(BaseModel):
    """Response from memory operations."""
    query_id: str
    status: str
    data: Optional[Any] = None
    keys: List[str] = Field(default_factory=list)
    error: Optional[str] = None


class StatsResponse(BaseModel):
    """Response for stats endpoint."""
    is_running: bool
    llm_manager: Dict[str, Any]
    scheduler: Dict[str, Any]


class HealthResponse(BaseModel):
    """Response for health endpoint."""
    status: str
    version: str


# =============================================================================
# Application Factory
# =============================================================================

def create_app(kernel: Optional[AIOSKernel] = None) -> FastAPI:
    """
    Create FastAPI application.
    
    Args:
        kernel: Optional pre-created kernel instance
        
    Returns:
        Configured FastAPI app
    """
    # Create or use provided kernel
    _kernel = kernel
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """Manage kernel lifecycle."""
        nonlocal _kernel
        
        if _kernel is None:
            # Load config if available
            config_path = os.getenv("AIOS_CONFIG", "config/default.yaml")
            if os.path.exists(config_path):
                _kernel = AIOSKernel(KernelConfig.from_yaml(config_path))
            else:
                _kernel = AIOSKernel()
        
        # Store in app state
        app.state.kernel = _kernel
        
        # Start kernel
        await _kernel.start()
        logger.info("AIOS Server started")
        
        yield
        
        # Stop kernel
        await _kernel.stop()
        logger.info("AIOS Server stopped")
    
    # Create app
    app = FastAPI(
        title="AIOS - LLM Agent Operating System",
        description="Kernel API for managing LLM-based agents",
        version="0.1.0",
        lifespan=lifespan,
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # ==========================================================================
    # Routes
    # ==========================================================================
    
    @app.get("/health", response_model=HealthResponse)
    async def health():
        """Health check endpoint."""
        return HealthResponse(status="healthy", version="0.1.0")
    
    @app.get("/stats", response_model=StatsResponse)
    async def stats(request: Request):
        """Get kernel statistics."""
        kernel: AIOSKernel = request.app.state.kernel
        return kernel.get_stats()
    
    # --------------------------------------------------------------------------
    # LLM Endpoints (Section 3.1)
    # --------------------------------------------------------------------------
    
    @app.post("/llm/chat", response_model=LLMChatResponse)
    async def llm_chat(request_data: LLMChatRequest, request: Request):
        """
        Send a chat completion request.
        
        Paper Reference: Section 3.1 - llm_chat syscall
        """
        kernel: AIOSKernel = request.app.state.kernel
        
        # Convert to SDK query
        messages = [
            Message(
                role=msg.role,
                content=msg.content,
                name=msg.name,
                tool_calls=msg.tool_calls,
                tool_call_id=msg.tool_call_id,
            )
            for msg in request_data.messages
        ]
        
        query = LLMQuery(
            agent_id=request_data.agent_id,
            messages=messages,
            model=request_data.model,
            max_tokens=request_data.max_tokens,
            temperature=request_data.temperature,
            top_p=request_data.top_p,
            stop_sequences=request_data.stop_sequences,
            stream=request_data.stream,
            tools=request_data.tools,
            tool_choice=request_data.tool_choice,
        )
        
        # Process through kernel
        response = await kernel.process_query(query)
        
        if response.status == ResponseStatus.ERROR:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=response.error or "LLM request failed",
            )
        
        # Build response
        llm_response = response if isinstance(response, LLMResponse) else None
        
        return LLMChatResponse(
            query_id=response.query_id,
            status=response.status.value if hasattr(response.status, "value") else str(response.status),
            content=llm_response.content if llm_response else "",
            finish_reason=llm_response.finish_reason if llm_response else "stop",
            tool_calls=llm_response.tool_calls if llm_response else [],
            usage=llm_response.usage if llm_response else {},
            model=llm_response.model if llm_response else "",
            execution_time_ms=response.execution_time_ms,
            error=response.error,
        )
    
    # --------------------------------------------------------------------------
    # Memory Endpoints (Section 3.5)
    # --------------------------------------------------------------------------
    
    @app.post("/memory/read")
    async def memory_read(request_data: MemoryReadRequest, request: Request):
        """Read from agent memory."""
        kernel: AIOSKernel = request.app.state.kernel
        
        from aios.sdk.models import MemoryQuery as SDKMemoryQuery, MemoryOperation
        
        query = SDKMemoryQuery(
            agent_id=request_data.agent_id,
            operation=MemoryOperation.READ,
            key=request_data.key,
        )
        
        response = await kernel.process_query(query)
        
        return {
            "query_id": response.query_id,
            "status": response.status.value if hasattr(response.status, "value") else str(response.status),
            "data": response.data,
            "error": response.error,
        }
    
    @app.post("/memory/write")
    async def memory_write(request_data: MemoryWriteRequest, request: Request):
        """Write to agent memory."""
        kernel: AIOSKernel = request.app.state.kernel
        
        from aios.sdk.models import MemoryQuery as SDKMemoryQuery, MemoryOperation
        
        query = SDKMemoryQuery(
            agent_id=request_data.agent_id,
            operation=MemoryOperation.WRITE,
            key=request_data.key,
            value=request_data.value,
            ttl=request_data.ttl,
        )
        
        response = await kernel.process_query(query)
        
        return {
            "query_id": response.query_id,
            "status": response.status.value if hasattr(response.status, "value") else str(response.status),
            "data": response.data,
            "error": response.error,
        }
    
    @app.post("/memory/delete")
    async def memory_delete(request_data: MemoryDeleteRequest, request: Request):
        """Delete from agent memory."""
        kernel: AIOSKernel = request.app.state.kernel
        
        from aios.sdk.models import MemoryQuery as SDKMemoryQuery, MemoryOperation
        
        query = SDKMemoryQuery(
            agent_id=request_data.agent_id,
            operation=MemoryOperation.DELETE,
            key=request_data.key,
        )
        
        response = await kernel.process_query(query)
        
        return {
            "query_id": response.query_id,
            "status": response.status.value if hasattr(response.status, "value") else str(response.status),
            "error": response.error,
        }
    
    @app.post("/memory/list")
    async def memory_list(request_data: MemoryListRequest, request: Request):
        """List keys in agent memory."""
        kernel: AIOSKernel = request.app.state.kernel
        
        from aios.sdk.models import MemoryQuery as SDKMemoryQuery, MemoryOperation
        
        query = SDKMemoryQuery(
            agent_id=request_data.agent_id,
            operation=MemoryOperation.LIST,
            prefix=request_data.prefix,
        )
        
        response = await kernel.process_query(query)
        
        return {
            "query_id": response.query_id,
            "status": response.status.value if hasattr(response.status, "value") else str(response.status),
            "keys": getattr(response, "keys", []),
            "error": response.error,
        }
    
    return app


class AIOSServer:
    """
    AIOS HTTP Server wrapper.
    
    Provides convenient methods for running the server.
    
    Example:
        server = AIOSServer()
        await server.start()  # Non-blocking
        # or
        server.run()  # Blocking
    """
    
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        kernel: Optional[AIOSKernel] = None,
    ):
        """
        Initialize server.
        
        Args:
            host: Host to bind to
            port: Port to listen on
            kernel: Optional pre-created kernel
        """
        self.host = host
        self.port = port
        self.kernel = kernel
        self.app = create_app(kernel)
        self._server = None
    
    def run(self) -> None:
        """Run server (blocking)."""
        import uvicorn
        uvicorn.run(self.app, host=self.host, port=self.port)
    
    async def start(self) -> None:
        """Start server (non-blocking)."""
        import uvicorn
        
        config = uvicorn.Config(self.app, host=self.host, port=self.port)
        self._server = uvicorn.Server(config)
        await self._server.serve()
    
    async def stop(self) -> None:
        """Stop server."""
        if self._server:
            self._server.should_exit = True

