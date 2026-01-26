"""
Data models for Codeforces problem parsing.
Represents structured information extracted from problem statements.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class Difficulty(Enum):
    """Problem difficulty rating."""
    EASY = "easy"           # 800-1200
    MEDIUM = "medium"       # 1300-1700
    HARD = "hard"           # 1800-2200
    EXPERT = "expert"       # 2300+
    UNKNOWN = "unknown"


@dataclass
class Constraints:
    """Problem constraints extracted from statement."""
    n_min: Optional[int] = None
    n_max: Optional[int] = None
    value_min: Optional[int] = None
    value_max: Optional[int] = None
    time_limit_seconds: float = 1.0
    memory_limit_mb: int = 256
    test_cases_count: Optional[int] = None  # Number of test cases per input
    sum_constraint: Optional[str] = None    # e.g., "sum of n over all test cases <= 2*10^5"
    additional: Dict[str, Any] = field(default_factory=dict)
    
    def requires_fast_io(self) -> bool:
        """Check if constraints suggest fast I/O is needed."""
        if self.n_max and self.n_max >= 10**5:
            return True
        return False
    
    def may_overflow_int32(self) -> bool:
        """Check if values might overflow 32-bit integers."""
        if self.value_max and self.value_max > 2 * 10**9:
            return True
        if self.n_max and self.value_max:
            # Product might overflow
            if self.n_max * self.value_max > 2 * 10**9:
                return True
        return False


@dataclass
class TestCase:
    """A single test case with input and expected output."""
    input: str
    expected_output: str
    is_sample: bool = True  # True if from problem statement
    description: Optional[str] = None  # Optional explanation


@dataclass
class InputFormat:
    """Describes the input format structure."""
    description: str
    variables: List[str] = field(default_factory=list)  # Variable names mentioned
    has_multiple_test_cases: bool = False
    first_line_format: Optional[str] = None  # e.g., "n m" or "t"
    
    
@dataclass
class OutputFormat:
    """Describes the expected output format."""
    description: str
    per_test_case: bool = True  # Output per test case or single output
    format_notes: Optional[str] = None  # e.g., "print YES/NO", "modulo 10^9+7"


@dataclass
class EdgeCase:
    """A potential edge case to consider."""
    description: str
    example_input: Optional[str] = None
    why_tricky: Optional[str] = None


@dataclass
class ProblemSpec:
    """
    Complete specification of a Codeforces problem.
    This is the main data structure produced by parsing.
    """
    # Identification
    problem_id: Optional[str] = None  # e.g., "1A", "1850E"
    contest_id: Optional[int] = None
    title: str = ""
    url: Optional[str] = None
    
    # Problem statement
    statement: str = ""  # Raw problem statement text
    
    # Extracted structure
    constraints: Constraints = field(default_factory=Constraints)
    input_format: Optional[InputFormat] = None
    output_format: Optional[OutputFormat] = None
    
    # Test cases
    sample_tests: List[TestCase] = field(default_factory=list)
    
    # Analysis
    edge_cases: List[EdgeCase] = field(default_factory=list)
    difficulty: Difficulty = Difficulty.UNKNOWN
    
    # Technique hints (populated by retriever)
    detected_techniques: List[str] = field(default_factory=list)
    
    # Checklist tracking
    checklist: Dict[str, bool] = field(default_factory=lambda: {
        "constraints_extracted": False,
        "input_format_understood": False,
        "output_format_understood": False,
        "samples_parsed": False,
        "edge_cases_identified": False,
        "technique_identified": False,
        "solution_implemented": False,
        "samples_passed": False,
        "stress_tested": False,
    })
    
    def mark_done(self, item: str) -> None:
        """Mark a checklist item as done."""
        if item in self.checklist:
            self.checklist[item] = True
    
    def get_pending_items(self) -> List[str]:
        """Get list of pending checklist items."""
        return [k for k, v in self.checklist.items() if not v]
    
    def is_complete(self) -> bool:
        """Check if all checklist items are done."""
        return all(self.checklist.values())
    
    def summary(self) -> str:
        """Generate a brief summary of the problem."""
        lines = [
            f"Problem: {self.title} ({self.problem_id or 'unknown'})",
            f"Time: {self.constraints.time_limit_seconds}s, Memory: {self.constraints.memory_limit_mb}MB",
            f"N range: [{self.constraints.n_min}, {self.constraints.n_max}]",
            f"Samples: {len(self.sample_tests)}",
            f"Edge cases: {len(self.edge_cases)}",
            f"Techniques: {', '.join(self.detected_techniques) or 'TBD'}",
        ]
        return "\n".join(lines)

