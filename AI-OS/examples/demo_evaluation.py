"""
AIOS Evaluation Framework Demo

Demonstrates the evaluation capabilities:
- Throughput and latency measurement
- FIFO vs Round Robin comparison
- Scaling evaluation
- Benchmark running

Paper Reference: Section 4, Figures 6-15
"""

import asyncio
import logging

# Colorful output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*70}{Colors.END}\n")

def print_section(text):
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- {text} ---{Colors.END}\n")

def print_result(text):
    print(f"{Colors.GREEN}  ✓ {text}{Colors.END}")

def print_data(label, data):
    print(f"{Colors.YELLOW}    {label}:{Colors.END} {data}")


async def demo_metrics():
    """Demo metrics collection."""
    from aios.evaluation.metrics import MetricsCollector
    
    print_section("1. Metrics Collection")
    
    collector = MetricsCollector()
    collector.start()
    
    # Simulate syscall metrics
    import time
    base = time.time()
    
    for i in range(10):
        await collector.record_syscall(
            syscall_id=f"sc-{i}",
            syscall_type="llm",
            agent_id=f"agent-{i % 3}",
            submit_time=base,
            start_time=base + 0.05,
            end_time=base + 0.15,
            success=True,
        )
    
    collector.stop()
    
    result = collector.get_results("demo", "fifo")
    
    print_result(f"Collected {result.total_syscalls} syscall metrics")
    print_data("Agents tracked", result.agent_count)
    print_data("Avg waiting time", f"{result.avg_waiting_time:.2f}ms")
    print_data("Avg execution time", f"{result.avg_execution_time:.2f}ms")
    print_data("Fairness index", f"{result.fairness_index:.3f}")


async def demo_workload():
    """Demo running a workload."""
    from aios.evaluation.harness import EvaluationHarness, WorkloadConfig
    
    print_section("2. Workload Execution")
    
    harness = EvaluationHarness()
    
    workload = WorkloadConfig(
        name="demo-workload",
        agent_count=5,
        queries_per_agent=10,
        query_mix={"llm": 0.5, "memory": 0.4, "tool": 0.1},
        random_seed=42,
    )
    
    print(f"  Running workload: {workload.agent_count} agents, {workload.queries_per_agent} queries each")
    print(f"  Query mix: {workload.query_mix}\n")
    
    result = await harness.run_workload(workload, strategy="fifo")
    
    print_result(f"Completed {result.total_syscalls} syscalls")
    print_data("Duration", f"{result.duration_seconds:.2f}s")
    print_data("Throughput", f"{result.syscalls_per_second:.1f} syscalls/sec")
    print_data("Success rate", f"{result.successful_syscalls/result.total_syscalls*100:.1f}%")


async def demo_comparison():
    """Demo comparing FIFO and Round Robin."""
    from aios.evaluation.harness import EvaluationHarness, WorkloadConfig
    from aios.evaluation.plots import generate_comparison_report
    
    print_section("3. FIFO vs Round Robin Comparison")
    
    harness = EvaluationHarness()
    
    workload = WorkloadConfig(
        name="comparison",
        agent_count=4,
        queries_per_agent=8,
        random_seed=42,
    )
    
    print(f"  Running comparison with {workload.agent_count} agents...\n")
    
    results = await harness.compare_strategies(workload)
    
    fifo = results["fifo"]
    rr = results["round_robin"]
    
    print(f"\n  {Colors.CYAN}Results:{Colors.END}")
    print(f"  {'Metric':<25} {'FIFO':>12} {'Round Robin':>12}")
    print(f"  {'-'*50}")
    print(f"  {'Avg Wait Time (ms)':<25} {fifo.avg_waiting_time:>12.2f} {rr.avg_waiting_time:>12.2f}")
    print(f"  {'P90 Wait Time (ms)':<25} {fifo.p90_waiting_time:>12.2f} {rr.p90_waiting_time:>12.2f}")
    print(f"  {'Throughput (qps)':<25} {fifo.syscalls_per_second:>12.1f} {rr.syscalls_per_second:>12.1f}")
    print(f"  {'Fairness Index':<25} {fifo.fairness_index:>12.3f} {rr.fairness_index:>12.3f}")


