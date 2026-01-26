# Self-Correcting Codeforces Tutor

An AI-powered tutoring system for Codeforces problem solving with **self-correcting capabilities**. Given a problem statement and samples, it produces a verified solution using a self-correcting loop.

## 🔄 The Self-Correcting Loop

```
Understand → Retrieve → Solve → Verify → Repair (repeat until verified)
```

1. **Understand**: Parse problem, extract constraints, edge cases, I/O format
2. **Retrieve**: Find relevant techniques, pitfalls, and code templates via RAG
3. **Solve**: Generate approach with correctness argument, then code
4. **Verify**: Run sample tests, stress tests, metamorphic tests
5. **Repair**: If failed, analyze failure and fix (repeat up to N times)

## 🚀 Quick Start

### 1. Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp env.example .env
# Edit .env with your ALFA_CLAIM
```

### 2. Run Demo

```bash
python main.py --demo
```

### 3. Interactive Mode

```bash
python main.py
```

### 4. From Problem File

```bash
python main.py --problem path/to/problem.txt
```

## 📁 Project Structure

```
SelfCorrectingRag/
├── main.py                    # CLI entry point
├── requirements.txt           # Python dependencies
├── env.example               # Environment template
│
├── src/
│   ├── __init__.py
│   ├── config.py             # Configuration loader
│   ├── tutor.py              # Main Tutor orchestrator
│   │
│   ├── llm/
│   │   └── client.py         # Alfa LLM wrapper
│   │
│   ├── parser/
│   │   ├── models.py         # ProblemSpec, Constraints, TestCase
│   │   ├── parser.py         # LLM-based problem parser
│   │   └── fetcher.py        # CF URL parser utilities
│   │
│   ├── retriever/
│   │   ├── knowledge_base.py # Loads techniques/pitfalls/templates
│   │   └── retriever.py      # Semantic search for techniques
│   │
│   ├── solver/
│   │   ├── models.py         # Solution, Approach, Complexity
│   │   └── solver.py         # Approach + code generation
│   │
│   └── verifier/
│       ├── runner.py         # Code execution with timeout
│       ├── stress.py         # Random testing + oracle comparison
│       ├── metamorphic.py    # Testing without oracle
│       └── verifier.py       # Main verification orchestrator
│
├── knowledge_base/
│   ├── techniques.yaml       # 20+ algorithm technique cards
│   └── pitfalls.yaml         # 15+ common bug patterns
│
├── templates/
│   ├── binary_search.py
│   ├── union_find.py
│   ├── segment_tree.py
│   ├── dp_knapsack.py
│   ├── bfs_dfs.py
│   ├── mod_arithmetic.py
│   └── fast_io.py
│
└── tests/                    # Test suite
```

## 🧠 Features

### Problem Parsing
- LLM-based extraction of constraints, I/O format, edge cases
- Automatic sample test extraction from problem statement
- Difficulty estimation

### RAG-Based Retrieval
- **20+ Technique Cards**: Binary search, DP variants, graphs, data structures, etc.
- **15+ Pitfall Registry**: Integer overflow, off-by-one, wrong bounds, TLE causes
- **7 Code Templates**: Ready-to-use implementations

### Solution Generation
- Step-by-step approach with key insight
- Correctness argument
- Complexity analysis with TLE estimation
- Code generation using templates

### Verification
- **Sample Tests**: Run against provided examples
- **Stress Testing**: Random inputs + brute-force oracle comparison
- **Metamorphic Testing**: Test invariants without oracle
  - Permutation invariance
  - Reversal invariance
  - Output format checking

### Self-Correction
- Automatic failure analysis
- Targeted pitfall retrieval based on error type
- Up to N repair attempts
- Full repair history tracking

## 📋 Checklist Tracking

The tutor tracks progress on:
- [ ] Constraints extracted
- [ ] Input format understood
- [ ] Output format understood
- [ ] Samples parsed
- [ ] Edge cases identified
- [ ] Technique identified
- [ ] Solution implemented
- [ ] Samples passed
- [ ] Stress tested

## 💻 Programmatic Usage

```python
from src import Tutor

tutor = Tutor()

output = tutor.solve_with_samples(
    problem_statement=\"\"\"
    Find the sum of n integers.
    Constraints: 1 ≤ n ≤ 10^5, 1 ≤ a_i ≤ 10^9
    \"\"\",
    sample_inputs=["3\\n1 2 3"],
    sample_outputs=["6"],
    oracle_code=\"\"\"
    n = int(input())
    print(sum(map(int, input().split())))
    \"\"\"
)

print(output)  # Complete solution with verification summary
print(output.code)  # Just the code
```

## ⚙️ Configuration

Set in `.env` or environment:

```bash
# Required
ALFA_CLAIM=your-project-uuid

# Optional
ALFA_ENV=qa
DEFAULT_MODEL=claude-4-sonnet
CODE_TIMEOUT_SECONDS=5
MAX_REPAIR_ITERATIONS=5
STRESS_TEST_COUNT=100
```

## 🎯 Output Format

The tutor produces:

1. **Solution Outline** - Approach summary, key insight, steps
2. **Complexity** - Time/space with explanation
3. **Final Code** - Single Python file
4. **Verification Summary**:
   - Samples: N/M passed
   - Stress tests: K tests run
   - Assumptions made
5. **Checklist** - All requirements marked

## 📝 License

MIT

