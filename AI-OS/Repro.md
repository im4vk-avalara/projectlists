# AIOS Reproduction Guide

Commands to run demos, tests, and benchmarks for the AIOS implementation.

---

## Quick Start

### Prerequisites
```bash
# Python 3.10+ required
python --version  # Should be 3.10 or higher

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Environment Setup
```bash
# Copy example config
cp config/example.env .env

# Edit with your API keys
# OPENAI_API_KEY=sk-...
# For local models, no API key needed
```

---

## Running the Kernel

### Run M2 Features Demo
```bash
# Demonstrates all Milestone 2 kernel features:
# - Context Manager (snapshots)
# - Memory Manager (LRU-K)
# - Storage Manager (versioning)
# - Tool Manager (registration)
# - Access Manager (privileges)
python examples/demo_m2_features.py
```

### Run Full Kernel Demo (M3)
```bash
# Complete AIOS kernel with all managers integrated:
# - LLM Core interaction
# - Memory operations with LRU-K
# - Storage with versioning
# - Tool execution with validation
# - Access control enforcement
# - Context management for RR scheduling
# - Multi-agent concurrent execution
python examples/demo_full_kernel.py
```

### Run Agent Adapters Demo (M4)
```bash
# Demonstrates agent framework adapters:
# - ReAct (Reasoning + Acting)
# - Reflexion (Self-reflection)
# - AutoGen (Multi-agent conversation)
# - Interpreter (Code execution)
python examples/demo_adapters.py
```

### Run Evaluation Framework Demo (M5)
```bash
# Demonstrates evaluation capabilities:
# - Metrics collection
# - Workload execution
# - FIFO vs Round Robin comparison
# - Scaling evaluation
# - Benchmark suite execution
python examples/demo_evaluation.py
```

### Start AIOS Kernel Server
```bash
# Default: localhost:8000
python -m aios.kernel.server

# With custom config
python -m aios.kernel.server --config config/development.yaml

# With specific port
python -m aios.kernel.server --port 8080

# With debug logging
AIOS_LOG_LEVEL=DEBUG python -m aios.kernel.server
```

### Verify Kernel is Running
```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {"status": "healthy", "modules": ["llm", "scheduler", "context", "memory", "storage", "tool", "access"]}
```

---

## Running Example Agents

### Travel Agent (Figure 1)
```bash
# Start kernel first (in separate terminal)
python -m aios.kernel.server

# Run travel agent demo
python -m aios.agents.travel_agent

# With custom query
python -m aios.agents.travel_agent --query "Plan a trip from SF to Tokyo"
```

### Other Agents
```bash
# Recommendation agent
python -m aios.agents.rec_agent

# Math agent
python -m aios.agents.math_agent --problem "Solve x^2 + 2x - 3 = 0"

# Coding agent
python -m aios.agents.coding_agent --task "Write a function to sort a list"

# Narrative agent
python -m aios.agents.narrative_agent --prompt "Write a short story about AI"
```

### Multi-Agent Demo
```bash
# Run 5 agents concurrently
python -m aios.demos.multi_agent --num-agents 5

# With specific scheduling strategy
python -m aios.demos.multi_agent --num-agents 10 --strategy round_robin
```

---

## Running Tests

### All Tests
```bash
pytest tests/ -v
```

### Unit Tests Only
```bash
pytest tests/unit/ -v

# Specific module
pytest tests/unit/test_scheduler.py -v
pytest tests/unit/test_memory_manager.py -v
pytest tests/unit/test_context_manager.py -v
```

### Integration Tests
```bash
pytest tests/integration/ -v

# With coverage
pytest tests/integration/ --cov=aios --cov-report=html
```

### Regression Tests
```bash
# Context interruption similarity tests
pytest tests/regression/test_context_similarity.py -v
```

### Quick Smoke Test
```bash
# Run minimal test suite (< 1 minute)
pytest tests/ -v -m "smoke"
```

---

## Benchmarks and Evaluation

### Throughput and Latency (Figures 6-7)
```bash
# Run on default model (mock for quick test)
python -m aios.evaluation.harness --benchmark throughput_latency

# With specific model
python -m aios.evaluation.harness --benchmark throughput_latency --model llama-3.1-8b

# With specific frameworks
python -m aios.evaluation.harness --benchmark throughput_latency \
    --frameworks react,reflexion,autogen
```

### Scaling Analysis (Figure 8)
```bash
# Quick scaling test (fewer agents)
python -m aios.evaluation.harness --benchmark scaling --agent-counts 10,25,50

