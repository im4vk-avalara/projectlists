"""
AIOS Evaluation Harness

Provides infrastructure for running evaluation workloads.

Paper Reference: Section 4, Figures 6-8
"""

import asyncio
import logging
import time
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional
import tempfile

from aios.kernel.aios_kernel import AIOSKernel, KernelConfig
from aios.evaluation.metrics import MetricsCollector, BenchmarkResult
from aios.sdk.models import (
    LLMQuery,
    MemoryQuery,
    ToolQuery,
    Message,
    MemoryOperation,
    ResponseStatus,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkloadConfig:
    """
    Configuration for a workload.
    
    Attributes:
        name: Workload name
        agent_count: Number of concurrent agents
        queries_per_agent: Queries each agent makes
        query_mix: Distribution of query types
        think_time_ms: Delay between queries (simulates thinking)
        random_seed: For reproducibility
    """
    name: str = "default"
    agent_count: int = 5
    queries_per_agent: int = 10
    query_mix: Dict[str, float] = field(default_factory=lambda: {
        "llm": 0.6,
        "memory": 0.3,
        "tool": 0.1,
    })
    think_time_ms: int = 0
    random_seed: Optional[int] = None


@dataclass
class HarnessConfig:
    """
    Configuration for the evaluation harness.
    
    Attributes:
        kernel_config: AIOS kernel configuration
        warmup_queries: Queries to run before measurement
        verbose: Enable verbose logging
    """
    kernel_config: Optional[KernelConfig] = None
    warmup_queries: int = 5
    verbose: bool = False


class EvaluationHarness:
    """
    Harness for running AIOS evaluations.
    
    Supports:
    - Multi-agent concurrent workloads
    - Configurable query mixes
    - Metrics collection
    - FIFO vs Round Robin comparison
    
    Paper Reference: Section 4
    
    Example:
        harness = EvaluationHarness()
        
        workload = WorkloadConfig(
            agent_count=10,
            queries_per_agent=50,
        )
        
        result = await harness.run_workload(workload, strategy="fifo")
    """
    
    def __init__(self, config: Optional[HarnessConfig] = None):
        self.config = config or HarnessConfig()
        self._kernel: Optional[AIOSKernel] = None
        self._collector = MetricsCollector()
        self._temp_dir: Optional[str] = None
    
    async def setup(self, strategy: str = "fifo") -> None:
        """Set up the kernel for evaluation."""
        self._temp_dir = tempfile.mkdtemp()
        
        kernel_config = self.config.kernel_config or KernelConfig(
            scheduling_strategy=strategy,
            storage_root=self._temp_dir,
            auto_approve_confirmations=True,
        )
        kernel_config.scheduling_strategy = strategy
        
        self._kernel = AIOSKernel(config=kernel_config)
        await self._kernel.start()
        
        logger.info(f"Evaluation harness setup complete (strategy={strategy})")
    
    async def teardown(self) -> None:
        """Tear down the kernel."""
        if self._kernel:
            await self._kernel.stop()
            self._kernel = None
        
        if self._temp_dir:
            import shutil
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None
    
    async def run_workload(
        self,
        workload: WorkloadConfig,
        strategy: str = "fifo",
    ) -> BenchmarkResult:
        """
        Run a workload and collect metrics.
        
        Paper Reference: Section 4.1
        
        Args:
            workload: Workload configuration
            strategy: Scheduling strategy ("fifo" or "round_robin")
            
        Returns:
            BenchmarkResult with collected metrics
        """
        await self.setup(strategy)
        
        try:
            # Initialize random
            if workload.random_seed is not None:
                random.seed(workload.random_seed)
            
            # Warmup
            if self.config.warmup_queries > 0:
                await self._run_warmup(workload)
            
            # Start metrics collection
            self._collector.reset()
            self._collector.start()
            
            # Run agents concurrently
            agent_tasks = []
            for i in range(workload.agent_count):
                agent_id = f"agent-{i}"
                task = asyncio.create_task(
                    self._run_agent(agent_id, workload)
                )
                agent_tasks.append(task)
            
            # Wait for all agents to complete
            await asyncio.gather(*agent_tasks)
            
            # Stop metrics collection
            self._collector.stop()
            
            # Get results
            result = self._collector.get_results(workload.name, strategy)
            
            logger.info(
                f"Workload '{workload.name}' completed: "
                f"{result.total_syscalls} syscalls, "
                f"{result.syscalls_per_second:.1f} syscalls/sec"
            )
            
            return result
            
        finally:
            await self.teardown()
    
    async def _run_warmup(self, workload: WorkloadConfig) -> None:
        """Run warmup queries."""
        logger.debug(f"Running {self.config.warmup_queries} warmup queries")
        
        for i in range(self.config.warmup_queries):
            query = LLMQuery(
                agent_id="warmup-agent",
                messages=[Message(role="user", content=f"Warmup {i}")],
            )
            await self._kernel.process_query(query)
    
    async def _run_agent(
        self,
        agent_id: str,
        workload: WorkloadConfig,
    ) -> None:
        """Run a single agent's workload."""
        for i in range(workload.queries_per_agent):
            # Select query type based on mix
            query_type = self._select_query_type(workload.query_mix)
            
            # Create query
            query = self._create_query(agent_id, query_type, i)
            
            # Record timing
            submit_time = time.time()
            
            try:
                # Execute query
                start_time = time.time()
                response = await self._kernel.process_query(query)
                end_time = time.time()
                
                success = response.status == ResponseStatus.SUCCESS
                error = response.error if hasattr(response, 'error') else None
                
            except Exception as e:
                end_time = time.time()
                start_time = submit_time
                success = False
                error = str(e)
            
            # Record metrics
            await self._collector.record_syscall(
                syscall_id=f"{agent_id}-{i}",
                syscall_type=query_type,
                agent_id=agent_id,
                submit_time=submit_time,
                start_time=start_time,
                end_time=end_time,
                success=success,
                error=error,
            )
            
            # Think time
            if workload.think_time_ms > 0:
                await asyncio.sleep(workload.think_time_ms / 1000)
    
    def _select_query_type(self, mix: Dict[str, float]) -> str:
        """Select a query type based on the mix distribution."""
        r = random.random()
        cumulative = 0.0
        
        for query_type, probability in mix.items():
            cumulative += probability
            if r < cumulative:
                return query_type
        
        return list(mix.keys())[0]
    
    def _create_query(
        self,
        agent_id: str,
        query_type: str,
        sequence: int,
    ):
        """Create a query of the specified type."""
        if query_type == "llm":
            return LLMQuery(
                agent_id=agent_id,
                messages=[
                    Message(role="user", content=f"Query {sequence} from {agent_id}")
                ],
                max_tokens=50,
            )
        elif query_type == "memory":
            if sequence % 2 == 0:
                return MemoryQuery(
                    agent_id=agent_id,
                    operation=MemoryOperation.WRITE,
                    key=f"key-{sequence}",
                    value={"data": f"value-{sequence}"},
                )
            else:
                return MemoryQuery(
                    agent_id=agent_id,
                    operation=MemoryOperation.READ,
                    key=f"key-{sequence - 1}",
                )
        elif query_type == "tool":
            return ToolQuery(
                agent_id=agent_id,
                tool_name="calculator",
                parameters={"expression": f"{sequence} + {sequence}"},
            )
        else:
            raise ValueError(f"Unknown query type: {query_type}")
    
    async def compare_strategies(
        self,
        workload: WorkloadConfig,
    ) -> Dict[str, BenchmarkResult]:
        """
        Compare FIFO and Round Robin strategies.
        
        Paper Reference: Section 4.2, Figures 6-7
        
        Args:
            workload: Workload configuration
            
        Returns:
            Dict with results for each strategy
        """
        results = {}
        
        for strategy in ["fifo", "round_robin"]:
            logger.info(f"Running workload with {strategy} strategy...")
            result = await self.run_workload(workload, strategy)
            results[strategy] = result
        
        # Log comparison
        fifo = results["fifo"]
        rr = results["round_robin"]
        
        logger.info("\n=== Strategy Comparison ===")
        logger.info(f"FIFO:        {fifo.avg_waiting_time:.2f}ms avg wait, fairness={fifo.fairness_index:.3f}")
        logger.info(f"Round Robin: {rr.avg_waiting_time:.2f}ms avg wait, fairness={rr.fairness_index:.3f}")
        
        return results
    
    async def scaling_evaluation(
        self,
        base_workload: WorkloadConfig,
        agent_counts: List[int],
        strategy: str = "fifo",
    ) -> List[BenchmarkResult]:
        """
        Evaluate how performance scales with agent count.
        
        Paper Reference: Section 4.2, Figure 8
        
        Args:
            base_workload: Base workload configuration
            agent_counts: List of agent counts to test
            strategy: Scheduling strategy
            
        Returns:
            List of results for each agent count
        """
        results = []
        
        for count in agent_counts:
            workload = WorkloadConfig(
                name=f"{base_workload.name}-{count}agents",
                agent_count=count,
                queries_per_agent=base_workload.queries_per_agent,
                query_mix=base_workload.query_mix,
                think_time_ms=base_workload.think_time_ms,
            )
            
            logger.info(f"Running with {count} agents...")
            result = await self.run_workload(workload, strategy)
            results.append(result)
        
        return results

