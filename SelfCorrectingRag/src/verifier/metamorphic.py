"""
Metamorphic Testing - Testing without an oracle.
Uses input transformations and output relations to verify correctness.
"""

from typing import Callable, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum

from .runner import TestRunner, ExecutionResult, ExecutionStatus


class RelationType(Enum):
    """Type of metamorphic relation."""
    EQUALITY = "equality"           # T(f(x)) = f(T(x))
    SUBSET = "subset"               # f(T(x)) ⊆ f(x)
    ORDERING = "ordering"           # f(x1) <= f(x2) if x1 <= x2
    INVARIANT = "invariant"         # f(x) has property P
    INVERSE = "inverse"             # f(f^(-1)(y)) = y


@dataclass
class MetamorphicRelation:
    """A metamorphic testing relation."""
    name: str
    relation_type: RelationType
    input_transform: Callable[[str], str]
    output_relation: Callable[[str, str], bool]
    description: str = ""


@dataclass
class MetamorphicTestResult:
    """Result of metamorphic testing."""
    passed: bool
    relation_name: str
    tests_run: int
    first_failure: Optional[Tuple[str, str, str, str]] = None  # (orig_in, trans_in, orig_out, trans_out)
    
    def summary(self) -> str:
        if self.passed:
            return f"✓ Metamorphic relation '{self.relation_name}' held ({self.tests_run} tests)"
        if self.first_failure:
            orig_in, trans_in, orig_out, trans_out = self.first_failure
            return (
                f"✗ Metamorphic relation '{self.relation_name}' VIOLATED\n"
                f"Original input: {orig_in[:100]}\n"
                f"Transformed input: {trans_in[:100]}\n"
                f"Original output: {orig_out[:100]}\n"
                f"Transformed output: {trans_out[:100]}"
            )
        return f"✗ Metamorphic test failed"


class MetamorphicTester:
    """
    Performs metamorphic testing - useful when no oracle is available.
    
    Metamorphic testing exploits relationships between inputs and outputs:
    - If we know that sorting an array and then reversing should give
      the reverse-sorted array, we can test this relation.
    """
    
    def __init__(self, runner: Optional[TestRunner] = None):
        """Initialize tester."""
        self.runner = runner or TestRunner()
    
    def test_relation(
        self,
        code: str,
        relation: MetamorphicRelation,
        inputs: List[str],
    ) -> MetamorphicTestResult:
        """
        Test a metamorphic relation on multiple inputs.
        
        Args:
            code: Solution code.
            relation: The metamorphic relation to test.
            inputs: List of original inputs to test.
            
        Returns:
            MetamorphicTestResult.
        """
        for i, original_input in enumerate(inputs):
            # Transform input
            transformed_input = relation.input_transform(original_input)
            
            # Run on original input
            orig_result = self.runner.run(code, original_input, "")
            if orig_result.status != ExecutionStatus.SUCCESS:
                # Can't test if execution fails
                continue
            
            # Run on transformed input
            trans_result = self.runner.run(code, transformed_input, "")
            if trans_result.status != ExecutionStatus.SUCCESS:
                continue
            
            # Check if relation holds
            if not relation.output_relation(orig_result.output, trans_result.output):
                return MetamorphicTestResult(
                    passed=False,
                    relation_name=relation.name,
                    tests_run=i + 1,
                    first_failure=(
                        original_input,
                        transformed_input,
                        orig_result.output,
                        trans_result.output
                    )
                )
        
        return MetamorphicTestResult(
            passed=True,
            relation_name=relation.name,
            tests_run=len(inputs)
        )
    
    def test_invariant(
        self,
        code: str,
        invariant: Callable[[str, str], bool],
        inputs: List[str],
        invariant_name: str = "invariant"
    ) -> MetamorphicTestResult:
        """
        Test that output satisfies an invariant for all inputs.
        
        Args:
            code: Solution code.
            invariant: Function (input, output) -> bool.
            inputs: List of inputs to test.
            invariant_name: Name for reporting.
            
        Returns:
            MetamorphicTestResult.
        """
        for i, test_input in enumerate(inputs):
            result = self.runner.run(code, test_input, "")
            if result.status != ExecutionStatus.SUCCESS:
                continue
            
            if not invariant(test_input, result.output):
                return MetamorphicTestResult(
                    passed=False,
                    relation_name=invariant_name,
                    tests_run=i + 1,
                    first_failure=(test_input, test_input, result.output, "INVARIANT VIOLATED")
                )
        
        return MetamorphicTestResult(
            passed=True,
            relation_name=invariant_name,
            tests_run=len(inputs)
        )


