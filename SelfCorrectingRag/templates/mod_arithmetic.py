"""Modular Arithmetic Templates"""

MOD = 10**9 + 7  # Common modulo in competitive programming


def mod_pow(base: int, exp: int, mod: int = MOD) -> int:
    """
    Fast modular exponentiation: base^exp mod mod
    Time: O(log exp)
    """
    result = 1
    base %= mod
    while exp > 0:
        if exp & 1:
            result = result * base % mod
        exp >>= 1
        base = base * base % mod
    return result


def mod_inverse(a: int, mod: int = MOD) -> int:
    """
    Modular multiplicative inverse using Fermat's little theorem.
    Only works when mod is prime!
    a^(-1) ≡ a^(mod-2) (mod mod)
    """
    return mod_pow(a, mod - 2, mod)


def mod_divide(a: int, b: int, mod: int = MOD) -> int:
    """
    Division under modulo: (a / b) mod mod
    Only works when mod is prime!
    """
    return a * mod_inverse(b, mod) % mod


class ModInt:
    """Integer wrapper that automatically applies modulo."""
    
    def __init__(self, val: int, mod: int = MOD):
        self.val = val % mod
        self.mod = mod
    
    def __add__(self, other):
        if isinstance(other, ModInt):
            return ModInt((self.val + other.val) % self.mod, self.mod)
        return ModInt((self.val + other) % self.mod, self.mod)
    
    def __sub__(self, other):
        if isinstance(other, ModInt):
            return ModInt((self.val - other.val + self.mod) % self.mod, self.mod)
        return ModInt((self.val - other + self.mod) % self.mod, self.mod)
    
    def __mul__(self, other):
        if isinstance(other, ModInt):
            return ModInt(self.val * other.val % self.mod, self.mod)
        return ModInt(self.val * other % self.mod, self.mod)
    
    def __truediv__(self, other):
        if isinstance(other, ModInt):
            return ModInt(mod_divide(self.val, other.val, self.mod), self.mod)
        return ModInt(mod_divide(self.val, other, self.mod), self.mod)
    
    def __pow__(self, exp):
        return ModInt(mod_pow(self.val, exp, self.mod), self.mod)
    
    def __repr__(self):
        return f"ModInt({self.val})"
    
    def __int__(self):
        return self.val


# Precompute factorials for nCr calculations
class Combinatorics:
    """Precomputed factorials for fast nCr calculations."""
    
    def __init__(self, max_n: int, mod: int = MOD):
        self.mod = mod
        self.fact = [1] * (max_n + 1)
        self.inv_fact = [1] * (max_n + 1)
        
        for i in range(1, max_n + 1):
            self.fact[i] = self.fact[i-1] * i % mod
        
        self.inv_fact[max_n] = mod_inverse(self.fact[max_n], mod)
        for i in range(max_n - 1, -1, -1):
            self.inv_fact[i] = self.inv_fact[i+1] * (i+1) % mod
    
    def nCr(self, n: int, r: int) -> int:
        """Compute C(n, r) = n! / (r! * (n-r)!)"""
        if r < 0 or r > n:
            return 0
        return self.fact[n] * self.inv_fact[r] % self.mod * self.inv_fact[n-r] % self.mod
    
    def nPr(self, n: int, r: int) -> int:
        """Compute P(n, r) = n! / (n-r)!"""
        if r < 0 or r > n:
            return 0
        return self.fact[n] * self.inv_fact[n-r] % self.mod


# Example usage:
# print(mod_pow(2, 10))  # 1024
# print(mod_inverse(2))  # 500000004 (2^(-1) mod 10^9+7)
# 
# comb = Combinatorics(100000)
# print(comb.nCr(10, 3))  # 120