# Full scaling test (matches paper)
python -m aios.evaluation.harness --benchmark scaling --agent-counts 250,500,750,1000,2000
```

### FIFO vs Round Robin Comparison
```bash
python -m aios.evaluation.harness --benchmark scheduling_comparison \
    --strategies fifo,round_robin \
    --agent-counts 50,100,200
```

### Generate Plots
```bash
# After running benchmarks, generate plots
python -m aios.evaluation.plotting.generate_all

# Specific plot
python -m aios.evaluation.plotting.throughput_latency --input results/throughput.json
python -m aios.evaluation.plotting.scaling --input results/scaling.json
```

---

## Benchmark Suite (Figures 10-15)

### HumanEval
```bash
python -m aios.evaluation.benchmarks.humaneval --num-problems 50
```

### MINT
```bash
python -m aios.evaluation.benchmarks.mint --num-tasks 20
```

### GAIA
```bash
python -m aios.evaluation.benchmarks.gaia --subset validation
```

### SWE-Bench-Lite
```bash
python -m aios.evaluation.benchmarks.swebench --num-issues 10
```

---

## Framework Adapters

### ReAct
```bash
# Run ReAct agent through AIOS
python -m aios.adapters.react --task "Research and summarize AI news"
```

### AutoGen
```bash
# Run AutoGen multi-agent conversation through AIOS
python -m aios.adapters.autogen --scenario coding_task
```

### Open-Interpreter
```bash
# Run Open-Interpreter through AIOS
python -m aios.adapters.open_interpreter --command "List files in current directory"
```

### MetaGPT
```bash
# Run MetaGPT through AIOS
python -m aios.adapters.metagpt --project "Simple calculator app"
```

---

## Configuration Options

### Scheduling Strategy
```yaml
# config/development.yaml
scheduler:
  strategy: fifo  # or round_robin
  round_robin:
    tokens_per_slice: 50
    max_time_ms: 500
```

### Memory Settings
```yaml
memory_manager:
  eviction_policy: lru-k
  lru_k_value: 2
  memory_limit_mb: 512
  swap_threshold_percent: 75
```

### LLM Backends
```yaml
llm_cores:
  - name: core-0
    backend: openai
    model: gpt-4
  - name: core-1
    backend: huggingface
    model: meta-llama/Llama-2-7b
```

---

## Docker (Optional)

### Build Image
```bash
docker build -t aios:latest .
```

### Run Container
```bash
# Start kernel
docker run -p 8000:8000 -e OPENAI_API_KEY=$OPENAI_API_KEY aios:latest

# Run with local models (GPU)
docker run --gpus all -p 8000:8000 aios:latest --config config/local_models.yaml
```

---

## Troubleshooting

### Common Issues

**Port already in use:**
```bash
# Find and kill process on port 8000
lsof -i :8000
kill -9 <PID>
```

**OpenAI API errors:**
```bash
# Verify API key
echo $OPENAI_API_KEY

# Test API directly
curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
```

**Memory issues with large models:**
```bash
# Reduce memory limit
export AIOS_MEMORY_LIMIT_MB=256

# Use smaller model
python -m aios.kernel.server --model mistral-7b-instruct
```

### Debug Mode
```bash
# Full debug logging
AIOS_LOG_LEVEL=DEBUG python -m aios.kernel.server

# Log to file
python -m aios.kernel.server --log-file aios.log
```

---

## Example Output

### Successful Agent Run
```
$ python -m aios.agents.travel_agent
[INFO] Connecting to AIOS kernel at localhost:8000
[INFO] Agent travel-001 initialized
[INFO] Processing query: "Plan a trip from SF to NYC"
[INFO] Step 1/7: Preference Retrieval... done (1.2s)
[INFO] Step 2/7: Flight Recommendation... done (2.1s)
...
[INFO] Step 7/7: Reviews and Tips... done (1.5s)
[SUCCESS] Travel plan completed in 12.3s total
```

### Benchmark Output
```
$ python -m aios.evaluation.harness --benchmark throughput_latency
[INFO] Running throughput/latency benchmark
[INFO] Frameworks: ReAct, Reflexion, AutoGen, Open-Interpreter, MetaGPT
[INFO] Model: llama-3.1-8b
[INFO] Running with AIOS... done (120s)
[INFO] Running without AIOS... done (180s)

Results:
  ReAct:
    Throughput: 1.0 (with AIOS) vs 0.52 (without) - 1.92x improvement
    Latency: 0.35 (with AIOS) vs 1.0 (without) - 2.86x improvement
  ...

[INFO] Plots saved to results/plots/
```

