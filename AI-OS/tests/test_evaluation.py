"""
Tests for Evaluation Framework

Paper Reference: Section 4
"""

import pytest
import asyncio

from aios.evaluation.metrics import (
    MetricsCollector,
    SyscallMetrics,
    AgentMetrics,
    BenchmarkResult,
)
from aios.evaluation.harness import (
    EvaluationHarness,
    HarnessConfig,
    WorkloadConfig,
)
from aios.evaluation.benchmark import (
    BenchmarkRunner,
    BenchmarkSuite,
    BenchmarkTask,
    create_math_benchmark,
)
from aios.evaluation.plots import (
    generate_comparison_report,
    generate_scaling_report,
    generate_ascii_bar_chart,
)


class TestSyscallMetrics:
    """Tests for SyscallMetrics."""
    
    def test_create_metrics(self):
        """Test creating syscall metrics."""
        metrics = SyscallMetrics(
            syscall_id="sc-1",
            syscall_type="llm",
            agent_id="agent-1",
            submit_time=1000.0,
            start_time=1000.1,
            end_time=1000.5,
            success=True,
        )
        
        assert abs(metrics.waiting_time - 100.0) < 0.01  # 0.1s = 100ms
        assert abs(metrics.execution_time - 400.0) < 0.01  # 0.4s = 400ms
        assert abs(metrics.total_time - 500.0) < 0.01  # 0.5s = 500ms
    
    def test_to_dict(self):
        """Test serialization."""
        metrics = SyscallMetrics(
            syscall_id="sc-1",
            syscall_type="llm",
            agent_id="agent-1",
            submit_time=0.0,
            start_time=0.0,
            end_time=0.0,
            success=True,
        )
        
        data = metrics.to_dict()
        assert "syscall_id" in data
        assert "waiting_time_ms" in data


class TestAgentMetrics:
    """Tests for AgentMetrics."""
    
    def test_add_syscall(self):
        """Test adding syscalls."""
        agent = AgentMetrics(agent_id="agent-1")
        
        agent.add_syscall(SyscallMetrics(
            syscall_id="1",
            syscall_type="llm",
            agent_id="agent-1",
            submit_time=0.0,
            start_time=0.1,
            end_time=0.5,
            success=True,
        ))
        
        agent.add_syscall(SyscallMetrics(
            syscall_id="2",
            syscall_type="llm",
            agent_id="agent-1",
            submit_time=0.0,
            start_time=0.2,
            end_time=0.6,
            success=False,
        ))
        
        assert agent.syscall_count == 2
        assert agent.success_count == 1
        assert agent.error_count == 1
        assert agent.success_rate == 0.5
    
    def test_avg_times(self):
        """Test average time calculations."""
        agent = AgentMetrics(agent_id="agent-1")
        
        for i in range(10):
            agent.add_syscall(SyscallMetrics(
                syscall_id=str(i),
                syscall_type="llm",
                agent_id="agent-1",
                submit_time=0.0,
                start_time=0.1,
                end_time=0.2,
                success=True,
            ))
        
        assert abs(agent.avg_waiting_time - 100.0) < 0.01  # 0.1s
        assert abs(agent.avg_execution_time - 100.0) < 0.01  # 0.1s


class TestMetricsCollector:
    """Tests for MetricsCollector."""
    
    @pytest.mark.asyncio
    async def test_collect_metrics(self):
        """Test collecting metrics."""
        collector = MetricsCollector()
        collector.start()
        
        await collector.record_syscall(
            syscall_id="1",
            syscall_type="llm",
            agent_id="agent-1",
            submit_time=0.0,
            start_time=0.1,
            end_time=0.5,
            success=True,
        )
        
        await collector.record_syscall(
            syscall_id="2",
            syscall_type="memory",
            agent_id="agent-2",
            submit_time=0.0,
            start_time=0.05,
            end_time=0.1,
            success=True,
        )
        
        collector.stop()
        
        result = collector.get_results("test", "fifo")
        
        assert result.total_syscalls == 2
        assert len(result.agent_metrics) == 2
    
    @pytest.mark.asyncio
    async def test_fairness_index(self):
        """Test fairness calculation."""
        collector = MetricsCollector()
        collector.start()
        
        # Equal distribution - should be fair
        for i in range(3):
            for j in range(10):
                await collector.record_syscall(
                    syscall_id=f"{i}-{j}",
                    syscall_type="llm",
                    agent_id=f"agent-{i}",
                    submit_time=0.0,
                    start_time=0.0,
                    end_time=0.1,
                    success=True,
                )
        
        collector.stop()
        result = collector.get_results("test", "fifo")
        
        # Equal distribution should have fairness ~1.0
        assert result.fairness_index > 0.95