async def demo_scaling():
    """Demo scaling evaluation."""
    from aios.evaluation.harness import EvaluationHarness, WorkloadConfig
    from aios.evaluation.plots import generate_ascii_bar_chart
    
    print_section("4. Scaling Evaluation")
    
    harness = EvaluationHarness()
    
    base_workload = WorkloadConfig(
        name="scaling",
        queries_per_agent=5,
    )
    
    agent_counts = [2, 4, 6, 8]
    print(f"  Testing with agent counts: {agent_counts}\n")
    
    results = await harness.scaling_evaluation(
        base_workload,
        agent_counts,
        strategy="fifo",
    )
    
    # Show results
    print(f"\n  {Colors.CYAN}Scaling Results:{Colors.END}")
    print(f"  {'Agents':<10} {'Syscalls':>10} {'Throughput':>15} {'Avg Wait':>12}")
    print(f"  {'-'*47}")
    
    for result in results:
        print(
            f"  {result.agent_count:<10} "
            f"{result.total_syscalls:>10} "
            f"{result.syscalls_per_second:>15.1f} "
            f"{result.avg_waiting_time:>12.2f}"
        )
    
    # Bar chart
    print(f"\n  Throughput by Agent Count:")
    throughput_data = {f"{r.agent_count} agents": r.syscalls_per_second for r in results}
    chart = generate_ascii_bar_chart("", throughput_data, width=30)
    for line in chart.split("\n"):
        print(f"  {line}")


async def demo_benchmark():
    """Demo running a benchmark suite."""
    from aios.evaluation.benchmark import (
        BenchmarkRunner,
        BenchmarkSuite,
        BenchmarkTask,
        create_math_benchmark,
    )
    
    print_section("5. Benchmark Suite")
    
    # Create a simple benchmark
    suite = BenchmarkSuite(
        name="quick-test",
        description="Quick benchmark test",
    )
    suite.add_task(BenchmarkTask("1", "What is 2+2?", "4"))
    suite.add_task(BenchmarkTask("2", "Say hello", None))
    suite.add_task(BenchmarkTask("3", "What is 10*10?", "100"))
    
    print(f"  Running benchmark suite: {suite.name}")
    print(f"  Tasks: {len(suite)}\n")
    
    runner = BenchmarkRunner()
    results = await runner.run(suite)
    
    print_result(f"Completed {results['total_tasks']} tasks")
    print_data("Success rate", f"{results['success_rate']*100:.1f}%")
    print_data("Avg time per task", f"{results['avg_time_per_task_ms']:.2f}ms")
    
    # Show task results
    print(f"\n  {Colors.CYAN}Task Results:{Colors.END}")
    for task_result in results["results"]:
        status = "✓" if task_result["success"] else "✗"
        print(f"    {status} Task {task_result['task_id']}: {task_result['steps']} steps")


async def main():
    logging.getLogger().setLevel(logging.WARNING)
    
    print_header("AIOS Evaluation Framework Demo")
    
    print(f"""  {Colors.BLUE}This demo showcases the evaluation framework for measuring
  and benchmarking AIOS performance, as described in Section 4.{Colors.END}
""")
    
    await demo_metrics()
    await demo_workload()
    await demo_comparison()
    await demo_scaling()
    await demo_benchmark()
    
    print_header("Demo Complete!")
    
    print(f"""
  {Colors.CYAN}The evaluation framework provides:
  
  ┌─────────────────────────────────────────────────────────────────┐
  │  Metrics Collection                                              │
  │  ┌────────────┐  ┌────────────┐  ┌────────────┐                │
  │  │ Waiting    │  │ Execution  │  │ Throughput │                │
  │  │ Time       │  │ Time       │  │ (qps)      │                │
  │  └────────────┘  └────────────┘  └────────────┘                │
  │                                                                  │
  │  Strategy Comparison                                             │
  │  ┌────────────────────────────────────────────┐                 │
  │  │ FIFO vs Round Robin                        │                 │
  │  │ • Latency comparison                        │                 │
  │  │ • Fairness index (Jain's)                   │                 │
  │  │ • Per-agent analysis                        │                 │
  │  └────────────────────────────────────────────┘                 │
  │                                                                  │
  │  Benchmark Suite                                                 │
  │  ┌────────────────────────────────────────────┐                 │
  │  │ • Task-based evaluation                     │                 │
  │  │ • Success rate tracking                     │                 │
  │  │ • Parallel/sequential execution             │                 │
  │  └────────────────────────────────────────────┘                 │
  └─────────────────────────────────────────────────────────────────┘
  
  Paper Reference: Section 4, Figures 6-15{Colors.END}
""")


if __name__ == "__main__":
    asyncio.run(main())

