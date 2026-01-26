"""Fast I/O Templates for Competitive Programming"""

import sys
from typing import List, Tuple


# ============ FAST INPUT ============

def setup_fast_io():
    """Setup fast I/O for interactive problems."""
    input = sys.stdin.readline
    return input


def read_all() -> List[str]:
    """Read all input at once and split into tokens."""
    return sys.stdin.read().split()


class FastReader:
    """
    Fast reader that reads all input at once.
    Much faster than line-by-line for large inputs.
    """
    
    def __init__(self):
        self.tokens = iter(sys.stdin.read().split())
    
    def next(self) -> str:
        return next(self.tokens)
    
    def next_int(self) -> int:
        return int(next(self.tokens))
    
    def next_float(self) -> float:
        return float(next(self.tokens))
    
    def next_line(self) -> str:
        # Note: This doesn't work well with mixed usage
        return next(self.tokens)
    
    def next_ints(self, n: int) -> List[int]:
        return [self.next_int() for _ in range(n)]
    
    def next_array(self) -> List[int]:
        """Read n followed by n integers."""
        n = self.next_int()
        return self.next_ints(n)


# ============ FAST OUTPUT ============

class FastWriter:
    """Buffer output for faster printing."""
    
    def __init__(self):
        self.buffer = []
    
    def write(self, *args, sep=' ', end='\n'):
        self.buffer.append(sep.join(map(str, args)) + end)
    
    def flush(self):
        sys.stdout.write(''.join(self.buffer))
        self.buffer.clear()


def print_fast(*args, sep=' ', end='\n'):
    """Faster print using sys.stdout.write."""
    sys.stdout.write(sep.join(map(str, args)) + end)


# ============ COMMON INPUT PATTERNS ============

def read_int() -> int:
    """Read a single integer."""
    return int(sys.stdin.readline())


def read_ints() -> List[int]:
    """Read a line of space-separated integers."""
    return list(map(int, sys.stdin.readline().split()))


def read_str() -> str:
    """Read a line and strip whitespace."""
    return sys.stdin.readline().strip()


def read_grid(rows: int) -> List[List[int]]:
    """Read a grid of integers."""
    return [read_ints() for _ in range(rows)]


def read_graph_edges(m: int, directed: bool = False, one_indexed: bool = True) -> List[List[int]]:
    """
    Read m edges and build adjacency list.
    
    Args:
        m: Number of edges
        directed: If False, add edges in both directions
        one_indexed: If True, subtract 1 from node indices
    """
    n = read_int()
    adj = [[] for _ in range(n)]
    
    for _ in range(m):
        u, v = read_ints()
        if one_indexed:
            u -= 1
            v -= 1
        adj[u].append(v)
        if not directed:
            adj[v].append(u)
    
    return adj


# ============ TEMPLATE MAIN ============

def solve():
    """Main solution function - replace with actual logic."""
    n = read_int()
    arr = read_ints()
    
    # Solution here
    result = sum(arr)
    
    print(result)


def main():
    """Main entry point with optional multiple test cases."""
    t = read_int()  # Number of test cases
    for _ in range(t):
        solve()


# Uncomment for single test case:
# if __name__ == "__main__":
#     solve()

# Uncomment for multiple test cases:
# if __name__ == "__main__":
#     main()

