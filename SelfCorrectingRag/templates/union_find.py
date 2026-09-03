"""Union-Find (Disjoint Set Union) Template"""


class DSU:
    """Disjoint Set Union with path compression and union by rank."""
    
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n
        self.size = [1] * n  # Size of each component
        self.components = n   # Number of components
    
    def find(self, x: int) -> int:
        """Find root with path compression."""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x: int, y: int) -> bool:
        """
        Union two sets. Returns True if they were in different sets.
        """
        px, py = self.find(x), self.find(y)
        if px == py:
            return False
        
        # Union by rank
        if self.rank[px] < self.rank[py]:
            px, py = py, px
        self.parent[py] = px
        self.size[px] += self.size[py]
        
        if self.rank[px] == self.rank[py]:
            self.rank[px] += 1
        
        self.components -= 1
        return True
    
    def connected(self, x: int, y: int) -> bool:
        """Check if x and y are in the same set."""
        return self.find(x) == self.find(y)
    
    def get_size(self, x: int) -> int:
        """Get size of the component containing x."""
        return self.size[self.find(x)]


# Example usage:
# dsu = DSU(n)
# dsu.union(0, 1)
# print(dsu.connected(0, 1))  # True
# print(dsu.components)  # n - 1

