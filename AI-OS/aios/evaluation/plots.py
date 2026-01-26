"""
AIOS Evaluation Plots

Generates plots for evaluation results.

Paper Reference: Section 4, Figures 6-15
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from pathlib import Path

from aios.evaluation.metrics import BenchmarkResult


@dataclass
class PlotData:
    """Data for a single plot."""
    title: str
    x_label: str
    y_label: str
    data: Dict[str, List[float]]


def generate_comparison_report(
    fifo_result: BenchmarkResult,
    rr_result: BenchmarkResult,
) -> str:
    """
    Generate a text comparison report.
    
    Paper Reference: Section 4.2, Figures 6-7
    """
    lines = [
        "=" * 70,
        "AIOS Scheduling Strategy Comparison",
        "=" * 70,
        "",
        f"Workload: {fifo_result.name}",
        f"Agent Count: {fifo_result.agent_count}",
        f"Total Syscalls: {fifo_result.total_syscalls}",
        "",
        "-" * 70,
        f"{'Metric':<30} {'FIFO':>15} {'Round Robin':>15}",
        "-" * 70,
        f"{'Avg Waiting Time (ms)':<30} {fifo_result.avg_waiting_time:>15.2f} {rr_result.avg_waiting_time:>15.2f}",
        f"{'Avg Execution Time (ms)':<30} {fifo_result.avg_execution_time:>15.2f} {rr_result.avg_execution_time:>15.2f}",
        f"{'P50 Waiting Time (ms)':<30} {fifo_result.p50_waiting_time:>15.2f} {rr_result.p50_waiting_time:>15.2f}",
        f"{'P90 Waiting Time (ms)':<30} {fifo_result.p90_waiting_time:>15.2f} {rr_result.p90_waiting_time:>15.2f}",
        f"{'P99 Waiting Time (ms)':<30} {fifo_result.p99_waiting_time:>15.2f} {rr_result.p99_waiting_time:>15.2f}",
        f"{'Syscalls/Second':<30} {fifo_result.syscalls_per_second:>15.2f} {rr_result.syscalls_per_second:>15.2f}",
        f"{'Fairness Index':<30} {fifo_result.fairness_index:>15.3f} {rr_result.fairness_index:>15.3f}",
        f"{'Success Rate':<30} {fifo_result.successful_syscalls/fifo_result.total_syscalls*100:>14.1f}% {rr_result.successful_syscalls/rr_result.total_syscalls*100:>14.1f}%",
        "-" * 70,
        "",
    ]
    
    # Per-agent comparison
    lines.append("Per-Agent Waiting Times (ms):")
    lines.append("-" * 70)
    lines.append(f"{'Agent':<20} {'FIFO Avg Wait':>20} {'RR Avg Wait':>20}")
    lines.append("-" * 70)
    
    for agent_id in sorted(fifo_result.agent_metrics.keys()):
        fifo_agent = fifo_result.agent_metrics.get(agent_id)
        rr_agent = rr_result.agent_metrics.get(agent_id)
        
        if fifo_agent and rr_agent:
            lines.append(
                f"{agent_id:<20} "
                f"{fifo_agent.avg_waiting_time:>20.2f} "
                f"{rr_agent.avg_waiting_time:>20.2f}"
            )
    
    lines.append("-" * 70)
    lines.append("")
    lines.append("Analysis:")
    
    # Analysis
    if rr_result.fairness_index > fifo_result.fairness_index:
        lines.append("• Round Robin provides better fairness across agents")
    else:
        lines.append("• FIFO provides comparable or better fairness")
    
    if fifo_result.avg_waiting_time < rr_result.avg_waiting_time:
        lines.append("• FIFO has lower average waiting time (better throughput)")
    else:
        lines.append("• Round Robin has lower average waiting time")
    
    lines.append("")
    lines.append("=" * 70)
    
    return "\n".join(lines)


def generate_scaling_report(
    results: List[BenchmarkResult],
) -> str:
    """
    Generate a scaling evaluation report.
    
    Paper Reference: Section 4.2, Figure 8
    """
    lines = [
        "=" * 70,
        "AIOS Scaling Evaluation",
        "=" * 70,
        "",
        f"Strategy: {results[0].strategy if results else 'N/A'}",
        "",
        "-" * 70,
        f"{'Agents':<10} {'Syscalls':>12} {'Throughput':>15} {'Avg Wait (ms)':>15} {'Fairness':>12}",
        "-" * 70,
    ]
    
    for result in results:
        lines.append(
            f"{result.agent_count:<10} "
            f"{result.total_syscalls:>12} "
            f"{result.syscalls_per_second:>15.2f} "
            f"{result.avg_waiting_time:>15.2f} "
            f"{result.fairness_index:>12.3f}"
        )
    
    lines.append("-" * 70)
    lines.append("")
    
    # Calculate scaling efficiency
    if len(results) >= 2:
        base = results[0]
        for result in results[1:]:
            scale_factor = result.agent_count / base.agent_count
            throughput_ratio = result.syscalls_per_second / base.syscalls_per_second
            efficiency = throughput_ratio / scale_factor * 100
            
            lines.append(
                f"Scaling efficiency at {result.agent_count} agents: {efficiency:.1f}%"
            )
    
    lines.append("")
    lines.append("=" * 70)
    
    return "\n".join(lines)


def generate_ascii_bar_chart(
    title: str,
    data: Dict[str, float],
    width: int = 50,
) -> str:
    """Generate an ASCII bar chart."""
    if not data:
        return "No data"
    
    max_val = max(data.values())
    max_label_len = max(len(k) for k in data.keys())
    
    lines = [title, "-" * (max_label_len + width + 10)]
    
    for label, value in data.items():
        bar_len = int((value / max_val) * width) if max_val > 0 else 0
        bar = "█" * bar_len
        lines.append(f"{label:<{max_label_len}} │{bar} {value:.2f}")
    
    lines.append("-" * (max_label_len + width + 10))
    
    return "\n".join(lines)


def export_results_json(
    results: List[BenchmarkResult],
    output_path: str,
) -> None:
    """Export results to JSON for external plotting."""
    data = [r.to_dict() for r in results]
    
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)


def generate_html_report(
    results: Dict[str, BenchmarkResult],
    output_path: str,
) -> None:
    """Generate an HTML report with embedded charts."""
    html = """<!DOCTYPE html>
