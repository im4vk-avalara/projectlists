# AIOS: LLM Agent Operating System

A kernel-level architecture for managing LLM-based agents, implementing the research paper "AIOS: LLM Agent Operating System" (arXiv:2403.16971).

## Overview

AIOS provides:
- **LLM Core Abstraction** - Unified interface for different LLM backends (Alfa, OpenAI, local models)
- **Agent Scheduler** - FIFO and Round Robin scheduling with context switching
- **Memory Manager** - Runtime memory with LRU-K eviction
- **Storage Manager** - Persistent storage with versioning and semantic search
- **Tool Manager** - Standardized tool registration and execution
- **Access Manager** - Privilege-based access control

## Quick Start

### Installation

```bash
# Install from source
pip install -e .

# With OpenAI support
pip install -e ".[openai]"

# With all dependencies
pip install -e ".[all]"

# For development
pip install -e ".[dev]"
```

### Configuration

#### Using Alfa (LLM Proxy) - Recommended

Set up your environment variables:

```bash
# Copy example env file
cp config/example.env .env

# Edit .env with your Alfa credentials
ALFA_CLAIM=your-project-uuid  # From Alfa onboarding
ALFA_ENV=qa                    # or prod
```

Update `config/default.yaml` to use Alfa:

```yaml
llm_cores:
  - name: "core-0"
    backend: "alfa"
    model: "claude-4-sonnet"  # or gpt-5, gpt-4o, gpt-4o-mini
    alfa_env: "qa"
```

Available Alfa models:
- `claude-4-sonnet` - Claude 4 Sonnet
- `claude-3-5-sonnet` - Claude 3.5 Sonnet
- `gpt-5` - GPT-5
- `gpt-4o` - GPT-4o
- `gpt-4o-mini` - GPT-4o Mini

### Running the Server

```bash
# Start AIOS server (uses mock LLM by default)
python -m aios

# With custom config
python -m aios --config config/default.yaml --port 8000
```

### Using the SDK

```python
import asyncio
from aios import AIOSClient
from aios.kernel.aios_kernel import AIOSKernel

async def main():
    # Option 1: Local kernel (in-process)
    kernel = AIOSKernel()
    await kernel.start()
    
    client = AIOSClient(kernel=kernel, agent_id="my-agent")
    
    # Chat with LLM
    response = await client.chat([
        {"role": "user", "content": "Hello!"}
    ])
    print(response.content)
    
    # Memory operations
    await client.memory_write("key", {"data": "value"})
    data = await client.memory_read("key")
    
    await kernel.stop()

asyncio.run(main())
```

### HTTP API

When the server is running:

```bash
# Health check
curl http://localhost:8000/health

# Chat completion
curl -X POST http://localhost:8000/llm/chat \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'

# Memory write
curl -X POST http://localhost:8000/memory/write \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "my-agent",
    "key": "test",
    "value": {"data": 123}
  }'
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Agent Frameworks                      │
│         (ReAct, Reflexion, AutoGen, MetaGPT)            │
├─────────────────────────────────────────────────────────┤
│                      AIOS SDK                            │
│    (Query/Response, send_request, Client APIs)          │
├─────────────────────────────────────────────────────────┤
│                     AIOS Kernel                          │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │  LLM Core   │  │  Scheduler   │  │Context Manager│   │
│  │  Manager    │  │  (FIFO/RR)   │  │  (Snapshot)   │   │
│  └─────────────┘  └──────────────┘  └───────────────┘   │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐   │
│  │   Memory    │  │   Storage    │  │     Tool      │   │
│  │   Manager   │  │   Manager    │  │    Manager    │   │
│  └─────────────┘  └──────────────┘  └───────────────┘   │
│  ┌─────────────┐                                        │
│  │   Access    │                                        │
│  │   Manager   │                                        │
│  └─────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

## Configuration

Edit `config/default.yaml`:

```yaml
kernel:
  host: "0.0.0.0"
  port: 8000

llm_cores:
  - name: "core-0"
    backend: "openai"
    model: "gpt-4o-mini"

scheduler:
  strategy: "round_robin"  # or "fifo"
```

Set your API key:
```bash
export OPENAI_API_KEY=sk-your-key-here
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=aios

# Run specific tests
pytest tests/test_scheduler.py -v
```

## Project Structure

```
AI-OS/
├── aios/
│   ├── __init__.py          # Package exports
│   ├── __main__.py           # CLI entry point
│   ├── core/                  # LLM Core module
│   │   ├── adapters/         # LLM backends
│   │   └── llm.py            # Core manager
│   ├── kernel/               # Kernel modules
│   │   ├── scheduler.py      # FIFO/RR scheduler
│   │   ├── syscall.py        # Syscall definitions
│   │   └── aios_kernel.py    # Main kernel
│   ├── sdk/                  # SDK for agents
│   │   ├── models.py         # Query/Response
│   │   └── client.py         # SDK client
│   └── server/               # HTTP server
│       └── app.py            # FastAPI app
├── tests/                    # Test suite
├── examples/                 # Example agents
├── config/                   # Configuration
└── docs/                     # Spec Pack docs
```

## Paper Reference

This implementation follows:
- **arXiv:2403.16971v5** - AIOS: LLM Agent Operating System

Key sections implemented:
- Section 3.1: LLM Core abstraction
- Section 3.3: Agent scheduling (FIFO/Round Robin)
- Section 3.4: Context management (text-based)
- Section 3.5: Memory management
- Section 3.6: Storage management
- Section 3.7: Tool management
- Section 3.8: Access control

## License

MIT License

