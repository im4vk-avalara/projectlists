"""
Solution models for the Solver module.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class SolutionStatus(Enum):
    """Status of a solution attempt."""
    PENDING = "pending"
    GENERATED = "generated"
    VERIFIED = "verified"
    FAILED = "failed"
    REPAIRED = "repaired"


@dataclass
class Complexity:
    """Time and space complexity analysis."""
    time: str  # e.g., "O(n log n)"
    space: str  # e.g., "O(n)"
    explanation: str = ""
    fits_constraints: bool = True
    estimated_operations: Optional[int] = None  # Rough count for n_max
    
    def will_tle(self, time_limit_seconds: float = 1.0) -> bool:
        """
        Estimate if solution will TLE.
        Rough heuristic: ~10^8 operations per second.
        """
        if self.estimated_operations is None:
            return False
        ops_per_second = 10**8
        return self.estimated_operations > ops_per_second * time_limit_seconds


@dataclass
class Approach:
    """Solution approach description."""
    summary: str  # One-line summary
    steps: List[str]  # Step-by-step algorithm
    key_insight: str  # The main idea
    correctness_argument: str  # Why this works
    techniques_used: List[str] = field(default_factory=list)
    edge_case_handling: Dict[str, str] = field(default_factory=dict)


@dataclass 
class Solution:
    """
    Complete solution to a competitive programming problem.
    """
    # Core solution
    approach: Optional[Approach] = None
    complexity: Optional[Complexity] = None
    code: str = ""
    language: str = "python"
    
    # Metadata
    status: SolutionStatus = SolutionStatus.PENDING
    version: int = 1
    
    # Verification results
    samples_passed: bool = False
    stress_test_passed: bool = False
    stress_test_count: int = 0
    
    # Repair history
    repair_attempts: int = 0
    repair_history: List[Dict[str, Any]] = field(default_factory=list)
    
    # Assumptions and notes
    assumptions: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    
    def add_repair(self, failure_input: str, fix_description: str) -> None:
        """Record a repair attempt."""
        self.repair_attempts += 1
        self.version += 1
        self.repair_history.append({
            "version": self.version,
            "failure_input": failure_input[:500],
            "fix": fix_description
        })
    
    def summary(self) -> str:
        """Generate a summary of the solution."""
        lines = [
            f"Solution v{self.version} [{self.status.value}]",
            f"Approach: {self.approach.summary if self.approach else 'N/A'}",
            f"Complexity: Time {self.complexity.time if self.complexity else 'N/A'}, "
            f"Space {self.complexity.space if self.complexity else 'N/A'}",
            f"Samples: {'✓' if self.samples_passed else '✗'}",
            f"Stress: {'✓' if self.stress_test_passed else '✗'} ({self.stress_test_count} tests)",
            f"Repairs: {self.repair_attempts}",
        ]
        return "\n".join(lines)


@dataclass
class FailureReport:
    """Report of a test failure for debugging."""
    failing_input: str
    expected_output: str
    actual_output: str
    error_type: str  # "wrong_answer", "runtime_error", "tle", "mle"
    error_message: Optional[str] = None
    root_cause_hypothesis: str = ""
    suggested_fixes: List[str] = field(default_factory=list)
    relevant_pitfalls: List[str] = field(default_factory=list)
    
    def summary(self) -> str:
        """Generate failure summary."""
        lines = [
            f"=== FAILURE REPORT ===",
            f"Type: {self.error_type}",
            f"Input:\n{self.failing_input[:500]}",
            f"\nExpected:\n{self.expected_output[:200]}",
            f"\nActual:\n{self.actual_output[:200]}",
            f"\nHypothesis: {self.root_cause_hypothesis}",
        ]
        if self.suggested_fixes:
            lines.append(f"\nSuggested fixes:")
            for fix in self.suggested_fixes:
                lines.append(f"  - {fix}")
        return "\n".join(lines)

