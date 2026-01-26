"""
AIOS Metrics Collection

Collects and aggregates performance metrics for evaluation.

Paper Reference: Section 4, Figures 6-8
"""

import asyncio
import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class SyscallMetrics:
    """
    Metrics for a single syscall execution.
    
    Paper Reference: Section 4.1 - syscall timing
    """
    syscall_id: str
    syscall_type: str
    agent_id: str
    submit_time: float
    start_time: float
    end_time: float
    success: bool
    error: Optional[str] = None
    
    @property
    def waiting_time(self) -> float:
        """Time spent waiting in queue (ms)."""
        return (self.start_time - self.submit_time) * 1000
    
    @property
    def execution_time(self) -> float:
        """Time spent executing (ms)."""
        return (self.end_time - self.start_time) * 1000
    
    @property
    def total_time(self) -> float:
        """Total time from submit to complete (ms)."""
        return (self.end_time - self.submit_time) * 1000
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "syscall_id": self.syscall_id,
            "syscall_type": self.syscall_type,
            "agent_id": self.agent_id,
            "waiting_time_ms": self.waiting_time,
            "execution_time_ms": self.execution_time,
            "total_time_ms": self.total_time,
            "success": self.success,
            "error": self.error,
        }


@dataclass
class AgentMetrics:
    """
    Aggregated metrics for an agent.
    
    Paper Reference: Section 4.1 - per-agent metrics
    """
    agent_id: str
    syscall_count: int = 0
    total_waiting_time: float = 0.0
    total_execution_time: float = 0.0
    success_count: int = 0
    error_count: int = 0
    syscalls: List[SyscallMetrics] = field(default_factory=list)
    
    @property
    def avg_waiting_time(self) -> float:
        """Average waiting time (ms)."""
        if not self.syscall_count:
            return 0.0
        return self.total_waiting_time / self.syscall_count
    
    @property
    def avg_execution_time(self) -> float:
        """Average execution time (ms)."""
        if not self.syscall_count:
            return 0.0
        return self.total_execution_time / self.syscall_count
    
    @property
    def success_rate(self) -> float:
        """Success rate (0-1)."""
        if not self.syscall_count:
            return 0.0
        return self.success_count / self.syscall_count
    
    def add_syscall(self, metrics: SyscallMetrics) -> None:
        """Add a syscall's metrics."""
        self.syscall_count += 1
        self.total_waiting_time += metrics.waiting_time
        self.total_execution_time += metrics.execution_time
        
        if metrics.success:
            self.success_count += 1
        else:
            self.error_count += 1
        
        self.syscalls.append(metrics)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "syscall_count": self.syscall_count,
            "avg_waiting_time_ms": self.avg_waiting_time,
            "avg_execution_time_ms": self.avg_execution_time,
            "success_rate": self.success_rate,
            "success_count": self.success_count,
            "error_count": self.error_count,
        }


@dataclass
class BenchmarkResult:
    """
    Results from a benchmark run.
    
    Paper Reference: Section 4, Figures 6-8
    """
    name: str
    strategy: str  # fifo or round_robin
    agent_count: int
    duration_seconds: float
    total_syscalls: int
    successful_syscalls: int
    failed_syscalls: int
    
    # Timing metrics (in ms)
    avg_waiting_time: float
    avg_execution_time: float
    avg_total_time: float
    
    p50_waiting_time: float = 0.0
    p90_waiting_time: float = 0.0
    p99_waiting_time: float = 0.0
    
    p50_execution_time: float = 0.0
    p90_execution_time: float = 0.0
    p99_execution_time: float = 0.0
    
    # Throughput
    syscalls_per_second: float = 0.0
    
    # Per-agent metrics
    agent_metrics: Dict[str, AgentMetrics] = field(default_factory=dict)
    
    # Fairness metrics (for RR)
    fairness_index: float = 1.0  # Jain's fairness index
    
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "strategy": self.strategy,
            "agent_count": self.agent_count,
            "duration_seconds": self.duration_seconds,
            "total_syscalls": self.total_syscalls,
            "successful_syscalls": self.successful_syscalls,
            "failed_syscalls": self.failed_syscalls,
            "avg_waiting_time_ms": self.avg_waiting_time,
            "avg_execution_time_ms": self.avg_execution_time,
            "avg_total_time_ms": self.avg_total_time,
            "p50_waiting_time_ms": self.p50_waiting_time,
            "p90_waiting_time_ms": self.p90_waiting_time,
            "p99_waiting_time_ms": self.p99_waiting_time,
            "syscalls_per_second": self.syscalls_per_second,
            "fairness_index": self.fairness_index,
            "agent_metrics": {k: v.to_dict() for k, v in self.agent_metrics.items()},
        }


