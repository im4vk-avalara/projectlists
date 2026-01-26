"""BFS and DFS Templates for Graphs and Grids"""

from collections import deque
from typing import List, Tuple, Set, Optional


def bfs_graph(adj: List[List[int]], start: int, target: int = -1) -> List[int]:
    """
    BFS on adjacency list graph.
    Returns distances from start to all nodes (-1 if unreachable).
    
    Args:
        adj: Adjacency list
        start: Starting node
        target: Optional early termination target
    """
    n = len(adj)
    dist = [-1] * n
    dist[start] = 0
    queue = deque([start])
    
    while queue:
        node = queue.popleft()
        if node == target:
            break
        for neighbor in adj[node]:
            if dist[neighbor] == -1:
                dist[neighbor] = dist[node] + 1
                queue.append(neighbor)
    
    return dist


def bfs_grid(
    grid: List[List[int]], 
    start: Tuple[int, int],
    target: Optional[Tuple[int, int]] = None,
    blocked: int = 1
) -> List[List[int]]:
    """
    BFS on 2D grid. Returns distance matrix.
    
    Args:
        grid: 2D grid
        start: (row, col) starting position
        target: Optional (row, col) for early termination
        blocked: Value representing blocked cells
    """
    rows, cols = len(grid), len(grid[0])
    dist = [[-1] * cols for _ in range(rows)]
    
    sr, sc = start
    if grid[sr][sc] == blocked:
        return dist
    
    dist[sr][sc] = 0
    queue = deque([start])
    
    # 4 directions: up, down, left, right
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
    
    while queue:
        r, c = queue.popleft()
        if target and (r, c) == target:
            break
        
        for dr, dc in directions:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols:
                if dist[nr][nc] == -1 and grid[nr][nc] != blocked:
                    dist[nr][nc] = dist[r][c] + 1
                    queue.append((nr, nc))
    
    return dist


def dfs_iterative(adj: List[List[int]], start: int) -> List[int]:
    """
    Iterative DFS returning visited order.
    """
    n = len(adj)
    visited = [False] * n
    order = []
    stack = [start]
    
    while stack:
        node = stack.pop()
        if visited[node]:
            continue
        visited[node] = True
        order.append(node)
        
        for neighbor in reversed(adj[node]):  # Reverse for consistent order
            if not visited[neighbor]:
                stack.append(neighbor)
    
    return order


def dfs_recursive(adj: List[List[int]], start: int) -> Tuple[List[int], List[int]]:
    """
    Recursive DFS returning (entry_time, exit_time) for each node.
    Useful for tree queries, cycle detection, etc.
    """
    n = len(adj)
    visited = [False] * n
    entry = [0] * n
    exit_time = [0] * n
    timer = [0]  # Mutable for closure
    
    def dfs(node: int, parent: int = -1):
        visited[node] = True
        entry[node] = timer[0]
        timer[0] += 1
        
        for neighbor in adj[node]:
            if not visited[neighbor]:
                dfs(neighbor, node)
        
        exit_time[node] = timer[0]
        timer[0] += 1
    
    dfs(start)
    return entry, exit_time


def find_connected_components(adj: List[List[int]]) -> List[List[int]]:
    """Find all connected components in undirected graph."""
    n = len(adj)
    visited = [False] * n
    components = []
    
    for start in range(n):
        if visited[start]:
            continue
        
        component = []
        stack = [start]
        
        while stack:
            node = stack.pop()
            if visited[node]:
                continue
            visited[node] = True
            component.append(node)
            
            for neighbor in adj[node]:
                if not visited[neighbor]:
                    stack.append(neighbor)
        
        components.append(component)
    
    return components


def topological_sort(adj: List[List[int]]) -> List[int]:
    """
    Topological sort using Kahn's algorithm (BFS).
    Returns empty list if cycle exists.
    """
    n = len(adj)
    in_degree = [0] * n
    
    for node in range(n):
        for neighbor in adj[node]:
            in_degree[neighbor] += 1
    
    queue = deque([node for node in range(n) if in_degree[node] == 0])
    order = []
    
    while queue:
        node = queue.popleft()
        order.append(node)
        
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    
    return order if len(order) == n else []  # Empty if cycle


# Example usage:
# adj = [[1, 2], [2], []]  # 0->1, 0->2, 1->2
# print(bfs_graph(adj, 0))  # [0, 1, 1]
# print(topological_sort(adj))  # [0, 1, 2]

