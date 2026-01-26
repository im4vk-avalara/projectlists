"""
AIOS Benchmark Runner

Provides tools for running standardized benchmarks.

Paper Reference: Section 4.2, Figures 10-15
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
import tempfile

from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
from aios.adapters.react import ReActAdapter
from aios.adapters.base import AdapterConfig, AgentResult
from aios.evaluation.metrics import BenchmarkResult, MetricsCollector

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkTask:
    """A single benchmark task."""
    task_id: str
    prompt: str
    expected_answer: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskResult:
    """Result of a benchmark task."""
    task_id: str
    success: bool
    output: str
    expected: Optional[str]
    execution_time_ms: float
    steps: int
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "success": self.success,
            "output": self.output,
            "expected": self.expected,
            "execution_time_ms": self.execution_time_ms,
            "steps": self.steps,
            "error": self.error,
        }


@dataclass
class BenchmarkSuite:
    """
    A collection of benchmark tasks.
    
    Paper Reference: Section 4.2 (HumanEval, MINT, GAIA, SWE-Bench)
    """
    name: str
    description: str
    tasks: List[BenchmarkTask] = field(default_factory=list)
    
    def add_task(self, task: BenchmarkTask) -> None:
        """Add a task to the suite."""
        self.tasks.append(task)
    
    def __len__(self) -> int:
        return len(self.tasks)
    
    @classmethod
    def from_json(cls, path: str) -> "BenchmarkSuite":
        """Load a benchmark suite from JSON."""
        with open(path, "r") as f:
            data = json.load(f)
        
        suite = cls(
            name=data.get("name", "unknown"),
            description=data.get("description", ""),
        )
        
        for task_data in data.get("tasks", []):
            task = BenchmarkTask(
                task_id=task_data.get("task_id", ""),
                prompt=task_data.get("prompt", ""),
                expected_answer=task_data.get("expected_answer"),
                metadata=task_data.get("metadata", {}),
            )
            suite.add_task(task)
        
        return suite
    
    def to_json(self, path: str) -> None:
        """Save the benchmark suite to JSON."""
        data = {
            "name": self.name,
            "description": self.description,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "prompt": t.prompt,
                    "expected_answer": t.expected_answer,
                    "metadata": t.metadata,
                }
                for t in self.tasks
            ],
        }
        
        with open(path, "w") as f:
            json.dump(data, f, indent=2)


class BenchmarkRunner:
    """
    Runs benchmarks on AIOS agents.
    
    Paper Reference: Section 4.2
    
    Example:
        runner = BenchmarkRunner()
        
        suite = BenchmarkSuite("math", "Math problems")
        suite.add_task(BenchmarkTask("1", "What is 2+2?", "4"))
        
        results = await runner.run(suite)
    """
    
    def __init__(
        self,
        kernel_config: Optional[KernelConfig] = None,
        adapter_config: Optional[AdapterConfig] = None,
    ):
        self.kernel_config = kernel_config
        self.adapter_config = adapter_config or AdapterConfig(
            max_iterations=10,
            verbose=False,
        )
        self._temp_dir: Optional[str] = None
    
    async def run(
        self,
        suite: BenchmarkSuite,
        strategy: str = "fifo",
        parallel: bool = False,
        max_parallel: int = 4,
    ) -> Dict[str, Any]:
        """
        Run a benchmark suite.
        
        Args:
            suite: Benchmark suite to run
            strategy: Scheduling strategy
            parallel: Run tasks in parallel
            max_parallel: Max parallel tasks
            
        Returns:
            Dict with results and metrics
        """
        self._temp_dir = tempfile.mkdtemp()
        
        config = self.kernel_config or KernelConfig(
            scheduling_strategy=strategy,
            storage_root=self._temp_dir,
            auto_approve_confirmations=True,
        )
        config.scheduling_strategy = strategy
        
        kernel = AIOSKernel(config=config)
        await kernel.start()
        
        try:
            start_time = time.time()
            
            if parallel:
                results = await self._run_parallel(kernel, suite, max_parallel)
            else:
                results = await self._run_sequential(kernel, suite)
            
            end_time = time.time()
            
            # Calculate summary
            successful = sum(1 for r in results if r.success)
            total = len(results)
            
            summary = {
                "suite_name": suite.name,
                "strategy": strategy,
                "total_tasks": total,
                "successful_tasks": successful,
                "failed_tasks": total - successful,
                "success_rate": successful / total if total > 0 else 0,
                "total_time_seconds": end_time - start_time,
                "avg_time_per_task_ms": (
                    sum(r.execution_time_ms for r in results) / total
                    if total > 0 else 0
                ),
                "results": [r.to_dict() for r in results],
            }
            
            logger.info(
                f"Benchmark '{suite.name}' completed: "
                f"{successful}/{total} tasks successful "
                f"({summary['success_rate']*100:.1f}%)"
            )
            
            return summary
            
        finally:
            await kernel.stop()
            
            if self._temp_dir:
                import shutil
                shutil.rmtree(self._temp_dir, ignore_errors=True)
    
    async def _run_sequential(
        self,
        kernel: AIOSKernel,
        suite: BenchmarkSuite,
    ) -> List[TaskResult]:
        """Run tasks sequentially."""
        results = []
        
        for i, task in enumerate(suite.tasks):
            logger.debug(f"Running task {i+1}/{len(suite)}: {task.task_id}")
            result = await self._run_task(kernel, task)
            results.append(result)
        
        return results
    
    async def _run_parallel(
        self,
        kernel: AIOSKernel,
        suite: BenchmarkSuite,
        max_parallel: int,
    ) -> List[TaskResult]:
        """Run tasks in parallel with concurrency limit."""
        semaphore = asyncio.Semaphore(max_parallel)
        
        async def run_with_limit(task: BenchmarkTask) -> TaskResult:
            async with semaphore:
                return await self._run_task(kernel, task)
        
        tasks = [run_with_limit(t) for t in suite.tasks]
        results = await asyncio.gather(*tasks)
        
        return list(results)
    
    async def _run_task(
        self,
        kernel: AIOSKernel,
        task: BenchmarkTask,
    ) -> TaskResult:
        """Run a single benchmark task."""
        adapter = ReActAdapter(
            kernel,
            agent_id=f"bench-{task.task_id}",
            config=self.adapter_config,
        )
        
        start_time = time.time()
        
        try:
            result = await adapter.run(task.prompt)
            end_time = time.time()
            
            # Check correctness
            success = result.success
            if task.expected_answer and result.output:
                # Simple string matching - could be enhanced
                success = self._check_answer(result.output, task.expected_answer)
            
            return TaskResult(
                task_id=task.task_id,
                success=success,
                output=result.output,
                expected=task.expected_answer,
                execution_time_ms=(end_time - start_time) * 1000,
                steps=result.iterations,
            )
            
        except Exception as e:
            end_time = time.time()
            return TaskResult(
                task_id=task.task_id,
                success=False,
                output="",
                expected=task.expected_answer,
                execution_time_ms=(end_time - start_time) * 1000,
                steps=0,
                error=str(e),
            )
    
    def _check_answer(self, output: str, expected: str) -> bool:
        """Check if the output matches the expected answer."""
        # Normalize strings
        output_norm = output.lower().strip()
        expected_norm = expected.lower().strip()
        
        # Exact match
        if output_norm == expected_norm:
            return True
        
        # Contains match
        if expected_norm in output_norm:
            return True
        
        # Try numeric comparison
        try:
            output_num = float(output_norm.replace(",", ""))
            expected_num = float(expected_norm.replace(",", ""))
            return abs(output_num - expected_num) < 0.01
        except ValueError:
            pass
        
        return False


# Built-in benchmark suites

def create_math_benchmark() -> BenchmarkSuite:
    """Create a simple math benchmark suite."""
    suite = BenchmarkSuite(
        name="math-basic",
        description="Basic math problems",
    )
    
    problems = [
        ("1", "What is 15 + 27?", "42"),
        ("2", "What is 100 - 37?", "63"),
        ("3", "What is 12 * 8?", "96"),
        ("4", "What is 144 / 12?", "12"),
        ("5", "What is 2^10?", "1024"),
        ("6", "What is the square root of 81?", "9"),
        ("7", "What is 25% of 200?", "50"),
        ("8", "What is 7 factorial?", "5040"),
    ]
    
    for task_id, prompt, answer in problems:
        suite.add_task(BenchmarkTask(task_id, prompt, answer))
    
    return suite


def create_coding_benchmark() -> BenchmarkSuite:
    """Create a simple coding benchmark suite."""
    suite = BenchmarkSuite(
        name="coding-basic",
        description="Basic coding problems",
    )
    
    problems = [
        ("1", "Write Python code to print 'Hello, World!'", "Hello, World!"),
        ("2", "Write Python code to calculate the sum of numbers 1 to 10", "55"),
        ("3", "Write Python code to check if 17 is prime", "True"),
        ("4", "Write Python code to reverse the string 'hello'", "olleh"),
    ]
    
    for task_id, prompt, answer in problems:
        suite.add_task(BenchmarkTask(task_id, prompt, answer))
    
    return suite

