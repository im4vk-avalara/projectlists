#!/usr/bin/env python3
"""
Self-Correcting Codeforces Tutor - CLI Entry Point

Usage:
    python main.py                    # Interactive mode
    python main.py --demo             # Run demo with example problem
    python main.py --problem FILE     # Load problem from file
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from src.tutor import Tutor, TutorOutput
from src.config import config


# Demo problem: A simple Codeforces-style problem
DEMO_PROBLEM = """
# Sum of Array

Time limit: 1 second
Memory limit: 256 MB

## Problem Statement

You are given an array of n integers. Find the sum of all elements in the array.

## Input

The first line contains a single integer n (1 ≤ n ≤ 10^5) — the number of elements.
The second line contains n space-separated integers a_1, a_2, ..., a_n (1 ≤ a_i ≤ 10^9) — the elements of the array.

## Output

Print a single integer — the sum of all elements.

## Examples

Input
5
1 2 3 4 5

Output
15

Input
3
10 20 30

Output
60

## Note

In the first example, 1 + 2 + 3 + 4 + 5 = 15.
"""

# Brute-force oracle for the demo problem
DEMO_ORACLE = """
import sys
input = sys.stdin.readline

n = int(input())
arr = list(map(int, input().split()))
print(sum(arr))
"""


def run_demo():
    """Run the tutor on a demo problem."""
    print("=" * 60)
    print("SELF-CORRECTING CODEFORCES TUTOR - DEMO")
    print("=" * 60)
    print()
    print("Problem: Sum of Array")
    print("This demo will solve a simple problem to show the flow.")
    print()
    
    # Initialize tutor
    try:
        tutor = Tutor()
    except ValueError as e:
        print(f"Error: {e}")
        print("Please set ALFA_CLAIM environment variable.")
        return
    
    # Define samples explicitly
    sample_inputs = [
        "5\n1 2 3 4 5",
        "3\n10 20 30"
    ]
    sample_outputs = [
        "15",
        "60"
    ]
    
    # Run tutor
    output = tutor.solve_with_samples(
        problem_statement=DEMO_PROBLEM,
        sample_inputs=sample_inputs,
        sample_outputs=sample_outputs,
        problem_id="DEMO-1",
        oracle_code=DEMO_ORACLE
    )
    
    print()
    print(output)


def run_interactive():
    """Run the tutor in interactive mode."""
    print("=" * 60)
    print("SELF-CORRECTING CODEFORCES TUTOR - INTERACTIVE MODE")
    print("=" * 60)
    print()
    print("Paste your problem statement, then enter 'END' on a new line.")
    print("Then provide sample inputs/outputs when prompted.")
    print()
    
    # Read problem statement
    print("Problem statement:")
    lines = []
    while True:
        try:
            line = input()
            if line.strip().upper() == 'END':
                break
            lines.append(line)
        except EOFError:
            break
    
    problem_statement = '\n'.join(lines)
    
    if not problem_statement.strip():
        print("No problem statement provided. Exiting.")
        return
    
    # Read samples
    samples_input = []
    samples_output = []
    
    print()
    print("How many sample test cases? ", end="")
    try:
        num_samples = int(input().strip())
    except (ValueError, EOFError):
        num_samples = 0
    
    for i in range(num_samples):
        print(f"\nSample {i+1} input (END to finish):")
        inp_lines = []
        while True:
            try:
                line = input()
                if line.strip().upper() == 'END':
                    break
                inp_lines.append(line)
            except EOFError:
                break
        samples_input.append('\n'.join(inp_lines))
        
        print(f"Sample {i+1} expected output (END to finish):")
        out_lines = []
        while True:
            try:
                line = input()
                if line.strip().upper() == 'END':
                    break
                out_lines.append(line)
            except EOFError:
                break
        samples_output.append('\n'.join(out_lines))
    
    # Initialize and run tutor
    try:
        tutor = Tutor()
    except ValueError as e:
        print(f"Error: {e}")
        print("Please set ALFA_CLAIM environment variable.")
        return
    
    print()
    print("Solving problem...")
    print()
    
    output = tutor.solve_with_samples(
        problem_statement=problem_statement,
        sample_inputs=samples_input,
        sample_outputs=samples_output
    )
    
    print()
    print(output)


def run_from_file(filepath: str):
    """Run the tutor on a problem from a file."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}")
        return
    
    with open(path, 'r') as f:
        problem_statement = f.read()
    
    print(f"Loaded problem from: {filepath}")
    print()
    
    # Initialize and run tutor
    try:
        tutor = Tutor()
    except ValueError as e:
        print(f"Error: {e}")
        print("Please set ALFA_CLAIM environment variable.")
        return
    
    # For file mode, samples should be in the problem statement
    output = tutor.solve(
        problem_statement=problem_statement,
        problem_id=path.stem
    )
    
    print()
    print(output)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Self-Correcting Codeforces Tutor"
    )
    parser.add_argument(
        '--demo',
        action='store_true',
        help='Run demo with example problem'
    )
    parser.add_argument(
        '--problem',
        type=str,
        help='Path to problem statement file'
    )
    parser.add_argument(
        '--model',
        type=str,
        default=None,
        help='LLM model to use (default: from config)'
    )
    
    args = parser.parse_args()
    
    if args.demo:
        run_demo()
    elif args.problem:
        run_from_file(args.problem)
    else:
        run_interactive()


if __name__ == "__main__":
    main()

