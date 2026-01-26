"""
AIOS Evaluation Framework - Quick Demo

A faster demo showing key evaluation capabilities without slow operations.
"""

import asyncio
import logging
import time

# Colorful output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}  {text}{Colors.END}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.END}\n")

def print_section(text):
    print(f"\n{Colors.CYAN}{Colors.BOLD}--- {text} ---{Colors.END}\n")

def print_result(text):
    print(f"{Colors.GREEN}  ✓ {text}{Colors.END}")


async def main():
    # Suppress most logging
    logging.getLogger().setLevel(logging.WARNING)
    
    print_header("AIOS Evaluation Framework - Quick Demo")
    
    # 1. Metrics Collection
    print_section("1. Metrics Collection")
    
    from aios.evaluation.metrics import MetricsCollector
    
    collector = MetricsCollector()
    collector.start()
    
    base = time.time()
    for i in range(20):
        await collector.record_syscall(
            syscall_id=f"sc-{i}",
            syscall_type="llm" if i % 3 == 0 else "memory",
            agent_id=f"agent-{i % 4}",
            submit_time=base,
            start_time=base + 0.01,
            end_time=base + 0.05,
            success=True,
        )
    
    collector.stop()
    result = collector.get_results("metrics-demo", "fifo")
    
    print_result(f"Collected {result.total_syscalls} syscall metrics")
    print(f"    Agents: {result.agent_count}")
    print(f"    Throughput: {result.syscalls_per_second:.0f} syscalls/sec")
    print(f"    Avg Wait: {result.avg_waiting_time:.2f}ms")
    print(f"    Fairness Index: {result.fairness_index:.3f}")
    
    # 2. Per-Agent Stats
    print_section("2. Per-Agent Statistics")
    
    for agent_id, metrics in sorted(result.agent_metrics.items()):
        print(f"    {agent_id}: {metrics.syscall_count} syscalls, "
              f"avg wait {metrics.avg_waiting_time:.2f}ms")
    
    # 3. Comparison Report
    print_section("3. Strategy Comparison Report")
    
    from aios.evaluation.metrics import BenchmarkResult
    from aios.evaluation.plots import generate_comparison_report
    
    # Simulated results for demo
    fifo_result = BenchmarkResult(
        name="demo",
        strategy="fifo",
        agent_count=4,
        duration_seconds=5.0,
        total_syscalls=200,
        successful_syscalls=195,
        failed_syscalls=5,
        avg_waiting_time=45.2,
        avg_execution_time=12.5,
        avg_total_time=57.7,
        p50_waiting_time=40.0,
        p90_waiting_time=80.0,
        p99_waiting_time=120.0,
        syscalls_per_second=40.0,
        fairness_index=0.85,
    )
    
    rr_result = BenchmarkResult(
        name="demo",
        strategy="round_robin",
        agent_count=4,
        duration_seconds=5.0,
        total_syscalls=200,
        successful_syscalls=198,
        failed_syscalls=2,
        avg_waiting_time=52.1,
        avg_execution_time=12.5,
        avg_total_time=64.6,
        p50_waiting_time=45.0,
        p90_waiting_time=75.0,
        p99_waiting_time=100.0,
        syscalls_per_second=40.0,
        fairness_index=0.98,
    )
    
    print(f"  {'Metric':<25} {'FIFO':>12} {'Round Robin':>12}")
    print(f"  {'-'*50}")
    print(f"  {'Avg Wait Time (ms)':<25} {fifo_result.avg_waiting_time:>12.2f} {rr_result.avg_waiting_time:>12.2f}")
    print(f"  {'P90 Wait Time (ms)':<25} {fifo_result.p90_waiting_time:>12.2f} {rr_result.p90_waiting_time:>12.2f}")
    print(f"  {'Fairness Index':<25} {fifo_result.fairness_index:>12.3f} {rr_result.fairness_index:>12.3f}")
    print(f"  {'Success Rate':<25} {fifo_result.successful_syscalls/fifo_result.total_syscalls*100:>11.1f}% {rr_result.successful_syscalls/rr_result.total_syscalls*100:>11.1f}%")
    
    # 4. ASCII Bar Chart
    print_section("4. Visualization")
    
    from aios.evaluation.plots import generate_ascii_bar_chart
    
    data = {
        "agent-0": 52,
        "agent-1": 48,
        "agent-2": 50,
        "agent-3": 50,
    }
    
    chart = generate_ascii_bar_chart("Syscalls per Agent", data, width=30)
    for line in chart.split("\n"):
        print(f"  {line}")
    
    # 5. Benchmark Suite
    print_section("5. Benchmark Suite")
    
    from aios.evaluation.benchmark import BenchmarkSuite, BenchmarkTask
    
    suite = BenchmarkSuite(
        name="math-test",
        description="Basic math problems"
    )
    suite.add_task(BenchmarkTask("1", "What is 2+2?", "4"))
    suite.add_task(BenchmarkTask("2", "What is 10*10?", "100"))
    suite.add_task(BenchmarkTask("3", "What is 144/12?", "12"))
    
    print_result(f"Created suite '{suite.name}' with {len(suite)} tasks")
    for task in suite.tasks:
        print(f"    Task {task.task_id}: {task.prompt[:30]}...")
    
    # Summary
    print_header("Demo Complete!")
    
    print(f"""
  {Colors.CYAN}The AIOS Evaluation Framework provides:

  ┌──────────────────────────────────────────────────────┐
  │  MetricsCollector   - Syscall timing & throughput    │
  │  EvaluationHarness  - Multi-agent workload runner    │
  │  BenchmarkRunner    - Task-based benchmarks          │
  │  Plotting           - Reports & visualizations       │
  └──────────────────────────────────────────────────────┘

  Paper Reference: Section 4, Figures 6-15{Colors.END}
""")


if __name__ == "__main__":
    asyncio.run(main())

