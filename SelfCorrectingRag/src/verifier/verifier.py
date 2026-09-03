"""
Verifier - Main verification orchestrator.
Combines sample testing, stress testing, and metamorphic testing.
"""

from typing import Optional, List, Callable
from dataclasses import dataclass, field

from .runner import TestRunner, ExecutionResult, ExecutionStatus
from .stress import StressTester, StressTestResult, InputGenerator
from .metamorphic import (
    MetamorphicTester, MetamorphicRelation, MetamorphicTestResult,
    create_permutation_invariance_relation, create_output_format_invariant
)
from ..parser.models import ProblemSpec, TestCase
from ..solver.models import Solution, FailureReport
from ..config import config


@dataclass
class VerificationResult:
    """Complete verification result."""
    # Sample tests
    samples_passed: bool = False
    sample_results: List[ExecutionResult] = field(default_factory=list)
    
    # Stress tests
    stress_passed: bool = False
    stress_result: Optional[StressTestResult] = None
    
    # Metamorphic tests
    metamorphic_passed: bool = False
    metamorphic_results: List[MetamorphicTestResult] = field(default_factory=list)
    
    # Overall
    all_passed: bool = False
    failure_report: Optional[FailureReport] = None
    assumptions: List[str] = field(default_factory=list)
    
    def summary(self) -> str:
        """Generate verification summary."""
        lines = ["=== VERIFICATION SUMMARY ==="]
        
        # Samples
        passed = sum(1 for r in self.sample_results if r.passed)
        total = len(self.sample_results)
        status = "✓" if self.samples_passed else "✗"
        lines.append(f"{status} Sample tests: {passed}/{total} passed")
        
        # Stress
        if self.stress_result:
            status = "✓" if self.stress_passed else "✗"
            lines.append(f"{status} Stress tests: {self.stress_result.tests_run} tests")
        else:
            lines.append("⊘ Stress tests: skipped (no oracle)")
        
        # Metamorphic
        if self.metamorphic_results:
            passed = sum(1 for r in self.metamorphic_results if r.passed)
            total = len(self.metamorphic_results)
            status = "✓" if self.metamorphic_passed else "✗"
            lines.append(f"{status} Metamorphic tests: {passed}/{total} relations held")
        
        # Overall
        lines.append("")
        if self.all_passed:
            lines.append("✓ ALL VERIFICATION PASSED")
        else:
            lines.append("✗ VERIFICATION FAILED")
            if self.failure_report:
                lines.append(f"\nFirst failure: {self.failure_report.error_type}")
        
        # Assumptions
        if self.assumptions:
            lines.append("\nAssumptions:")
            for a in self.assumptions:
                lines.append(f"  • {a}")
        
        return "\n".join(lines)


