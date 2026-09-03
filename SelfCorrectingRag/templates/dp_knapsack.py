"""Knapsack DP Templates"""

from typing import List, Tuple


def knapsack_01(weights: List[int], values: List[int], capacity: int) -> int:
    """
    0/1 Knapsack: Each item can be taken at most once.
    Returns maximum value achievable within capacity.
    
    Time: O(n * capacity)
    Space: O(capacity)
    """
    n = len(weights)
    dp = [0] * (capacity + 1)
    
    for i in range(n):
        # Iterate backwards to avoid using same item twice
        for w in range(capacity, weights[i] - 1, -1):
            dp[w] = max(dp[w], dp[w - weights[i]] + values[i])
    
    return dp[capacity]


def knapsack_unbounded(weights: List[int], values: List[int], capacity: int) -> int:
    """
    Unbounded Knapsack: Each item can be taken unlimited times.
    Returns maximum value achievable within capacity.
    
    Time: O(n * capacity)
    Space: O(capacity)
    """
    dp = [0] * (capacity + 1)
    
    for w in range(1, capacity + 1):
        for i in range(len(weights)):
            if weights[i] <= w:
                dp[w] = max(dp[w], dp[w - weights[i]] + values[i])
    
    return dp[capacity]


def subset_sum(nums: List[int], target: int) -> bool:
    """
    Check if there's a subset with given sum.
    
    Time: O(n * target)
    Space: O(target)
    """
    dp = [False] * (target + 1)
    dp[0] = True
    
    for num in nums:
        for s in range(target, num - 1, -1):
            dp[s] = dp[s] or dp[s - num]
    
    return dp[target]


def count_subset_sum(nums: List[int], target: int) -> int:
    """
    Count number of subsets with given sum.
    
    Time: O(n * target)
    Space: O(target)
    """
    dp = [0] * (target + 1)
    dp[0] = 1
    
    for num in nums:
        for s in range(target, num - 1, -1):
            dp[s] += dp[s - num]
    
    return dp[target]


def coin_change_min(coins: List[int], amount: int) -> int:
    """
    Minimum coins needed to make amount.
    Returns -1 if impossible.
    
    Time: O(n * amount)
    Space: O(amount)
    """
    dp = [float('inf')] * (amount + 1)
    dp[0] = 0
    
    for coin in coins:
        for a in range(coin, amount + 1):
            dp[a] = min(dp[a], dp[a - coin] + 1)
    
    return dp[amount] if dp[amount] != float('inf') else -1


def coin_change_count(coins: List[int], amount: int) -> int:
    """
    Count number of ways to make amount using coins.
    
    Time: O(n * amount)
    Space: O(amount)
    """
    dp = [0] * (amount + 1)
    dp[0] = 1
    
    for coin in coins:
        for a in range(coin, amount + 1):
            dp[a] += dp[a - coin]
    
    return dp[amount]


# Example usage:
# weights = [1, 2, 3]
# values = [6, 10, 12]
# capacity = 5
# print(knapsack_01(weights, values, capacity))  # 22 (items 1 and 2)