class TestEvaluationHarness:
    """Tests for EvaluationHarness."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_run_workload(self):
        """Test running a simple workload."""
        harness = EvaluationHarness()
        
        workload = WorkloadConfig(
            name="test-workload",
            agent_count=2,
            queries_per_agent=3,
            random_seed=42,
        )
        
        result = await harness.run_workload(workload, strategy="fifo")
        
        assert result.name == "test-workload"
        assert result.agent_count == 2
        assert result.total_syscalls == 6
        assert result.strategy == "fifo"
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_compare_strategies(self):
        """Test comparing FIFO and RR."""
        harness = EvaluationHarness()
        
        workload = WorkloadConfig(
            name="comparison",
            agent_count=3,
            queries_per_agent=5,
            random_seed=42,
        )
        
        results = await harness.compare_strategies(workload)
        
        assert "fifo" in results
        assert "round_robin" in results
        assert results["fifo"].total_syscalls == results["round_robin"].total_syscalls


class TestBenchmarkSuite:
    """Tests for BenchmarkSuite."""
    
    def test_create_suite(self):
        """Test creating a benchmark suite."""
        suite = BenchmarkSuite(
            name="test",
            description="Test suite",
        )
        
        suite.add_task(BenchmarkTask("1", "What is 2+2?", "4"))
        suite.add_task(BenchmarkTask("2", "What is 3+3?", "6"))
        
        assert len(suite) == 2
    
    def test_builtin_math(self):
        """Test built-in math benchmark."""
        suite = create_math_benchmark()
        
        assert suite.name == "math-basic"
        assert len(suite) > 0


class TestBenchmarkRunner:
    """Tests for BenchmarkRunner."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_run_simple(self):
        """Test running a simple benchmark."""
        runner = BenchmarkRunner()
        
        suite = BenchmarkSuite("test", "Test")
        suite.add_task(BenchmarkTask("1", "Say hello", None))
        
        results = await runner.run(suite)
        
        assert results["total_tasks"] == 1
        assert "results" in results


class TestPlots:
    """Tests for plotting utilities."""
    
    def test_comparison_report(self):
        """Test generating comparison report."""
        fifo = BenchmarkResult(
            name="test",
            strategy="fifo",
            agent_count=5,
            duration_seconds=10.0,
            total_syscalls=100,
            successful_syscalls=95,
            failed_syscalls=5,
            avg_waiting_time=50.0,
            avg_execution_time=30.0,
            avg_total_time=80.0,
        )
        
        rr = BenchmarkResult(
            name="test",
            strategy="round_robin",
            agent_count=5,
            duration_seconds=10.0,
            total_syscalls=100,
            successful_syscalls=98,
            failed_syscalls=2,
            avg_waiting_time=45.0,
            avg_execution_time=30.0,
            avg_total_time=75.0,
        )
        
        report = generate_comparison_report(fifo, rr)
        
        assert "FIFO" in report
        assert "Round Robin" in report
    
    def test_ascii_chart(self):
        """Test ASCII bar chart generation."""
        data = {
            "agent-1": 10.5,
            "agent-2": 20.3,
            "agent-3": 15.2,
        }
        
        chart = generate_ascii_bar_chart("Test Chart", data)
        
        assert "agent-1" in chart
        assert "agent-2" in chart

