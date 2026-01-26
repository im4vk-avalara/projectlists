"""
Pytest Configuration and Fixtures

Provides shared fixtures for AIOS tests.
"""

import asyncio
import pytest
from typing import AsyncGenerator, Generator

from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
from aios.sdk.client import AIOSClient
from aios.core.adapters.mock_adapter import MockAdapter


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def kernel_config() -> KernelConfig:
    """Create test kernel configuration."""
    return KernelConfig(
        host="127.0.0.1",
        port=8001,  # Use different port for tests
        log_level="DEBUG",
        scheduling_strategy="fifo",
        llm_cores=[],  # Will use mock by default
    )


@pytest.fixture
async def kernel(kernel_config: KernelConfig) -> AsyncGenerator[AIOSKernel, None]:
    """Create and start a test kernel."""
    k = AIOSKernel(config=kernel_config)
    await k.start()
    yield k
    await k.stop()


@pytest.fixture
async def client(kernel: AIOSKernel) -> AsyncGenerator[AIOSClient, None]:
    """Create a test client connected to the kernel."""
    c = AIOSClient(kernel=kernel, agent_id="test-agent")
    yield c
    await c.close()


@pytest.fixture
def mock_adapter() -> MockAdapter:
    """Create a mock LLM adapter for testing."""
    return MockAdapter(
        model="test-model",
        default_response="Test response from mock LLM",
        latency_ms=10,
    )