# ============ COMMON METAMORPHIC RELATIONS ============

def create_permutation_invariance_relation() -> MetamorphicRelation:
    """
    For problems where order doesn't matter:
    shuffling input should give same output.
    """
    import random
    
    def shuffle_array_input(inp: str) -> str:
        lines = inp.strip().split('\n')
        if len(lines) >= 2:
            # Assume second line is array
            first = lines[0]
            arr = lines[1].split()
            random.shuffle(arr)
            return first + '\n' + ' '.join(arr)
        return inp
    
    def outputs_equal(out1: str, out2: str) -> bool:
        return out1.strip() == out2.strip()
    
    return MetamorphicRelation(
        name="permutation_invariance",
        relation_type=RelationType.EQUALITY,
        input_transform=shuffle_array_input,
        output_relation=outputs_equal,
        description="Shuffling input array should not change output"
    )


def create_scaling_relation(scale_factor: int = 2) -> MetamorphicRelation:
    """
    For problems with linear scaling:
    doubling all values should double the output (or similar relation).
    """
    def scale_input(inp: str) -> str:
        lines = inp.strip().split('\n')
        result = []
        for line in lines:
            try:
                nums = [str(int(x) * scale_factor) for x in line.split()]
                result.append(' '.join(nums))
            except ValueError:
                result.append(line)
        return '\n'.join(result)
    
    def check_scaled_output(out1: str, out2: str) -> bool:
        try:
            v1 = int(out1.strip())
            v2 = int(out2.strip())
            return v2 == v1 * scale_factor
        except ValueError:
            return True  # Can't verify, assume OK
    
    return MetamorphicRelation(
        name=f"scaling_by_{scale_factor}",
        relation_type=RelationType.ORDERING,
        input_transform=scale_input,
        output_relation=check_scaled_output,
        description=f"Scaling input by {scale_factor} should scale output by {scale_factor}"
    )


def create_reversal_relation() -> MetamorphicRelation:
    """
    For symmetric problems:
    reversing input should give same or reversed output.
    """
    def reverse_array_input(inp: str) -> str:
        lines = inp.strip().split('\n')
        if len(lines) >= 2:
            first = lines[0]
            arr = lines[1].split()
            return first + '\n' + ' '.join(reversed(arr))
        return inp
    
    def outputs_equal(out1: str, out2: str) -> bool:
        return out1.strip() == out2.strip()
    
    return MetamorphicRelation(
        name="reversal_invariance",
        relation_type=RelationType.EQUALITY,
        input_transform=reverse_array_input,
        output_relation=outputs_equal,
        description="Reversing input array should not change output"
    )


def create_output_format_invariant(expected_format: str = "integer") -> Callable:
    """
    Create an invariant that checks output format.
    
    Args:
        expected_format: "integer", "yes_no", "array", etc.
    """
    def check_format(inp: str, out: str) -> bool:
        out = out.strip()
        if expected_format == "integer":
            try:
                int(out)
                return True
            except ValueError:
                return False
        elif expected_format == "yes_no":
            return out.upper() in ("YES", "NO")
        elif expected_format == "array":
            try:
                [int(x) for x in out.split()]
                return True
            except ValueError:
                return False
        return True
    
    return check_format


def create_bounds_invariant(min_val: Optional[int] = None, max_val: Optional[int] = None) -> Callable:
    """
    Create an invariant that checks output is within bounds.
    """
    def check_bounds(inp: str, out: str) -> bool:
        try:
            val = int(out.strip())
            if min_val is not None and val < min_val:
                return False
            if max_val is not None and val > max_val:
                return False
            return True
        except ValueError:
            return True  # Not a single integer, can't check
    
    return check_bounds