class MetricsCollector:
    """
    Collects and aggregates metrics during evaluation.
    
    Paper Reference: Section 4
    
    Example:
        collector = MetricsCollector()
        
        # Record syscalls
        collector.record_syscall(metrics)
        
        # Get results
        result = collector.get_results("benchmark-1", "fifo")
    """
    
    def __init__(self):
        self._syscalls: List[SyscallMetrics] = []
        self._agent_metrics: Dict[str, AgentMetrics] = {}
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._lock = asyncio.Lock()
    
    def start(self) -> None:
        """Start metrics collection."""
        self._start_time = time.time()
        self._syscalls = []
        self._agent_metrics = {}
        logger.debug("Metrics collection started")
    
    def stop(self) -> None:
        """Stop metrics collection."""
        self._end_time = time.time()
        logger.debug("Metrics collection stopped")
    
    async def record_syscall(
        self,
        syscall_id: str,
        syscall_type: str,
        agent_id: str,
        submit_time: float,
        start_time: float,
        end_time: float,
        success: bool,
        error: Optional[str] = None,
    ) -> None:
        """Record metrics for a syscall."""
        metrics = SyscallMetrics(
            syscall_id=syscall_id,
            syscall_type=syscall_type,
            agent_id=agent_id,
            submit_time=submit_time,
            start_time=start_time,
            end_time=end_time,
            success=success,
            error=error,
        )
        
        async with self._lock:
            self._syscalls.append(metrics)
            
            # Update agent metrics
            if agent_id not in self._agent_metrics:
                self._agent_metrics[agent_id] = AgentMetrics(agent_id=agent_id)
            self._agent_metrics[agent_id].add_syscall(metrics)
    
    def get_results(
        self,
        name: str,
        strategy: str,
    ) -> BenchmarkResult:
        """
        Get aggregated benchmark results.
        
        Paper Reference: Section 4.1
        """
        duration = (self._end_time or time.time()) - (self._start_time or time.time())
        
        if not self._syscalls:
            return BenchmarkResult(
                name=name,
                strategy=strategy,
                agent_count=len(self._agent_metrics),
                duration_seconds=duration,
                total_syscalls=0,
                successful_syscalls=0,
                failed_syscalls=0,
                avg_waiting_time=0,
                avg_execution_time=0,
                avg_total_time=0,
            )
        
        # Calculate aggregate metrics
        waiting_times = [s.waiting_time for s in self._syscalls]
        execution_times = [s.execution_time for s in self._syscalls]
        total_times = [s.total_time for s in self._syscalls]
        
        successful = sum(1 for s in self._syscalls if s.success)
        failed = len(self._syscalls) - successful
        
        # Percentiles
        sorted_waiting = sorted(waiting_times)
        sorted_execution = sorted(execution_times)
        
        def percentile(data: List[float], p: float) -> float:
            if not data:
                return 0.0
            k = (len(data) - 1) * p / 100
            f = int(k)
            c = f + 1 if f + 1 < len(data) else f
            return data[f] + (k - f) * (data[c] - data[f])
        
        # Calculate Jain's fairness index
        fairness = self._calculate_fairness_index()
        
        return BenchmarkResult(
            name=name,
            strategy=strategy,
            agent_count=len(self._agent_metrics),
            duration_seconds=duration,
            total_syscalls=len(self._syscalls),
            successful_syscalls=successful,
            failed_syscalls=failed,
            avg_waiting_time=statistics.mean(waiting_times),
            avg_execution_time=statistics.mean(execution_times),
            avg_total_time=statistics.mean(total_times),
            p50_waiting_time=percentile(sorted_waiting, 50),
            p90_waiting_time=percentile(sorted_waiting, 90),
            p99_waiting_time=percentile(sorted_waiting, 99),
            p50_execution_time=percentile(sorted_execution, 50),
            p90_execution_time=percentile(sorted_execution, 90),
            p99_execution_time=percentile(sorted_execution, 99),
            syscalls_per_second=len(self._syscalls) / duration if duration > 0 else 0,
            agent_metrics=self._agent_metrics.copy(),
            fairness_index=fairness,
        )
    
    def _calculate_fairness_index(self) -> float:
        """
        Calculate Jain's fairness index.
        
        J = (sum(x_i))^2 / (n * sum(x_i^2))
        
        Where x_i is the throughput of agent i.
        J = 1 means perfect fairness, J = 1/n means worst case.
        """
        if len(self._agent_metrics) <= 1:
            return 1.0
        
        # Calculate per-agent syscall counts
        counts = [m.syscall_count for m in self._agent_metrics.values()]
        
        if not counts or sum(counts) == 0:
            return 1.0
        
        n = len(counts)
        sum_x = sum(counts)
        sum_x2 = sum(x ** 2 for x in counts)
        
        if sum_x2 == 0:
            return 1.0
        
        return (sum_x ** 2) / (n * sum_x2)
    
    def get_per_agent_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get per-agent statistics."""
        return {
            agent_id: metrics.to_dict()
            for agent_id, metrics in self._agent_metrics.items()
        }
    
    def reset(self) -> None:
        """Reset all collected metrics."""
        self._syscalls = []
        self._agent_metrics = {}
        self._start_time = None
        self._end_time = None

