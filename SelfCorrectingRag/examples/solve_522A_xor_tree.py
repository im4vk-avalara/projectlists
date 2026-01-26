#!/usr/bin/env python3
"""
Example: Solving Codeforces 522A - Reposts (simplified as Tree DP)
https://codeforces.com/problemset/problem/522/A

Difficulty: D (Tree DP / DFS on Graph)

Run: python examples/solve_522A_reposts.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import Tutor


# Codeforces 522A - Reposts
PROBLEM = '''
# A. Reposts
Time limit: 1 second
Memory limit: 256 MB

## Problem Statement
One day Polycarp published a funny picture in a social network making a post. 
His friends started reposting Polycarp's post to their news feed. 
Some of them repost the reposts and so on.

Given the reposts in format "name1 reposted name2", meaning that name1 
reposted from name2. Find the longest chain of reposts.

The initial post is by "polycarp" (case insensitive).

## Input
The first line contains integer n (1 ≤ n ≤ 200) — the number of reposts.

The next n lines contain the repost descriptions as "name1 reposted name2" 
(without quotes). All the names in input consist of lowercase or uppercase 
English letters and are no longer than 24 characters.

It is guaranteed that all the names in repost descriptions are mentioned 
in input at least once.

## Output
Print the maximum length of the repost chain. 
(Polycarp's initial post counts as length 1)
'''

SAMPLE_INPUTS = [
    '''5
tourist reposted Polycarp
Petr reposted Tourist
WJMZBMR reposted Petr
sdya reposted wjmzbmr
vepifanov reposted sdya''',
    '''6
Mike reposted Polycarp
Max reposted Polycarp
EveryOne reposted Polycarp
111 reposted Polycarp
VosMarik reposted Polycarp
Linderman reposted Polycarp'''
]
SAMPLE_OUTPUTS = ['6', '2']

# Oracle: Build graph and find longest path from polycarp
ORACLE = '''
import sys
from collections import defaultdict
sys.setrecursionlimit(10000)

n = int(input())

# Build adjacency list (parent -> children)
children = defaultdict(list)
depth = {}

for _ in range(n):
    line = input().split()
    name1 = line[0].lower()
    name2 = line[2].lower()
    children[name2].append(name1)

# DFS to find max depth
def dfs(node):
    if node not in children or not children[node]:
        return 1
    max_child = 0
    for child in children[node]:
        max_child = max(max_child, dfs(child))
    return max_child + 1

print(dfs('polycarp'))
'''


def main():
    print('=' * 60)
    print('Solving Codeforces 522A - Reposts')
    print('https://codeforces.com/problemset/problem/522/A')
    print('Difficulty: D (Tree/Graph DFS)')
    print('=' * 60)
    print()
    
    tutor = Tutor()
    
    output = tutor.solve_with_samples(
        problem_statement=PROBLEM,
        sample_inputs=SAMPLE_INPUTS,
        sample_outputs=SAMPLE_OUTPUTS,
        problem_id='522A',
        oracle_code=ORACLE
    )
    
    print()
    print(output)
    
    # Save submittable code
    code = output.code
    output_file = Path(__file__).parent.parent / 'solution_522A.py'
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