class Verifier:
    """
    Main verification orchestrator.
    Runs sample tests, stress tests, and metamorphic tests.
    """
    
    def __init__(
        self,
        runner: Optional[TestRunner] = None,
        stress_tester: Optional[StressTester] = None,
        metamorphic_tester: Optional[MetamorphicTester] = None
    ):
        """Initialize verifier."""
        self.runner = runner or TestRunner()
        self.stress_tester = stress_tester or StressTester(self.runner)
        self.metamorphic_tester = metamorphic_tester or MetamorphicTester(self.runner)
    
    def verify(
        self,
        solution: Solution,
        problem: ProblemSpec,
        oracle_code: Optional[str] = None,
        stress_test_count: Optional[int] = None,
        metamorphic_relations: Optional[List[MetamorphicRelation]] = None
    ) -> VerificationResult:
        """
        Perform complete verification of a solution.
        
        Args:
            solution: The solution to verify.
            problem: Problem specification with samples.
            oracle_code: Optional brute-force oracle for stress testing.
            stress_test_count: Number of stress tests.
            metamorphic_relations: Relations to test.
            
        Returns:
            VerificationResult with all test outcomes.
        """
        result = VerificationResult()
        
        # Step 1: Check syntax
        valid, error = self.runner.check_syntax(solution.code)
        if not valid:
            result.failure_report = FailureReport(
                failing_input="",
                expected_output="",
                actual_output="",
                error_type="compilation_error",
                error_message=error
            )
            return result
        
        # Step 2: Run sample tests
        result.sample_results = self._run_samples(solution.code, problem.sample_tests)
        result.samples_passed = all(r.passed for r in result.sample_results)
        
        if result.samples_passed:
            problem.mark_done("samples_passed")
            solution.samples_passed = True
        else:
            # Create failure report from first failing sample
            for r in result.sample_results:
                if not r.passed:
                    result.failure_report = self._create_failure_report(r)
                    break
            return result
        
        # Step 3: Stress test (if oracle provided)
        if oracle_code:
            result.stress_result = self._run_stress_tests(
                solution.code,
                oracle_code,
                problem,
                stress_test_count
            )
            result.stress_passed = result.stress_result.passed
            
            if result.stress_passed:
                problem.mark_done("stress_tested")
                solution.stress_test_passed = True
                solution.stress_test_count = result.stress_result.tests_run
            else:
                result.failure_report = FailureReport(
                    failing_input=result.stress_result.failing_input or "",
                    expected_output=result.stress_result.oracle_output or "",
                    actual_output=result.stress_result.first_failure.output if result.stress_result.first_failure else "",
                    error_type=result.stress_result.first_failure.status.value if result.stress_result.first_failure else "wrong_answer"
                )
                return result
        else:
            result.assumptions.append("No oracle provided - stress testing skipped")
        
        # Step 4: Metamorphic testing
        if metamorphic_relations:
            result.metamorphic_results = self._run_metamorphic_tests(
                solution.code,
                problem,
                metamorphic_relations
            )
            result.metamorphic_passed = all(r.passed for r in result.metamorphic_results)
            
            if not result.metamorphic_passed:
                for r in result.metamorphic_results:
                    if not r.passed and r.first_failure:
                        orig_in, trans_in, orig_out, trans_out = r.first_failure
                        result.failure_report = FailureReport(
                            failing_input=f"Original: {orig_in}\nTransformed: {trans_in}",
                            expected_output=f"Relation '{r.relation_name}' should hold",
                            actual_output=f"Original out: {orig_out}\nTransformed out: {trans_out}",
                            error_type="metamorphic_violation"
                        )
                        break
                return result
        else:
            # Run default metamorphic tests
            result.metamorphic_results = self._run_default_metamorphic_tests(
                solution.code, problem
            )
            result.metamorphic_passed = all(r.passed for r in result.metamorphic_results)
        
        # All passed
        result.all_passed = result.samples_passed and (
            result.stress_passed or result.stress_result is None
        ) and result.metamorphic_passed
        
        return result
    
    def verify_samples_only(
        self,
        solution: Solution,
        problem: ProblemSpec
    ) -> VerificationResult:
        """Quick verification using only sample tests."""
        result = VerificationResult()
        
        valid, error = self.runner.check_syntax(solution.code)
        if not valid:
            result.failure_report = FailureReport(
                failing_input="",
                expected_output="",
                actual_output="",
                error_type="compilation_error",
                error_message=error
            )
            return result
        
        result.sample_results = self._run_samples(solution.code, problem.sample_tests)
        result.samples_passed = all(r.passed for r in result.sample_results)
        result.all_passed = result.samples_passed
        
        if not result.samples_passed:
            for r in result.sample_results:
                if not r.passed:
                    result.failure_report = self._create_failure_report(r)
                    break
        
        return result
    
    def _run_samples(
        self, 
        code: str, 
        samples: List[TestCase]
    ) -> List[ExecutionResult]:
        """Run code on sample tests."""
        return self.runner.run_multiple(code, samples)
    
    def _run_stress_tests(
        self,
        solution_code: str,
        oracle_code: str,
        problem: ProblemSpec,
        num_tests: Optional[int]
    ) -> StressTestResult:
        """Run stress tests with oracle."""
        gen = InputGenerator(problem.constraints)
        
        # Determine value range from constraints (with sensible stress test limits)
        v_min = problem.constraints.value_min if problem.constraints.value_min is not None else 1
        v_max = problem.constraints.value_max if problem.constraints.value_max is not None else 100
        # Limit to reasonable stress test range
        v_min = max(v_min, -1000)
        v_max = min(v_max, 1000)
        
        # Create input generator based on problem structure
        def generate_input() -> str:
            n = gen.small_n()
            lines = [str(n)]
            arr = gen.random_array(n, v_min, v_max)
            lines.append(' '.join(map(str, arr)))
            return '\n'.join(lines)
        
        return self.stress_tester.stress_test(
            solution_code,
            oracle_code,
            generate_input,
            num_tests
        )
    
    def _run_metamorphic_tests(
        self,
        code: str,
        problem: ProblemSpec,
        relations: List[MetamorphicRelation]
    ) -> List[MetamorphicTestResult]:
        """Run metamorphic tests with specified relations."""
        # Generate some test inputs
        gen = InputGenerator(problem.constraints)
        # Determine value range from constraints
        v_min = problem.constraints.value_min if problem.constraints.value_min is not None else 1
        v_max = problem.constraints.value_max if problem.constraints.value_max is not None else 100
        v_min = max(v_min, -1000)
        v_max = min(v_max, 1000)
        
        inputs = []
        for _ in range(20):
            n = gen.small_n()
            arr = gen.random_array(n, v_min, v_max)
            inputs.append(f"{n}\n{' '.join(map(str, arr))}")
        
        results = []
        for relation in relations:
            result = self.metamorphic_tester.test_relation(code, relation, inputs)
            results.append(result)
        
        return results
    
    def _run_default_metamorphic_tests(
        self,
        code: str,
        problem: ProblemSpec
    ) -> List[MetamorphicTestResult]:
        """Run default metamorphic tests."""
        # Generate some test inputs from samples and random
        inputs = [test.input for test in problem.sample_tests]
        
        gen = InputGenerator(problem.constraints)
        # Determine value range from constraints (with sensible stress test limits)
        v_min = problem.constraints.value_min if problem.constraints.value_min is not None else 1
        v_max = problem.constraints.value_max if problem.constraints.value_max is not None else 100
        v_min = max(v_min, -1000)
        v_max = min(v_max, 1000)
        
        for _ in range(10):
            n = gen.small_n()
            arr = gen.random_array(n, v_min, v_max)
            inputs.append(f"{n}\n{' '.join(map(str, arr))}")
        
        results = []
        
        # Test output format invariant
        format_check = create_output_format_invariant("integer")
        result = self.metamorphic_tester.test_invariant(
            code, format_check, inputs, "output_format"
        )
        results.append(result)
        
        return results
    
    def _create_failure_report(self, result: ExecutionResult) -> FailureReport:
        """Create a failure report from an execution result."""
        return FailureReport(
            failing_input="(sample input)",
            expected_output=result.expected,
            actual_output=result.output,
            error_type=result.status.value,
            error_message=result.error_message
        )

