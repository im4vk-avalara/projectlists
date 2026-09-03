"""Binary Search Template - Find first position where condition is True"""


def binary_search_first_true(lo: int, hi: int, check) -> int:
    """
    Find the first value x in [lo, hi] where check(x) is True.
    Assumes check(x) is monotonic: False, False, ..., True, True
    Returns hi + 1 if no such x exists.
    """
    while lo < hi:
        mid = (lo + hi) // 2
        if check(mid):
            hi = mid
        else:
            lo = mid + 1
    return lo if check(lo) else hi + 1


def binary_search_last_true(lo: int, hi: int, check) -> int:
    """
    Find the last value x in [lo, hi] where check(x) is True.
    Assumes check(x) is monotonic: True, True, ..., False, False
    Returns lo - 1 if no such x exists.
    """
    while lo < hi:
        mid = (lo + hi + 1) // 2  # Round up to avoid infinite loop
        if check(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo if check(lo) else lo - 1


def binary_search_real(lo: float, hi: float, check, eps: float = 1e-9) -> float:
    """Binary search on real numbers with precision eps."""
    for _ in range(100):  # ~100 iterations gives ~10^-30 precision
        mid = (lo + hi) / 2
        if check(mid):
            hi = mid
        else:
            lo = mid
    return lo


# Example usage:
# Find minimum x such that arr[x] >= target
# ans = binary_search_first_true(0, n-1, lambda x: arr[x] >= target)

