"""
Stress Tester - Random test generation and oracle comparison.
"""

import random
import string
from typing import Optional, Callable, List, Tuple, Any
from dataclasses import dataclass, field

from .runner import TestRunner, ExecutionResult, ExecutionStatus
from ..parser.models import ProblemSpec, Constraints
from ..config import config


@dataclass
class StressTestResult:
    """Result of stress testing."""
    passed: bool
    tests_run: int
    first_failure: Optional[ExecutionResult] = None
    failing_input: Optional[str] = None
    oracle_output: Optional[str] = None
    
    def summary(self) -> str:
        if self.passed:
            return f"✓ Stress test PASSED ({self.tests_run} tests)"
        return (
            f"✗ Stress test FAILED at test #{self.tests_run}\n"
            f"Input: {self.failing_input[:200] if self.failing_input else 'N/A'}\n"
            f"Expected: {self.oracle_output[:100] if self.oracle_output else 'N/A'}\n"
            f"Got: {self.first_failure.output[:100] if self.first_failure else 'N/A'}"
        )


class InputGenerator:
    """
    Generates random test inputs based on constraints.
    """
    
    def __init__(self, constraints: Constraints, seed: Optional[int] = None):
        """
        Initialize generator with problem constraints.
        """
        self.constraints = constraints
        if seed is not None:
            random.seed(seed)
    
    def random_int(self, lo: int, hi: int) -> int:
        """Generate random integer in [lo, hi]."""
        return random.randint(lo, hi)
    
    def random_array(
        self, 
        n: int, 
        lo: int, 
        hi: int, 
        distinct: bool = False
    ) -> List[int]:
        """Generate random array of integers."""
        if distinct:
            if hi - lo + 1 < n:
                raise ValueError("Not enough distinct values in range")
            return random.sample(range(lo, hi + 1), n)
        return [random.randint(lo, hi) for _ in range(n)]
    
    def random_string(
        self, 
        length: int, 
        alphabet: str = string.ascii_lowercase
    ) -> str:
        """Generate random string."""
        return ''.join(random.choice(alphabet) for _ in range(length))
    
    def random_permutation(self, n: int) -> List[int]:
        """Generate random permutation of 1..n."""
        perm = list(range(1, n + 1))
        random.shuffle(perm)
        return perm
    
    def random_tree_edges(self, n: int) -> List[Tuple[int, int]]:
        """Generate random tree with n nodes (1-indexed)."""
        if n == 1:
            return []
        edges = []
        for i in range(2, n + 1):
            parent = random.randint(1, i - 1)
            edges.append((parent, i))
        random.shuffle(edges)
        return edges
    
    def random_graph_edges(
        self, 
        n: int, 
        m: int, 
        directed: bool = False,
        allow_self_loops: bool = False,
        allow_multi_edges: bool = False
    ) -> List[Tuple[int, int]]:
        """Generate random graph with n nodes and m edges."""
        edges = set()
        max_edges = n * n if directed else n * (n - 1) // 2
        if not allow_self_loops:
            max_edges = n * (n - 1) if directed else n * (n - 1) // 2
        
        m = min(m, max_edges)
        
        while len(edges) < m:
            u = random.randint(1, n)
            v = random.randint(1, n)
            if not allow_self_loops and u == v:
                continue
            if not directed and u > v:
                u, v = v, u
            if not allow_multi_edges and (u, v) in edges:
                continue
            edges.add((u, v))
        
        return list(edges)
    
    def small_n(self) -> int:
        """Get a small n value for stress testing."""
        n_max = self.constraints.n_max or 100
        # Use small values for stress testing
        return min(random.randint(1, 20), n_max)
    
    def small_value(self) -> int:
        """Get a small value for stress testing."""
        v_min = self.constraints.value_min if self.constraints.value_min is not None else 1
        v_max = self.constraints.value_max if self.constraints.value_max is not None else 100
        # Cap at reasonable values for stress testing
        v_min = max(v_min, -1000)  # Limit negative values for stress tests
        v_max = min(v_max, 1000)   # Limit positive values for stress tests
        return random.randint(v_min, v_max)