<html>
<head>
    <title>AIOS Evaluation Report</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 40px; }
        h1 { color: #2c3e50; }
        h2 { color: #34495e; border-bottom: 2px solid #3498db; padding-bottom: 10px; }
        table { border-collapse: collapse; width: 100%; margin: 20px 0; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background-color: #3498db; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .metric { font-weight: bold; }
        .good { color: #27ae60; }
        .bar { background: linear-gradient(90deg, #3498db 0%, #2980b9 100%); height: 20px; border-radius: 4px; }
        .chart-container { margin: 20px 0; }
    </style>
</head>
<body>
    <h1>AIOS Evaluation Report</h1>
    <p>Generated by AIOS Evaluation Framework</p>
"""
    
    # Summary table
    html += "<h2>Strategy Comparison</h2>\n<table>\n"
    html += "<tr><th>Metric</th>"
    for strategy in results.keys():
        html += f"<th>{strategy.upper()}</th>"
    html += "</tr>\n"
    
    metrics = [
        ("Total Syscalls", lambda r: r.total_syscalls),
        ("Avg Waiting Time (ms)", lambda r: f"{r.avg_waiting_time:.2f}"),
        ("Avg Execution Time (ms)", lambda r: f"{r.avg_execution_time:.2f}"),
        ("Throughput (syscalls/s)", lambda r: f"{r.syscalls_per_second:.2f}"),
        ("Fairness Index", lambda r: f"{r.fairness_index:.3f}"),
    ]
    
    for metric_name, getter in metrics:
        html += f"<tr><td class='metric'>{metric_name}</td>"
        for result in results.values():
            html += f"<td>{getter(result)}</td>"
        html += "</tr>\n"
    
    html += "</table>\n"
    
    # Per-agent chart
    html += "<h2>Per-Agent Waiting Times</h2>\n"
    
    for strategy, result in results.items():
        html += f"<h3>{strategy.upper()}</h3>\n"
        html += "<div class='chart-container'>\n"
        
        max_wait = max(m.avg_waiting_time for m in result.agent_metrics.values()) if result.agent_metrics else 1
        
        for agent_id, metrics in sorted(result.agent_metrics.items()):
            width = (metrics.avg_waiting_time / max_wait) * 100 if max_wait > 0 else 0
            html += f"<div>{agent_id}: <div class='bar' style='width: {width}%'></div> {metrics.avg_waiting_time:.2f}ms</div>\n"
        
        html += "</div>\n"
    
    html += "</body></html>"
    
    with open(output_path, "w") as f:
        f.write(html)

