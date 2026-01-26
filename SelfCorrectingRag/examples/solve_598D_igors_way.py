#!/usr/bin/env python3
"""
Example: Solving Codeforces 598D - Igor In the Museum
https://codeforces.com/problemset/problem/598/D

Difficulty: D (BFS/DFS with Component Preprocessing)

Run: python examples/solve_598D_igors_way.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import Tutor


# Codeforces 598D - Igor In the Museum
PROBLEM = '''
# D. Igor In the Museum
Time limit: 1 second
Memory limit: 256 MB

## Problem Statement
Igor is in a museum with n × m halls. Some halls are occupied by paintings 
(denoted by '*') and some are empty (denoted by '.'). Igor can only move 
through empty halls (4 directions: up, down, left, right).

For each query, Igor starts at some empty hall and wants to know how many 
paintings he can see. A painting is visible if it's adjacent (in 4 directions) 
to any hall Igor can reach from his starting position.

## Input
The first line contains three integers n, m, k (1 ≤ n, m ≤ 1000; 1 ≤ k ≤ 10^5) — 
the museum dimensions and the number of queries.

Each of the next n lines contains m characters — the museum description.

The next k lines contain two integers x, y (1 ≤ x ≤ n; 1 ≤ y ≤ m) — 
the starting position for each query. It is guaranteed that the starting 
position is always an empty hall.

## Output
For each query, print the number of paintings Igor can see.
'''

SAMPLE_INPUTS = [
    '''2 4 3
*.**
*...
1 2
1 3
2 4'''
]
SAMPLE_OUTPUTS = ['6\n6\n6']

# Oracle: BFS to precompute component paintings count
ORACLE = '''
import sys
from collections import deque
input = sys.stdin.readline

n, m, k = map(int, input().split())
grid = []
for _ in range(n):
    grid.append(input().strip())

# For each cell, store component ID and count
comp_id = [[-1] * m for _ in range(n)]
comp_count = {}  # component_id -> paintings count

directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
current_comp = 0

for i in range(n):
    for j in range(m):
        if grid[i][j] == '.' and comp_id[i][j] == -1:
            # BFS to find all cells in this component
            queue = deque([(i, j)])
            comp_id[i][j] = current_comp
            paintings = 0
            
            while queue:
                x, y = queue.popleft()
                
                for dx, dy in directions:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < n and 0 <= ny < m:
                        if grid[nx][ny] == '*':
                            paintings += 1
                        elif comp_id[nx][ny] == -1:
                            comp_id[nx][ny] = current_comp
                            queue.append((nx, ny))
            
            comp_count[current_comp] = paintings
            current_comp += 1

for _ in range(k):
    x, y = map(int, input().split())
    x -= 1
    y -= 1
    print(comp_count[comp_id[x][y]])
'''


def main():
    print('=' * 60)
    print('Solving Codeforces 598D - Igor In the Museum')
    print('https://codeforces.com/problemset/problem/598/D')
    print('Difficulty: D (BFS with Component Preprocessing)')
    print('=' * 60)
    print()
    
    tutor = Tutor()
    
    output = tutor.solve_with_samples(
        problem_statement=PROBLEM,
        sample_inputs=SAMPLE_INPUTS,
        sample_outputs=SAMPLE_OUTPUTS,
        problem_id='598D',
        oracle_code=ORACLE
    )
    
    print()
    print(output)
    
    # Save submittable code
    code = output.code
    output_file = Path(__file__).parent.parent / 'solution_598D.py'
    with open(output_file, 'w') as f:
        f.write(code)
    
    print()
    print('=' * 60)
    print('📋 SUBMITTABLE CODE:')
    print('=' * 60)
    print()
    print(code)
    print()
    print('=' * 60)
    print(f'💾 Saved to: {output_file}')
    print('=' * 60)


if __name__ == '__main__':
    main()