class StressTester:
    """
    Stress tester that compares solution against brute-force oracle.
    """
    
    def __init__(
        self, 
        runner: Optional[TestRunner] = None,
        max_tests: Optional[int] = None
    ):
        """
        Initialize stress tester.
        
        Args:
            runner: Test runner instance.
            max_tests: Maximum number of stress tests.
        """
        self.runner = runner or TestRunner()
        self.max_tests = max_tests or config.execution.stress_test_count
    
    def stress_test(
        self,
        solution_code: str,
        oracle_code: str,
        input_generator: Callable[[], str],
        num_tests: Optional[int] = None
    ) -> StressTestResult:
        """
        Run stress tests comparing solution against oracle.
        
        Args:
            solution_code: The solution to test.
            oracle_code: Brute-force correct solution.
            input_generator: Function that generates random input strings.
            num_tests: Number of tests to run.
            
        Returns:
            StressTestResult with pass/fail status.
        """
        num_tests = num_tests or self.max_tests
        
        for i in range(num_tests):
            # Generate random input
            test_input = input_generator()
            
            # Run oracle to get expected output
            oracle_result = self.runner.run(oracle_code, test_input, "")
            if oracle_result.status == ExecutionStatus.RUNTIME_ERROR:
                # Oracle failed, skip this test
                continue
            if oracle_result.status == ExecutionStatus.TIMEOUT:
                # Oracle too slow, skip
                continue
            
            expected = oracle_result.output
            
            # Run solution
            solution_result = self.runner.run(solution_code, test_input, expected)
            
            if not solution_result.passed:
                return StressTestResult(
                    passed=False,
                    tests_run=i + 1,
                    first_failure=solution_result,
                    failing_input=test_input,
                    oracle_output=expected
                )
        
        return StressTestResult(
            passed=True,
            tests_run=num_tests
        )
    
    def stress_test_with_generator(
        self,
        solution_code: str,
        oracle_code: str,
        constraints: Constraints,
        input_template: str,
        num_tests: Optional[int] = None
    ) -> StressTestResult:
        """
        Stress test with automatic input generation based on template.
        
        Args:
            solution_code: Solution to test.
            oracle_code: Oracle solution.
            constraints: Problem constraints.
            input_template: Template string like "n\\n{array}" or "n m\\n{edges}".
            num_tests: Number of tests.
            
        Returns:
            StressTestResult.
        """
        gen = InputGenerator(constraints)
        
        def generate_input() -> str:
            n = gen.small_n()
            
            # Parse template and fill in values
            lines = []
            template_lower = input_template.lower()
            
            if '{array}' in template_lower:
                arr = gen.random_array(n, 1, gen.small_value())
                if 'n' in template_lower.split('\n')[0]:
                    lines.append(str(n))
                lines.append(' '.join(map(str, arr)))
            elif '{permutation}' in template_lower:
                perm = gen.random_permutation(n)
                if 'n' in template_lower.split('\n')[0]:
                    lines.append(str(n))
                lines.append(' '.join(map(str, perm)))
            elif '{tree}' in template_lower:
                edges = gen.random_tree_edges(n)
                lines.append(str(n))
                for u, v in edges:
                    lines.append(f"{u} {v}")
            elif '{string}' in template_lower:
                s = gen.random_string(n)
                if 'n' in template_lower.split('\n')[0]:
                    lines.append(str(n))
                lines.append(s)
            else:
                # Default: just n and array
                lines.append(str(n))
                arr = gen.random_array(n, 1, gen.small_value())
                lines.append(' '.join(map(str, arr)))
            
            return '\n'.join(lines)
        
        return self.stress_test(
            solution_code, 
            oracle_code, 
            generate_input,
            num_tests
        )


def create_brute_force_oracle(problem: ProblemSpec) -> Optional[str]:
    """
    Attempt to create a simple brute-force oracle for common problem types.
    Returns None if no automatic oracle can be generated.
    
    This is a placeholder - in practice, you'd want to generate this
    based on the problem type or have the user provide it.
    """
    # This would need problem-specific logic
    # For now, return None to indicate manual oracle is needed
    return None

