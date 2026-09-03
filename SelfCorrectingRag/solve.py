#!/usr/bin/env python3
"""
Quick solver script - Paste a Codeforces problem and get submittable code.

Usage:
    python solve.py

Then paste the problem statement and samples when prompted.
The final code will be saved to 'solution.py' for easy submission.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src import Tutor


def main():
    print("=" * 60)
    print("SELF-CORRECTING CODEFORCES SOLVER")
    print("=" * 60)
    print()
    print("Paste your problem statement, then type 'END' on a new line.")
    print()
    
    # Read problem statement
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
        print("No problem provided. Exiting.")
        return
    
    # Read samples
    print()
    print("How many sample test cases?")
    try:
        num_samples = int(input().strip())
    except (ValueError, EOFError):
        num_samples = 0
    
    samples_in = []
    samples_out = []
    
    for i in range(num_samples):
        print(f"\nSample {i+1} INPUT (type 'END' when done):")
        inp_lines = []
        while True:
            try:
                line = input()
                if line.strip().upper() == 'END':
                    break
                inp_lines.append(line)
            except EOFError:
                break
        samples_in.append('\n'.join(inp_lines))
        
        print(f"Sample {i+1} EXPECTED OUTPUT (type 'END' when done):")
        out_lines = []
        while True:
            try:
                line = input()
                if line.strip().upper() == 'END':
                    break
                out_lines.append(line)
            except EOFError:
                break
        samples_out.append('\n'.join(out_lines))
    
    # Optional: oracle code for stress testing
    print("\nDo you have a brute-force solution for stress testing? (y/n)")
    has_oracle = input().strip().lower() == 'y'
    oracle = None
    
    if has_oracle:
        print("Paste brute-force code, then 'END':")
        oracle_lines = []
        while True:
            try:
                line = input()
                if line.strip().upper() == 'END':
                    break
                oracle_lines.append(line)
            except EOFError:
                break
        oracle = '\n'.join(oracle_lines)
    
    # Solve
    print()
    print("=" * 60)
    print("SOLVING...")
    print("=" * 60)
    print()
    
    tutor = Tutor()
    output = tutor.solve_with_samples(
        problem_statement=problem_statement,
        sample_inputs=samples_in,
        sample_outputs=samples_out,
        oracle_code=oracle
    )
    
    # Show output
    print()
    print(output)
    
    # Save code to file
    code = output.code
    with open('solution.py', 'w') as f:
        f.write(code)
    
    print()
    print("=" * 60)
    print("📄 CODE SAVED TO: solution.py")
    print("=" * 60)
    print()
    print("You can submit this code to Codeforces!")
    print()
    print("--- SUBMITTABLE CODE ---")
    print(code)
    print("--- END CODE ---")


if __name__ == "__main__":
    main()

