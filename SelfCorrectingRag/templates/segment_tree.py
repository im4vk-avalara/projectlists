"""Segment Tree Template - Range queries and point updates"""

from typing import List, Callable, TypeVar

T = TypeVar('T')


class SegmentTree:
    """
    Segment Tree for range queries and point updates.
    Supports any associative operation (sum, min, max, gcd, etc.)
    """
    
    def __init__(
        self, 
        arr: List[T], 
        merge: Callable[[T, T], T],
        identity: T
    ):
        """
        Initialize segment tree.
        
        Args:
            arr: Initial array
            merge: Associative function to combine two values
            identity: Identity element for merge (0 for sum, inf for min, etc.)
        """
        self.n = len(arr)
        self.merge = merge
        self.identity = identity
        self.tree = [identity] * (2 * self.n)
        
        # Build tree
        for i in range(self.n):
            self.tree[self.n + i] = arr[i]
        for i in range(self.n - 1, 0, -1):
            self.tree[i] = merge(self.tree[2*i], self.tree[2*i+1])
    
    def update(self, pos: int, val: T) -> None:
        """Update position pos to value val."""
        pos += self.n
        self.tree[pos] = val
        while pos > 1:
            pos //= 2
            self.tree[pos] = self.merge(self.tree[2*pos], self.tree[2*pos+1])
    
    def query(self, left: int, right: int) -> T:
        """Query range [left, right) - right is exclusive."""
        result = self.identity
        left += self.n
        right += self.n
        
        while left < right:
            if left & 1:
                result = self.merge(result, self.tree[left])
                left += 1
            if right & 1:
                right -= 1
                result = self.merge(result, self.tree[right])
            left //= 2
            right //= 2
        
        return result


# Common segment tree variants
def sum_segment_tree(arr: List[int]) -> SegmentTree:
    """Create a sum segment tree."""
    return SegmentTree(arr, lambda a, b: a + b, 0)


def min_segment_tree(arr: List[int]) -> SegmentTree:
    """Create a min segment tree."""
    return SegmentTree(arr, min, float('inf'))


def max_segment_tree(arr: List[int]) -> SegmentTree:
    """Create a max segment tree."""
    return SegmentTree(arr, max, float('-inf'))


# Example usage:
# st = sum_segment_tree([1, 2, 3, 4, 5])
# print(st.query(0, 3))  # Sum of arr[0:3] = 6
# st.update(1, 10)       # arr[1] = 10
# print(st.query(0, 3))  # Sum = 1 + 10 + 3 = 14

